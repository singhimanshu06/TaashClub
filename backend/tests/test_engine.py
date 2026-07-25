"""Unit tests for the pure TaashClub engine."""
import random

import pytest

from app.game.callbreak.engine import Game, GameError, build_round_schedule
from app.game.base import Card, Phase, Player, Suit, hand_sort_key
from app.game.callbreak.models import Variant


def make_players(n: int) -> list[Player]:
    return [Player(id=f"p{i}", name=f"P{i}", join_order=i) for i in range(n)]


def new_game(n=4, variant=Variant.SINGLE_RUN, seed=42) -> Game:
    return Game(n, variant, make_players(n), rng=random.Random(seed))


# --- starting hand size & schedules ------------------------------------
@pytest.mark.parametrize("n,expected", [(4, 13), (5, 10), (6, 8)])
def test_starting_cards(n, expected):
    assert new_game(n).starting_cards == expected


@pytest.mark.parametrize(
    "n,variant,length",
    [
        (4, Variant.SINGLE_RUN, 13),
        (5, Variant.SINGLE_RUN, 10),
        (6, Variant.SINGLE_RUN, 8),
        (4, Variant.DOWN_AND_UP, 26),
        (5, Variant.DOWN_AND_UP, 20),
        (6, Variant.DOWN_AND_UP, 16),
    ],
)
def test_schedule_length(n, variant, length):
    assert len(new_game(n, variant).round_schedule) == length


def test_down_and_up_has_double_one_at_turn():
    sched = build_round_schedule(13, Variant.DOWN_AND_UP)
    assert sched == [13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1,
                     1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    assert sched[12] == 1 and sched[13] == 1


def test_deal_counts_and_leftovers():
    g = new_game(5)  # 10 cards each, 2 left over in round 1
    g.start()
    assert all(len(p.hand) == 10 for p in g.players)
    dealt = sum(len(p.hand) for p in g.players)
    assert dealt == 50  # 52 - 2 leftover


# --- trump cycle -------------------------------------------------------
def test_trump_cycle_by_round_index():
    g = new_game(4, Variant.DOWN_AND_UP)
    seen = []
    g.start()
    seen.append(g.trump)
    for _ in range(5):
        _fast_forward_round(g)
        seen.append(g.trump)
    assert seen[:5] == [Suit.SPADE, Suit.HEART, Suit.CLUB, Suit.DIAMOND, Suit.SPADE]


# --- starter rotation --------------------------------------------------
def test_starter_rotation_cycles_all_seats():
    g = new_game(5)
    starters = []
    g.start()
    starters.append(g.starter_idx)
    for _ in range(6):
        _fast_forward_round(g)
        starters.append(g.starter_idx)
    assert starters[:6] == [0, 1, 2, 3, 4, 0]


# --- follow-suit legality ---------------------------------------------
def test_follow_suit_enforced_and_free_discard():
    g = new_game(4)
    # Hand out a controlled deal by overriding after start.
    g.start()
    for p in g.players:
        p.bid = 1
    # force into PLAYING
    g.phase = Phase.PLAYING
    g.turn_idx = 0
    g.led_suit = None
    g.current_trick = []
    g.players[0].hand = [Card(Suit.HEART, 9)]
    g.players[1].hand = [Card(Suit.HEART, 5), Card(Suit.SPADE, 14)]
    g.players[2].hand = [Card(Suit.CLUB, 5)]
    g.players[3].hand = [Card(Suit.CLUB, 6)]

    g.play_card("p0", Card(Suit.HEART, 9))          # leads hearts
    # p1 holds a heart -> must follow; spade is illegal
    assert g.legal_cards("p1") == [Card(Suit.HEART, 5)]
    with pytest.raises(GameError):
        g.play_card("p1", Card(Suit.SPADE, 14))
    g.play_card("p1", Card(Suit.HEART, 5))
    # p2 has no heart -> free discard allowed
    assert Card(Suit.CLUB, 5) in g.legal_cards("p2")
    g.play_card("p2", Card(Suit.CLUB, 5))


# --- trick winner ------------------------------------------------------
def test_trump_beats_led_suit():
    # trump = SPADE (round 0). Hearts led, one spade played -> spade wins.
    trick = [
        {"seat": 0, "card": Card(Suit.HEART, 14)},
        {"seat": 1, "card": Card(Suit.SPADE, 2)},
        {"seat": 2, "card": Card(Suit.HEART, 3)},
        {"seat": 3, "card": Card(Suit.CLUB, 10)},
    ]
    assert Game._trick_winner(trick, Suit.HEART, Suit.SPADE) == 1


def test_highest_of_led_when_no_trump():
    trick = [
        {"seat": 0, "card": Card(Suit.HEART, 9)},
        {"seat": 1, "card": Card(Suit.HEART, 12)},
        {"seat": 2, "card": Card(Suit.CLUB, 14)},  # off-suit, cannot win
        {"seat": 3, "card": Card(Suit.HEART, 4)},
    ]
    assert Game._trick_winner(trick, Suit.HEART, Suit.SPADE) == 1


# --- scoring -----------------------------------------------------------
def test_scoring_exact_over_under_and_nil():
    g = new_game(4)
    g.start()
    g.players[0].bid, g.players[0].tricks_won = 3, 3   # exact -> 13
    g.players[1].bid, g.players[1].tricks_won = 2, 4   # over -> 0
    g.players[2].bid, g.players[2].tricks_won = 5, 1   # under -> 0
    g.players[3].bid, g.players[3].tricks_won = 0, 0   # nil hit -> 10
    g._end_round()
    scores = {r["player_id"]: r["points"] for r in g.last_round_result}
    assert scores == {"p0": 13, "p1": 0, "p2": 0, "p3": 10}
    assert g.players[0].total_score == 13
    assert g.players[3].total_score == 10


# --- bidding validation ------------------------------------------------
def test_bid_out_of_range_and_turn_order():
    g = new_game(4)
    g.start()  # round 0: starter seat 0, 13 cards
    with pytest.raises(GameError):
        g.place_bid("p1", 1)          # not p1's turn
    with pytest.raises(GameError):
        g.place_bid("p0", 14)         # above cards_this_round
    g.place_bid("p0", 0)              # nil allowed
    assert g.players[0].bid == 0
    assert g.turn_idx == 1


# --- helper ------------------------------------------------------------
def _fast_forward_round(g: Game) -> None:
    """Bid 0 for everyone and auto-play out the round to reach the next one."""
    while g.phase == Phase.BIDDING:
        g.place_bid(g.players[g.turn_idx].id, 0)
    while g.phase == Phase.PLAYING:
        if g.awaiting_trick_clear:
            g.commit_trick()  # simulate the post-trick hold clearing
            continue
        pid = g.players[g.turn_idx].id
        card = g.legal_cards(pid)[0]
        g.play_card(pid, card)
    if g.phase == Phase.ROUND_END:
        g.advance_round()


def test_hand_sort_order_spade_heart_club_diamond_descending():
    hand = [
        Card(Suit.DIAMOND, 5),
        Card(Suit.SPADE, 2),
        Card(Suit.SPADE, 14),
        Card(Suit.CLUB, 10),
        Card(Suit.HEART, 7),
        Card(Suit.HEART, 13),
    ]
    ordered = sorted(hand, key=hand_sort_key)
    assert ordered == [
        Card(Suit.SPADE, 14),
        Card(Suit.SPADE, 2),
        Card(Suit.HEART, 13),
        Card(Suit.HEART, 7),
        Card(Suit.CLUB, 10),
        Card(Suit.DIAMOND, 5),
    ]


def test_dealt_hands_are_sorted_in_display_order():
    g = new_game(4, seed=3)
    g.start()
    for p in g.players:
        assert list(p.hand) == sorted(p.hand, key=hand_sort_key)


def test_trick_held_then_committed():
    g = new_game(4)
    g.start()
    for _ in range(4):  # everyone bids
        g.place_bid(g.players[g.turn_idx].id, 1)
    assert g.phase == Phase.PLAYING
    # Play all four cards of the first trick.
    for _ in range(4):
        assert not g.awaiting_trick_clear
        pid = g.players[g.turn_idx].id
        g.play_card(pid, g.legal_cards(pid)[0])
    # Trick is full: held on the table, winner decided, nobody on turn.
    assert g.awaiting_trick_clear is True
    assert g.last_trick_winner_seat is not None
    assert len(g.current_trick) == 4
    assert g.to_state()["current_player_id"] is None
    assert g.to_state()["trick_winner_id"] == g.players[g.last_trick_winner_seat].id
    # Cannot play into a held trick.
    with pytest.raises(GameError):
        pid = g.players[g.last_trick_winner_seat].id
        g.play_card(pid, g.players[g.last_trick_winner_seat].hand[0])
    winner_seat = g.last_trick_winner_seat
    g.commit_trick()
    assert g.awaiting_trick_clear is False
    assert len(g.current_trick) == 0
    assert g.players[winner_seat].tricks_won == 1
    assert g.turn_idx == winner_seat  # winner leads next


def test_full_game_reaches_game_end():
    g = new_game(4, Variant.SINGLE_RUN, seed=7)
    g.start()
    guard = 0
    while g.phase != Phase.GAME_END and guard < 100:
        _fast_forward_round(g)
        guard += 1
    assert g.phase == Phase.GAME_END
    standings = g.final_standings()
    assert len(standings) == 4
    assert [s["rank"] for s in standings] == [1, 2, 3, 4]


# --- round history & mid-game scoreboard -------------------------------
def test_round_history_accumulates_one_entry_per_round():
    g = new_game(4, Variant.SINGLE_RUN, seed=11)
    g.start()
    assert g.round_history == []
    _fast_forward_round(g)  # round 0 done
    assert len(g.round_history) == 1
    entry = g.round_history[0]
    assert entry["round_index"] == 0
    assert entry["trump"] == Suit.SPADE.value  # round 0 trump
    assert entry["cards_this_round"] == 13
    assert len(entry["results"]) == 4
    # Per-round points are present and sum consistently with last_round_result.
    pts = {r["player_id"]: r["points"] for r in entry["results"]}
    last_pts = {r["player_id"]: r["points"] for r in g.last_round_result}
    assert pts == last_pts

    _fast_forward_round(g)  # round 1 done
    assert len(g.round_history) == 2
    assert g.round_history[1]["round_index"] == 1
    assert g.round_history[1]["trump"] == Suit.HEART.value


def test_round_history_covers_all_rounds_at_game_end():
    g = new_game(4, Variant.SINGLE_RUN, seed=7)
    g.start()
    guard = 0
    while g.phase != Phase.GAME_END and guard < 100:
        _fast_forward_round(g)
        guard += 1
    # single_run of 4p = 13 rounds -> 13 history entries (rounds 0..12).
    assert len(g.round_history) == g.total_rounds
    assert [e["round_index"] for e in g.round_history] == list(range(13))
    # Trump cycle is preserved across the history.
    trumps = [e["trump"] for e in g.round_history]
    assert trumps[:4] == ["S", "H", "C", "D"]
    assert trumps[4] == "S"


def test_total_score_exposed_mid_game_in_to_state():
    """Cumulative totals are sent to clients during play (not just at game end)."""
    g = new_game(4, seed=5)
    g.start()
    # Round 0 still in progress: everyone's cumulative total is 0.
    state = g.to_state("p0")
    assert all(p["total_score"] == 0 for p in state["players"])
    assert state["round_history"] == []

    # Finish round 0 with a known scoring setup.
    _fast_forward_round(g)
    state = g.to_state("p0")
    # After round 0 ends, the per-player total_score in to_state reflects round 0.
    assert sum(p["total_score"] for p in state["players"]) == sum(
        r["points"] for r in g.round_history[0]["results"]
    )
    # round_history is now populated and exposed via to_state.
    assert len(state["round_history"]) == 1


def test_to_state_round_history_matches_engine_round_history():
    g = new_game(4, seed=9)
    g.start()
    for _ in range(3):
        _fast_forward_round(g)
    state = g.to_state("p0")
    assert state["round_history"] == g.round_history
    assert len(state["round_history"]) == 3
