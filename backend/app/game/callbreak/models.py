"""Callbreak-specific data models.

These are the rules that distinguish Callbreak from other trick-taking games:
the trump cycle, the hand-size variants, and the decreasing-cards round
schedule. Generic deck/player types live in ``app.game.base``.
"""
from __future__ import annotations

from enum import Enum

from ..base import Suit

# Trump follows this fixed cycle by absolute round index (Callbreak rule #5).
TRUMP_CYCLE = [Suit.SPADE, Suit.HEART, Suit.CLUB, Suit.DIAMOND]


class Variant(str, Enum):
    SINGLE_RUN = "single_run"      # starting_cards -> 1
    DOWN_AND_UP = "down_and_up"    # starting_cards -> 1 -> 1 -> starting_cards


def build_round_schedule(starting_cards: int, variant: Variant) -> list[int]:
    """Cards-per-round schedule for the whole match.

    SINGLE_RUN:  starting_cards -> 1
    DOWN_AND_UP: starting_cards -> 1, then 1 -> starting_cards (the 1-card
                 round is played twice back-to-back at the turn).
    """
    down = list(range(starting_cards, 0, -1))            # [s, ..., 1]
    if variant == Variant.SINGLE_RUN:
        return down
    up = list(range(1, starting_cards + 1))              # [1, ..., s]
    return down + up
