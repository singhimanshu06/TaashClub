"""The shared HOME code must remain reusable across completed matches."""
import asyncio

import pytest
from fastapi import HTTPException, Request

import app.main as main
from app.game.base import Phase
from app.game.room import ConnectionManager, RoomManager
from app.protocol import JoinRoomRequest, LeaveRoomRequest


class FakeWebSocket:
    def __init__(self):
        self.messages = []
        self.closed_with = None

    async def accept(self):
        pass

    async def send_json(self, message):
        self.messages.append(message)

    async def close(self, code=None):
        self.closed_with = code


@pytest.fixture
def home(monkeypatch):
    manager = RoomManager()
    monkeypatch.setattr(main, "rooms", manager)
    monkeypatch.setattr(main, "connections", ConnectionManager())
    monkeypatch.setattr(main, "HOME_POST_GAME_GRACE_SECONDS", 10)
    monkeypatch.setattr(main, "rest_limiters", {
        "join": main.SlidingWindowLimiter(100, 60),
    })
    room = manager.get_default()
    host = room.add_player("Host")
    host.connected = True
    room.sockets[host.id] = FakeWebSocket()
    room.add_bots(host.id)
    room.start_game(host.id)
    return room


def join_request():
    return Request({"type": "http", "headers": [], "client": ("test", 1234)})


async def finish(home):
    home.game.force_end()
    await main._after_state_change(home)


def test_home_keeps_scoreboard_for_grace_and_publishes_same_deadline_to_everyone(home):
    async def run():
        spectator = home.add_spectator("Watcher")
        ws = FakeWebSocket()
        await main.connections.connect_spectator(home, spectator.spectator_id, ws)
        await finish(home)
        finished_at, reset_at = home.finished_at, home.reset_at
        assert reset_at is not None
        assert ws.messages[-1]["state"]["room_reset_at"] == reset_at
        assert next(iter(home.sockets.values())).messages[-1]["state"]["room_reset_at"] == reset_at

        home.add_chat(spectator.chat_id, "Keep watching")
        late = home.add_spectator("Late watcher")
        late_ws = FakeWebSocket()
        await main.connections.connect_spectator(home, late.spectator_id, late_ws)
        await main._after_state_change(home)
        await main._reset_home_if_due()
        assert main.rooms.get("HOME") is home
        assert home.finished_at == finished_at
        assert home.reset_at == reset_at
        assert late_ws.messages[-1]["state"]["room_reset_at"] == reset_at
        assert ws.closed_with is None

    asyncio.run(run())


def test_join_during_scoreboard_grace_has_specific_retry_message(home):
    async def run():
        await finish(home)
        for _ in range(2):
            with pytest.raises(HTTPException) as exc:
                await main.join_room("home", JoinRoomRequest(name="Returning"), join_request())
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "ROOM_RESET_PENDING"
            assert "new game opens" in exc.value.detail["message"]
            assert exc.value.headers["Retry-After"] == "10"
        assert main.rooms.get("HOME") is home

    asyncio.run(run())


def test_reset_closes_players_and_spectators_and_clears_all_match_state(home):
    async def run():
        spectator = home.add_spectator("Watcher")
        spectator_ws = FakeWebSocket()
        await main.connections.connect_spectator(home, spectator.spectator_id, spectator_ws)
        host_id = home.host_id
        player_ws = home.sockets[host_id]
        home.add_chat(host_id, "Old match chat")
        await finish(home)
        home.finished_at -= 11
        await main._reset_home_if_due()

        fresh = main.rooms.get("HOME")
        assert fresh is not home
        assert fresh.code == "HOME"
        assert fresh.game_type == "twentyeight"
        assert fresh.num_players == 4
        assert fresh.options == home.options
        assert fresh.players == []
        assert fresh.host_id is None
        assert fresh.game is None
        assert fresh.spectators == {}
        assert fresh.chat_log == []
        assert fresh.leave_tokens == {}
        assert fresh.reset_at is None
        assert home.retired
        assert not home.has_player(host_id)
        assert home.get_spectator(spectator.spectator_id) is None
        assert home.sockets == home.spectator_sockets == {}
        assert player_ws.closed_with == spectator_ws.closed_with == 4010
        await main._reset_home_if_due()
        assert main.rooms.get("HOME") is fresh

    asyncio.run(run())


def test_join_itself_resets_due_home_without_waiting_for_cleanup_tick(home):
    async def run():
        await finish(home)
        home.finished_at -= 11
        joined = await main.join_room("home", JoinRoomRequest(name="New host"), join_request())
        fresh = main.rooms.get("HOME")
        assert fresh is not home
        assert fresh.host_id == joined.player_id
        assert joined.join_order == 0
        assert [p.name for p in fresh.players] == ["New host"]

        # An old browser must not be able to reconnect to the replacement match.
        ws = FakeWebSocket()
        await main.game_socket(ws, "HOME", player_id=home.host_id)
        assert ws.closed_with == 4003

    asyncio.run(run())


def test_reset_cancels_old_background_tasks_and_conversion_timers(home):
    async def run():
        await finish(home)
        bot_task = asyncio.create_task(asyncio.Event().wait())
        hold_task = asyncio.create_task(asyncio.Event().wait())
        conversion_task = asyncio.create_task(asyncio.Event().wait())
        home._bot_tasks.update({bot_task, hold_task})
        home.conversion_timers[home.host_id] = conversion_task
        home.finished_at -= 11
        await main._reset_home_if_due()
        await asyncio.gather(bot_task, hold_task, conversion_task, return_exceptions=True)
        assert all(t.cancelled() for t in [bot_task, hold_task, conversion_task])
        assert not home._bot_tasks
        assert not home.conversion_timers
        fresh = main.rooms.get("HOME")
        await main.handle_event(home, home.host_id, {"type": "chat", "text": "Stale message"})
        await main._after_state_change(home)
        assert not fresh.chat_log
        assert fresh.game is None

    asyncio.run(run())


def test_active_home_and_private_games_are_not_reset(home):
    async def run():
        await main._reset_home_if_due()
        assert main.rooms.get("HOME") is home
        assert home.reset_at is None
        assert not home.retired

        private = main.rooms.create_room("twentyeight", 4, {})
        for _ in range(4):
            private.add_bot()
        private.start_game(private.host_id)
        private.game.force_end()
        await main._after_state_change(private)
        assert private.reset_at is None
        assert private.finished_at is None
        await main._reset_home_if_due()
        assert main.rooms.get(private.code) is private

    asyncio.run(run())


def test_last_human_leaving_ends_home_and_schedules_reopening(home, monkeypatch):
    async def run():
        monkeypatch.setattr(main, "BOT_CONVERSION_GRACE_SECONDS", 0)
        monkeypatch.setattr(main, "BOT_THINK_MIN", 3600)
        monkeypatch.setattr(main, "BOT_THINK_MAX", 3600)
        host_id = home.host_id
        try:
            await main.leave_room("HOME", LeaveRoomRequest(
                player_id=host_id, leave_token=home.leave_tokens[host_id],
            ))
            await home.conversion_timers[host_id]
            assert all(p.is_bot for p in home.players)
            assert home.game.phase == Phase.GAME_END
            assert home.reset_at is not None
            home.finished_at -= 11
            await main._reset_home_if_due()
            assert main.rooms.get("HOME").game is None
        finally:
            tasks = list(home._bot_tasks) + list(home.conversion_timers.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run())


def test_naturally_completed_all_bot_match_also_schedules_reset(home, monkeypatch):
    async def run():
        monkeypatch.setattr(main, "BOT_THINK_MIN", 0)
        monkeypatch.setattr(main, "BOT_THINK_MAX", 0)
        monkeypatch.setattr(main, "BOT_AUTO_ADVANCE_SECONDS", 0)
        monkeypatch.setattr(main, "TRICK_HOLD_SECONDS", 0)
        for player in home.players:
            player.is_bot = True

        async def play_to_end():
            await main._after_state_change(home)
            while home.game.phase != Phase.GAME_END:
                await asyncio.sleep(0)

        try:
            await asyncio.wait_for(play_to_end(), timeout=5)
            assert home.finished_at is not None
            assert home.reset_at is not None
            home.finished_at -= 11
            await main._reset_home_if_due()
            assert main.rooms.get("HOME").players == []
        finally:
            tasks = list(home._bot_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run())


def test_cleanup_loop_reopens_home_even_while_spectator_stays_connected(home, monkeypatch):
    async def run():
        spectator = home.add_spectator("Watcher")
        ws = FakeWebSocket()
        await main.connections.connect_spectator(home, spectator.spectator_id, ws)
        await finish(home)
        home.finished_at -= 11
        calls = 0

        async def one_tick(_):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise asyncio.CancelledError

        monkeypatch.setattr(main.asyncio, "sleep", one_tick)
        with pytest.raises(asyncio.CancelledError):
            await main._cleanup_rooms_loop()
        assert main.rooms.get("HOME") is not home
        assert ws.closed_with == 4010

    asyncio.run(run())


def test_spectator_cannot_attach_to_retired_home_during_accept(home):
    async def run():
        await finish(home)
        spectator = home.add_spectator("Watcher")

        class ResetDuringAccept(FakeWebSocket):
            async def accept(self):
                home.finished_at -= 11
                await main._reset_home_if_due()

        ws = ResetDuringAccept()
        assert not await main.connections.connect_spectator(home, spectator.spectator_id, ws)
        assert ws.closed_with == 4010
        assert not main.rooms.get("HOME").spectator_sockets

    asyncio.run(run())
