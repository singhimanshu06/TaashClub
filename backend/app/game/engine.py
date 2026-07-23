"""Pure LAKDI game engine — server-authoritative rules, no networking.

A single ``Game`` instance owns the full state for one room's match. All rule
enforcement (dealing, bidding limits, follow-suit legality, trick resolution,
scoring, round/game progression) lives here so it can be unit-tested in
isolation.
"""
from __future__ import annotations

import random
from typing import Optional

from .models import (
    Card,
    Phase,
    Player,
    Suit,
    TRUMP_CYCLE,
    Variant,
    build_deck,
    hand_sort_key,
)

DECK_SIZE = 52


class GameError(Exception):
    """Raised on an illegal action; the caller surfaces the message to a client."""


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


class Game:
    def __init__(
        self,
        num_players: int,
        variant: Variant,
        players: list[Player],
        rng: Optional[random.Random] = None,
    ):
        if num_players not in (4, 5, 6):
            raise GameError("num_players must be 4, 5, or 6")
        if len(players) != num_players:
            raise GameError("player count does not match num_players")

        self.num_players = num_players
        self.variant = variant
        self.players = sorted(players, key=lambda p: p.join_order)
        self.rng = rng or random.Random()

        self.starting_cards = DECK_SIZE // num_players     # 13 / 10 / 8
        self.round_schedule = build_round_schedule(self.starting_cards, variant)

        self.round_index = -1                              # incremented by start_round()
        self.phase = Phase.LOBBY
        self.trump: Optional[Suit] = None
        self.starter_idx = 0                               # seat that bids/leads first
        self.turn_idx = 0                                  # whose turn right now
        self.current_trick: list[dict] = []                # [{"seat": i, "card": Card}]
        self.led_suit: Optional[Suit] = None
        # When the last card of a trick is played, the trick is kept on the table
        # (awaiting_trick_clear=True) until commit_trick() is called — this lets
        # the UI show the completed trick for a few seconds before it clears.
        self.awaiting_trick_clear = False
        self.last_trick_winner_seat: Optional[int] = None
        self.last_round_result: Optional[list[dict]] = None
        # Per-round result history accumulated as each round ends. Used by the
        # end-of-game detailed-scores view. Each entry:
        # {"round_index", "trump", "cards_this_round", "results": [...]}
        self.round_history: list[dict] = []

    # ----- lookups -------------------------------------------------------
    @property
    def cards_this_round(self) -> int:
        return self.round_schedule[self.round_index]

    @property
    def total_rounds(self) -> int:
        return len(self.round_schedule)

    def _player_by_id(self, player_id: str) -> Player:
        for p in self.players:
            if p.id == player_id:
                return p
        raise GameError("unknown player")

    def _seat_of(self, player_id: str) -> int:
        return self._player_by_id(player_id).join_order

    # ----- lifecycle -----------------------------------------------------
    def start(self) -> None:
        """Begin the match from the lobby."""
        if self.phase != Phase.LOBBY:
            raise GameError("game already started")
        self._start_round()

    def _start_round(self) -> None:
        self.round_index += 1
        n = self.cards_this_round

        # Fresh shuffle every round; only n * num_players cards are dealt.
        deck = build_deck()
        self.rng.shuffle(deck)
        for seat, player in enumerate(self.players):
            player.hand = sorted(deck[seat * n:(seat + 1) * n], key=hand_sort_key)
            player.bid = None
            player.tricks_won = 0

        self.trump = TRUMP_CYCLE[self.round_index % 4]
        self.starter_idx = self.round_index % self.num_players
        self.turn_idx = self.starter_idx
        self.current_trick = []
        self.led_suit = None
        self.awaiting_trick_clear = False
        self.last_trick_winner_seat = None
        self.phase = Phase.BIDDING

    # ----- bidding -------------------------------------------------------
    def place_bid(self, player_id: str, value: int) -> None:
        if self.phase != Phase.BIDDING:
            raise GameError("not in bidding phase")
        seat = self._seat_of(player_id)
        if seat != self.turn_idx:
            raise GameError("not your turn to bid")
        if not isinstance(value, int) or value < 0 or value > self.cards_this_round:
            raise GameError(f"bid must be between 0 and {self.cards_this_round}")

        self.players[seat].bid = value

        if all(p.bid is not None for p in self.players):
            # Everyone has bid -> start play from the round starter.
            self.phase = Phase.PLAYING
            self.turn_idx = self.starter_idx
            self.led_suit = None
        else:
            self.turn_idx = (self.turn_idx + 1) % self.num_players

    # ----- playing -------------------------------------------------------
    def legal_cards(self, player_id: str) -> list[Card]:
        """Follow-suit only: must follow led suit if held, else any card."""
        player = self._player_by_id(player_id)
        if self.led_suit is None:
            return list(player.hand)
        same = [c for c in player.hand if c.suit == self.led_suit]
        return same if same else list(player.hand)

    def play_card(self, player_id: str, card: Card) -> None:
        if self.phase != Phase.PLAYING:
            raise GameError("not in playing phase")
        if self.awaiting_trick_clear:
            raise GameError("previous trick is still resolving")
        seat = self._seat_of(player_id)
        if seat != self.turn_idx:
            raise GameError("not your turn to play")
        player = self.players[seat]
        if card not in player.hand:
            raise GameError("card not in hand")
        if card not in self.legal_cards(player_id):
            raise GameError("must follow the led suit")

        player.hand.remove(card)
        if not self.current_trick:
            self.led_suit = card.suit
        self.current_trick.append({"seat": seat, "card": card})

        if len(self.current_trick) == self.num_players:
            # Trick is full: decide the winner but leave the cards on the table.
            # commit_trick() (called after the hold) clears it and advances play.
            self.last_trick_winner_seat = self._trick_winner(
                self.current_trick, self.led_suit, self.trump
            )
            self.awaiting_trick_clear = True
        else:
            self.turn_idx = (self.turn_idx + 1) % self.num_players

    def commit_trick(self) -> None:
        """Clear a completed trick, award it, and advance (or end the round)."""
        if not self.awaiting_trick_clear:
            return
        winner_seat = self.last_trick_winner_seat
        self.players[winner_seat].tricks_won += 1
        self.current_trick = []
        self.led_suit = None
        self.turn_idx = winner_seat  # winner leads the next trick
        self.awaiting_trick_clear = False
        self.last_trick_winner_seat = None

        if not self.players[0].hand:  # all hands empty -> round over
            self._end_round()

    @staticmethod
    def _trick_winner(trick: list[dict], led_suit: Suit, trump: Suit) -> int:
        trumps = [e for e in trick if e["card"].suit == trump]
        pool = trumps if trumps else [e for e in trick if e["card"].suit == led_suit]
        best = max(pool, key=lambda e: e["card"].rank)
        return best["seat"]

    def _end_round(self) -> None:
        result = []
        for p in self.players:
            hit = p.tricks_won == p.bid
            points = (10 + p.bid) if hit else 0
            p.total_score += points
            result.append(
                {
                    "player_id": p.id,
                    "name": p.name,
                    "bid": p.bid,
                    "tricks_won": p.tricks_won,
                    "points": points,
                    "hit": hit,
                }
            )
        self.last_round_result = result
        # Accumulate a per-round snapshot (with the trump and cards dealt) for
        # the end-of-game detailed-scores view. `to_state` exposes this list.
        self.round_history.append(
            {
                "round_index": self.round_index,
                "trump": self.trump.value if self.trump else None,
                "cards_this_round": self.cards_this_round,
                "results": result,
            }
        )

        if self.round_index + 1 >= self.total_rounds:
            self.phase = Phase.GAME_END
        else:
            self.phase = Phase.ROUND_END

    def advance_round(self) -> None:
        """Move from ROUND_END into the next round's bidding."""
        if self.phase != Phase.ROUND_END:
            raise GameError("no round to advance")
        self._start_round()

    def force_end(self) -> None:
        """End the game immediately (e.g. all humans left).

        Abandons the current round — its points are not scored into totals. The
        final standings reflect only completed rounds. Clears any in-progress
        trick so the state is clean for GAME_END serialization.
        """
        self.awaiting_trick_clear = False
        self.current_trick = []
        self.led_suit = None
        self.last_trick_winner_seat = None
        self.phase = Phase.GAME_END

    # ----- serialization -------------------------------------------------
    def final_standings(self) -> list[dict]:
        ranked = sorted(self.players, key=lambda p: p.total_score, reverse=True)
        return [
            {"player_id": p.id, "name": p.name, "total_score": p.total_score, "rank": i + 1}
            for i, p in enumerate(ranked)
        ]

    def to_state(self, viewer_id: Optional[str] = None) -> dict:
        """Redacted view: only ``viewer_id`` sees their own hand."""
        # During the post-trick hold nobody is on turn — the completed trick
        # just sits on the table until commit_trick() runs.
        current_player_id = (
            self.players[self.turn_idx].id
            if self.phase in (Phase.BIDDING, Phase.PLAYING) and not self.awaiting_trick_clear
            else None
        )
        trick_winner_id = (
            self.players[self.last_trick_winner_seat].id
            if self.awaiting_trick_clear and self.last_trick_winner_seat is not None
            else None
        )
        return {
            "phase": self.phase.value,
            "num_players": self.num_players,
            "variant": self.variant.value,
            "round_index": self.round_index,
            "total_rounds": self.total_rounds,
            "cards_this_round": self.cards_this_round if self.round_index >= 0 else None,
            "trump": self.trump.value if self.trump else None,
            "starter_id": self.players[self.starter_idx].id if self.round_index >= 0 else None,
            "current_player_id": current_player_id,
            "awaiting_trick_clear": self.awaiting_trick_clear,
            "trick_winner_id": trick_winner_id,
            "led_suit": self.led_suit.value if self.led_suit else None,
            "current_trick": [
                {"player_id": self.players[e["seat"]].id, "card": e["card"].to_dict()}
                for e in self.current_trick
            ],
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "seat": p.join_order,
                    "bid": p.bid,
                    "tricks_won": p.tricks_won,
                    "hand_count": len(p.hand),
                    "hand": [c.to_dict() for c in p.hand] if p.id == viewer_id else None,
                    "connected": p.connected,
                    "is_bot": p.is_bot,
                    # Cumulative total through all completed rounds. During the
                    # active round this reflects "up to the previous round"; the
                    # current round's points are added only when it ends. Used by
                    # the in-game scorecard toggle.
                    "total_score": p.total_score,
                }
                for p in self.players
            ],
            "your_legal_cards": (
                [c.to_dict() for c in self.legal_cards(viewer_id)]
                if viewer_id and self.phase == Phase.PLAYING and current_player_id == viewer_id
                else None
            ),
            "last_round_result": self.last_round_result,
            "round_history": self.round_history,
            "final_standings": self.final_standings() if self.phase == Phase.GAME_END else None,
        }
