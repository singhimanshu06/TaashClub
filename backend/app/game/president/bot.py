"""President bot brain — heuristic, no networking.

Strategy: clear low cards early (the goal is to empty your hand). When leading a
fresh combo, lead the smallest single/pair/triple/quad available so low ranks
go out first. When following, play the cheapest legal combo that beats the
pile; if that would burn a high card we'd rather keep, pass instead. Bomb with
a 2 only when it unblocks low cards or when it would finish our hand.

During the between-round exchange, the bot returns its lowest card(s).
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Card, GameError, Phase
from .models import exchange_rank, president_sort_key

if TYPE_CHECKING:
    from .engine import Game


class PresidentBotBrain:
    """Adapts the President heuristic to the generic ``BotBrain`` protocol."""

    def decide_action(
        self, game: "Game", player_id: str, rng: random.Random
    ) -> tuple[str, dict]:
        if game.phase == Phase.EXCHANGE and game.exchange_state:
            if game.exchange_state.get("step") == "choose_return":
                if game._seat_of(player_id) == game.exchange_state["receiver_seat"]:
                    return self._choose_return_action(game, player_id)
            raise GameError("bot has no exchange action right now")
        if game.phase != Phase.PLAYING:
            raise GameError("no bot action available in this phase")
        return self._decide_play(game, player_id, rng)

    # ----- exchange ------------------------------------------------------
    def _choose_return_action(self, game: "Game", player_id: str) -> tuple[str, dict]:
        player = game._player_by_id(player_id)
        count = game.exchange_state["count"]
        # Return the `count` lowest cards (3s/4s, not the 2 or Ace).
        lowest = sorted(player.hand, key=president_sort_key)[-count:]
        return "choose_return", {"cards": [c.to_dict() for c in lowest]}

    # ----- play ----------------------------------------------------------
    def _decide_play(self, game: "Game", player_id: str, rng: random.Random) -> tuple[str, dict]:
        player = game._player_by_id(player_id)
        legal = game.legal_actions(player_id)
        if not legal:
            raise GameError("bot has no legal actions")

        combos = [a for a in legal if a["action"] == "play_combo"]
        bombs = [a for a in legal if a["action"] == "bomb"]
        can_pass = any(a["action"] == "pass" for a in legal)

        # Leading a fresh combo: dump the smallest combo available, preferring
        # larger sizes when we hold many of a low rank (clear them in one go).
        if game.pile_top is None:
            if not combos:
                # Only bombs available (shouldn't happen on a fresh lead with cards).
                if bombs:
                    b = rng.choice(bombs)
                    return "bomb", {"lead": b["lead"]}
                raise GameError("bot has no lead action")
            # Prefer the combo whose top rank is lowest (clear low cards first),
            # but favour playing multiple cards of the same low rank when possible.
            combos.sort(key=lambda a: (a["cards"][0]["rank"], -len(a["cards"])))
            chosen = combos[0]
            return "play_combo", {"cards": chosen["cards"]}

        # Following an existing combo.
        # 1. If we can finish our hand this play, do it.
        winning_hand = [a for a in combos if len(a["cards"]) == len(player.hand)]
        if winning_hand:
            chosen = winning_hand[0]
            return "play_combo", {"cards": chosen["cards"]}

        # 2. Bomb if it unblocks low cards and we have a 2 (and we're not close
        #    to a cheap win on the current pile). Bomb when our smallest legal
        #    combo's rank is high (we'd burn a valuable card) and we hold low
        #    cards we could lead after bombing.
        if bombs and combos:
            cheapest = min(combos, key=lambda a: a["cards"][0]["rank"])
            # Bomb if the cheapest follow is a J(11)+ and we have low cards to lead.
            if cheapest["cards"][0]["rank"] >= 11 and self._has_low_lead(game, player):
                # Choose a bomb whose lead is as low as possible.
                bombs.sort(key=lambda b: b["lead"][0]["rank"] if b["lead"] else 99)
                b = bombs[0]
                return "bomb", {"lead": b["lead"]}

        # 3. Otherwise play the cheapest legal combo, unless it would burn a
        #    high card we'd rather keep — in that case pass.
        if combos:
            cheapest = min(combos, key=lambda a: a["cards"][0]["rank"])
            top_rank = cheapest["cards"][0]["rank"]
            # Play anything 10 or below; pass rather than burn J+ unless we
            # have lots of high cards (in which case we need to move them).
            high_count = sum(1 for c in player.hand if c.rank >= 11)
            if top_rank <= 10 or high_count >= 3:
                return "play_combo", {"cards": cheapest["cards"]}
            if can_pass:
                return "pass", {}
            # Forced to play (can't pass while leading — but we're following).
            return "play_combo", {"cards": cheapest["cards"]}

        # 4. No legal combo — pass, or bomb as a last resort.
        if can_pass:
            return "pass", {}
        if bombs:
            b = rng.choice(bombs)
            return "bomb", {"lead": b["lead"]}
        raise GameError("bot stuck with no legal action")

    def _has_low_lead(self, game: "Game", player) -> bool:
        """True if the player has any non-2 combo of rank <= 7 to lead after a bomb."""
        by_rank: dict[int, int] = {}
        for c in player.hand:
            if c.rank != 2:
                by_rank[c.rank] = by_rank.get(c.rank, 0) + 1
        return any(rank <= 7 and count >= 1 for rank, count in by_rank.items())
