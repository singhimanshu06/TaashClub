"""Room lifecycle + WebSocket connection management (in-memory, MVP)."""
from __future__ import annotations

import random
import string
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket

from .bot import random_bot_name
from .engine import Game, GameError
from .models import Player, Variant

CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LEN = 4
CHAT_MAX_LEN = 300
CHAT_HISTORY = 200


def _gen_code(rng: random.Random) -> str:
    return "".join(rng.choice(CODE_ALPHABET) for _ in range(CODE_LEN))


@dataclass
class Room:
    code: str
    num_players: int
    variant: Variant
    host_id: Optional[str] = None
    players: list[Player] = field(default_factory=list)   # in join order
    game: Optional[Game] = None
    sockets: dict[str, WebSocket] = field(default_factory=dict)
    chat_log: list[dict] = field(default_factory=list)
    clearing: bool = False   # guards the async post-trick clear (one task at a time)
    # Bot driver bookkeeping. bot_busy prevents scheduling two bot actions for
    # the same turn; _bot_tasks holds strong refs to in-flight bot/auto-advance
    # tasks so the event loop doesn't garbage-collect them mid-flight (a known
    # asyncio footgun when the only reference is dropped too early).
    bot_busy: bool = False
    auto_advance_busy: bool = False
    _bot_tasks: set = field(default_factory=set)
    # Pending disconnect→bot conversion tasks, keyed by player_id. Cancelled if
    # the player reconnects before the grace period expires.
    conversion_timers: dict = field(default_factory=dict)

    @property
    def started(self) -> bool:
        return self.game is not None

    @property
    def has_bots(self) -> bool:
        return any(p.is_bot for p in self.players)

    def add_chat(self, player_id: str, text: str) -> Optional[dict]:
        text = (text or "").strip()[:CHAT_MAX_LEN]
        if not text:
            return None
        author = next((p for p in self.players if p.id == player_id), None)
        msg = {
            "player_id": player_id,
            "name": author.name if author else "?",
            "text": text,
            "ts": time.time(),
        }
        self.chat_log.append(msg)
        del self.chat_log[:-CHAT_HISTORY]  # keep only the most recent messages
        return msg

    def is_full(self) -> bool:
        return len(self.players) >= self.num_players

    def add_player(self, name: str) -> Player:
        if self.started:
            raise GameError("game already started")
        if self.is_full():
            raise GameError("room is full")
        player = Player(id=_gen_code(random.Random()) + str(len(self.players)),
                        name=name.strip()[:20] or f"Player {len(self.players) + 1}",
                        join_order=len(self.players))
        self.players.append(player)
        if self.host_id is None:
            self.host_id = player.id
        return player

    def add_bot(self) -> Player:
        """Fill the next empty seat with a server-driven bot (no socket)."""
        if self.started:
            raise GameError("game already started")
        if self.is_full():
            raise GameError("room is full")
        taken = {p.name for p in self.players}
        bot = Player(id="bot-" + _gen_code(random.Random()) + str(len(self.players)),
                     name=random_bot_name(random.Random(), taken),
                     join_order=len(self.players),
                     connected=True,
                     is_bot=True)
        self.players.append(bot)
        if self.host_id is None:
            self.host_id = bot.id
        return bot

    def has_player(self, player_id: str) -> bool:
        return any(p.id == player_id for p in self.players)

    def start_game(self, player_id: str) -> None:
        if player_id != self.host_id:
            raise GameError("only the host can start the game")
        if not self.is_full():
            raise GameError(f"need {self.num_players} players to start")
        if self.started:
            raise GameError("game already started")
        # Randomize the playing/bidding order once; it is fixed for the whole
        # game. join_order becomes the (now random) seat index the engine uses.
        shuffled = list(self.players)
        random.Random().shuffle(shuffled)
        for seat, p in enumerate(shuffled):
            p.join_order = seat
        self.game = Game(self.num_players, self.variant, self.players)
        self.game.start()

    def add_one_bot(self, player_id: str) -> None:
        """Host-only: add a single bot to the next empty seat (lobby only)."""
        if player_id != self.host_id:
            raise GameError("only the host can add bots")
        if self.started:
            raise GameError("game already started")
        if self.is_full():
            raise GameError("room is full")
        self.add_bot()

    def add_bots(self, player_id: str) -> None:
        """Host-only: fill all remaining seats with bots (lobby only)."""
        if player_id != self.host_id:
            raise GameError("only the host can add bots")
        if self.started:
            raise GameError("game already started")
        while not self.is_full():
            self.add_bot()

    def lobby_snapshot(self) -> dict:
        return {
            "code": self.code,
            "num_players": self.num_players,
            "variant": self.variant.value,
            "host_id": self.host_id,
            "started": self.started,
            "players": [
                {"id": p.id, "name": p.name, "seat": p.join_order, "connected": p.connected, "is_bot": p.is_bot}
                for p in self.players
            ],
        }


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self._rng = random.Random()

    def create_room(self, num_players: int, variant: Variant) -> Room:
        if num_players not in (4, 5, 6):
            raise GameError("num_players must be 4, 5, or 6")
        code = _gen_code(self._rng)
        while code in self.rooms:
            code = _gen_code(self._rng)
        room = Room(code=code, num_players=num_players, variant=variant)
        self.rooms[code] = room
        return room

    def get(self, code: str) -> Room:
        room = self.rooms.get(code.upper())
        if room is None:
            raise GameError("room not found")
        return room


class ConnectionManager:
    """Tracks live sockets per room and broadcasts redacted state to each viewer."""

    async def connect(self, room: Room, player_id: str, ws: WebSocket) -> None:
        await ws.accept()
        room.sockets[player_id] = ws
        for p in room.players:
            if p.id == player_id:
                p.connected = True

    def disconnect(self, room: Room, player_id: str) -> None:
        room.sockets.pop(player_id, None)
        for p in room.players:
            if p.id == player_id:
                p.connected = False

    async def send_to(self, room: Room, player_id: str, message: dict) -> None:
        ws = room.sockets.get(player_id)
        if ws is not None:
            await ws.send_json(message)

    async def broadcast(self, room: Room, message: dict) -> None:
        """Send an identical message to every connected player (e.g. chat)."""
        for player_id, ws in list(room.sockets.items()):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(room, player_id)

    async def broadcast_state(self, room: Room) -> None:
        """Send each connected player their own redacted view of the game/lobby."""
        for player_id, ws in list(room.sockets.items()):
            if room.game is not None:
                payload = {"type": "state_update", "state": room.game.to_state(player_id)}
            else:
                payload = {"type": "lobby_update", "lobby": room.lobby_snapshot()}
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(room, player_id)
