"""Pure Twenty-Eight game engine — server-authoritative rules, no networking.

Implements the ``BaseGame`` protocol from ``app.game.base``. A single ``Game``
instance owns the full state for one room's match over ``total_rounds`` deals.

Rules implemented (original version):

- 4 players, partnerships fixed by seating (seats 0/2 vs 1/3).
- 32-card deck (7..A), ranking J > 9 > A > 10 > K > Q > 8 > 7.
- Bidding 14..28 starting right after the dealer (clockwise); the opener must
  bid and cannot pass; passing locks a player out; overcalling your own
  partner's standing bid requires >= 20; three consecutive passes (equivalently,
  everyone else having passed) ends the auction.
- The winning bidder names the trump suit secretly (server-side state). Nobody
  else learns it until it is exposed. Play does not begin until trump is named.
- While trump is hidden it behaves as an ordinary suit for everyone (including
  the bidder, who may lead it): highest card of the led suit wins.
- Exposure: any player who is on turn, void in the led suit (the bidder
  included) may expose trump via ``expose_trump``. From that moment trumps
  behave normally for the REST of the deal — cards of the trump suit played
  BEFORE the exposure in the current trick stay ordinary cards. The exposing
  player must play a trump on that trick if they hold one.
- Post-exposure follow rules: follow suit if able; if void you may play
  anything, but must overtrump a trump played after the exposure by the
  immediately preceding player if possible.
- Highest trump wins the trick (post-exposure cards only), else the highest
  card of the led suit.
- A deal ends early (at trick commit) once the opposition has captured more
  than ``TOTAL_CARD_POINTS - bid`` points: the bidder's partnership can no
  longer reach the bid, so the result is decided.
- Scoring is per partnership (opposite seats): bidder's team must capture card
  points >= their bid: +1 to both partners if made, -1 if not. Most game
  points after ``total_rounds`` deals wins (ties possible and declared).
"""
from __future__ import annotations

import random
from typing import Optional

from ..base import (
    Card,
    GameError,
    Phase,
    Player,
    Suit,
    hand_sort_key,
)
from .models import (
    CARDS_PER_PLAYER,
    DEFAULT_DEAL_COUNT,
    DEAL_COUNTS,
    GAME_TYPE,
    MAX_BID,
    MIN_BID,
    NUM_PLAYERS,
    PARTNER_OVERCALL_MIN,
    TOTAL_CARD_POINTS,
    build_28_deck,
    card_points,
    card_strength,
)


class Game:
    def __init__(
        self,
        num_players: int,
        options: dict,
        players: list[Player],
        rng: Optional[random.Random] = None,
    ):
        if num_players != NUM_PLAYERS:
            raise GameError(f"Twenty-Eight requires exactly {NUM_PLAYERS} players")
        if len(players) != num_players:
            raise GameError("player count does not match num_players")

        self.game_type = GAME_TYPE
        self.num_players = NUM_PLAYERS
        deals = options.get("deals")
        self.total_rounds = (
            int(deals) if deals is not None and int(deals) in DEAL_COUNTS else DEFAULT_DEAL_COUNT
        )
        self.players = sorted(players, key=lambda p: p.join_order)
        self.rng = rng or random.Random()

        self.round_index = -1                          # incremented by _start_deal()
        self.phase = Phase.LOBBY
        self.turn_idx = 0

        # Auction state (this deal).
        self.dealer_idx = 0
        self.high_bid: Optional[int] = None
        self.bidder_seat: Optional[int] = None
        self.passed_seats: set[int] = set()
        self.awaiting_trump = False                    # auction over, trump not named yet

        # Trump state (this deal). ``trump`` is hidden server-side until
        # exposed (redacted in to_state for viewers other than the bidder).
        self.trump: Optional[Suit] = None
        self.trump_exposed = False
        # Position in the CURRENT trick where exposure happened; trump-suit
        # cards played before it stay ordinary. None = no exposure in the
        # current trick (either not exposed at all, or exposure was in an
        # earlier trick — then all cards count).
        self.expose_idx: Optional[int] = None

        # Trick state.
        self.current_trick: list[dict] = []            # [{"seat": i, "card": Card}]
        self.led_suit: Optional[Suit] = None
        self.awaiting_trick_clear = False
        self.last_trick_winner_seat: Optional[int] = None
        self.captured = [0, 0]                         # card points per team this deal

        self.last_round_result: Optional[list[dict]] = None
        self.round_history: list[dict] = []

    # ----- lookups -------------------------------------------------------
    def _player_by_id(self, player_id: str) -> Player:
        for p in self.players:
            if p.id == player_id:
                return p
        raise GameError("unknown player")

    def _seat_of(self, player_id: str) -> int:
        return self._player_by_id(player_id).join_order

    @staticmethod
    def team_of(seat: int) -> int:
        """Partnership id: opposite seats share a team (0/2 and 1/3)."""
        return seat % 2

    # ----- lifecycle -----------------------------------------------------
    def start(self) -> None:
        if self.phase != Phase.LOBBY:
            raise GameError("game already started")
        self._start_deal()

    def _start_deal(self) -> None:
        self.round_index += 1
        deck = build_28_deck()
        self.rng.shuffle(deck)
        n = CARDS_PER_PLAYER
        for seat, player in enumerate(self.players):
            player.hand = sorted(deck[seat * n:(seat + 1) * n], key=hand_sort_key)
            player.bid = None
            player.tricks_won = 0

        self.dealer_idx = self.round_index % self.num_players
        self.high_bid = None
        self.bidder_seat = None
        self.passed_seats = set()
        self.awaiting_trump = False
        self.trump = None
        self.trump_exposed = False
        self.expose_idx = None
        self.current_trick = []
        self.led_suit = None
        self.awaiting_trick_clear = False
        self.last_trick_winner_seat = None
        self.captured = [0, 0]
        self.turn_idx = (self.dealer_idx + 1) % self.num_players
        self.phase = Phase.BIDDING

    # ----- bidding -------------------------------------------------------
    def _min_raise_for(self, seat: int) -> int:
        """Minimum legal next bid for ``seat`` given the standing high bid."""
        if self.high_bid is None:
            return MIN_BID
        min_bid = self.high_bid + 1
        if self.team_of(seat) == self.team_of(self.bidder_seat):   # partner overcall
            min_bid = max(min_bid, PARTNER_OVERCALL_MIN)
        return min_bid

    def place_bid(self, player_id: str, value: int) -> None:
        if self.phase != Phase.BIDDING:
            raise GameError("not in bidding phase")
        if self.awaiting_trump:
            raise GameError("bidding is over — name the trump suit")
        seat = self._seat_of(player_id)
        if seat != self.turn_idx:
            raise GameError("not your turn to bid")
        if seat in self.passed_seats:
            raise GameError("you already passed")
        if not isinstance(value, int) or value < MIN_BID or value > MAX_BID:
            raise GameError(f"bid must be between {MIN_BID} and {MAX_BID}")
        min_raise = self._min_raise_for(seat)
        if value < min_raise:
            hint = f", minimum {min_raise}" if self.high_bid is not None else ""
            raise GameError(f"bid too low{hint}")

        self.high_bid = value
        self.bidder_seat = seat
        self.players[seat].bid = value
        self.passed_seats.discard(seat)

        if self._auction_over():
            self._finish_auction()
        else:
            self._advance_bidding_turn()

    def pass_bid(self, player_id: str) -> None:
        if self.phase != Phase.BIDDING:
            raise GameError("not in bidding phase")
        if self.awaiting_trump:
            raise GameError("bidding is over — name the trump suit")
        seat = self._seat_of(player_id)
        if seat != self.turn_idx:
            raise GameError("not your turn to bid")
        if seat in self.passed_seats:
            raise GameError("you already passed")
        if self.high_bid is None:
            raise GameError("the opening bid is mandatory")

        self.passed_seats.add(seat)
        if self._auction_over():
            self._finish_auction()
        else:
            self._advance_bidding_turn()

    def _auction_over(self) -> bool:
        """Done once at least one bid stands and everyone else has passed."""
        return (
            self.high_bid is not None
            and self.bidder_seat is not None
            and all(
                s in self.passed_seats
                for s in range(self.num_players)
                if s != self.bidder_seat
            )
        )

    def _advance_bidding_turn(self) -> None:
        idx = self.turn_idx
        for _ in range(self.num_players):
            idx = (idx + 1) % self.num_players
            if idx not in self.passed_seats:
                self.turn_idx = idx
                return
        self.turn_idx = (idx + 1) % self.num_players

    def _finish_auction(self) -> None:
        """Everyone else passed: the high bidder now names trump."""
        for seat in range(self.num_players):
            if self.team_of(seat) == self.team_of(self.bidder_seat):
                self.players[seat].bid = self.high_bid
            else:
                self.players[seat].bid = None
        self.awaiting_trump = True
        self.turn_idx = self.bidder_seat

    def set_trump(self, player_id: str, suit: Suit) -> None:
        if self.phase != Phase.BIDDING or not self.awaiting_trump:
            raise GameError("not waiting for trump")
        seat = self._seat_of(player_id)
        if seat != self.bidder_seat:
            raise GameError("only the winning bidder names trump")
        if not isinstance(suit, Suit):
            try:
                suit = Suit(suit)
            except ValueError:
                raise GameError("invalid suit") from None

        self.trump = suit
        self.awaiting_trump = False
        self.trump_exposed = False
        self.phase = Phase.PLAYING
        self.turn_idx = (self.dealer_idx + 1) % self.num_players
        self.led_suit = None

    # ----- playing -------------------------------------------------------
    def expose_trump(self, player_id: str) -> None:
        """        Reveal the hidden trump suit mid-deal.

        Legal only for the player currently on turn who cannot follow the led
        suit (the original rule's trigger). From the next card onward the
        revealed suit acts as trump for the rest of the deal; the caller must
        play a trump on the current trick if they hold one (enforced by
        legal_cards via the void check). Trump-suit cards already played to
        this trick stay ordinary cards.
        """
        if self.phase != Phase.PLAYING:
            raise GameError("not in playing phase")
        if self.awaiting_trick_clear:
            raise GameError("previous trick is still resolving")
        if self.trump is None or self.trump_exposed:
            raise GameError("trump is not hidden")
        seat = self._seat_of(player_id)
        if seat != self.turn_idx:
            raise GameError("not your turn")
        if self.led_suit is None:
            raise GameError("cannot reveal trump on a fresh lead")
        if any(c.suit == self.led_suit for c in self.players[seat].hand):
            raise GameError("you can still follow suit")

        self.trump_exposed = True
        self.expose_idx = len(self.current_trick)

    def legal_cards(self, player_id: str) -> list[Card]:
        """Cards the player may legally play right now (empty if not their turn state)."""
        player = self._player_by_id(player_id)
        hand = player.hand
        if self.led_suit is None:
            # Leading: while trump is hidden it is an ordinary suit for
            # everyone, so anything goes.
            return list(hand)

        # Following.
        same = [c for c in hand if c.suit == self.led_suit]
        if same:
            return same

        # Void in the led suit.
        if not self.trump_exposed:
            # Secret trump behaves like an ordinary suit — anything goes.
            return list(hand)

        # Post-exposure: must overtrump the immediately preceding trump if
        # able — but only when that trump was played AFTER the exposure
        # (pre-exposure cards stay ordinary for the whole trick).
        prev_idx = len(self.current_trick) - 1
        exposed_here = self.expose_idx is None or prev_idx >= self.expose_idx
        prev = self.current_trick[-1]["card"] if self.current_trick else None
        if exposed_here and prev is not None and self.trump is not None and prev.suit == self.trump:
            higher = [
                c
                for c in hand
                if c.suit == self.trump and card_strength(c) > card_strength(prev)
            ]
            if higher:
                return higher
        return list(hand)

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
            raise GameError("illegal card for this trick")

        player.hand.remove(card)
        if not self.current_trick:
            self.led_suit = card.suit
        self.current_trick.append({"seat": seat, "card": card})

        if len(self.current_trick) == self.num_players:
            self.last_trick_winner_seat = self._trick_winner()
            self.awaiting_trick_clear = True
        else:
            self.turn_idx = (self.turn_idx + 1) % self.num_players

    def commit_trick(self) -> None:
        """Clear a completed trick, award it, and advance (or end the deal)."""
        if not self.awaiting_trick_clear:
            return
        winner_seat = self.last_trick_winner_seat
        self.players[winner_seat].tricks_won += 1
        self.captured[self.team_of(winner_seat)] += sum(
            card_points(e["card"]) for e in self.current_trick
        )
        self.current_trick = []
        self.led_suit = None
        self.turn_idx = winner_seat  # winner leads the next trick
        self.awaiting_trick_clear = False
        self.last_trick_winner_seat = None
        self.expose_idx = None  # exposure now applies to every card

        if not self.players[0].hand:  # all hands empty -> deal over
            self._end_deal()
            return

        # Early decision: once the opposition holds more than
        # TOTAL_CARD_POINTS - bid points, the bidder's partnership cannot
        # reach the bid — no point playing the remaining tricks.
        if self.bidder_seat is not None and self.high_bid is not None:
            opposition = 1 - self.team_of(self.bidder_seat)
            if self.captured[opposition] > TOTAL_CARD_POINTS - self.high_bid:
                self._end_deal()

    def _trick_winner(self) -> int:
        trick = self.current_trick
        led = self.led_suit
        trump_pool = []
        if self.trump_exposed and self.trump is not None:
            first_trump_idx = self.expose_idx if self.expose_idx is not None else 0
            trump_pool = [
                e for i, e in enumerate(trick)
                if i >= first_trump_idx and e["card"].suit == self.trump
            ]
        if trump_pool:
            best = max(trump_pool, key=lambda e: card_strength(e["card"]))
        else:
            pool = [e for e in trick if e["card"].suit == led]
            best = max(pool, key=lambda e: card_strength(e["card"]))
        return best["seat"]

    # ----- scoring / rounds ---------------------------------------------
    def _end_deal(self) -> None:
        bidder_team = self.team_of(self.bidder_seat)
        target = self.high_bid
        got = self.captured[bidder_team]
        made = got >= target
        delta = 1 if made else -1

        result = []
        for p in self.players:
            same_team = self.team_of(p.join_order) == bidder_team
            points = delta if same_team else 0
            p.total_score += points
            result.append(
                {
                    "player_id": p.id,
                    "name": p.name,
                    "bid": target if same_team else None,
                    "tricks_won": p.tricks_won,
                    "points": points,
                    "hit": made,
                }
            )
        self.last_round_result = result
        self.round_history.append(
            {
                "round_index": self.round_index,
                "trump": self.trump.value if self.trump else None,
                "bidder_id": self.players[self.bidder_seat].id,
                "high_bid": target,
                "captured_points": got,
                "bid_made": made,
                "results": result,
            }
        )

        if self.round_index + 1 >= self.total_rounds:
            self.phase = Phase.GAME_END
        else:
            self.phase = Phase.ROUND_END

    def advance_round(self) -> None:
        if self.phase != Phase.ROUND_END:
            raise GameError("no round to advance")
        self._start_deal()

    def force_end(self) -> None:
        """End the game immediately (e.g. all humans left)."""
        self.awaiting_trick_clear = False
        self.current_trick = []
        self.led_suit = None
        self.last_trick_winner_seat = None
        self.phase = Phase.GAME_END

    # ----- generic action envelope (BaseGame) ---------------------------
    def apply_action(self, player_id: str, action: str, params: Optional[dict] = None) -> None:
        params = params or {}
        if action == "place_bid":
            self.place_bid(player_id, int(params["value"]))
        elif action == "pass":
            self.pass_bid(player_id)
        elif action == "set_trump":
            self.set_trump(player_id, params["suit"])
        elif action == "expose_trump":
            self.expose_trump(player_id)
        elif action == "play_card":
            self.play_card(player_id, Card.from_dict(params["card"]))
        elif action == "advance_round":
            self.advance_round()
        else:
            raise GameError(f"unknown action: {action}")

    def legal_actions(self, player_id: str) -> list[dict]:
        """All actions the player may legally take right now, as envelopes."""
        if self.phase not in (Phase.BIDDING, Phase.PLAYING):
            return []
        if self.awaiting_trick_clear:
            return []
        if self.players[self.turn_idx].id != player_id:
            return []

        if self.phase == Phase.BIDDING:
            if self.awaiting_trump:
                return [
                    {"action": "set_trump", "suit": s.value} for s in Suit
                ]
            seat = self._seat_of(player_id)
            actions = [
                {"action": "place_bid", "value": v}
                for v in range(max(MIN_BID, self._min_raise_for(seat)), MAX_BID + 1)
            ]
            if self.high_bid is not None:
                actions.append({"action": "pass"})
            return actions

        actions = [{"action": "play_card", "card": c.to_dict()} for c in self.legal_cards(player_id)]
        # Reveal option: on turn, mid-trick, not yet exposed, void in led suit.
        if (
            self.trump is not None
            and not self.trump_exposed
            and self.led_suit is not None
            and not any(c.suit == self.led_suit for c in self.players[self.turn_idx].hand)
        ):
            actions.append({"action": "expose_trump"})
        return actions

    # ----- serialization -------------------------------------------------
    def final_standings(self) -> list[dict]:
        ranked = sorted(self.players, key=lambda p: p.total_score, reverse=True)
        return [
            {"player_id": p.id, "name": p.name, "total_score": p.total_score, "rank": i + 1}
            for i, p in enumerate(ranked)
        ]

    def to_state(self, viewer_id: Optional[str] = None) -> dict:
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
        # Hidden trump redaction: the bidder always sees the suit; everyone
        # sees it once exposed (or once the deal has finished).
        deal_done = self.phase in (Phase.ROUND_END, Phase.GAME_END)
        viewer_is_bidder = (
            viewer_id is not None
            and self.bidder_seat is not None
            and self.players[self.bidder_seat].id == viewer_id
        )
        if self.trump is None or self.trump_exposed or deal_done or viewer_is_bidder:
            visible_trump = self.trump.value if self.trump else None
        else:
            visible_trump = None
        return {
            "game_type": self.game_type,
            "phase": self.phase.value,
            "num_players": self.num_players,
            "total_rounds": self.total_rounds,
            "round_index": self.round_index,
            "dealer_id": self.players[self.dealer_idx].id,
            "high_bid": self.high_bid,
            "bidder_id": self.players[self.bidder_seat].id if self.bidder_seat is not None else None,
            "awaiting_trump": self.awaiting_trump,
            "trump_exposed": self.trump_exposed,
            "trump": visible_trump,
            "starter_id": (
                self.players[(self.dealer_idx + 1) % self.num_players].id
                if self.round_index >= 0
                else None
            ),
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
                    "passed": p.join_order in self.passed_seats,
                    "total_score": p.total_score,
                }
                for p in self.players
            ],
            "teams": {
                p.id: str(self.team_of(p.join_order)) for p in self.players
            },
            "team_scores": {
                str(team): next(
                    p.total_score
                    for p in self.players
                    if self.team_of(p.join_order) == team
                )
                for team in (0, 1)
            },
            # Card points captured in tricks so far this deal, per partnership.
            "team_captured": {
                str(team): self.captured[team] for team in (0, 1)
            },
            "your_legal_cards": (
                [c.to_dict() for c in self.legal_cards(viewer_id)]
                if viewer_id and self.phase == Phase.PLAYING and current_player_id == viewer_id
                else None
            ),
            "your_legal_actions": (
                self.legal_actions(viewer_id) if viewer_id else None
            ),
            "last_round_result": self.last_round_result,
            "round_history": self.round_history,
            "final_standings": self.final_standings() if self.phase == Phase.GAME_END else None,
        }
