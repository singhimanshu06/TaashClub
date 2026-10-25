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
    # Private credentials for explicit departures; player IDs are public in state.
    leave_tokens: dict[str, str] = field(default_factory=dict)
    # Reservations include REST joins that never establish a WebSocket.
    lobby_disconnected_at: dict[str, float] = field(default_factory=dict)
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
    created_at: float = field(default_factory=time.monotonic)
    last_activity_at: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_activity_at = time.monotonic()

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
        player = Player(id=secrets.token_urlsafe(16),
                        name=name.strip()[:20] or f"Player {len(self.players) + 1}",
                        join_order=len(self.players), connected=False)
        self.players.append(player)
        self.leave_tokens[player.id] = secrets.token_urlsafe(24)
        self.lobby_disconnected_at[player.id] = time.monotonic()
        self.touch()
        if self.host_id is None:
            self.host_id = player.id
        return player

    def remove_lobby_player(self, player_id: str) -> bool:
        """Release a seat, preserving join order and transferring host ownership."""
        if self.started:
            raise GameError("cannot remove a player after the game starts")
        if not self.has_player(player_id):
            return False
        self.players = [p for p in self.players if p.id != player_id]
        self.leave_tokens.pop(player_id, None)
        self.lobby_disconnected_at.pop(player_id, None)
        for seat, player in enumerate(self.players):
            player.join_order = seat
        if self.host_id == player_id:
            self.host_id = next((p.id for p in self.players if not p.is_bot), None)
        self.touch()
        return True

    def expire_lobby_seats(self, grace_seconds: float) -> list[str]:
        if self.started:
            return []
        now = time.monotonic()
        expired = [pid for pid, since in self.lobby_disconnected_at.items()
                   if pid not in self.sockets and now - since >= grace_seconds]
        for player_id in expired:
            self.remove_lobby_player(player_id)
        return expired

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
        self.touch()
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
        if any(not p.is_bot and not p.connected for p in self.players):
            raise GameError("all players must be connected to start")
        # Randomize the playing/bidding order once; it is fixed for the whole
        # game. join_order becomes the (now random) seat index the engine uses.
        shuffled = list(self.players)
        random.Random().shuffle(shuffled)
        for seat, p in enumerate(shuffled):
            p.join_order = seat
        self.game = self.spec.engine_factory(self.num_players, self.options, self.players, random.Random())
        self.game.start()
        self.lobby_disconnected_at.clear()

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

    def get_default(self) -> Room:
        """Return the stable Twenty-Eight shared room."""
        code = "HOME"
        room = self.rooms.get(code)
        if room is not None:
            return room

        game_type = "twentyeight"
        spec = get_game_spec(game_type)
        num_players = 4
        options = {
            key: schema["default"]
            for key, schema in spec.options_schema.items()
            if "default" in schema
        }
        room = Room(code=code, game_type=game_type, num_players=num_players, options=options)
        self.rooms[code] = room
        return room

    def create_room(self, game_type: str, num_players: int, options: dict,
                    max_active_rooms: int | None = None) -> Room:
        if max_active_rooms is not None:
            active_rooms = sum(code != "HOME" for code in self.rooms)
            if active_rooms >= max_active_rooms:
                raise GameError("maximum active room limit reached")
        spec = get_game_spec(game_type)
        if not (spec.min_players <= num_players <= spec.max_players):
            raise GameError(
                f"{spec.display_name} supports {spec.min_players}-{spec.max_players} players"
            )
        code = _gen_code(self._rng)
        while code == "HOME" or code in self.rooms:
            code = _gen_code(self._rng)
        room = Room(code=code, game_type=game_type, num_players=num_players, options=options)
        self.rooms[code] = room
        return room

    def cleanup_expired(self, max_age_seconds: float) -> list[str]:
        """Remove abandoned non-default rooms and cancel their background work."""
        now = time.monotonic()
        expired = []
        for code, room in list(self.rooms.items()):
            if (code == "HOME" or room.sockets or room.spectator_sockets
                    or room.conversion_timers):
                continue
            if now - room.last_activity_at < max_age_seconds:
                continue
            for task in list(room._bot_tasks):
                if not task.done():
                    task.cancel()
            for task in list(room.conversion_timers.values()):
                if not task.done():
                    task.cancel()
            self.rooms.pop(code, None)
            expired.append(code)
        return expired

    def get(self, code: str) -> Room:
        normalized = code.upper()
        room = self.rooms.get(normalized)
        if room is None and normalized == "HOME":
            room = self.get_default()
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

    async def connect(self, room: Room, player_id: str, ws: WebSocket) -> bool:
        await ws.accept()
        # A leave/expiry may have run while accept yielded.
        if not room.has_player(player_id):
            await ws.close(code=4003)
            return False
        room.touch()
        previous = room.sockets.get(player_id)
        room.sockets[player_id] = ws
        room.lobby_disconnected_at.pop(player_id, None)
        for p in room.players:
            if p.id == player_id:
                p.connected = True
        if previous is not None and previous is not ws:
            try:
                await previous.close(code=4009)
            except Exception:
                pass
        return room.sockets.get(player_id) is ws

    async def connect_spectator(self, room: Room, spectator_id: str, ws: WebSocket) -> None:
        await ws.accept()
        room.touch()
        previous = room.spectator_sockets.get(spectator_id)
        if previous is not None and previous is not ws:
            try:
                await previous.close(code=4009)
            except Exception:
                pass
        room.spectator_sockets[spectator_id] = ws

    def disconnect(self, room: Room, player_id: str, ws: Optional[WebSocket] = None) -> bool:
        if ws is not None and room.sockets.get(player_id) is not ws:
            return False
        room.sockets.pop(player_id, None)
        room.touch()
        for p in room.players:
            if p.id == player_id:
                p.connected = False
                if not room.started:
                    room.lobby_disconnected_at.setdefault(player_id, time.monotonic())
        return True

    def disconnect_spectator(self, room: Room, spectator_id: str, ws: Optional[WebSocket] = None) -> None:
        # A reconnect can replace a socket. Do not let the old receive loop
        # remove the replacement when it eventually observes its close.
        if ws is None or room.spectator_sockets.get(spectator_id) is ws:
            room.spectator_sockets.pop(spectator_id, None)
            room.touch()

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
                self.disconnect(room, player_id, ws)
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
                self.disconnect(room, player_id, ws)
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
