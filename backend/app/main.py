"""FastAPI app: REST for room create/join + WebSocket for real-time play."""
from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .game.engine import GameError
from .game.models import Card
from .game.room import ConnectionManager, RoomManager, Room
from .protocol import (
    CreateRoomRequest,
    CreateRoomResponse,
    JoinRoomRequest,
    JoinRoomResponse,
)

# How long a completed trick stays on the table before it clears. Override with
# LAKDI_TRICK_HOLD (e.g. 0 in automated tests).
TRICK_HOLD_SECONDS = float(os.environ.get("LAKDI_TRICK_HOLD", "5"))

app = FastAPI(title="LAKDI")

# In production set ALLOWED_ORIGINS to your Railway domain, e.g.:
#   ALLOWED_ORIGINS=https://lakdi.up.railway.app
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


@app.post("/rooms", response_model=CreateRoomResponse)
def create_room(req: CreateRoomRequest):
    try:
        room = rooms.create_room(req.num_players, req.variant)
    except GameError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CreateRoomResponse(code=room.code)


@app.post("/rooms/{code}/join", response_model=JoinRoomResponse)
def join_room(code: str, req: JoinRoomRequest):
    try:
        room = rooms.get(code)
        player = room.add_player(req.name)
    except GameError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JoinRoomResponse(player_id=player.id, join_order=player.join_order, code=room.code)


@app.get("/rooms/{code}")
def get_room(code: str):
    try:
        room = rooms.get(code)
    except GameError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return room.lobby_snapshot()


@app.websocket("/ws/{code}")
async def game_socket(ws: WebSocket, code: str, player_id: str):
    try:
        room = rooms.get(code)
    except GameError:
        await ws.close(code=4004)
        return
    if not room.has_player(player_id):
        await ws.close(code=4003)
        return

    await connections.connect(room, player_id, ws)
    await connections.send_to(room, player_id, {"type": "chat_history", "messages": room.chat_log})
    await connections.broadcast_state(room)

    try:
        while True:
            msg = await ws.receive_json()
            await handle_event(room, player_id, msg)
    except WebSocketDisconnect:
        connections.disconnect(room, player_id)
        await connections.broadcast_state(room)


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
        elif event == "place_bid":
            _require_game(room).place_bid(player_id, int(msg["value"]))
        elif event == "play_card":
            _require_game(room).play_card(player_id, Card.from_dict(msg["card"]))
        elif event == "advance_round":
            _require_game(room).advance_round()
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

    await connections.broadcast_state(room)

    # A completed trick is held on the table, then cleared after a short delay.
    # Guard with room.clearing so only one hold task runs per trick.
    if room.game and room.game.awaiting_trick_clear and not room.clearing:
        room.clearing = True
        asyncio.create_task(_hold_and_clear_trick(room))


async def _hold_and_clear_trick(room: Room) -> None:
    try:
        await asyncio.sleep(TRICK_HOLD_SECONDS)
        if room.game and room.game.awaiting_trick_clear:
            room.game.commit_trick()
            # Release the guard *before* broadcasting. broadcast_state() awaits
            # (yields to the event loop) and commit_trick() has already reopened
            # play, so the guard must be clear here — otherwise a trick that
            # completes during the broadcast would find clearing=True, skip
            # scheduling its own clear, and the round would deadlock.
            room.clearing = False
            await connections.broadcast_state(room)
    finally:
        room.clearing = False


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
