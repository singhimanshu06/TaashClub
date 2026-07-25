"""Unit tests for the bot brain (bot.py).

The bot functions are pure: they take a Game + player_id and return a legal
decision without mutating state. These tests exercise bidding range/clamping and
the invariant that bot_play always returns a legal card across many random
deals, including the 1-card edge case.
"""
import random

import pytest

from app.game.names import BOT_NAMES, random_bot_name
from app.game.callbreak.bot import bot_bid, bot_play
from app.game.callbreak.engine import Game
from app.game.base import Card, Phase, Player, Suit
from app.game.callbreak.models import Variant


def make_players(n: int, bot_seats: set[int] = frozenset()) -> list[Player]:
    return [Player(id=f"p{i}", name=f"P{i}", join_order=i, is_bot=(i in bot_seats))
            for i in range(n)]


def new_game(n=4, variant=Variant.SINGLE_RUN, seed=42, bot_seats=frozenset()) -> Game:
    return Game(n, variant, make_players(n, bot_seats), rng=random.Random(seed))


def _force_playing(g: Game) -> None:
    """Skip bidding with 0 bids and land in PLAYING."""
    while g.phase == Phase.BIDDING:
        g.place_bid(g.players[g.turn_idx].id, 0)


def test_bot_names_short_and_unique():
    assert len(BOT_NAMES) >= 20
    assert len(BOT_NAMES) == len(set(BOT_NAMES))  # no duplicates in the pool
    for name in BOT_NAMES:
        assert len(name) <= 12, f"{name!r} exceeds 12 letters"


def test_random_bot_name_avoids_taken():
    rng = random.Random(0)
    taken = set()
    picked = set()
    for _ in range(len(BOT_NAMES)):
        name = random_bot_name(rng, taken)
        assert name not in taken
        taken.add(name)
        picked.add(name)
    # Once exhausted, falls back to a synthesized BotN name.
    fb = random_bot_name(rng, taken)
    assert fb.startswith("Bot")


def test_bot_bid_within_range():
    g = new_game(4, seed=1, bot_seats={0, 1, 2, 3})
    g.start()
    rng = random.Random(0)
    for p in g.players:
        bid = bot_bid(g, p.id, rng)
        assert 0 <= bid <= g.cards_this_round


def test_bot_bid_zero_when_no_winners():
    g = new_game(4, seed=5)
    g.start()
    # Strip the bot's hand to pure low non-trump cards so it has no winners.
    bot = g.players[0]
    bot.hand = [Card(Suit.CLUB, 2), Card(Suit.DIAMOND, 3)]
    # Force trump to spades (round 0) so clubs/diamonds are side suits.
    bid = bot_bid(g, bot.id, random.Random(0))
    assert bid == 0


def test_bot_play_always_legal_across_many_deals():
    """Across many random games the bot must only ever return a legal card.

    This is the core invariant: bot_play must never break follow-suit rules or
    pick a card not in the player's hand.
    """
    rng = random.Random(123)
    for seed in range(60):
        g = new_game(4, Variant.DOWN_AND_UP, seed=seed, bot_seats={0, 1, 2, 3})
        g.start()
        guard = 0
        while g.phase != Phase.GAME_END and guard < 2000:
            guard += 1
            if g.phase == Phase.BIDDING:
                pid = g.players[g.turn_idx].id
                g.place_bid(pid, bot_bid(g, pid, rng))
            elif g.phase == Phase.PLAYING:
                if g.awaiting_trick_clear:
                    g.commit_trick()
                    continue
                pid = g.players[g.turn_idx].id
                legal = g.legal_cards(pid)
                card = bot_play(g, pid, rng)
                assert card in legal, f"bot played illegal card {card}; legal={legal}"
                assert card in g._player_by_id(pid).hand
                g.play_card(pid, card)
            elif g.phase == Phase.ROUND_END:
                g.advance_round()
        assert g.phase == Phase.GAME_END


def test_bot_play_one_card_round():
    """The 1-card round is a degenerate hand — bot must return that single card."""
    g = new_game(4, seed=9, bot_seats={0, 1, 2, 3})
    g.start()
    rng = random.Random(0)
    # Fast-forward to the final 1-card round (round index 12 for single run of 4p).
    while g.cards_this_round != 1:
        _fast_forward_round(g, bid=0)
    _force_playing(g)
    bot = next(p for p in g.players if p.is_bot)
    # Put the bot on turn.
    g.turn_idx = g.players.index(bot)
    card = bot_play(g, bot.id, rng)
    assert card in g.legal_cards(bot.id)
    assert len(bot.hand) == 1


def test_bot_play_follows_led_suit_when_held():
    g = new_game(4, seed=2)
    g.start()
    _force_playing(g)
    bot = g.players[0]
    # Bot holds a heart and a spade; hearts is led -> must play a heart.
    bot.hand = [Card(Suit.HEART, 5), Card(Suit.SPADE, 14)]
    g.led_suit = Suit.HEART
    g.current_trick = [{"seat": 1, "card": Card(Suit.HEART, 9)}]
    g.turn_idx = 0
    card = bot_play(g, bot.id, random.Random(0))
    assert card.suit == Suit.HEART


def test_bot_play_can_discard_when_void_in_led():
    g = new_game(4, seed=3)
    g.start()
    _force_playing(g)
    bot = g.players[0]
    bot.hand = [Card(Suit.SPADE, 14), Card(Suit.CLUB, 2)]
    g.led_suit = Suit.HEART
    g.current_trick = [{"seat": 1, "card": Card(Suit.HEART, 9)}]
    g.turn_idx = 0
    card = bot_play(g, bot.id, random.Random(0))
    assert card in bot.hand


def _fast_forward_round(g: Game, bid: int = 0) -> None:
    while g.phase == Phase.BIDDING:
        g.place_bid(g.players[g.turn_idx].id, bid)
    while g.phase == Phase.PLAYING:
        if g.awaiting_trick_clear:
            g.commit_trick()
            continue
        pid = g.players[g.turn_idx].id
        g.play_card(pid, g.legal_cards(pid)[0])
    if g.phase == Phase.ROUND_END:
        g.advance_round()
