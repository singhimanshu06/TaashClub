"""Twenty-Eight bot brain — simple heuristics, no networking.

``bot_bid`` / ``bot_choose_trump`` / ``bot_play`` return legal decisions built
on top of the engine's ``legal_*`` helpers. They never mutate state; the caller
(the bot driver in ``main.py``) applies the returned action envelope.

The bots read the engine's raw state (including the hidden trump) the same way
the Callbreak bots read theirs — they are server-side seats, not hidden-info
clients.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Card, GameError, Phase, Suit

if TYPE_CHECKING:
    from .engine import Game

from .models import MAX_BID, MIN_BID, card_points, card_strength


def _partner_seat(seat: int) -> int:
    return (seat + 2) % 4


def bot_bid(game: "Game", player_id: str, rng: random.Random) -> tuple[str, dict]:
    """Heuristic bid: estimate capturable points from hand honours.

    The opener must open (>= 14). After that, raise to our estimate whenever
    it clears the minimum raise (incl. the >= 20 partner-overcall rule),
    otherwise pass.
    """
    seat = game._seat_of(player_id)
    estimate = sum(card_points(c) for c in game.players[seat].hand)
    jitter = rng.choice([-1, 0, 0, 1])

    min_raise = max(MIN_BID, game._min_raise_for(seat))
    target = min(MAX_BID, estimate + jitter)

    if game.high_bid is None:
        # Mandatory opening bid.
        return "place_bid", {"value": max(MIN_BID, target)}
    if target >= min_raise:
        return "place_bid", {"value": target}
    return "pass", {}


def bot_choose_trump(game: "Game", player_id: str) -> tuple[str, dict]:
    """Pick the suit with the most honour points (length as tiebreaker)."""
    hand = game._player_by_id(player_id).hand
    stats: dict[Suit, list[int]] = {}
    for c in hand:
        p, n = stats.get(c.suit, [0, 0])
        stats[c.suit] = [p + card_points(c), n + 1]
    best = max(Suit, key=lambda s: tuple(stats.get(s, [0, 0])))
    return "set_trump", {"suit": best.value}


def _low(cards: list[Card]) -> Card:
    return min(cards, key=lambda c: card_strength(c))


def _high(cards: list[Card]) -> Card:
    return max(cards, key=lambda c: card_strength(c))


def bot_play(game: "Game", player_id: str, rng: random.Random) -> tuple[str, dict]:
    seat = game._seat_of(player_id)
    player = game.players[seat]
    my_team = game.team_of(seat)
    aggressive = game.captured[my_team] < (game.high_bid or 0)
    trump = game.trump

    # Optional reveal: void in the led suit and holding some of the trump suit.
    can_reveal = (
        game.trump is not None
        and not game.trump_exposed
        and game.led_suit is not None
        and not any(c.suit == game.led_suit for c in player.hand)
        and any(c.suit == trump for c in player.hand)
    )
    if can_reveal:
        return "expose_trump", {}

    legal = game.legal_cards(player_id)
    if len(legal) == 1:
        return "play_card", {"card": legal[0].to_dict()}

    def dump() -> Card:
        # Throw the weakest card, preferring zero-point ones.
        zero = [c for c in legal if card_points(c) == 0]
        return _low(zero or legal)

    # --- Leading ---------------------------------------------------------
    if game.led_suit is None:
        if aggressive:
            # Lead strength: J/9-type winners first.
            return "play_card", {"card": _high(legal).to_dict()}
        return "play_card", {"card": dump().to_dict()}

    # --- Following (has led suit) ----------------------------------------
    led_legal = [c for c in legal if c.suit == game.led_suit]
    if led_legal:
        current_led = [
            e["card"] for e in game.current_trick if e["card"].suit == game.led_suit
        ]
        to_beat = _high(current_led) if current_led else None
        winners = [c for c in led_legal if to_beat is None or card_strength(c) > card_strength(to_beat)]
        if aggressive and winners:
            return "play_card", {"card": _low(winners).to_dict()}
        return "play_card", {"card": _low(led_legal).to_dict()}

    # --- Void -------------------------------------------------------------
    # The exposer's own must-play-trump obligation shows up in legal_cards.
    trump_cards = [c for c in legal if trump is not None and c.suit == trump]
    if aggressive and trump_cards and game.trump_exposed:
        already = [
            e["card"] for e in game.current_trick if e["card"].suit == trump
        ]
        if not already:
            return "play_card", {"card": _low(trump_cards).to_dict()}
        best_so_far = _high(already)
        winners = [c for c in trump_cards if card_strength(c) > card_strength(best_so_far)]
        if winners:
            return "play_card", {"card": _low(winners).to_dict()}
    return "play_card", {"card": dump().to_dict()}


class TwentyEightBotBrain:
    """Adapts the heuristics above to the generic ``BotBrain`` protocol."""

    def decide_action(
        self, game: "Game", player_id: str, rng: random.Random
    ) -> tuple[str, dict]:
        if game.phase == Phase.BIDDING:
            if game.awaiting_trump:
                return bot_choose_trump(game, player_id)
            return bot_bid(game, player_id, rng)
        if game.phase == Phase.PLAYING and not game.awaiting_trick_clear:
            return bot_play(game, player_id, rng)
        raise GameError("no bot action available in this phase")
