"""Core data models for the LAKDI game engine.

These are pure data structures with no networking concerns. Cards use an
integer rank (2-14, where 11=J, 12=Q, 13=K, 14=A) so ranks compare naturally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Suit(str, Enum):
    SPADE = "S"
    HEART = "H"
    CLUB = "C"
    DIAMOND = "D"


# Trump follows this fixed cycle by absolute round index (rule #5).
TRUMP_CYCLE = [Suit.SPADE, Suit.HEART, Suit.CLUB, Suit.DIAMOND]

# Hand display order: suits grouped Spade, Heart, Club, Diamond; ranks high -> low.
SUIT_DISPLAY_ORDER = {Suit.SPADE: 0, Suit.HEART: 1, Suit.CLUB: 2, Suit.DIAMOND: 3}


def hand_sort_key(card: "Card") -> tuple[int, int]:
    """Sort a hand as Spade->Heart->Club->Diamond, each suit descending by rank."""
    return (SUIT_DISPLAY_ORDER[card.suit], -card.rank)

# Rank integer -> display label for the face cards.
RANK_LABELS = {11: "J", 12: "Q", 13: "K", 14: "A"}
MIN_RANK = 2
MAX_RANK = 14


class Variant(str, Enum):
    SINGLE_RUN = "single_run"      # starting_cards -> 1
    DOWN_AND_UP = "down_and_up"    # starting_cards -> 1 -> 1 -> starting_cards


class Phase(str, Enum):
    LOBBY = "lobby"
    BIDDING = "bidding"
    PLAYING = "playing"
    ROUND_END = "round_end"
    GAME_END = "game_end"


@dataclass(frozen=True)
class Card:
    suit: Suit
    rank: int  # 2-14

    @property
    def label(self) -> str:
        return f"{RANK_LABELS.get(self.rank, str(self.rank))}{self.suit.value}"

    def to_dict(self) -> dict:
        return {"suit": self.suit.value, "rank": self.rank}

    @staticmethod
    def from_dict(d: dict) -> "Card":
        return Card(suit=Suit(d["suit"]), rank=int(d["rank"]))


@dataclass
class Player:
    id: str
    name: str
    join_order: int              # 0-based seat order, fixed for the game
    hand: list[Card] = field(default_factory=list)
    bid: Optional[int] = None    # None until announced this round
    tricks_won: int = 0          # tricks won this round
    total_score: int = 0         # cumulative across rounds
    connected: bool = True
    is_bot: bool = False         # server-driven AI seat (no socket)


def build_deck() -> list[Card]:
    """Standard 52-card deck."""
    return [Card(suit, rank) for suit in Suit for rank in range(MIN_RANK, MAX_RANK + 1)]
