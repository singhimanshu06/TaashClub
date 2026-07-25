"""Request/response schemas for REST endpoints."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CreateRoomRequest(BaseModel):
    game_type: str = Field(..., min_length=1)
    num_players: int = Field(..., ge=1)
    options: dict = Field(default_factory=dict)


class CreateRoomResponse(BaseModel):
    code: str


class JoinRoomRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=20)


class JoinRoomResponse(BaseModel):
    player_id: str
    join_order: int
    code: str


class GameInfo(BaseModel):
    """One entry in the ``GET /games`` listing (frontend game picker)."""
    game_type: str
    display_name: str
    description: str
    min_players: int
    max_players: int
    options_schema: dict
