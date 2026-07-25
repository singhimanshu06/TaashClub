"""Game registry — the single source of truth for available games.

Each ``GameSpec`` bundles a game's engine factory, bot brain, player-count
range, and option schema. The room layer and REST ``/games`` endpoint read
this; adding a game means appending one entry here (plus its package under
``game/<name>/``) — no changes to room/socket/main infra.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from .base import BaseGame, BotBrain, Player
from .callbreak.engine import GAME_TYPE as CALLBREAK_TYPE
from .callbreak.engine import Game as CallbreakGame
from .callbreak.bot import CallbreakBotBrain
from .callbreak.models import Variant
from .president.engine import GAME_TYPE as PRESIDENT_TYPE
from .president.engine import Game as PresidentGame
from .president.bot import PresidentBotBrain
from .president.models import DEFAULT_ROUND_COUNT, ROUND_COUNTS


@dataclass
class GameSpec:
    game_type: str
    display_name: str
    description: str
    min_players: int
    max_players: int
    engine_factory: Callable[..., BaseGame]
    bot_brain: BotBrain
    options_schema: dict   # machine-readable, for the frontend game picker


def _callbreak_factory(
    num_players: int, options: dict, players: list[Player], rng: random.Random
) -> BaseGame:
    variant = Variant(options.get("variant", Variant.SINGLE_RUN.value))
    return CallbreakGame(num_players, variant, players, rng=rng)


def _president_factory(
    num_players: int, options: dict, players: list[Player], rng: random.Random
) -> BaseGame:
    return PresidentGame(num_players, options, players, rng=rng)


GAME_REGISTRY: dict[str, GameSpec] = {
    CALLBREAK_TYPE: GameSpec(
        game_type=CALLBREAK_TYPE,
        display_name="LAKDI",
        description="Decreasing-cards, exact-bid trick-taking. Trump cycles each round.",
        min_players=4,
        max_players=6,
        engine_factory=_callbreak_factory,
        bot_brain=CallbreakBotBrain(),
        options_schema={
            "variant": {
                "type": "enum",
                "values": [v.value for v in Variant],
                "default": Variant.SINGLE_RUN.value,
                "labels": {"single_run": "Single run", "down_and_up": "Down & up"},
            },
        },
    ),
    PRESIDENT_TYPE: GameSpec(
        game_type=PRESIDENT_TYPE,
        display_name="President",
        description="Shed your hand fastest. Bomb with a 2, skip same-rank repeats, exchange cards between rounds.",
        min_players=5,
        max_players=5,
        engine_factory=_president_factory,
        bot_brain=PresidentBotBrain(),
        options_schema={
            "rounds": {
                "type": "enum",
                "values": [str(n) for n in ROUND_COUNTS],
                "default": str(DEFAULT_ROUND_COUNT),
                "labels": {str(n): f"{n} rounds" for n in ROUND_COUNTS},
            },
        },
    ),
}


def get_game_spec(game_type: str) -> GameSpec:
    spec = GAME_REGISTRY.get(game_type)
    if spec is None:
        from .base import GameError
        raise GameError(f"unknown game type: {game_type}")
    return spec


def list_games() -> list[dict]:
    """Summary for the ``GET /games`` endpoint (frontend game picker)."""
    return [
        {
            "game_type": spec.game_type,
            "display_name": spec.display_name,
            "description": spec.description,
            "min_players": spec.min_players,
            "max_players": spec.max_players,
            "options_schema": spec.options_schema,
        }
        for spec in GAME_REGISTRY.values()
    ]
