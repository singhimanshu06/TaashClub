"""Async-layer tests: drive a full game through main.handle_event + the
scheduled post-trick clear task, exercising the trick-hold state machine and
the room.clearing guard end to end (no sockets — broadcasts are no-ops)."""
import asyncio

import app.main as main
from app.game.room import Room
from app.game.models import Variant


def _started_room() -> Room:
    room = Room(code="TEST", num_players=4, variant=Variant.SINGLE_RUN)
    for n in ["A", "B", "C", "D"]:
        room.add_player(n)
    room.start_game(room.host_id)
    return room


async def _play_full_game(room: Room):
    g = room.game
    guard = 0
    while g.phase.value != "game_end" and guard < 5000:
        guard += 1
        if g.awaiting_trick_clear:
            await asyncio.sleep(0.005)  # let the scheduled clear task run
            continue
        if g.phase.value == "bidding":
            pid = g.players[g.turn_idx].id
            await main.handle_event(room, pid, {"type": "place_bid", "value": 0})
        elif g.phase.value == "playing":
            pid = g.players[g.turn_idx].id
            card = g.legal_cards(pid)[0].to_dict()
            await main.handle_event(room, pid, {"type": "play_card", "card": card})
        elif g.phase.value == "round_end":
            await main.handle_event(room, room.host_id, {"type": "advance_round"})
    return g


def test_full_game_through_handlers_no_deadlock():
    async def run():
        main.TRICK_HOLD_SECONDS = 0.0
        room = _started_room()
        g = await _play_full_game(room)
        assert g.phase.value == "game_end"
        assert room.clearing is False           # guard always released
        assert not g.awaiting_trick_clear
        assert len(g.final_standings()) == 4

    asyncio.run(run())


def test_clearing_guard_resets_after_each_trick():
    """After every completed trick the guard returns to False (never stuck)."""
    async def run():
        main.TRICK_HOLD_SECONDS = 0.0
        room = _started_room()
        g = room.game
        # bid out
        while g.phase.value == "bidding":
            await main.handle_event(room, g.players[g.turn_idx].id,
                                    {"type": "place_bid", "value": 1})
        # play the first full trick
        for _ in range(4):
            pid = g.players[g.turn_idx].id
            await main.handle_event(room, pid,
                                    {"type": "play_card", "card": g.legal_cards(pid)[0].to_dict()})
        assert g.awaiting_trick_clear and room.clearing        # held + guarded
        await asyncio.sleep(0.02)                              # let hold task run
        assert not g.awaiting_trick_clear and not room.clearing  # cleared + released

    asyncio.run(run())
