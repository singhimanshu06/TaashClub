"""Generic bot name pool, shared across all games.

Each game may theme its own additional names, but this provides a sensible
default pool so ``Room.add_bot`` doesn't need to know which game is running.
"""
from __future__ import annotations

import random

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
