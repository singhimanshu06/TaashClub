"""Unit coverage for spectator sessions and their public state boundary."""
import asyncio
import json

import pytest

import app.main as main
from app.game.base import GameError, Phase, Player
from app.game.callbreak.engine import Game as CallbreakGame
from app.game.callbreak.models import Variant
from app.game.president.engine import Game as PresidentGame
from app.game.room import MAX_SPECTATORS, ConnectionManager, Room
from app.game.twentyeight.engine import Game as TwentyEightGame


class FakeWebSocket:
    def __init__(self):
        self.messages = []
        self.accepted = False
        self.closed_with = None

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.messages.append(message)

    async def close(self, code=None):
        self.closed_with = code


def full_room() -> Room:
    room = Room(code="TEST", game_type="callbreak", num_players=4, options={"variant": "single_run"})
    for name in ["Alice", "Bob", "Cara", "Dan"]:
        room.add_player(name)
    return room


def started_room() -> Room:
    room = full_room()
    room.start_game(room.host_id)
    return room


def test_neutral_state_redacts_hands_for_every_game():
    def players(count):
        return [Player(id=f"p{i}", name=f"P{i}", join_order=i) for i in range(count)]

    cases = [
        CallbreakGame(4, Variant.SINGLE_RUN, players(4)),
        PresidentGame(5, {"rounds": "5"}, players(5)),
        TwentyEightGame(4, {}, players(4)),
    ]

    for game in cases:
        game.start()
        state = game.to_state(None)
        assert all(player["hand"] is None for player in state["players"])
        assert state["your_legal_cards"] is None
        assert state["your_legal_actions"] is None


def test_spectator_does_not_consume_a_seat_and_requires_full_room():
    room = Room(code="TEST", game_type="callbreak", num_players=4, options={})
    with pytest.raises(GameError, match="once the room is full"):
        room.add_spectator("Watcher")

    for name in ["Alice", "Bob", "Cara", "Dan"]:
        room.add_player(name)
    spectator = room.add_spectator("Watcher")

    assert len(room.players) == 4
    assert room.is_full()
    assert room.get_spectator(spectator.spectator_id) is spectator
    assert spectator.spectator_id not in room.lobby_snapshot()


def test_spectator_limit_counts_live_sockets_only():
    room = full_room()
    sessions = [room.add_spectator(f"Watcher {i}") for i in range(MAX_SPECTATORS)]
    room.spectator_sockets = {s.spectator_id: FakeWebSocket() for s in sessions}

    with pytest.raises(GameError, match="spectator limit"):
        room.add_spectator("One too many")

    room.spectator_sockets.pop(sessions[0].spectator_id)
    assert room.add_spectator("Replacement")


def test_spectator_chat_does_not_expose_auth_token():
    room = full_room()
    spectator = room.add_spectator("Watcher")
    message = room.add_chat(spectator.chat_id, "hello")

    assert message["player_id"] is None
    assert message["author_id"] == spectator.chat_id
    assert message["name"] == "Watcher"
    assert spectator.spectator_id not in json.dumps(message)


def test_spectator_receives_neutral_state_without_private_cards():
    async def run():
        room = started_room()
        spectator = room.add_spectator("Watcher")
        ws = FakeWebSocket()
        connections = ConnectionManager()
        await connections.connect_spectator(room, spectator.spectator_id, ws)
        await connections.broadcast_state(room)

        state_message = next(m for m in ws.messages if m["type"] == "state_update")
        state = state_message["state"]
        assert state["phase"] == Phase.BIDDING.value
        assert all(player["hand"] is None for player in state["players"])
        assert state["your_legal_cards"] is None
        assert state["your_legal_actions"] is None

    asyncio.run(run())


def test_spectator_can_chat_but_cannot_mutate_game(monkeypatch):
    async def run():
        room = started_room()
        spectator = room.add_spectator("Watcher")
        ws = FakeWebSocket()
        connections = main.ConnectionManager()
        monkeypatch.setattr(main, "connections", connections)
        await connections.connect_spectator(room, spectator.spectator_id, ws)
        phase = room.game.phase

        await main.handle_spectator_event(room, spectator.spectator_id, {"type": "chat", "text": "hi"})
        assert room.chat_log[-1]["name"] == "Watcher"
        assert ws.messages[-1]["message"]["author_id"] == spectator.chat_id

        await main.handle_spectator_event(
            room,
            spectator.spectator_id,
            {"type": "action", "action": "place_bid", "params": {"value": 99}},
        )
        assert room.game.phase == phase

    asyncio.run(run())
