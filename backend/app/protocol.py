"""Request/response schemas for REST endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .game.models import Variant


class CreateRoomRequest(BaseModel):
    num_players: int = Field(..., ge=4, le=6)
    variant: Variant


class CreateRoomResponse(BaseModel):
    code: str


class JoinRoomRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=20)


class JoinRoomResponse(BaseModel):
    player_id: str
    join_order: int
    code: str
