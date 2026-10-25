"""FastAPI app: REST for room create/join + WebSocket for real-time play."""
from __future__ import annotations

import asyncio
import json
import os
import random
import secrets
import time
from collections import deque
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .game.base import GameError, Phase
from .game.room import MAX_SPECTATORS, ConnectionManager, RoomManager, Room
from .game.registry import get_game_spec, list_games
from .protocol import (
    CreateRoomRequest,
    CreateRoomResponse,
    GameInfo,
    JoinRoomRequest,
    JoinRoomResponse,
    LeaveRoomRequest,
    SpectateRoomRequest,
    SpectateRoomResponse,
)

# How long a completed trick stays on the table before it clears. Override with
# TAASHCLUB_TRICK_HOLD (e.g. 0 in automated tests).
TRICK_HOLD_SECONDS = float(os.environ.get("TAASHCLUB_TRICK_HOLD", "3"))
# Bot "thinking" delay range (seconds). Jittered per action for a human feel.
BOT_THINK_MIN = float(os.environ.get("TAASHCLUB_BOT_THINK_MIN", "0.6"))
BOT_THINK_MAX = float(os.environ.get("TAASHCLUB_BOT_THINK_MAX", "1.2"))
# How long a bot game waits in ROUND_END before auto-advancing. Set high enough
# for a human to read the scoreboard, low enough to keep the game moving. 0
# disables auto-advance (the human must always click).
BOT_AUTO_ADVANCE_SECONDS = float(os.environ.get("TAASHCLUB_BOT_AUTO_ADVANCE", "6"))
# How long to wait after a player disconnects before converting their seat to a
# bot (so the game continues for everyone else). If they reconnect before this
# fires, the conversion is cancelled.
BOT_CONVERSION_GRACE_SECONDS = float(os.environ.get("TAASHCLUB_BOT_CONVERSION_GRACE", "60"))
MAX_ACTIVE_CONNECTIONS = int(os.environ.get("MAX_ACTIVE_CONNECTIONS", "50"))
MAX_IN_FLIGHT_HTTP = int(os.environ.get("MAX_IN_FLIGHT_HTTP", "20"))
REST_RATE_LIMIT = int(os.environ.get("REST_RATE_LIMIT", "30"))
REST_RATE_WINDOW_SECONDS = float(os.environ.get("REST_RATE_WINDOW_SECONDS", "60"))
WS_MESSAGES_PER_SECOND = int(os.environ.get("WS_MESSAGES_PER_SECOND", "20"))
MAX_WS_MESSAGE_BYTES = int(os.environ.get("MAX_WS_MESSAGE_BYTES", "65536"))
MAX_ACTIVE_ROOMS = int(os.environ.get("MAX_ACTIVE_ROOMS", "10"))
EMPTY_ROOM_TTL_SECONDS = float(os.environ.get("EMPTY_ROOM_TTL_SECONDS", "180"))
LOBBY_RECONNECT_GRACE_SECONDS = float(os.environ.get("LOBBY_RECONNECT_GRACE_SECONDS", "30"))

app = FastAPI(title="TaashClub")


class AdmissionLimitMiddleware:
    """Bound total live scopes and simultaneous HTTP work in this process."""

    def __init__(self, app: Callable):
        self.app = app
        self.active_connections = 0
        self.active_http = 0

    async def __call__(self, scope: dict, receive: Callable, send: Callable):
        scope_type = scope["type"]
        if scope_type not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if self.active_connections >= MAX_ACTIVE_CONNECTIONS:
            if scope_type == "websocket":
                await send({"type": "websocket.close", "code": 1013})
            else:
                await self._reject_http(send, 503, "server is temporarily busy")
            return

        if scope_type == "http" and self.active_http >= MAX_IN_FLIGHT_HTTP:
            await self._reject_http(send, 503, "server is temporarily busy")
            return

        self.active_connections += 1
        if scope_type == "http":
            self.active_http += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.active_connections -= 1
            if scope_type == "http":
                self.active_http -= 1

    @staticmethod
    async def _reject_http(send: Callable, status: int, message: str) -> None:
        body = json.dumps({"detail": message}).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"retry-after", b"1"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        events = self._events.setdefault(key, deque())
        cutoff = now - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(now)
        return True

    def prune(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        cutoff = now - self.window_seconds
        for key in list(self._events):
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                del self._events[key]


app.add_middleware(AdmissionLimitMiddleware)

# In production set ALLOWED_ORIGINS to your deployment domain, e.g.:
#   ALLOWED_ORIGINS=https://taashclub.fly.dev
# Leave unset (or "*") for local dev.
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "*")
_origins = [o.strip() for o in _raw_origins.split(",")] if _raw_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

rooms = RoomManager()
connections = ConnectionManager()
rest_limiters = {
    "create": SlidingWindowLimiter(REST_RATE_LIMIT, REST_RATE_WINDOW_SECONDS),
    "join": SlidingWindowLimiter(REST_RATE_LIMIT, REST_RATE_WINDOW_SECONDS),
    "spectate": SlidingWindowLimiter(REST_RATE_LIMIT, REST_RATE_WINDOW_SECONDS),
}


def _client_ip(headers, client) -> str:
    # Fly Proxy supplies this header. The fallback keeps local development useful.
    return headers.get("fly-client-ip") or (client.host if client else "unknown")


def _check_rest_limit(request: Request, endpoint: str) -> None:
    limiter = rest_limiters[endpoint]
    if limiter.allow(_client_ip(request.headers, request.client)):
        return
    raise HTTPException(
        status_code=429,
        detail="too many requests",
        headers={"Retry-After": str(max(1, int(REST_RATE_WINDOW_SECONDS)))},
    )


async def _cleanup_rooms_loop() -> None:
    while True:
        await asyncio.sleep(1)
        for room in list(rooms.rooms.values()):
            if room.expire_lobby_seats(LOBBY_RECONNECT_GRACE_SECONDS):
                await _after_state_change(room)
        rooms.cleanup_expired(EMPTY_ROOM_TTL_SECONDS)
        for limiter in rest_limiters.values():
            limiter.prune()


@app.on_event("startup")
async def start_cleanup_task() -> None:
    app.state.room_cleanup_task = asyncio.create_task(_cleanup_rooms_loop())


@app.on_event("shutdown")
async def stop_cleanup_task() -> None:
    task = getattr(app.state, "room_cleanup_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class WebSocketLimitExceeded(Exception):
    pass


async def _receive_limited_json(ws: WebSocket, limiter: SlidingWindowLimiter, key: str) -> dict:
    if not limiter.allow(key):
        await ws.close(code=1013, reason="message rate limit exceeded")
        raise WebSocketLimitExceeded
    message = await ws.receive()
    if message.get("type") == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    data = message.get("bytes")
    if data is None:
        data = (message.get("text") or "").encode()
    if len(data) > MAX_WS_MESSAGE_BYTES:
        await ws.close(code=1009, reason="message too large")
        raise WebSocketLimitExceeded
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("message must be an object")
    return value


@app.get("/games", response_model=list[GameInfo])
def games():
    return list_games()


@app.post("/rooms", response_model=CreateRoomResponse)
def create_room(req: CreateRoomRequest, request: Request):
    _check_rest_limit(request, "create")
    rooms.cleanup_expired(EMPTY_ROOM_TTL_SECONDS)
    try:
        room = rooms.create_room(
            req.game_type, req.num_players, req.options, MAX_ACTIVE_ROOMS
        )
    except GameError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CreateRoomResponse(code=room.code)


@app.post("/rooms/{code}/join", response_model=JoinRoomResponse)
async def join_room(code: str, req: JoinRoomRequest, request: Request):
    _check_rest_limit(request, "join")
    try:
        room = rooms.get(code)
        room.expire_lobby_seats(LOBBY_RECONNECT_GRACE_SECONDS)
        player = room.add_player(req.name)
    except GameError as e:
        raise HTTPException(status_code=400, detail=str(e))
    response = JoinRoomResponse(player_id=player.id, leave_token=room.leave_tokens[player.id],
                                join_order=player.join_order, code=room.code)
    await _after_state_change(room)
    return response


@app.post("/rooms/{code}/leave")
async def leave_room(code: str, req: LeaveRoomRequest):
    # Missing rooms/players are already departed, so retries remain harmless.
    try:
        room = rooms.get(code)
    except GameError:
        return {"left": True}
    if not room.has_player(req.player_id):
        return {"left": True}
    token = room.leave_tokens.get(req.player_id)
    if token is None or not secrets.compare_digest(token, req.leave_token):
        raise HTTPException(status_code=403, detail="invalid player session")

    ws = room.sockets.get(req.player_id)
    connections.disconnect(room, req.player_id)
    if not room.started:
        room.remove_lobby_player(req.player_id)
    else:
        # Never remove seats from a running engine. Preserve its reconnect/bot
        # takeover policy, even if a game started while Leave was in flight.
        _schedule_conversion_if_needed(room, req.player_id)
        await _broadcast_player_status(room, req.player_id, False)
    if ws is not None:
        try:
            await ws.close(code=4003)
        except Exception:
            pass
    await _after_state_change(room)
    return {"left": True}


@app.post("/rooms/{code}/spectate", response_model=SpectateRoomResponse)
def spectate_room(code: str, req: SpectateRoomRequest, request: Request):
    _check_rest_limit(request, "spectate")
    try:
        room = rooms.get(code)
        spectator = room.add_spectator(req.name)
    except GameError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SpectateRoomResponse(
        spectator_id=spectator.spectator_id,
        chat_id=spectator.chat_id,
        code=room.code,
    )


@app.get("/rooms/{code}")
def get_room(code: str):
    try:
        room = rooms.get(code)
    except GameError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return room.lobby_snapshot()


@app.websocket("/ws/{code}")
async def game_socket(
    ws: WebSocket,
    code: str,
    player_id: str | None = None,
    spectator_id: str | None = None,
):
    try:
        room = rooms.get(code)
    except GameError:
        # Must accept the WebSocket before closing, otherwise the custom close
        # code is lost and the client sees an abnormal 1006 close (which it
        # treats as a transient drop and retries forever instead of giving up).
        await ws.accept()
        await ws.close(code=4004)
        return
    if player_id is None and spectator_id is None:
        await ws.accept()
        await ws.close(code=4003)
        return

    if player_id is None:
        spectator = room.get_spectator(spectator_id or "")
        if spectator is None:
            await ws.accept()
            await ws.close(code=4005)
            return
        if len(room.spectator_sockets) >= MAX_SPECTATORS and spectator_id not in room.spectator_sockets:
            await ws.accept()
            await ws.close(code=4008)
            return

        await connections.connect_spectator(room, spectator.spectator_id, ws)
        message_limiter = SlidingWindowLimiter(WS_MESSAGES_PER_SECOND, 1)
        client_ip = _client_ip(ws.headers, ws.client)
        await connections.send_to_spectator(
            room,
            spectator.spectator_id,
            {"type": "chat_history", "messages": room.chat_log},
        )
        await _after_state_change(room)
        try:
            while True:
                msg = await _receive_limited_json(ws, message_limiter, client_ip)
                room.touch()
                await handle_spectator_event(room, spectator.spectator_id, msg)
        except (WebSocketDisconnect, WebSocketLimitExceeded, ValueError, json.JSONDecodeError):
            connections.disconnect_spectator(room, spectator.spectator_id, ws)
        return

    if not room.has_player(player_id):
        await ws.accept()
        await ws.close(code=4003)
        return

    if not await connections.connect(room, player_id, ws):
        return
    message_limiter = SlidingWindowLimiter(WS_MESSAGES_PER_SECOND, 1)
    client_ip = _client_ip(ws.headers, ws.client)

    # Player reconnected — cancel any pending disconnect→bot conversion. If
    # they were already converted (came back late), take back control.
    _cancel_conversion(room, player_id)
    for p in room.players:
        if p.id == player_id:
            p.is_bot = False

    try:
        # Private delivery also upgrades sessions saved before explicit leave
        # credentials were introduced. Never include this token in lobby state.
        await connections.send_to(room, player_id, {
            "type": "session_credentials", "leave_token": room.leave_tokens[player_id],
        })
        await _broadcast_player_status(room, player_id, True)
        await connections.send_to(room, player_id, {"type": "chat_history", "messages": room.chat_log})
        await _after_state_change(room)
        while True:
            msg = await _receive_limited_json(ws, message_limiter, client_ip)
            if room.sockets.get(player_id) is not ws:
                break
            room.touch()
            await handle_event(room, player_id, msg)
    except (WebSocketDisconnect, WebSocketLimitExceeded, ValueError, json.JSONDecodeError):
        pass
    finally:
        if connections.disconnect(room, player_id, ws):
            await _broadcast_player_status(room, player_id, False)
            _schedule_conversion_if_needed(room, player_id)
            await _after_state_change(room)


async def handle_event(room: Room, player_id: str, msg: dict) -> None:
    event = msg.get("type")

    # Chat is broadcast on its own channel and never touches game state.
    if event == "chat":
        chat_msg = room.add_chat(player_id, str(msg.get("text", "")))
        if chat_msg:
            await connections.broadcast(room, {"type": "chat", "message": chat_msg})
        return

    try:
        if event == "start_game":
            room.start_game(player_id)
        elif event == "add_bot":
            room.add_one_bot(player_id)
        elif event == "add_bots":
            room.add_bots(player_id)
        elif event == "action":
            # Generic in-game action envelope: {"type":"action","action":<name>,"params":{...}}
            # The engine owns all game-specific dispatch (place_bid, play_card,
            # advance_round, ...). Adding a new game needs no changes here.
            # A human action supersedes any pending bot auto-advance.
            _cancel_auto_advance(room)
            game = _require_game(room)
            action = msg["action"]
            params = msg.get("params") or {}
            game.apply_action(player_id, action, params)
        else:
            await connections.send_to(room, player_id,
                                      {"type": "error", "message": f"unknown event: {event}"})
            return
    except GameError as e:
        await connections.send_to(room, player_id, {"type": "error", "message": str(e)})
        return
    except (KeyError, ValueError, TypeError):
        await connections.send_to(room, player_id, {"type": "error", "message": "malformed message"})
        return

    await _after_state_change(room)


async def handle_spectator_event(room: Room, spectator_id: str, msg: dict) -> None:
    """Handle the only command available to spectators: chat."""
    spectator = room.get_spectator(spectator_id)
    if spectator is None:
        return
    if msg.get("type") == "chat":
        chat_msg = room.add_chat(spectator.chat_id, str(msg.get("text", "")))
        if chat_msg:
            await connections.broadcast(room, {"type": "chat", "message": chat_msg})
        return
    await connections.send_to_spectator(
        room,
        spectator_id,
        {"type": "error", "message": "Spectators can only send chat messages."},
    )


async def _after_state_change(room: Room) -> None:
    """Central post-action routine: broadcast, then drive the async side
    effects (trick hold, bot turns, bot auto-advance).

    Every state mutation path (client events, bot actions, trick commit) funnels
    through here so the bots see a consistent post-state hook.
    """
    await connections.broadcast_state(room)

    game = room.game
    if game is None:
        return

    # A completed trick is held on the table, then cleared after a short delay.
    if game.awaiting_trick_clear and not room.clearing:
        room.clearing = True
        asyncio.create_task(_hold_and_clear_trick(room))
        return

    # If it's a bot's turn to act, schedule its "think then act" task (one at a
    # time per room — bot_busy guards against duplicate scheduling). The task
    # ref is kept in room._bot_tasks so it isn't GC'd before it completes.
    if game.phase in (Phase.BIDDING, Phase.PLAYING, Phase.EXCHANGE) and not room.bot_busy:
        current = game.players[game.turn_idx]
        if current.is_bot:
            room.bot_busy = True
            t = asyncio.create_task(_bot_act(room, current.id))
            room._bot_tasks.add(t)
            t.add_done_callback(room._bot_tasks.discard)

    # Bot games auto-advance from ROUND_END so the match keeps moving on its own.
    if game.phase == Phase.ROUND_END and room.has_bots and not room.auto_advance_busy:
        room.auto_advance_busy = True
        t = asyncio.create_task(_bot_auto_advance(room))
        room._bot_tasks.add(t)
        t.add_done_callback(room._bot_tasks.discard)


async def _hold_and_clear_trick(room: Room) -> None:
    try:
        await asyncio.sleep(TRICK_HOLD_SECONDS)
        if room.game and room.game.awaiting_trick_clear:
            room.game.commit_trick()
            # Release the guard *before* broadcasting. _after_state_change()
            # awaits (yields to the event loop) and commit_trick() has already
            # reopened play, so the guard must be clear here — otherwise a trick
            # that completes during the broadcast would find clearing=True, skip
            # scheduling its own clear, and the round would deadlock.
            room.clearing = False
            await _after_state_change(room)
    finally:
        room.clearing = False


async def _bot_act(room: Room, player_id: str) -> None:
    """Think for a short jittered delay, then apply one bot action directly to
    the engine and re-enter the post-state-change loop.

    The bot brain (looked up from the room's game spec) decides which action is
    needed — the driver never branches on game-specific phases. The
    ``bot_busy`` guard is released *synchronously* before re-entering the loop
    (no await gap), so the loop can schedule the next bot immediately. It is
    NOT cleared in a ``finally`` — doing so would clobber the guard that
    ``_after_state_change`` just set for the next bot and drop that task's only
    reference, letting the loop GC it mid-flight. On sleep cancellation we
    release explicitly so the room doesn't deadlock.
    """
    try:
        await asyncio.sleep(random.uniform(BOT_THINK_MIN, BOT_THINK_MAX))
    except asyncio.CancelledError:
        room.bot_busy = False
        raise
    # Hand off the slot synchronously: the next _after_state_change call below
    # may set bot_busy=True again for the following bot.
    room.bot_busy = False
    game = room.game
    if game is None:
        return
    # Abort if the turn moved away or the player reconnected (no longer a bot).
    current = game.players[game.turn_idx]
    if current.id != player_id or not current.is_bot:
        return
    if game.phase in (Phase.BIDDING, Phase.PLAYING, Phase.EXCHANGE) and not game.awaiting_trick_clear:
        brain = room.spec.bot_brain
        action, params = brain.decide_action(game, player_id, random.Random())
        game.apply_action(player_id, action, params)
    else:
        return
    await _after_state_change(room)


async def _bot_auto_advance(room: Room) -> None:
    """Wait, then advance to the next round if we're still sitting at ROUND_END.

    A human clicking advance supersedes this via ``_cancel_auto_advance``; the
    phase check makes the task a no-op if state has already moved on. The guard
    is released before re-entering the loop for the same reason as ``_bot_act``.
    """
    try:
        await asyncio.sleep(BOT_AUTO_ADVANCE_SECONDS)
    except asyncio.CancelledError:
        room.auto_advance_busy = False
        raise
    room.auto_advance_busy = False
    game = room.game
    if game is not None and game.phase == Phase.ROUND_END:
        game.advance_round()
        await _after_state_change(room)


def _cancel_auto_advance(room: Room) -> None:
    """Cancel a pending auto-advance so a manual advance can't double-fire."""
    room.auto_advance_busy = False
    # Cancel any in-flight auto-advance coroutine still pending. We identify
    # them by their coroutine's qualified name (robust across calls).
    for t in list(room._bot_tasks):
        if not t.done() and "auto_advance" in getattr(t.get_coro(), "__qualname__", ""):
            t.cancel()


async def _broadcast_player_status(room: Room, player_id: str, connected: bool) -> None:
    player = next((p for p in room.players if p.id == player_id), None)
    if player is None:
        return
    await connections.broadcast(room, {
        "type": "player_status",
        "player_id": player_id,
        "name": player.name,
        "connected": connected,
    })


def _schedule_conversion_if_needed(room: Room, player_id: str) -> None:
    """After a disconnect, start the grace timer to convert the seat to a bot.

    Only fires if a game is in progress (not lobby/game_end) and the player
    isn't already a bot. If the player reconnects before the timer fires, the
    conversion is cancelled (see _cancel_conversion in the connect path).
    """
    game = room.game
    if game is None or game.phase in (Phase.LOBBY, Phase.GAME_END):
        return
    player = next((p for p in room.players if p.id == player_id), None)
    if player is None or player.is_bot:
        return
    _cancel_conversion(room, player_id)  # de-dupe in case one is already pending
    t = asyncio.create_task(_maybe_convert_to_bot(room, player_id))
    room.conversion_timers[player_id] = t


def _cancel_conversion(room: Room, player_id: str) -> None:
    """Cancel a pending disconnect→bot conversion (player reconnected in time)."""
    t = room.conversion_timers.pop(player_id, None)
    if t is not None and not t.done():
        t.cancel()


async def _maybe_convert_to_bot(room: Room, player_id: str) -> None:
    """After the grace period, convert a still-disconnected player to a bot.

    If all human players are now gone (no connected non-bot players), end the
    game immediately instead — there's nobody left to play for.
    """
    try:
        await asyncio.sleep(BOT_CONVERSION_GRACE_SECONDS)
    except asyncio.CancelledError:
        return

    room.conversion_timers.pop(player_id, None)
    game = room.game
    if game is None or game.phase in (Phase.LOBBY, Phase.GAME_END):
        return

    player = next((p for p in room.players if p.id == player_id), None)
    if player is None or player.is_bot or player.connected:
        return  # reconnected, already a bot, or gone — nothing to do

    player.is_bot = True

    # If no connected human players remain, end the game — nobody to play for.
    humans_alive = any(not p.is_bot and p.connected for p in room.players)
    if not humans_alive:
        # Cancel any other pending conversions — the game is over.
        for pid in list(room.conversion_timers):
            _cancel_conversion(room, pid)
        game.force_end()

    await _after_state_change(room)


def _require_game(room):
    if room.game is None:
        raise GameError("game has not started")
    return room.game


# Serve the built frontend (single origin) when a production build exists.
# This lets one shared URL (e.g. a tunnel to :8000) deliver both the app and
# the API/WebSocket. Declared LAST so /rooms and /ws take precedence.
# Build it with: cd frontend && npm run build
_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")
