"""Room lifecycle + WebSocket connection management (in-memory, MVP)."""
from __future__ import annotations

import random
import secrets
import string
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket

from .base import BaseGame, GameError, Player
from .names import random_bot_name
from .registry import GameSpec, get_game_spec

CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LEN = 4
CHAT_MAX_LEN = 300
CHAT_HISTORY = 200
MAX_SPECTATORS = 10


def _gen_code(rng: random.Random) -> str:
    return "".join(rng.choice(CODE_ALPHABET) for _ in range(CODE_LEN))


@dataclass
class Room:
    code: str
    game_type: str
    num_players: int
    options: dict
    host_id: Optional[str] = None
    players: list[Player] = field(default_factory=list)   # in join order
    game: Optional[BaseGame] = None
    sockets: dict[str, WebSocket] = field(default_factory=dict)
    # Spectators have their own credentials and sockets. They never become
    # players, so they do not consume seats or participate in player lifecycle.
    spectators: dict[str, "Spectator"] = field(default_factory=dict)
    spectator_sockets: dict[str, WebSocket] = field(default_factory=dict)
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
    def spec(self) -> GameSpec:
        return get_game_spec(self.game_type)

    @property
    def started(self) -> bool:
        return self.game is not None

    @property
    def has_bots(self) -> bool:
        return any(p.is_bot for p in self.players)

    def add_chat(self, author_id: str, text: str) -> Optional[dict]:
        text = (text or "").strip()[:CHAT_MAX_LEN]
        if not text:
            return None
        author = next((p for p in self.players if p.id == author_id), None)
        spectator = next((s for s in self.spectators.values() if s.chat_id == author_id), None)
        msg = {
            # Keep player_id for existing player chat consumers. Spectator chat
            # uses a separate non-secret author_id so the auth token is never
            # sent to other clients.
            "player_id": author.id if author else None,
            "author_id": author.id if author else (spectator.chat_id if spectator else author_id),
            "name": author.name if author else (spectator.name if spectator else "?"),
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

    def add_spectator(self, name: str) -> "Spectator":
        if not (self.started or self.is_full()):
            raise GameError("spectators can join once the room is full")
        if len(self.spectator_sockets) >= MAX_SPECTATORS:
            raise GameError("spectator limit reached")
        name = name.strip()[:20]
        if not name:
            raise GameError("spectator name is required")

        spectator_id = secrets.token_urlsafe(24)
        while spectator_id in self.spectators:
            spectator_id = secrets.token_urlsafe(24)
        spectator = Spectator(
            spectator_id=spectator_id,
            chat_id="spectator-" + secrets.token_hex(8),
            name=name,
        )
        self.spectators[spectator_id] = spectator
        return spectator

    def get_spectator(self, spectator_id: str) -> Optional["Spectator"]:
        return self.spectators.get(spectator_id)

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
        self.game = self.spec.engine_factory(self.num_players, self.options, self.players, random.Random())
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
        spec = self.spec
        return {
            "code": self.code,
            "game_type": self.game_type,
            "game_name": spec.display_name,
            "num_players": self.num_players,
            "options": self.options,
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

    def create_room(self, game_type: str, num_players: int, options: dict) -> Room:
        spec = get_game_spec(game_type)
        if not (spec.min_players <= num_players <= spec.max_players):
            raise GameError(
                f"{spec.display_name} supports {spec.min_players}-{spec.max_players} players"
            )
        code = _gen_code(self._rng)
        while code in self.rooms:
            code = _gen_code(self._rng)
        room = Room(code=code, game_type=game_type, num_players=num_players, options=options)
        self.rooms[code] = room
        return room

    def get(self, code: str) -> Room:
        room = self.rooms.get(code.upper())
        if room is None:
            raise GameError("room not found")
        return room


@dataclass
class Spectator:
    """A read-only room session; ``spectator_id`` is never exposed in chat."""

    spectator_id: str
    chat_id: str
    name: str


class ConnectionManager:
    """Tracks live sockets per room and broadcasts redacted state to each viewer."""

    async def connect(self, room: Room, player_id: str, ws: WebSocket) -> None:
        await ws.accept()
        room.sockets[player_id] = ws
        for p in room.players:
            if p.id == player_id:
                p.connected = True

    async def connect_spectator(self, room: Room, spectator_id: str, ws: WebSocket) -> None:
        await ws.accept()
        previous = room.spectator_sockets.get(spectator_id)
        if previous is not None and previous is not ws:
            try:
                await previous.close(code=4009)
            except Exception:
                pass
        room.spectator_sockets[spectator_id] = ws

    def disconnect(self, room: Room, player_id: str) -> None:
        room.sockets.pop(player_id, None)
        for p in room.players:
            if p.id == player_id:
                p.connected = False

    def disconnect_spectator(self, room: Room, spectator_id: str, ws: Optional[WebSocket] = None) -> None:
        # A reconnect can replace a socket. Do not let the old receive loop
        # remove the replacement when it eventually observes its close.
        if ws is None or room.spectator_sockets.get(spectator_id) is ws:
            room.spectator_sockets.pop(spectator_id, None)

    async def send_to(self, room: Room, player_id: str, message: dict) -> None:
        ws = room.sockets.get(player_id)
        if ws is not None:
            await ws.send_json(message)

    async def send_to_spectator(self, room: Room, spectator_id: str, message: dict) -> None:
        ws = room.spectator_sockets.get(spectator_id)
        if ws is not None:
            await ws.send_json(message)

    async def broadcast(self, room: Room, message: dict) -> None:
        """Send an identical message to every connected room client (e.g. chat)."""
        for player_id, ws in list(room.sockets.items()):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(room, player_id)
        for spectator_id, ws in list(room.spectator_sockets.items()):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect_spectator(room, spectator_id, ws)

    async def broadcast_state(self, room: Room) -> None:
        """Send each room client its redacted view of the game/lobby."""
        for player_id, ws in list(room.sockets.items()):
            if room.game is not None:
                state = room.game.to_state(player_id)
                # host_id is owned by the room, not the engine. Inject it into
                # every in-game state broadcast so clients can identify the host
                # even after a mid-game reload — at that point s.lobby is null
                # and no lobby_update will follow, so the client would otherwise
                # never learn who the host is, and host-only controls (e.g. the
                # "Next round" button on the round-end scoreboard) never appear.
                state["host_id"] = room.host_id
                payload = {"type": "state_update", "state": state}
            else:
                payload = {"type": "lobby_update", "lobby": room.lobby_snapshot()}
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(room, player_id)
        for spectator_id, ws in list(room.spectator_sockets.items()):
            if room.game is not None:
                state = room.game.to_state(None)
                state["host_id"] = room.host_id
                payload = {"type": "state_update", "state": state}
            else:
                payload = {"type": "lobby_update", "lobby": room.lobby_snapshot()}
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect_spectator(room, spectator_id, ws)
