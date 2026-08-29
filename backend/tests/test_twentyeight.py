"""Unit tests for the Twenty-Eight engine + bot brain."""
import random

import pytest

from app.game.base import Card, GameError, Phase, Player, Suit, hand_sort_key
from app.game.registry import GAME_REGISTRY
from app.game.twentyeight.bot import TwentyEightBotBrain
from app.game.twentyeight.engine import Game
from app.game.twentyeight.models import (
    MAX_BID,
    MIN_BID,
    PARTNER_OVERCALL_MIN,
    build_28_deck,
    card_points,
    card_strength,
)


def card(rank, suit=Suit.SPADE):
    return Card(suit=suit, rank=rank)


def make_players(n=4):
    return [Player(id=f"p{i}", name=f"P{i}", join_order=i) for i in range(n)]


def new_game(deals=2, seed=42):
    g = Game(4, {"deals": str(deals)}, make_players(), rng=random.Random(seed))
    g.start()
    return g


def pid(g, seat):
    return g.players[seat].id


def set_hand(g, seat, cards):
    g.players[seat].hand = list(cards)


def run_simple_auction(g, bid=16):
    """Seat 1 (the fixed opening seat on deal 1) wins the auction; rest pass."""
    assert g.turn_idx == 1
    g.apply_action(pid(g, 1), "place_bid", {"value": bid})
    while not g.awaiting_trump:
        g.apply_action(pid(g, g.turn_idx), "pass")


# --- deck / helpers -------------------------------------------------------
def test_deck_has_32_cards_ranks_7_to_ace():
    deck = build_28_deck()
    assert len(deck) == 32
    ranks = {c.rank for c in deck}
    assert ranks == {7, 8, 9, 10, 11, 12, 13, 14}


def test_strength_order_j_nine_ace_ten_k_q_eight_seven():
    j, nine, ace, ten, k, q, eight, seven = (
        card_strength(card(r)) for r in (11, 9, 14, 10, 13, 12, 8, 7)
    )
    assert j > nine > ace > ten > k > q > eight > seven


def test_point_values():
    assert card_points(card(11)) == 3
    assert card_points(card(9)) == 2
    assert card_points(card(14)) == 1
    assert card_points(card(10)) == 1
    for r in (7, 8, 12, 13):
        assert card_points(card(r)) == 0


# --- bidding --------------------------------------------------------------
def test_deal_starts_with_opening_turn_at_seat_after_dealer():
    g = new_game()
    assert g.phase == Phase.BIDDING
    assert g.dealer_idx == 0
    assert g.turn_idx == 1
    for p in g.players:
        assert len(p.hand) == 4
    # The held-back halves complete every seat to 8 cards with no overlap.
    assert len(g.pending_cards) == 4
    seen = []
    for seat in range(4):
        assert len(g.pending_cards[seat]) == 4
        seen += g.players[seat].hand + g.pending_cards[seat]
    assert len(seen) == 32
    assert len({(c.suit, c.rank) for c in seen}) == 32


def test_second_half_dealt_after_trump_is_named():
    g = new_game()
    run_simple_auction(g)
    first_hands = [list(p.hand) for p in g.players]
    pending = [list(cards) for cards in g.pending_cards]
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    assert g.phase == Phase.PLAYING
    assert g.pending_cards == []
    for seat in range(4):
        expected = sorted(first_hands[seat] + pending[seat], key=hand_sort_key)
        assert g.players[seat].hand == expected
        assert len(g.players[seat].hand) == 8
    # The dealt halves are untouched by the second deal.
    for seat in range(4):
        assert set(first_hands[seat]) <= set(g.players[seat].hand)


def test_opening_bid_is_mandatory_and_min_fourteen():
    g = new_game()
    with pytest.raises(GameError, match="mandatory"):
        g.apply_action(pid(g, 1), "pass")
    with pytest.raises(GameError, match="between"):
        g.apply_action(pid(g, 1), "place_bid", {"value": MIN_BID - 1})
    g.apply_action(pid(g, 1), "place_bid", {"value": MIN_BID})


def test_bid_must_be_at_most_max():
    g = new_game()
    with pytest.raises(GameError):
        g.apply_action(pid(g, 1), "place_bid", {"value": MAX_BID + 1})


def test_normal_raise_only_needs_plus_one():
    g = new_game()
    g.apply_action(pid(g, 1), "place_bid", {"value": 15})   # seat 1 (team 1)
    g.apply_action(pid(g, 2), "place_bid", {"value": 16})   # opponent, fine


def test_overcalling_own_partner_requires_at_least_20():
    g = new_game()
    g.apply_action(pid(g, 1), "place_bid", {"value": 17})   # team 1
    g.apply_action(pid(g, 2), "pass")
    with pytest.raises(GameError, match="minimum"):
        g.apply_action(pid(g, 3), "place_bid", {"value": 19})   # partner of 1
    g.apply_action(pid(g, 3), "place_bid", {"value": PARTNER_OVERCALL_MIN})


def test_pass_locks_player_out_and_auction_ends_when_others_passed():
    g = new_game()
    g.apply_action(pid(g, 1), "place_bid", {"value": 18})
    g.apply_action(pid(g, 2), "pass")
    g.apply_action(pid(g, 3), "place_bid", {"value": 20})   # partner overcall
    g.apply_action(pid(g, 0), "pass")
    g.apply_action(pid(g, 1), "place_bid", {"value": 21})
    g.apply_action(pid(g, 3), "pass")
    assert g.awaiting_trick_clear is False
    assert g.awaiting_trump
    assert g.bidder_seat == 1
    assert g.high_bid == 21
    # Both partners carry the standing bid.
    assert g.players[1].bid == 21 and g.players[3].bid == 21
    assert g.players[0].bid is None and g.players[2].bid is None


def test_a_passed_player_cannot_bid_even_out_of_protection():
    g = new_game()
    g.apply_action(pid(g, 1), "place_bid", {"value": 18})
    g.apply_action(pid(g, 2), "pass")
    # Simulate the turn landing back on the passed seat (defensive guard).
    g.passed_seats.add(2)
    g.turn_idx = 2
    with pytest.raises(GameError, match="already passed"):
        g.apply_action(pid(g, 2), "place_bid", {"value": 19})
    with pytest.raises(GameError, match="already passed"):
        g.apply_action(pid(g, 2), "pass")


# --- trump naming ---------------------------------------------------------
def test_set_trump_restricted_to_winning_bidder_then_play_begins():
    g = new_game()
    run_simple_auction(g)
    with pytest.raises(GameError, match="winning bidder"):
        g.apply_action(pid(g, 0), "set_trump", {"suit": "S"})
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    assert g.phase == Phase.PLAYING
    assert g.trump == Suit.SPADE
    assert not g.trump_exposed
    assert g.turn_idx == 1  # opener leads the first trick


def test_cannot_play_before_trump_is_named():
    g = new_game()
    run_simple_auction(g)
    with pytest.raises(GameError, match="not in playing"):
        c = g.players[1].hand[0]
        g.apply_action(pid(g, 1), "play_card", {"card": c.to_dict()})


# --- pre-exposure behaviour ------------------------------------------------
def test_bidder_may_lead_hidden_trump_like_any_suit():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    # Hidden trump is an ordinary suit for everyone, bidder included.
    set_hand(g, 1, [card(11, Suit.SPADE), card(7, Suit.HEART)])
    legal = {c.label for c in g.legal_cards(pid(g, 1))}
    assert legal == {"JS", "7H"}


def test_hidden_trump_led_wins_as_led_suit_only():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    # Bidder leads the hidden-trump J♠; it wins as the highest SPADE (28 order),
    # not as a trump.
    set_hand(g, 1, [card(11, Suit.SPADE)])
    set_hand(g, 2, [card(9, Suit.CLUB)])
    set_hand(g, 3, [card(14, Suit.SPADE)])   # A♠ (loses to J in 28 ranking)
    set_hand(g, 0, [card(8, Suit.HEART)])
    g.apply_action(pid(g, 1), "play_card", {"card": card(11, Suit.SPADE).to_dict()})
    g.apply_action(pid(g, 2), "play_card", {"card": card(9, Suit.CLUB).to_dict()})
    g.apply_action(pid(g, 3), "play_card", {"card": card(14, Suit.SPADE).to_dict()})
    g.apply_action(pid(g, 0), "play_card", {"card": card(8, Suit.HEART).to_dict()})
    assert g.last_trick_winner_seat == 1     # J♠ > A♠ by 28 ranking


def test_bidder_never_secretly_leads_trump_when_following_normally():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "H"})
    # Someone else led hearts; the bidder may follow with the J of hearts.
    g.players[1].turn = None
    set_hand(g, 1, [card(13, Suit.CLUB), card(11, Suit.HEART)])
    g.current_trick.append({"seat": 0, "card": card(9, Suit.HEART)})
    g.led_suit = Suit.HEART
    g.turn_idx = 1
    legal = g.legal_cards(pid(g, 1))
    assert legal == [card(11, Suit.HEART)]


def test_expose_requires_void_in_led_suit_and_on_turn():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    # Seat 1 is on turn, leading -> not allowed to reveal yet.
    set_hand(g, 1, [card(10, Suit.HEART), card(11, Suit.SPADE)])
    with pytest.raises(GameError, match="fresh lead"):
        g.apply_action(pid(g, 1), "expose_trump")
    # Seat 0 has already "led" hearts below; seat 2 can still follow -> reject.
    g.current_trick.append({"seat": 1, "card": card(10, Suit.HEART)})
    g.led_suit = Suit.HEART
    g.turn_idx = 2
    set_hand(g, 2, [card(9, Suit.HEART)])
    with pytest.raises(GameError, match="follow suit"):
        g.apply_action(pid(g, 2), "expose_trump")


def test_pre_exposure_trick_won_by_led_suit_even_with_trump_discards():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "D"})
    # Seat 1 leads 10♥; seat 2 discards J♠ (secret trump!); seat 3 void in ♥
    # discards 8♣; seat 0 plays A♥. Led suit wins pre-exposure (A > 10 in the
    # 28 ranking).
    set_hand(g, 1, [card(10, Suit.HEART)])
    set_hand(g, 2, [card(11, Suit.SPADE)])
    set_hand(g, 3, [card(8, Suit.CLUB)])
    set_hand(g, 0, [card(14, Suit.HEART)])
    g.apply_action(pid(g, 1), "play_card", {"card": card(10, Suit.HEART).to_dict()})
    g.apply_action(pid(g, 2), "play_card", {"card": card(11, Suit.SPADE).to_dict()})
    g.apply_action(pid(g, 3), "play_card", {"card": card(8, Suit.CLUB).to_dict()})
    g.apply_action(pid(g, 0), "play_card", {"card": card(14, Suit.HEART).to_dict()})
    assert g.awaiting_trick_clear
    assert g.last_trick_winner_seat == 0   # A♥ beats 10♥ pre-exposure


# --- exposure ---------------------------------------------------------------
def test_mid_trick_exposure_no_retroactive_trump_for_pre_exposure_cards():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    set_hand(g, 1, [card(10, Suit.HEART)])
    set_hand(g, 2, [card(11, Suit.SPADE)])          # pre-exposure discard of trump suit
    set_hand(g, 3, [card(8, Suit.CLUB)])            # void in ♥ -> reveals
    set_hand(g, 0, [card(14, Suit.HEART)])
    g.apply_action(pid(g, 1), "play_card", {"card": card(10, Suit.HEART).to_dict()})
    g.apply_action(pid(g, 2), "play_card", {"card": card(11, Suit.SPADE).to_dict()})
    g.apply_action(pid(g, 3), "expose_trump")
    assert g.trump_exposed
    g.apply_action(pid(g, 3), "play_card", {"card": card(8, Suit.CLUB).to_dict()})
    g.apply_action(pid(g, 0), "play_card", {"card": card(14, Suit.HEART).to_dict()})
    # J♠ was played BEFORE exposure -> stays an ordinary spade; A♥ wins.
    assert g.last_trick_winner_seat == 0


def test_mid_trick_exposure_trump_played_after_wins():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    set_hand(g, 1, [card(14, Suit.HEART)])
    set_hand(g, 2, [card(8, Suit.CLUB)])
    set_hand(g, 3, [card(9, Suit.SPADE)])           # void in ♥ -> reveals + trumps
    set_hand(g, 0, [card(10, Suit.HEART)])
    g.apply_action(pid(g, 1), "play_card", {"card": card(14, Suit.HEART).to_dict()})
    g.apply_action(pid(g, 2), "play_card", {"card": card(8, Suit.CLUB).to_dict()})
    g.apply_action(pid(g, 3), "expose_trump")
    g.apply_action(pid(g, 3), "play_card", {"card": card(9, Suit.SPADE).to_dict()})
    g.apply_action(pid(g, 0), "play_card", {"card": card(10, Suit.HEART).to_dict()})
    # 9♠ was played AFTER exposure -> real trump, beats A♥.
    assert g.last_trick_winner_seat == 3


def test_post_exposure_void_player_may_play_any_card():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    g.trump_exposed = True                          # no exposure ceremony: no exposer obligation
    set_hand(g, 1, [card(13, Suit.HEART)])          # leads K♥
    set_hand(g, 2, [card(9, Suit.SPADE)])           # void, plays 9♠
    # Seat 3 is void too and free to play anything — even a LOWER trump
    # (there is no overtrump obligation).
    set_hand(g, 3, [card(11, Suit.SPADE), card(7, Suit.SPADE)])
    set_hand(g, 0, [card(8, Suit.CLUB)])
    g.apply_action(pid(g, 1), "play_card", {"card": card(13, Suit.HEART).to_dict()})
    g.apply_action(pid(g, 2), "play_card", {"card": card(9, Suit.SPADE).to_dict()})
    legal3 = {c.label for c in g.legal_cards(pid(g, 3))}
    assert legal3 == {"JS", "7S"}                   # both legal, no overtrump required
    g.apply_action(pid(g, 3), "play_card", {"card": card(7, Suit.SPADE).to_dict()})
    g.apply_action(pid(g, 0), "play_card", {"card": card(8, Suit.CLUB).to_dict()})
    assert g.last_trick_winner_seat == 2            # 9♠ is the highest trump


def test_exposing_player_must_play_trump_if_holding_one():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    set_hand(g, 1, [card(13, Suit.HEART)])          # leads K♥
    set_hand(g, 2, [card(8, Suit.CLUB)])            # void, discards
    # Seat 3 is void in ♥, holds a trump alongside junk -> reveals and must
    # then play trump; the club is forbidden.
    set_hand(g, 3, [card(9, Suit.SPADE), card(8, Suit.CLUB)])
    set_hand(g, 0, [card(10, Suit.HEART)])
    g.apply_action(pid(g, 1), "play_card", {"card": card(13, Suit.HEART).to_dict()})
    g.apply_action(pid(g, 2), "play_card", {"card": card(8, Suit.CLUB).to_dict()})
    g.apply_action(pid(g, 3), "expose_trump")
    legal3 = {c.label for c in g.legal_cards(pid(g, 3))}
    assert legal3 == {"9S"}                         # must trump if able
    g.apply_action(pid(g, 3), "play_card", {"card": card(9, Suit.SPADE).to_dict()})
    g.apply_action(pid(g, 0), "play_card", {"card": card(10, Suit.HEART).to_dict()})
    assert g.last_trick_winner_seat == 3


def test_post_exposure_highest_trump_wins_else_led_suit():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "C"})
    g.trump_exposed = True
    set_hand(g, 1, [card(10, Suit.HEART)])
    set_hand(g, 2, [card(14, Suit.DIAMOND)])        # A♦ void discard (no trump)
    set_hand(g, 3, [card(7, Suit.HEART)])           # follows low
    set_hand(g, 0, [card(12, Suit.HEART)])          # Q♥ (10 beats Q in 28 ranking)
    g.apply_action(pid(g, 1), "play_card", {"card": card(10, Suit.HEART).to_dict()})
    g.apply_action(pid(g, 2), "play_card", {"card": card(14, Suit.DIAMOND).to_dict()})
    g.apply_action(pid(g, 3), "play_card", {"card": card(7, Suit.HEART).to_dict()})
    g.apply_action(pid(g, 0), "play_card", {"card": card(12, Suit.HEART).to_dict()})
    assert g.last_trick_winner_seat == 1


# --- redaction -----------------------------------------------------------
def test_trump_hidden_from_everyone_except_bidder_until_exposed():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "H"})
    state_bidder = g.to_state("p1")
    state_other = g.to_state("p2")
    assert state_bidder["trump"] == "H"
    assert state_other["trump"] is None

    g.trump_exposed = True
    assert g.to_state("p2")["trump"] == "H"
    assert g.to_state(None)["trump"] == "H"


def test_hand_visible_only_to_owner():
    g = new_game()
    for i, s in enumerate(g.to_state("p1")["players"]):
        assert (s["hand"] is not None) == (s["id"] == "p1")


# --- scoring ---------------------------------------------------------------
def test_bid_made_scoring_one_point_to_partnership():
    g = new_game()
    run_simple_auction(g, bid=20)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    g.captured = [4, 21]                            # seat-1 team is team 1
    g._end_deal()
    assert g.players[1].total_score == 1
    assert g.players[3].total_score == 1
    assert g.players[0].total_score == 0
    assert g.phase == Phase.ROUND_END
    entry = g.round_history[-1]
    assert entry["high_bid"] == 20 and entry["captured_points"] == 21
    assert entry["bid_made"] is True


def test_bid_failed_costs_one_point():
    g = new_game()
    run_simple_auction(g, bid=24)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    g.captured = [0, 23]
    g._end_deal()
    assert g.players[1].total_score == -1
    assert g.players[3].total_score == -1
    assert g.players[0].total_score == 0
    entry = g.round_history[-1]
    assert entry["bid_made"] is False


def test_team_scores_are_reported_per_partnership():
    g = new_game()
    run_simple_auction(g, bid=20)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    g.captured = [4, 21]                            # team 1 (seats 1 & 3) made it
    g._end_deal()
    assert g.to_state("p0")["team_scores"] == {"0": 0, "1": 1}
    assert g.to_state("p3")["team_scores"] == {"0": 0, "1": 1}


def test_team_captured_points_exposed_in_state():
    g = new_game()
    run_simple_auction(g)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    g.captured = [5, 9]
    state = g.to_state("p2")
    assert state["team_captured"] == {"0": 5, "1": 9}
    # Same value for both members of a team (p1 and p3 are partners).
    assert g.to_state("p1")["team_captured"] == g.to_state("p3")["team_captured"]


def test_match_ends_after_configured_deals_with_standings():
    g = new_game(deals=5)
    bot_brain = TwentyEightBotBrain()
    rng = random.Random(7)
    played = 0
    while g.phase != Phase.GAME_END and played < 500:
        if g.phase == Phase.ROUND_END:
            g.advance_round()
        elif g.awaiting_trick_clear:
            g.commit_trick()
        else:
            seat = g.turn_idx
            action, params = bot_brain.decide_action(g, pid(g, seat), rng)
            g.apply_action(pid(g, seat), action, params)
        played += 1
    assert g.phase == Phase.GAME_END, f"stuck after {played} steps"
    assert len(g.round_history) == 5
    standings = g.final_standings()
    assert len(standings) == 4
    total = sum(s["total_score"] for s in standings)
    # Each deal moves exactly one partnership: both partners get the same ±1.
    assert abs(total) <= 2 * 5
    assert total % 2 == 0


def test_deal_ends_early_when_bid_becomes_impossible():
    g = new_game()
    run_simple_auction(g, bid=20)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    g.captured = [9, 4]                     # opposition (team 0) has 9 > 28-20
    # Simulate a trick commit (empty hands prove the early end, not a normal one).
    g.current_trick = [{"seat": 0, "card": card(8)}]
    g.led_suit = Suit.SPADE
    g.awaiting_trick_clear = True
    g.last_trick_winner_seat = 0
    g.commit_trick()
    assert g.phase == Phase.ROUND_END
    assert len(g.round_history) == 1
    assert g.round_history[-1]["bid_made"] is False
    assert any(len(p.hand) > 0 for p in g.players)   # cards were left unplayed


def test_deal_continues_at_exact_boundary():
    g = new_game()
    run_simple_auction(g, bid=20)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    g.captured = [8, 4]                     # 8 == 28-20: bid still reachable
    g.current_trick = [{"seat": 0, "card": card(8)}]
    g.led_suit = Suit.SPADE
    g.awaiting_trick_clear = True
    g.last_trick_winner_seat = 0
    g.commit_trick()
    assert g.phase == Phase.PLAYING         # not decided yet
    assert g.round_history == []


def test_bid_made_early_does_not_end_deal():
    g = new_game()
    run_simple_auction(g, bid=14)
    g.apply_action(pid(g, 1), "set_trump", {"suit": "S"})
    g.captured = [2, 14]                    # bidder team already >= 14
    g.current_trick = [{"seat": 1, "card": card(11)}]
    g.led_suit = Suit.SPADE
    g.awaiting_trick_clear = True
    g.last_trick_winner_seat = 1
    g.commit_trick()
    assert g.phase == Phase.PLAYING         # plays out per request scope
    assert g.round_history == []


def test_registry_entry_exists():
    spec = GAME_REGISTRY.get("twentyeight")
    assert spec is not None
    assert spec.min_players == 4 and spec.max_players == 4
    assert [str(n) for n in spec.options_schema["deals"]["values"]] == ["5", "10", "20"]
