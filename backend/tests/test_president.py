"""Unit tests for the President engine + bot brain."""
import random

import pytest

from app.game.base import Card, Phase, Player, Suit
from app.game.president.engine import Game
from app.game.president.bot import PresidentBotBrain
from app.game.president.models import build_president_deck, exchange_rank


def make_players(n=5):
    return [Player(id=f"p{i}", name=f"P{i}", join_order=i) for i in range(n)]


def new_game(n=5, rounds=5, seed=42):
    players = make_players(n)
    g = Game(n, {"rounds": str(rounds)}, players, rng=random.Random(seed))
    g.start()
    return g


def card(rank, suit=Suit.SPADE):
    return Card(suit=suit, rank=rank)


def set_hand(game, pid, cards):
    p = game._player_by_id(pid)
    p.hand = list(cards)


def play(game, pid, ranks):
    """Helper: play a combo of given ranks (same suit doesn't matter)."""
    cards = [card(r) for r in ranks]
    # Ensure the player actually holds these (set_hand used).
    set_hand(game, pid, cards)  # for test convenience
    game.apply_action(pid, "play_combo", {"cards": [c.to_dict() for c in cards]})


# --- deck ---------------------------------------------------------------
def test_president_deck_has_50_cards_no_two_twos_removed():
    rng = random.Random(0)
    deck = build_president_deck(rng)
    assert len(deck) == 50
    twos = [c for c in deck if c.rank == 2]
    assert len(twos) == 2  # exactly two 2s remain


def test_each_player_gets_10_cards():
    g = new_game()
    for p in g.players:
        assert len(p.hand) == 10


def test_round_1_leader_holds_jack_of_hearts():
    g = new_game(seed=7)
    jh = Card(suit=Suit.HEART, rank=11)
    leader = g.players[g.turn_idx]
    assert jh in leader.hand


# --- combo validation ---------------------------------------------------
def test_cannot_play_mixed_ranks():
    g = new_game()
    pid = g.players[g.turn_idx].id
    with pytest.raises(Exception):
        # 3 and 4 are different ranks
        play(g, pid, [3, 4])


def test_cannot_play_2_as_normal_combo():
    g = new_game()
    pid = g.players[g.turn_idx].id
    # Player holds a 2 alongside other cards — the 2 must be bombed, not led.
    set_hand(g, pid, [card(2), card(5)])
    with pytest.raises(Exception, match="bomb"):
        g.apply_action(pid, "play_combo", {"cards": [card(2).to_dict()]})


def test_can_lead_2_when_only_holds_twos():
    """Edge case: a player holding only 2s on a fresh lead may lead a 2."""
    g = new_game()
    pid = g.players[g.turn_idx].id
    set_hand(g, pid, [card(2), card(2)])
    g.apply_action(pid, "play_combo", {"cards": [card(2).to_dict()]})
    assert g.pile_top is not None
    assert g.pile_top["rank"] == 2


def test_follow_must_match_size():
    g = new_game()
    # Leader plays a single 3.
    leader = g.players[g.turn_idx]
    set_hand(g, leader.id, [card(3), card(4)])
    g.apply_action(leader.id, "play_combo", {"cards": [card(3).to_dict()]})
    # Next player tries a pair of 4s — must fail (size mismatch).
    nxt = g.players[g.turn_idx]
    set_hand(g, nxt.id, [card(4), card(4)])
    with pytest.raises(Exception, match="size"):
        g.apply_action(nxt.id, "play_combo", {"cards": [card(4).to_dict(), card(4).to_dict()]})


def test_follow_must_be_higher_rank():
    g = new_game()
    leader = g.players[g.turn_idx]
    set_hand(g, leader.id, [card(7)])
    g.apply_action(leader.id, "play_combo", {"cards": [card(7).to_dict()]})
    nxt = g.players[g.turn_idx]
    set_hand(g, nxt.id, [card(5)])
    with pytest.raises(Exception, match="rank"):
        g.apply_action(nxt.id, "play_combo", {"cards": [card(5).to_dict()]})


# --- passing & pile clear -----------------------------------------------
def test_pass_not_allowed_when_leading():
    g = new_game()
    pid = g.players[g.turn_idx].id
    with pytest.raises(Exception, match="leading"):
        g.apply_action(pid, "pass", {})


def test_all_pass_clears_pile_last_player_leads():
    g = new_game(seed=1)
    # Leader plays a single 3.
    leader = g.players[g.turn_idx]
    set_hand(g, leader.id, [card(3), card(9)])
    g.apply_action(leader.id, "play_combo", {"cards": [card(3).to_dict()]})
    leader_id = leader.id
    # Everyone else passes.
    for _ in range(4):
        nxt = g.players[g.turn_idx]
        # give them a card so they're still active
        if not nxt.hand:
            set_hand(g, nxt.id, [card(14)])
        g.apply_action(nxt.id, "pass", {})
    # Pile should be cleared and leader leads again.
    assert g.pile_top is None
    assert g.turn_idx == g._seat_of(leader_id)


# --- bomb ---------------------------------------------------------------
def test_bomb_clears_pile_and_bomber_leads():
    g = new_game(seed=2)
    # Leader plays a single 5.
    leader = g.players[g.turn_idx]
    set_hand(g, leader.id, [card(5), card(7)])
    g.apply_action(leader.id, "play_combo", {"cards": [card(5).to_dict()]})
    # Next player bombs with a 2 and leads a single 3.
    bomber = g.players[g.turn_idx]
    set_hand(g, bomber.id, [card(2), card(3), card(8)])
    g.apply_action(bomber.id, "bomb", {"lead": [card(3).to_dict()]})
    assert g.pile_top is not None
    assert g.pile_top["rank"] == 3
    assert g.pile_top["size"] == 1
    assert g.turn_idx != g._seat_of(bomber.id)  # advanced to next player


def test_bomb_with_last_card_finishes():
    g = new_game(seed=2)
    leader = g.players[g.turn_idx]
    set_hand(g, leader.id, [card(5), card(9)])
    g.apply_action(leader.id, "play_combo", {"cards": [card(5).to_dict()]})
    bomber = g.players[g.turn_idx]
    # Bomber has only a 2 (their last card).
    set_hand(g, bomber.id, [card(2)])
    g.apply_action(bomber.id, "bomb", {"lead": []})
    assert bomber.id in [g.players[s].id for s in g._finish_order]
    assert len(bomber.hand) == 0


# --- skip ---------------------------------------------------------------
def test_skip_on_consecutive_same_rank_singles():
    g = new_game(seed=3)
    # Player A plays single 5; Player B plays single 5 -> next (C) skipped.
    a = g.players[g.turn_idx]
    set_hand(g, a.id, [card(5), card(9)])
    g.apply_action(a.id, "play_combo", {"cards": [card(5).to_dict()]})
    b = g.players[g.turn_idx]
    set_hand(g, b.id, [card(5), card(9)])
    g.apply_action(b.id, "play_combo", {"cards": [card(5).to_dict()]})
    # Next seat should be skipped for this combo.
    c_seat = g._next_active_seat_after(b.join_order)
    assert c_seat in g.skip_until_clear


def test_two_players_left_same_rank_skips_and_clears():
    """Regression: with two players left, a matching single skips the only
    opponent and the combo is uncontested — the pile must clear and the last
    player leads fresh (previously the pile could never clear and the game
    stuck on the same player's turn)."""
    g = new_game(seed=3)
    # Only players 0 and 1 still hold cards.
    set_hand(g, "p0", [card(6), card(10)])
    set_hand(g, "p1", [card(6), card(4), card(3)])
    set_hand(g, "p2", [])
    set_hand(g, "p3", [])
    set_hand(g, "p4", [])
    g.turn_idx = 0
    # p0 leads a single 6; p1 matches with a single 6.
    g.apply_action("p0", "play_combo", {"cards": [card(6).to_dict()]})
    g.apply_action("p1", "play_combo", {"cards": [card(6).to_dict()]})
    # p0 skipped -> nobody left to contest: pile clears, p1 leads fresh.
    assert g.pile_top is None
    assert g.skip_until_clear == set()
    assert g.turn_idx == 1
    # Normal two-player flow continues.
    g.apply_action("p1", "play_combo", {"cards": [card(4).to_dict()]})
    assert g.pile_top["rank"] == 4
    assert g.turn_idx == 0
    # p0 overtakes with their last card -> finishes; round ends.
    g.apply_action("p0", "play_combo", {"cards": [card(10).to_dict()]})
    assert g.phase == Phase.ROUND_END


def test_uncontested_skip_clears_pile_last_player_leads():
    """A skip that leaves only the last player able to act ends the combo:
    pile clears and the last player leads fresh."""
    g = new_game(seed=3)
    set_hand(g, "p0", [card(5), card(5), card(9)])
    set_hand(g, "p1", [card(5), card(8)])
    set_hand(g, "p2", [card(4)])
    set_hand(g, "p3", [])
    set_hand(g, "p4", [])
    g.turn_idx = 0
    g.apply_action("p0", "play_combo", {"cards": [card(5).to_dict()]})
    g.apply_action("p1", "play_combo", {"cards": [card(5).to_dict()]})
    # p2 is skipped by the p0/p1 match; p0 gets the turn (p2 can no longer
    # contest this combo).
    assert g.skip_until_clear == {2}
    assert g.turn_idx == 0
    # p0 matches again -> skipping p1 leaves nobody to contest: pile clears
    # and p0 leads fresh.
    g.apply_action("p0", "play_combo", {"cards": [card(5).to_dict()]})
    assert g.pile_top is None
    assert g.skip_until_clear == set()
    assert g.turn_idx == 0
    # p0 leads their remaining card; flow continues normally.
    g.apply_action("p0", "play_combo", {"cards": [card(9).to_dict()]})
    assert g.pile_top["rank"] == 9
    assert g.turn_idx == 1


def test_finish_passes_lead_clockwise_not_lowest_seat():
    """After a player finishes, the lead goes to the next seat clockwise from
    the finisher — not the lowest active seat."""
    g = new_game(seed=3)
    set_hand(g, "p0", [card(9), card(10)])
    set_hand(g, "p1", [])
    set_hand(g, "p2", [card(6)])
    set_hand(g, "p3", [])
    set_hand(g, "p4", [card(8)])
    g.turn_idx = 2
    # p2 leads their last card and finishes (seats 0, 2, 4 held cards).
    g.apply_action("p2", "play_combo", {"cards": [card(6).to_dict()]})
    # Next clockwise after seat 2 is seat 4 (not the lowest seat 0).
    assert g.turn_idx == 4


def test_finish_wraps_clockwise():
    """When the finisher is the highest active seat, the lead wraps to the
    lowest active seat."""
    g = new_game(seed=3)
    set_hand(g, "p0", [card(9), card(10)])
    set_hand(g, "p1", [])
    set_hand(g, "p2", [])
    set_hand(g, "p3", [card(8)])
    set_hand(g, "p4", [card(6)])
    g.turn_idx = 4
    # p4 leads their last card and finishes.
    g.apply_action("p4", "play_combo", {"cards": [card(6).to_dict()]})
    # Next clockwise after seat 4 wraps around to seat 0.
    assert g.turn_idx == 0


# --- round end & scoring ------------------------------------------------
def test_round_ends_when_one_player_has_cards():
    g = new_game(rounds=5, seed=5)
    # Force four players to empty their hands.
    for i, p in enumerate(g.players[:4]):
        set_hand(g, p.id, [])
        g._mark_finished(p.join_order)
    # The fifth player still has cards.
    fifth = g.players[4]
    assert fifth.hand  # has cards
    g._end_round()
    assert g.phase == Phase.ROUND_END
    assert g.roles[4] == fifth.id  # Asshole
    assert g.roles[0] == g.players[0].id  # President


def test_scoring_assigns_correct_points():
    g = new_game(rounds=5, seed=5)
    seats = [p.join_order for p in g.players]
    # Force a specific finish order: 0,1,2,3,4
    for s in seats:
        g._finish_order.append(s)
        g.players[s].hand = []  # mark as empty
    g.players[4].hand = [card(3)]  # last place still has a card
    g._end_round()
    assert g.players[0].total_score == 5   # President
    assert g.players[1].total_score == 3   # VP
    assert g.players[2].total_score == 1   # Neutral
    assert g.players[3].total_score == 0   # Vice-Asshole
    assert g.players[4].total_score == -2  # Asshole


# --- exchange -----------------------------------------------------------
def test_exchange_transfers_highest_cards_from_loser():
    g = new_game(rounds=5, seed=5)
    # Force finish order 0,1,2,3,4
    for i in range(5):
        g._finish_order.append(i)
    g.roles = {i: g.players[i].id for i in range(5)}
    # Give the Asshole (seat 4) some cards including two high ones.
    set_hand(g, g.players[4].id, [card(3), card(5), card(14), card(2)])
    # President (seat 0) has some cards.
    set_hand(g, g.players[0].id, [card(4), card(6)])
    original_asshole_high = [card(2), card(14)]
    original_asshole_low = [card(3), card(5)]
    # Manually trigger exchange step (bypass advance_round).
    g.exchange_state = {"pending": g._build_exchange_pending()}
    g.phase = Phase.EXCHANGE
    g._start_next_exchange_step()
    # Asshole's two highest (2 and A) should have moved to President.
    asshole = g.players[4]
    president = g.players[0]
    for c in original_asshole_high:
        assert c not in asshole.hand
        assert c in president.hand
    for c in original_asshole_low:
        assert c in asshole.hand


def test_choose_return_sends_cards_back():
    g = new_game(rounds=5, seed=5)
    for i in range(5):
        g._finish_order.append(i)
    g.roles = {i: g.players[i].id for i in range(5)}
    set_hand(g, g.players[4].id, [card(3), card(14), card(2)])
    set_hand(g, g.players[0].id, [card(4), card(6)])
    g.exchange_state = {"pending": g._build_exchange_pending()}
    g.phase = Phase.EXCHANGE
    g._start_next_exchange_step()
    # President (seat 0) must return 2 cards.
    president = g.players[0]
    return_cards = president.hand[:2]
    g.apply_action(president.id, "choose_return", {"cards": [c.to_dict() for c in return_cards]})
    # Returned cards should now be in Asshole's hand.
    asshole = g.players[4]
    for c in return_cards:
        assert c in asshole.hand


# --- game end -----------------------------------------------------------
def test_game_end_after_chosen_rounds():
    g = new_game(rounds=2, seed=5)
    # End round 1.
    g._finish_order = list(range(5))
    for i in range(5):
        g.players[i].hand = []
    g.players[4].hand = [card(3)]
    g._end_round()
    assert g.phase == Phase.ROUND_END
    # Advance to round 2 (deals + exchange). Force empty hands so exchange is
    # trivial — give everyone a card so they can return one.
    g.advance_round()
    # End round 2 -> game end (total_rounds=2).
    g._finish_order = list(range(5))
    for i in range(5):
        g.players[i].hand = []
    g.players[4].hand = [card(3)]
    g._end_round()
    assert g.phase == Phase.GAME_END
    assert g.final_standings() is not None


# --- bot ---------------------------------------------------------------
def test_bot_returns_legal_action():
    g = new_game(seed=10)
    brain = PresidentBotBrain()
    # Run a few turns; every bot decision must be legal-ish (apply cleanly).
    guard = 0
    while g.phase == Phase.PLAYING and guard < 500:
        guard += 1
        cur = g.players[g.turn_idx]
        action, params = brain.decide_action(g, cur.id, random.Random(guard))
        # Apply it; should not raise.
        g.apply_action(cur.id, action, params)
    assert g.phase != Phase.PLAYING or guard >= 500


def test_bot_full_round_completes():
    """A full round driven entirely by the bot brain should reach ROUND_END/GAME_END."""
    g = new_game(rounds=2, seed=123)
    brain = PresidentBotBrain()
    guard = 0
    while g.phase not in (Phase.ROUND_END, Phase.GAME_END) and guard < 5000:
        guard += 1
        cur = g.players[g.turn_idx]
        if g.phase == Phase.EXCHANGE:
            # Advance exchange via bot where applicable, else advance_round.
            if g.exchange_state.get("step") == "choose_return" and g._seat_of(cur.id) == g.exchange_state["receiver_seat"]:
                action, params = brain.decide_action(g, cur.id, random.Random(guard))
                g.apply_action(cur.id, action, params)
            else:
                # Try the next receiver, or if no exchange pending, advance.
                continue
        else:
            action, params = brain.decide_action(g, cur.id, random.Random(guard))
            g.apply_action(cur.id, action, params)
    assert g.phase in (Phase.ROUND_END, Phase.GAME_END)
