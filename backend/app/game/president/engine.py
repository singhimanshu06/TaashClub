"""Pure President game engine — server-authoritative rules, no networking.

Implements the ``BaseGame`` protocol from ``app.game.base``. A single ``Game``
instance owns the full state for one room's match (multiple rounds, with a
between-round card exchange).

Key concepts:
- A "combo" is 1-4 cards of the same rank (single/double/triple/quad).
- Players must follow the led combo's *size* with cards of >= rank, or pass.
- A single 2 is a "bomb": it clears the pile and the bomber leads a fresh combo.
- If two consecutive plays (ignoring passes) are the same rank+size where the
  size is 1 or 2, the next player is skipped for the current combo.
- A round ends when one player has cards left (the Asshole). Roles are assigned
  by finishing order and scored. Rounds 2+ start with an exchange where the
  Asshole/Vice-Asshole give their highest cards to the President/VP, who then
  choose cards to return.
"""
from __future__ import annotations

import random
from typing import Optional

from ..base import Card, GameError, Phase, Player, Suit
from .models import (
    CARDS_PER_PLAYER,
    DEFAULT_ROUND_COUNT,
    EXCHANGE_GIVE,
    GAME_TYPE,
    NUM_PLAYERS,
    ROLE_LABELS,
    SCORES,
    build_president_deck,
    exchange_rank,
    president_sort_key,
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
            raise GameError(f"President requires exactly {NUM_PLAYERS} players")
        if len(players) != num_players:
            raise GameError("player count does not match num_players")

        self.game_type = GAME_TYPE
        self.num_players = num_players
        rc = options.get("rounds", str(DEFAULT_ROUND_COUNT))
        self.total_rounds = int(rc) if rc is not None else DEFAULT_ROUND_COUNT
        self.players = sorted(players, key=lambda p: p.join_order)
        self.rng = rng or random.Random()

        self.round_index = -1
        self.phase = Phase.LOBBY
        self.turn_idx = 0
        # Pile state: the current combo to beat (None = fresh lead).
        self.pile_top: Optional[dict] = None   # {"rank": int, "size": int, "player_id": str}
        self.current_trick: list[dict] = []    # [{"player_id","cards":[dict]}] this "trick"
        # The seat that last played a combo (so a cleared pile returns the lead
        # to them). Tracked separately from pile_top because pile_top is None
        # during a fresh lead.
        self.last_play_seat: Optional[int] = None
        # Skip detection: last two *plays* (passes don't count, 2-bomb resets).
        self.last_play_ranks: list[tuple[int, int]] = []  # [(rank, size)]
        self.skip_until_clear: set[int] = set()  # seat indices skipped for current combo
        self.passes_this_combo: set[int] = set()  # who has passed the current combo
        self.awaiting_trick_clear = False        # protocol compat (always False here)
        self.last_round_result: Optional[list[dict]] = None
        self.round_history: list[dict] = []
        # Roles assigned at the end of a round, by finish_index -> player_id.
        self.roles: dict[int, str] = {}          # finish_index -> player_id
        # Per-round finishing order (seat indices, in finish order).
        self._finish_order: list[int] = []
        # Exchange state (when in EXCHANGE phase).
        self.exchange_state: Optional[dict] = None

    # ----- lookups -------------------------------------------------------
    def _player_by_id(self, player_id: str) -> Player:
        for p in self.players:
            if p.id == player_id:
                return p
        raise GameError("unknown player")

    def _seat_of(self, player_id: str) -> int:
        return self._player_by_id(player_id).join_order

    def _active_seats(self) -> list[int]:
        """Seats still holding cards (in seat order)."""
        return [p.join_order for p in self.players if p.hand]

    def _next_active_seat_after(self, seat: int) -> Optional[int]:
        active = self._active_seats()
        if not active:
            return None
        if seat in active:
            idx = active.index(seat)
            return active[(idx + 1) % len(active)]
        return active[0]

    # ----- lifecycle -----------------------------------------------------
    def start(self) -> None:
        if self.phase != Phase.LOBBY:
            raise GameError("game already started")
        self._deal_next_round()
        self._begin_play(lead_holder=None)

    def _deal_next_round(self) -> None:
        """Shuffle and deal 10 cards to each player. Does NOT set phase/leader."""
        self.round_index += 1
        deck = build_president_deck(self.rng)
        self.rng.shuffle(deck)
        for p in self.players:
            p.hand = sorted(deck[:CARDS_PER_PLAYER], key=president_sort_key)
            deck = deck[CARDS_PER_PLAYER:]

        self.pile_top = None
        self.current_trick = []
        self.last_play_seat = None
        self.last_play_ranks = []
        self.skip_until_clear = set()
        self.passes_this_combo = set()
        self.exchange_state = None
        self._finish_order = []

    def _begin_play(self, lead_holder: Optional[str]) -> None:
        """Set the leader and enter PLAYING. Cards must already be dealt."""
        if lead_holder is not None:
            self.turn_idx = self._seat_of(lead_holder)
        else:
            # Round 1: holder of J of Hearts leads.
            jh = Card(suit=Suit.HEART, rank=11)
            for p in self.players:
                if jh in p.hand:
                    self.turn_idx = p.join_order
                    break
            else:
                self.turn_idx = self.players[0].join_order
        self.phase = Phase.PLAYING

    # ----- combo helpers -------------------------------------------------
    @staticmethod
    def _validate_combo(cards: list[Card]) -> tuple[int, int]:
        """Return (rank, size) if cards form a valid same-rank combo, else raise."""
        if not cards or len(cards) > 4:
            raise GameError("combo must be 1-4 cards")
        ranks = {c.rank for c in cards}
        if len(ranks) != 1:
            raise GameError("combo cards must all share one rank")
        return cards[0].rank, len(cards)

    # ----- actions -------------------------------------------------------
    def apply_action(self, player_id: str, action: str, params: dict) -> None:
        if action == "play_combo":
            self._play_combo(player_id, [Card.from_dict(c) for c in params["cards"]])
        elif action == "pass":
            self._pass(player_id)
        elif action == "bomb":
            lead = [Card.from_dict(c) for c in params["lead"]] if params.get("lead") else []
            self._bomb(player_id, lead)
        elif action == "advance_round":
            self.advance_round()
        elif action == "choose_return":
            self._choose_return(player_id, [Card.from_dict(c) for c in params["cards"]])
        else:
            raise GameError(f"unknown action: {action}")

    def _play_combo(self, player_id: str, cards: list[Card]) -> None:
        if self.phase != Phase.PLAYING:
            raise GameError("not in playing phase")
        seat = self._seat_of(player_id)
        if seat != self.turn_idx:
            raise GameError("not your turn")
        if seat in self.skip_until_clear:
            raise GameError("you are skipped this combo")
        player = self._player_by_id(player_id)
        for c in cards:
            if c not in player.hand:
                raise GameError("card not in hand")
        rank, size = self._validate_combo(cards)
        # A 2 is bomb-only — except when the player holds nothing but 2s on a
        # fresh lead (otherwise they'd be stuck with no legal play).
        if rank == 2 and not (self.pile_top is None and all(c.rank == 2 for c in player.hand)):
            raise GameError("a 2 must be played as a bomb, not a combo")
        if self.pile_top is not None:
            if size != self.pile_top["size"]:
                raise GameError("must match the led combo size")
            if rank < self.pile_top["rank"]:
                raise GameError("must play a rank >= the led rank")

        self._commit_play(player_id, seat, cards, rank, size)

    def _bomb(self, player_id: str, lead: list[Card]) -> None:
        if self.phase != Phase.PLAYING:
            raise GameError("not in playing phase")
        seat = self._seat_of(player_id)
        if seat != self.turn_idx:
            raise GameError("not your turn")
        if seat in self.skip_until_clear:
            raise GameError("you are skipped this combo")
        player = self._player_by_id(player_id)
        two = next((c for c in player.hand if c.rank == 2), None)
        if two is None:
            raise GameError("you don't have a 2 to bomb")
        # Bomb clears the pile.
        player.hand.remove(two)
        self.pile_top = None
        self.current_trick = []
        self.last_play_ranks = []
        self.skip_until_clear = set()
        self.passes_this_combo = set()

        if player.hand:
            # Lead a fresh combo (same turn). If the player only holds 2s after
            # bombing, allow leading a 2 (otherwise they'd be stuck).
            only_twos = all(c.rank == 2 for c in player.hand)
            if not lead and not only_twos:
                raise GameError("you must lead a fresh combo after bombing")
            if lead:
                for c in lead:
                    if c not in player.hand:
                        raise GameError("lead card not in hand")
                rank, size = self._validate_combo(lead)
                if rank == 2:
                    raise GameError("cannot lead with a 2")
                self._commit_play(player_id, seat, lead, rank, size)
            else:
                # Only 2s left — lead a single 2 as a combo.
                self._commit_play(player_id, seat, [player.hand[0]], 2, 1)
        else:
            # The 2 was their last card: they finish, next active player leads.
            self._mark_finished(seat)
            self._advance_after_finish()

    def _commit_play(self, player_id: str, seat: int, cards: list[Card], rank: int, size: int) -> None:
        player = self._player_by_id(player_id)
        for c in cards:
            player.hand.remove(c)
        self.pile_top = {"rank": rank, "size": size, "player_id": player_id}
        self.current_trick.append({"player_id": player_id, "cards": [c.to_dict() for c in cards]})
        self.last_play_seat = seat
        self.passes_this_combo = set()

        # Skip detection: if this play's (rank, size) equals the immediately
        # previous play's (rank, size) and size is 1 or 2, skip the next player.
        self.last_play_ranks.append((rank, size))
        if len(self.last_play_ranks) >= 2 and size in (1, 2):
            prev = self.last_play_ranks[-2]
            cur = self.last_play_ranks[-1]
            if prev == cur:
                nxt = self._next_active_seat_after(seat)
                if nxt is not None:
                    self.skip_until_clear.add(nxt)

        if not player.hand:
            self._mark_finished(seat)
            self._advance_after_finish()
        else:
            self._advance_turn()

    def _pass(self, player_id: str) -> None:
        if self.phase != Phase.PLAYING:
            raise GameError("not in playing phase")
        seat = self._seat_of(player_id)
        if seat != self.turn_idx:
            raise GameError("not your turn")
        if seat in self.skip_until_clear:
            raise GameError("you are skipped this combo")
        if self.pile_top is None:
            raise GameError("you are leading — you must play a combo, not pass")

        self.passes_this_combo.add(seat)
        active = [s for s in self._active_seats() if s not in self.skip_until_clear]
        # Pile clears when everyone still active (and not skipped) OTHER than the
        # last player to play has passed — the last player doesn't pass, they
        # simply win the pile by default once everyone else gives up.
        must_pass = set(active)
        if self.last_play_seat is not None:
            must_pass.discard(self.last_play_seat)
        if self.passes_this_combo >= must_pass and must_pass:
            # Everyone else has passed: pile clears, last player to play leads.
            self.pile_top = None
            self.current_trick = []
            self.last_play_ranks = []
            self.skip_until_clear = set()
            self.passes_this_combo = set()
            if self.last_play_seat is not None and self.players[self.last_play_seat].hand:
                self.turn_idx = self.last_play_seat
            else:
                # Last player finished; advance to next active.
                self._advance_after_finish()
            return
        self._advance_turn()

    def _advance_turn(self) -> None:
        active = self._active_seats()
        if not active:
            return
        if self.turn_idx not in active:
            self.turn_idx = active[0]
        idx = active.index(self.turn_idx)
        for _ in range(len(active)):
            idx = (idx + 1) % len(active)
            seat = active[idx]
            if seat not in self.skip_until_clear:
                self.turn_idx = seat
                return
        # All remaining active seats are skipped — clear skips and advance.
        self.skip_until_clear = set()
        self.turn_idx = active[(active.index(self.turn_idx) + 1) % len(active)]

    def _mark_finished(self, seat: int) -> None:
        """Record a player as having emptied their hand this round."""
        if seat not in self._finish_order:
            self._finish_order.append(seat)

    def _advance_after_finish(self) -> None:
        """After a player empties their hand, advance turn or end the round."""
        active = self._active_seats()
        if len(active) <= 1:
            self._end_round()
            return
        self._advance_turn()

    def _end_round(self) -> None:
        # Record any remaining active player as last (the Asshole).
        remaining = [s for s in self._active_seats() if s not in self._finish_order]
        self._finish_order.extend(remaining)
        roles_by_finish: dict[int, str] = {}
        result = []
        for finish_idx, seat in enumerate(self._finish_order):
            player = self.players[seat]
            score = SCORES.get(finish_idx, 0)
            player.total_score += score
            roles_by_finish[finish_idx] = player.id
            result.append({
                "player_id": player.id,
                "name": player.name,
                "finish": finish_idx,
                "role": ROLE_LABELS.get(finish_idx, "?"),
                "round_score": score,
                "total_score": player.total_score,
            })
        self.roles = roles_by_finish
        self.last_round_result = result
        self.round_history.append({"round_index": self.round_index, "results": result})

        if self.round_index + 1 >= self.total_rounds:
            self.phase = Phase.GAME_END
        else:
            self.phase = Phase.ROUND_END

    def advance_round(self) -> None:
        if self.phase != Phase.ROUND_END:
            raise GameError("no round to advance")
        # Deal the next round FIRST so players have cards to exchange.
        self._deal_next_round()
        pending = self._build_exchange_pending()
        if pending:
            self.exchange_state = {"pending": pending}
            self.phase = Phase.EXCHANGE
            self._start_next_exchange_step()
        else:
            self._begin_play(lead_holder=self.roles.get(4))

    def _build_exchange_pending(self) -> list[dict]:
        """List of exchange pairs still to process this between-round."""
        pending = []
        if 4 in self.roles and 0 in self.roles and EXCHANGE_GIVE.get(4):
            pending.append({"from_finish": 4, "to_finish": 0, "count": EXCHANGE_GIVE[4]})
        if 3 in self.roles and 1 in self.roles and EXCHANGE_GIVE.get(3):
            pending.append({"from_finish": 3, "to_finish": 1, "count": EXCHANGE_GIVE[3]})
        return pending

    def _start_next_exchange_step(self) -> None:
        """Transfer the giver's best cards, then ask the receiver to choose returns."""
        if not self.exchange_state or not self.exchange_state["pending"]:
            self._start_next_round_after_exchange()
            return
        pair = self.exchange_state["pending"][0]
        giver_seat = self._seat_of(self.roles[pair["from_finish"]])
        receiver_seat = self._seat_of(self.roles[pair["to_finish"]])
        giver = self.players[giver_seat]
        receiver = self.players[receiver_seat]
        sorted_hand = sorted(giver.hand, key=exchange_rank, reverse=True)
        moved = sorted_hand[: pair["count"]]
        for c in moved:
            giver.hand.remove(c)
            receiver.hand.append(c)
        giver.hand.sort(key=president_sort_key)
        receiver.hand.sort(key=president_sort_key)
        self.exchange_state["step"] = "choose_return"
        self.exchange_state["giver_seat"] = giver_seat
        self.exchange_state["receiver_seat"] = receiver_seat
        self.exchange_state["count"] = pair["count"]
        self.turn_idx = receiver_seat  # receiver acts

    def _choose_return(self, player_id: str, cards: list[Card]) -> None:
        if self.phase != Phase.EXCHANGE:
            raise GameError("not in exchange phase")
        if not self.exchange_state or self.exchange_state.get("step") != "choose_return":
            raise GameError("no return choice pending")
        receiver_seat = self.exchange_state["receiver_seat"]
        if self._seat_of(player_id) != receiver_seat:
            raise GameError("not your turn to choose return cards")
        count = self.exchange_state["count"]
        if len(cards) != count:
            raise GameError(f"must return exactly {count} card(s)")
        receiver = self.players[receiver_seat]
        giver = self.players[self.exchange_state["giver_seat"]]
        for c in cards:
            if c not in receiver.hand:
                raise GameError("return card not in hand")
        for c in cards:
            receiver.hand.remove(c)
            giver.hand.append(c)
        receiver.hand.sort(key=president_sort_key)
        giver.hand.sort(key=president_sort_key)
        self.exchange_state["pending"].pop(0)
        if self.exchange_state["pending"]:
            self._start_next_exchange_step()
        else:
            self._start_next_round_after_exchange()

    def _start_next_round_after_exchange(self) -> None:
        self.exchange_state = None
        # Cards were already dealt by advance_round before the exchange began.
        self._begin_play(lead_holder=self.roles.get(4))

    def force_end(self) -> None:
        self.awaiting_trick_clear = False
        self.current_trick = []
        self.pile_top = None
        self.phase = Phase.GAME_END

    # ----- legal actions (for viewer + bot) ------------------------------
    def _player_combos(
        self, player: Player, min_rank: int, size: int, allow_twos: bool = False
    ) -> list[list[Card]]:
        """All same-rank combos of `size` from the player's hand with rank >= min_rank.

        2s are bomb-only and excluded by default. ``allow_twos`` is set only when
        a player holds nothing but 2s on a fresh lead (otherwise they'd be stuck
        with no legal play).
        """
        by_rank: dict[int, list[Card]] = {}
        for c in player.hand:
            by_rank.setdefault(c.rank, []).append(c)
        combos = []
        for rank, cards in by_rank.items():
            if rank == 2 and not allow_twos:
                continue  # 2s are bomb-only, never normal combos
            if rank >= min_rank and len(cards) >= size:
                combos.append(cards[:size])
        return combos

    def legal_actions(self, player_id: str) -> list[dict]:
        if self.phase == Phase.PLAYING:
            return self._legal_play_actions(player_id)
        if self.phase == Phase.EXCHANGE and self.exchange_state:
            if self.exchange_state.get("step") == "choose_return":
                if self._seat_of(player_id) == self.exchange_state["receiver_seat"]:
                    return [{"action": "choose_return", "count": self.exchange_state["count"]}]
        return []

    def _legal_play_actions(self, player_id: str) -> list[dict]:
        if self.players[self.turn_idx].id != player_id:
            return []
        seat = self._seat_of(player_id)
        if seat in self.skip_until_clear:
            return []  # skipped this combo
        player = self._player_by_id(player_id)
        actions: list[dict] = []
        only_twos = bool(player.hand) and all(c.rank == 2 for c in player.hand)
        if self.pile_top is None:
            for size in (1, 2, 3, 4):
                actions.extend(
                    {"action": "play_combo", "cards": [c.to_dict() for c in combo]}
                    for combo in self._player_combos(
                        player, min_rank=3, size=size, allow_twos=only_twos
                    )
                )
        else:
            size = self.pile_top["size"]
            actions.extend(
                {"action": "play_combo", "cards": [c.to_dict() for c in combo]}
                for combo in self._player_combos(player, min_rank=self.pile_top["rank"], size=size)
            )
            actions.append({"action": "pass"})
        if any(c.rank == 2 for c in player.hand):
            # A bomb is legal whenever there's a pile to clear, or the 2 is the
            # player's last card (finishes them), or the player holds only 2s
            # on a fresh lead (otherwise they'd be stuck with no legal play).
            only_twos = all(c.rank == 2 for c in player.hand)
            if self.pile_top is not None or len(player.hand) == 1 or (self.pile_top is None and only_twos):
                if len(player.hand) > 1:
                    for size in (1, 2, 3, 4):
                        for lead in self._player_combos(player, min_rank=3, size=size):
                            actions.append({
                                "action": "bomb",
                                "lead": [c.to_dict() for c in lead],
                            })
                    # If the only non-2 cards can't form a combo (shouldn't
                    # happen, but guard anyway), allow a bare bomb.
                    if not any(a["action"] == "bomb" for a in actions):
                        actions.append({"action": "bomb", "lead": []})
                else:
                    actions.append({"action": "bomb", "lead": []})
        return actions

    # ----- serialization -------------------------------------------------
    def final_standings(self) -> list[dict]:
        ranked = sorted(self.players, key=lambda p: p.total_score, reverse=True)
        return [
            {"player_id": p.id, "name": p.name, "total_score": p.total_score, "rank": i + 1}
            for i, p in enumerate(ranked)
        ]

    def to_state(self, viewer_id: Optional[str] = None) -> dict:
        current_player_id = None
        if self.phase in (Phase.PLAYING, Phase.EXCHANGE):
            current_player_id = self.players[self.turn_idx].id
        return {
            "game_type": self.game_type,
            "phase": self.phase.value,
            "num_players": self.num_players,
            "rounds_total": self.total_rounds,
            "round_index": self.round_index,
            "pile_top": self.pile_top,
            "current_player_id": current_player_id,
            "awaiting_trick_clear": False,
            "trick_winner_id": None,
            "led_suit": None,
            "current_trick": self.current_trick,
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "seat": p.join_order,
                    "bid": None,
                    "tricks_won": len(p.hand),  # reused as "cards remaining"
                    "hand_count": len(p.hand),
                    "hand": [c.to_dict() for c in p.hand] if p.id == viewer_id else None,
                    "connected": p.connected,
                    "is_bot": p.is_bot,
                    "total_score": p.total_score,
                }
                for p in self.players
            ],
            "your_legal_cards": None,
            "your_legal_actions": self.legal_actions(viewer_id) if viewer_id else None,
            "last_round_result": self.last_round_result,
            "round_history": self.round_history,
            "final_standings": self.final_standings() if self.phase == Phase.GAME_END else None,
            "roles": {str(k): v for k, v in self.roles.items()} if self.roles else {},
            "exchange": self._exchange_public_state(),
            "finish_order": [self.players[s].id for s in self._finish_order] if self._finish_order else [],
            "skipped_player_ids": [self.players[s].id for s in self.skip_until_clear],
        }

    def _exchange_public_state(self) -> Optional[dict]:
        if self.phase != Phase.EXCHANGE or not self.exchange_state:
            return None
        return {
            "step": self.exchange_state.get("step"),
            "giver_id": self.players[self.exchange_state["giver_seat"]].id
                if "giver_seat" in self.exchange_state else None,
            "receiver_id": self.players[self.exchange_state["receiver_seat"]].id
                if "receiver_seat" in self.exchange_state else None,
            "count": self.exchange_state.get("count"),
        }
