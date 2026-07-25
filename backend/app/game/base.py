"""Generic shared types and contracts for all card games on TaashClub.

Game-specific rules (trump cycling, bidding, scoring) live in per-game
packages under ``game/<name>/``. This module holds only the generic data
structures (Card, Player, Suit, Phase) and the ``BaseGame`` / ``BotBrain``
protocols that every game engine implements.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol, runtime_checkable


class GameError(Exception):
    """Raised on an illegal action; the caller surfaces the message to a client."""


class Suit(str, Enum):
    SPADE = "S"
    HEART = "H"
    CLUB = "C"
    DIAMOND = "D"


# Hand display order: suits grouped Spade, Heart, Club, Diamond; ranks high -> low.
SUIT_DISPLAY_ORDER = {Suit.SPADE: 0, Suit.HEART: 1, Suit.CLUB: 2, Suit.DIAMOND: 3}


def hand_sort_key(card: "Card") -> tuple[int, int]:
    """Sort a hand as Spade->Heart->Club->Diamond, each suit descending by rank."""
    return (SUIT_DISPLAY_ORDER[card.suit], -card.rank)


# Rank integer -> display label for the face cards.
RANK_LABELS = {11: "J", 12: "Q", 13: "K", 14: "A"}
MIN_RANK = 2
MAX_RANK = 14


class Phase(str, Enum):
    LOBBY = "lobby"
    BIDDING = "bidding"
    PLAYING = "playing"
    EXCHANGE = "exchange"        # between-round card swap (President etc.)
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
    bid: Optional[int] = None    # game-specific; None until set this round
    tricks_won: int = 0          # game-specific running count this round
    total_score: int = 0         # cumulative across rounds
    connected: bool = True
    is_bot: bool = False         # server-driven AI seat (no socket)


def build_deck() -> list[Card]:
    """Standard 52-card deck."""
    return [Card(suit, rank) for suit in Suit for rank in range(MIN_RANK, MAX_RANK + 1)]


@runtime_checkable
class BaseGame(Protocol):
    """Contract every game engine implements.

    The server's room/socket/bot driver (``main.py``) talks to engines only
    through this interface, so new games plug in without touching infra.
    """

    game_type: str
    phase: Phase
    turn_idx: int
    players: list[Player]
    awaiting_trick_clear: bool
    round_history: list[dict]

    def start(self) -> None: ...
    def apply_action(self, player_id: str, action: str, params: dict) -> None: ...
    def legal_actions(self, player_id: str) -> list[dict]: ...
    def commit_trick(self) -> None: ...
    def advance_round(self) -> None: ...
    def force_end(self) -> None: ...
    def final_standings(self) -> list[dict]: ...
    def to_state(self, viewer_id: Optional[str] = None) -> dict: ...


@runtime_checkable
class BotBrain(Protocol):
    """Decides a bot's next action as an (action, params) envelope.

    The brain inspects the game state to decide *what kind* of action is needed
    (bid vs play vs advance), so the generic driver in ``main.py`` never branches
    on game-specific phases.
    """

    def decide_action(
        self, game: BaseGame, player_id: str, rng: random.Random
    ) -> tuple[str, dict]: ...
