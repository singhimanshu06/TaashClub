"""Regression coverage for lobby reservations, explicit leave and reconnects."""
import asyncio
import json

import pytest
from fastapi import HTTPException, Request

import app.main as main
from app.game.base import GameError
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
def room(monkeypatch):
    manager = RoomManager()
    room = manager.create_room("callbreak", 4, {"variant": "single_run"})
    monkeypatch.setattr(main, "rooms", manager)
    monkeypatch.setattr(main, "connections", ConnectionManager())
    monkeypatch.setattr(main, "rest_limiters", {
        "join": main.SlidingWindowLimiter(1000, 60),
    })
    return room


def request():
    return Request({"type": "http", "headers": [], "client": ("test", 1234)})


async def join(room, name):
    return await main.join_room(room.code, JoinRoomRequest(name=name), request())


def departure(session):
    return LeaveRoomRequest(player_id=session.player_id, leave_token=session.leave_token)


def test_fourth_player_can_leave_and_immediately_rejoin(room):
    async def run():
        host = await join(room, "Host")
        host_ws = FakeWebSocket()
        await main.connections.connect(room, host.player_id, host_ws)
        await join(room, "Second")
        await join(room, "Third")
        fourth = await join(room, "Fourth")
        ws = FakeWebSocket()
        await main.connections.connect(room, fourth.player_id, ws)
        assert room.is_full()

        assert await main.leave_room(room.code, departure(fourth)) == {"left": True}
        assert ws.closed_with == 4003
        assert not room.has_player(fourth.player_id)
        assert len(room.players) == 3
        assert len(host_ws.messages[-1]["lobby"]["players"]) == 3
        assert await main.leave_room(room.code, departure(fourth)) == {"left": True}

        replacement = await join(room, "Fourth")
        assert replacement.player_id != fourth.player_id
        assert replacement.join_order == 3
        assert room.is_full()
        assert [p.join_order for p in room.players] == [0, 1, 2, 3]

    asyncio.run(run())


def test_leave_requires_private_credentials_and_never_broadcasts_them(room):
    async def run():
        player = await join(room, "Player")
        bad = LeaveRoomRequest(player_id=player.player_id, leave_token="wrong")
        with pytest.raises(HTTPException) as exc:
            await main.leave_room(room.code, bad)
        assert exc.value.status_code == 403
        assert room.has_player(player.player_id)
        assert player.leave_token not in json.dumps(room.lobby_snapshot())
        assert player.leave_token not in json.dumps(room.add_chat(player.player_id, "hello"))

    asyncio.run(run())


def test_host_transfers_to_next_human_and_seats_are_renumbered(room):
    host = room.add_player("Host")
    room.add_bot()
    successor = room.add_player("Next host")
    room.remove_lobby_player(host.id)
    assert room.host_id == successor.id
    assert [p.join_order for p in room.players] == [0, 1]
    room.remove_lobby_player(successor.id)
    assert room.host_id is None
    new_host = room.add_player("New host")
    assert room.host_id == new_host.id


def test_empty_room_remains_rejoinable_and_can_eventually_expire(room):
    async def run():
        host = await join(room, "Host")
        await main.leave_room(room.code, departure(host))
        assert room.players == []
        assert room.host_id is None
        assert room.leave_tokens == {}
        assert room.lobby_disconnected_at == {}
        replacement = await join(room, "Replacement")
        assert room.host_id == replacement.player_id
        await main.leave_room(room.code, departure(replacement))
        room.last_activity_at -= 181
        assert main.rooms.cleanup_expired(180) == [room.code]
        assert await main.leave_room(room.code, departure(replacement)) == {"left": True}

    asyncio.run(run())


def test_never_connected_reservations_expire_and_join_reclaims_capacity(room):
    async def run():
        sessions = [await join(room, name) for name in ["A", "B", "C", "D"]]
        assert all(not p.connected for p in room.players)
        with pytest.raises(HTTPException, match="room is full"):
            await join(room, "Extra")
        room.lobby_disconnected_at[sessions[-1].player_id] -= 31
        replacement = await join(room, "Replacement")
        assert not room.has_player(sessions[-1].player_id)
        assert room.has_player(replacement.player_id)
        assert room.is_full()

    asyncio.run(run())


def test_unexpected_disconnect_preserves_seat_until_grace_expires(room):
    async def run():
        player = room.add_player("Player")
        ws = FakeWebSocket()
        await main.connections.connect(room, player.id, ws)
        assert player.connected
        assert player.id not in room.lobby_disconnected_at
        assert main.connections.disconnect(room, player.id, ws)
        assert not player.connected
        assert room.expire_lobby_seats(30) == []
        room.lobby_disconnected_at[player.id] -= 31
        assert room.expire_lobby_seats(30) == [player.id]
        assert room.host_id is None

    asyncio.run(run())


def test_reconnect_cancels_lobby_expiry_and_preserves_identity(room):
    async def run():
        player = room.add_player("Player")
        token = room.leave_tokens[player.id]
        first, second = FakeWebSocket(), FakeWebSocket()
        await main.connections.connect(room, player.id, first)
        main.connections.disconnect(room, player.id, first)
        room.lobby_disconnected_at[player.id] -= 20
        await main.connections.connect(room, player.id, second)
        assert room.expire_lobby_seats(0) == []
        assert room.players == [player]
        assert room.leave_tokens[player.id] == token
        assert room.host_id == player.id

    asyncio.run(run())


def test_replacement_socket_is_not_disconnected_by_old_socket(room):
    async def run():
        player = room.add_player("Player")
        old, new = FakeWebSocket(), FakeWebSocket()
        await main.connections.connect(room, player.id, old)
        await main.connections.connect(room, player.id, new)
        assert old.closed_with == 4009
        assert not main.connections.disconnect(room, player.id, old)
        assert room.sockets[player.id] is new
        assert player.connected
        assert player.id not in room.lobby_disconnected_at

    asyncio.run(run())


def test_old_broadcast_failure_cannot_disconnect_replacement(room):
    async def run():
        player = room.add_player("Player")
        replacement = FakeWebSocket()

        class ReplacedWhileSending(FakeWebSocket):
            async def send_json(self, message):
                await main.connections.connect(room, player.id, replacement)
                raise RuntimeError("old socket closed")

        old = ReplacedWhileSending()
        await main.connections.connect(room, player.id, old)
        await main.connections.broadcast_state(room)
        assert room.sockets[player.id] is replacement
        assert player.connected

    asyncio.run(run())


def test_connect_cannot_restore_a_seat_removed_during_accept(room):
    async def run():
        player = room.add_player("Player")

        class RemovedWhileAccepting(FakeWebSocket):
            async def accept(self):
                room.remove_lobby_player(player.id)

        ws = RemovedWhileAccepting()
        assert not await main.connections.connect(room, player.id, ws)
        assert ws.closed_with == 4003
        assert not room.sockets

    asyncio.run(run())


def test_start_requires_connected_humans_but_allows_bots(room):
    async def run():
        host = room.add_player("Host")
        room.add_bots(host.id)
        with pytest.raises(GameError, match="all players must be connected"):
            room.start_game(host.id)
        await main.connections.connect(room, host.id, FakeWebSocket())
        room.start_game(host.id)
        assert room.started
        assert room.lobby_disconnected_at == {}

    asyncio.run(run())


def test_active_game_leave_preserves_seat_and_reconnect_cancels_conversion(room):
    async def run():
        sessions = [await join(room, name) for name in ["A", "B", "C", "D"]]
        for session in sessions:
            await main.connections.connect(room, session.player_id, FakeWebSocket())
        room.start_game(room.host_id)
        departing = sessions[-1]
        game = room.game
        try:
            await main.leave_room(room.code, departure(departing))
            player = next(p for p in room.players if p.id == departing.player_id)
            assert room.game is game
            assert len(game.players) == len(room.players) == 4
            assert not player.connected
            assert departing.player_id in room.conversion_timers
            assert room.expire_lobby_seats(0) == []
            with pytest.raises(GameError, match="after the game starts"):
                room.remove_lobby_player(player.id)
            await main.connections.connect(room, player.id, FakeWebSocket())
            main._cancel_conversion(room, player.id)
            assert player.id not in room.conversion_timers
            assert player.connected
        finally:
            for player_id in list(room.conversion_timers):
                main._cancel_conversion(room, player_id)

    asyncio.run(run())


def test_socket_handler_disconnect_starts_lobby_reservation(room):
    async def run():
        player = room.add_player("Player")

        class DisconnectingSocket(FakeWebSocket):
            headers = {}
            client = None

            async def receive(self):
                return {"type": "websocket.disconnect", "code": 1000}

        ws = DisconnectingSocket()
        await main.game_socket(ws, room.code, player_id=player.id)
        assert not player.connected
        assert room.has_player(player.id)
        assert player.id in room.lobby_disconnected_at
        assert player.id not in room.conversion_timers
        assert ws.messages[0] == {
            "type": "session_credentials", "leave_token": room.leave_tokens[player.id],
        }

    asyncio.run(run())


def test_replaced_socket_handler_cannot_process_queued_commands(room):
    async def run():
        player = room.add_player("Host")
        replacement = FakeWebSocket()

        class ReplacedWhileReceiving(FakeWebSocket):
            headers = {}
            client = None

            async def receive(self):
                await main.connections.connect(room, player.id, replacement)
                return {"type": "websocket.receive", "text": json.dumps({"type": "add_bots"})}

        old = ReplacedWhileReceiving()
        await main.game_socket(old, room.code, player_id=player.id)
        assert room.players == [player]
        assert room.sockets[player.id] is replacement
        assert player.connected
        assert player.id not in room.lobby_disconnected_at

    asyncio.run(run())
