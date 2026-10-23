import asyncio
import json

import pytest

import app.main as main
from app.game.base import GameError
from app.game.room import RoomManager


def test_sliding_window_limiter_is_per_key_and_expires_events():
    limiter = main.SlidingWindowLimiter(2, 10)

    assert limiter.allow("one", now=100)
    assert limiter.allow("one", now=101)
    assert not limiter.allow("one", now=102)
    assert limiter.allow("two", now=102)
    assert limiter.allow("one", now=111)


def test_room_manager_enforces_limit_and_expires_abandoned_rooms():
    manager = RoomManager()
    first = manager.create_room("callbreak", 4, {}, max_active_rooms=1)
    first.last_activity_at -= 181

    with pytest.raises(GameError, match="maximum active room limit"):
        manager.create_room("callbreak", 4, {}, max_active_rooms=1)

    assert manager.cleanup_expired(180) == [first.code]
    second = manager.create_room("callbreak", 4, {}, max_active_rooms=1)
    assert second.code != first.code


def test_home_room_is_not_expired():
    manager = RoomManager()
    home = manager.get_default()
    home.last_activity_at -= 100000

    assert manager.cleanup_expired(180) == []
    assert manager.get("HOME") is home


class ReceiveWebSocket:
    def __init__(self, message):
        self.message = message
        self.closed = None

    async def receive(self):
        return self.message

    async def close(self, code=None, reason=None):
        self.closed = (code, reason)


def test_websocket_message_size_is_rejected():
    async def run():
        ws = ReceiveWebSocket({"type": "websocket.receive", "text": "x" * 10})
        with pytest.raises(main.WebSocketLimitExceeded):
            await main._receive_limited_json(ws, main.SlidingWindowLimiter(20, 1), "ip")
        assert ws.closed[0] == 1009

    old_limit = main.MAX_WS_MESSAGE_BYTES
    main.MAX_WS_MESSAGE_BYTES = 4
    try:
        asyncio.run(run())
    finally:
        main.MAX_WS_MESSAGE_BYTES = old_limit


def test_websocket_message_rate_is_rejected():
    async def run():
        ws = ReceiveWebSocket({"type": "websocket.receive", "text": json.dumps({"type": "chat"})})
        limiter = main.SlidingWindowLimiter(1, 1)
        await main._receive_limited_json(ws, limiter, "ip")
        with pytest.raises(main.WebSocketLimitExceeded):
            await main._receive_limited_json(ws, limiter, "ip")
        assert ws.closed[0] == 1013

    asyncio.run(run())
