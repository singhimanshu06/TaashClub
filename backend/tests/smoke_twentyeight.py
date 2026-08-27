"""End-to-end Twenty-Eight bot game over WebSockets: 1 human + 3 bots.

Same shape as ``smoke_bots.py`` but for the Twenty-Eight engine: the human
host opens the auction at 14 (or passes), names trump when prompted, plays the
first legal card, and reveals trump whenever offered. The match runs to
game_end over 5 deals (room option ``deals``).

Usage: start the server, then `python tests/smoke_twentyeight.py`.
Set TAASHCLUB_TRICK_HOLD=0 and small TAASHCLUB_BOT_THINK_* to run it fast.
"""
import asyncio
import json
import os
import urllib.request

import websockets

PORT = os.environ.get("TAASHCLUB_PORT", "8000")
BASE = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}"


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"POST {path} failed: {e.code} {e.read().decode()}")


async def main():
    code = post("/rooms", {"game_type": "twentyeight", "num_players": 4, "options": {"deals": "5"}})["code"]
    human = post(f"/rooms/{code}/join", {"name": "Human"})["player_id"]

    ws = await websockets.connect(f"{WS}/ws/{code}?player_id={human}")
    latest = {}

    async def pump():
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "state_update":
                latest["state"] = msg["state"]
            elif msg.get("type") == "error":
                raise SystemExit(f"server error: {msg['message']}")

    task = asyncio.create_task(pump())

    await ws.send(json.dumps({"type": "add_bots"}))
    await ws.send(json.dumps({"type": "start_game"}))

    async def wait(cond, timeout=60):
        for _ in range(int(timeout / 0.02)):
            if cond():
                return
            await asyncio.sleep(0.02)
        raise SystemExit("timeout waiting for game state")

    await wait(lambda: "state" in latest)

    rounds_done = set()
    while True:
        await wait(lambda: "state" in latest)
        s = latest["state"]
        phase = s["phase"]

        if phase == "game_end":
            board = s["final_standings"]
            assert board and len(board) == 4
            assert len(s["round_history"]) == 5, f"expected 5 deals, got {len(s['round_history'])}"
            assert len(rounds_done) == 4, f"expected 4 round-ends, got {len(rounds_done)}"
            print("TWENTY-EIGHT GAME OVER — final scoreboard:")
            for row in board:
                print(f"  {row['rank']}. {row['name']}: {row['total_score']}")
            print("OK: 1 human + 3 bots played a full Twenty-Eight match (5 deals)")
            break

        cur = s.get("current_player_id")
        if phase == "bidding" and cur == human:
            if s.get("awaiting_trump"):
                await ws.send(json.dumps({"type": "action", "action": "set_trump", "params": {"suit": "S"}}))
            elif s.get("high_bid") is None:
                await ws.send(json.dumps({"type": "action", "action": "place_bid", "params": {"value": 14}}))
            else:
                await ws.send(json.dumps({"type": "action", "action": "pass"}))
        elif phase == "playing" and cur == human and not s.get("awaiting_trick_clear"):
            legal = s.get("your_legal_cards")
            if legal:
                await ws.send(json.dumps({"type": "action", "action": "play_card", "params": {"card": legal[0]}}))
        elif phase == "round_end":
            rounds_done.add(s.get("round_index"))
            await ws.send(json.dumps({"type": "action", "action": "advance_round"}))
        await asyncio.sleep(0.03)

    task.cancel()
    await ws.close()


asyncio.run(main())
