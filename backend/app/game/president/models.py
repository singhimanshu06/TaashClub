"""President (a.k.a. Asshole) — game-specific constants and helpers.

Ranking for normal combos: 3 < 4 < ... < K < A (Ace high). The 2 is a bomb-only
special card that resets the pile; it is never a legal *follow* of another combo.

For the between-round card exchange, "best" means highest by rank where the
bomb-only 2 ranks above the Ace: 2 > A > K > ... > 3.
"""
from __future__ import annotations

from enum import Enum
from ..base import Card, Suit, build_deck

GAME_TYPE = "president"

NUM_PLAYERS = 5
CARDS_PER_PLAYER = 10  # 50-card deck / 5 players

# Host-pickable round counts for a match.
ROUND_COUNTS = [5, 10, 15]
DEFAULT_ROUND_COUNT = 10

# Per-rank score awarded at the end of each round (cumulative across rounds).
SCORES = {
    0: 5,    # President (finished 1st)
    1: 3,    # Vice-President (2nd)
    2: 1,    # Neutral (3rd)
    3: 0,    # Vice-Asshole (4th) — gives 1 card
    4: -2,   # Asshole (5th, last)  — gives 2 cards
}

ROLE_LABELS = {
    0: "President",
    1: "Vice-President",
    2: "Neutral",
    3: "Vice-Asshole",
    4: "Asshole",
}

# Cards the loser must surrender: (finish_index -> count to give away).
EXCHANGE_GIVE = {4: 2, 3: 1}   # Asshole gives 2, Vice-Asshole gives 1


class RoundCount(str, Enum):
    FIVE = "5"
    TEN = "10"
    FIFTEEN = "15"


def build_president_deck(rng) -> list[Card]:
    """Standard 52-card deck minus two randomly-chosen 2s -> 50 cards."""
    deck = build_deck()
    twos = [c for c in deck if c.rank == 2]
    # Remove two of the four 2s at random (suit is irrelevant in President).
    for c in rng.sample(twos, 2):
        deck.remove(c)
    return deck


def exchange_rank(card: Card) -> int:
    """Sort key for the exchange: 2 > A > K > ... > 3 (higher = better)."""
    return card.rank if card.rank != 2 else 15


# Suit tiebreaker so same-rank cards group consistently across renders.
_SUIT_TIE = {Suit.SPADE: 0, Suit.HEART: 1, Suit.CLUB: 2, Suit.DIAMOND: 3}


def president_sort_key(card: Card) -> tuple[int, int]:
    """Display order: 2 -> A -> K -> ... -> 3, with a cosmetic suit tiebreaker.

    An *ascending* sort by this key yields value-descending display order (2
    first, 3 last). The 2 ranks above the Ace (15 vs 14); all other ranks use
    their natural integer value. Suit only breaks ties between same-rank cards.
    """
    return (-(card.rank if card.rank != 2 else 15), _SUIT_TIE[card.suit])


def combo_rank(card: Card) -> int:
    """Sort key for normal-combo comparison: 3 < 4 < ... < K < A (Ace high)."""
    return card.rank
