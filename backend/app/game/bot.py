"""LAKDI bot brain — pure heuristics, no networking.

``bot_bid`` and ``bot_play`` take a ``Game`` and a bot ``player_id`` and return a
legal decision. They never touch state; the caller (the bot driver in
``main.py``) applies the returned action to the engine.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .models import Card, Suit

if TYPE_CHECKING:
    from .engine import Game

# ~25 quirky, short (<=12 letters) names. Picked at random for bot seats;
# duplicates within a single room are avoided by ``Room.add_bot``.
BOT_NAMES = [
    "Ace", "Jokerman", "SirTrump", "Cleo", "CardShark",
    "Dealer", "Trumpzilla", "BidRogue", "NoTrump", "Slick",
    "Royal", "JokerJr", "Sneaky", "WildCard", "QueenBee",
    "KingMe", "Deuce", "HighRoll", "MiniAce", "ClubKing",
    "Spadey", "HeartBreak", "Diamondog", "FaceCard", "LowRoll",
]


def random_bot_name(rng: random.Random, taken: set[str]) -> str:
    """Pick a bot name not already in ``taken`` (existing players + bots)."""
    available = [n for n in BOT_NAMES if n not in taken]
    if not available:
        # All names in use (very unlikely); synthesize a unique fallback.
        i = 1
        while f"Bot{i}" in taken:
            i += 1
        return f"Bot{i}"
    return rng.choice(available)


def bot_bid(game: "Game", player_id: str, rng: random.Random) -> int:
    """Heuristic bid: count likely winners, clamp to [0, cards_this_round].

    A card is "likely a winner" if it's a high trump or the ace of a side suit.
    Adds small jitter so bots don't all bid identically.
    """
    player = game._player_by_id(player_id)
    trump = game.trump
    n = game.cards_this_round

    likely = 0
    for c in player.hand:
        if c.suit == trump and c.rank >= 12:           # trump Q+
            likely += 1
        elif c.suit != trump and c.rank == 14:          # off-suit ace
            likely += 1
        elif c.suit == trump and c.rank == 11:          # trump J — borderline
            likely += 1

    # Jitter: occasionally over/under-bid by one for variety.
    jitter = rng.choice([-1, 0, 0, 0, 1])
    bid = max(0, likely + jitter)
    return min(bid, n)


def bot_play(game: "Game", player_id: str, rng: random.Random) -> Card:
    """Heuristic play: always returns a member of ``legal_cards``.

    Strategy outline:
      - Leading: if still chasing tricks (tricks_won < bid) lead the lowest
        card of the suit where we hold the highest card (try to win cheaply);
        otherwise dump the lowest non-trump card we have.
      - Following: if we want more tricks and can win this trick cheaply with
        a legal card, do so (lowest winning legal card); else dump the lowest
        legal card. Use trump only when it both wins and is needed.
    """
    legal = game.legal_cards(player_id)
    if len(legal) == 1:
        return legal[0]

    player = game._player_by_id(player_id)
    trump = game.trump
    want_more = player.tricks_won < (player.bid or 0)

    def low(cards: list[Card]) -> Card:
        return min(cards, key=lambda c: c.rank)

    def high(cards: list[Card]) -> Card:
        return max(cards, key=lambda c: c.rank)

    # --- Leading a trick -------------------------------------------------
    if not game.current_trick:
        if not want_more:
            # Dump the lowest non-trump legal card (preserve trumps).
            non_trump = [c for c in legal if c.suit != trump]
            return low(non_trump) if non_trump else low(legal)
        # Want tricks: lead the lowest card of the suit where we hold the
        # highest top card — gives the best shot at winning cheaply.
        by_suit: dict[Suit, list[Card]] = {}
        for c in legal:
            by_suit.setdefault(c.suit, []).append(c)
        # Prefer suits where our top card is strong (ace or high trump).
        best_suit = max(
            by_suit,
            key=lambda s: high(by_suit[s]).rank + (5 if s == trump else 0),
        )
        return low(by_suit[best_suit])

    # --- Following -------------------------------------------------------
    led = game.led_suit
    # Highest card currently in the trick that could win (trump beats led).
    current = [e["card"] for e in game.current_trick]
    trumps_in_play = [c for c in current if c.suit == trump]
    if trumps_in_play:
        to_beat = high(trumps_in_play)
        can_win_with_trump = [c for c in legal if c.suit == trump and c.rank > to_beat.rank]
    else:
        led_cards = [c for c in current if c.suit == led]
        to_beat = high(led_cards) if led_cards else None
        can_win_with_trump = [c for c in legal if c.suit == trump] if to_beat is not None else []

    # Can we win with a legal card in the led suit (cheap, no trump)?
    led_legal = [c for c in legal if c.suit == led]
    cheap_win = None
    if led_legal and to_beat is not None and not trumps_in_play:
        winners = [c for c in led_legal if c.rank > to_beat.rank]
        if winners:
            cheap_win = low(winners)

    if want_more:
        if cheap_win is not None:
            return cheap_win
        # No cheap led-suit win. Use trump only if it actually wins and we
        # have trumps to spare (avoid wasting the last trump on a low card).
        if can_win_with_trump:
            # Don't burn a high trump to beat a low card if we're chasing.
            return low(can_win_with_trump)
        # Can't win — dump the lowest legal card (prefer non-trump).
        non_trump = [c for c in legal if c.suit != trump]
        return low(non_trump) if non_trump else low(legal)

    # Don't want more tricks: dump the lowest legal card, but if forced to
    # follow led with a winner, play the lowest such winner (unavoidable).
    if led_legal:
        return low(led_legal)
    non_trump = [c for c in legal if c.suit != trump]
    return low(non_trump) if non_trump else low(legal)
