"""Twenty-Eight — game-specific constants and helpers.

Played with a 32-card deck (7, 8, 9, 10, J, Q, K, A). Card strength for
trick-taking is NOT the natural rank order: J > 9 > A > 10 > K > Q > 8 > 7.
Point values captured in tricks: J=3, 9=2, A=1, 10=1; K/Q/8/7 = 0.

Bids run from MIN_BID=14 to MAX_BID=28 and are made on the first 4 cards of
each hand; the remaining 4 are dealt once the winning bidder names trump.
Simple scoring: +1 per deal if the bidding partnership captures at least
their bid, else -1.
"""
from __future__ import annotations

from ..base import Card, Suit, build_deck

GAME_TYPE = "twentyeight"

NUM_PLAYERS = 4
CARDS_PER_PLAYER = 8           # 32-card deck / 4 players
FIRST_DEAL_COUNT = 4           # dealt before bidding; rest after trump is named
MIN_RANK = 7                   # only 7 .. Ace are used
MIN_BID = 14
MAX_BID = 28
# Overcalling your own partner's standing bid requires at least this value.
PARTNER_OVERCALL_MIN = 20
# Total card points available in a deal (J=3 x4 + 9=2 x4 + A=1 x4 + 10=1 x4).
TOTAL_CARD_POINTS = 28

# Match length options set when creating a room.
DEAL_COUNTS = [5, 10, 20]
DEFAULT_DEAL_COUNT = 10

# Card points captured in tricks.
POINT_VALUES = {11: 3, 9: 2, 14: 1, 10: 1}   # J=3, 9=2, A=1, 10=1; rest 0

# Strength ordering for trick comparison: higher beats lower.
# J > 9 > A > 10 > K > Q > 8 > 7
STRENGTH = {11: 8, 9: 7, 14: 6, 10: 5, 13: 4, 12: 3, 8: 2, 7: 1}


def build_28_deck() -> list[Card]:
    """32-card Twenty-Eight deck: ranks 7 through Ace in every suit."""
    return [Card(suit, rank) for suit in Suit for rank in range(MIN_RANK, 15)]


def card_points(card: Card) -> int:
    """Point value the card contributes to the capturing team."""
    return POINT_VALUES.get(card.rank, 0)


def card_strength(card: Card) -> int:
    """Compare key for trick resolution (J > 9 > A > 10 > K > Q > 8 > 7)."""
    return STRENGTH[card.rank]


def hand_value(hand: list[Card]) -> int:
    """Heuristic: total point value of a hand's honour cards."""
    return sum(card_points(c) for c in hand)
