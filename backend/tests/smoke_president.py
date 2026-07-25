"""End-to-end President bot game over WebSockets: 1 human + 4 bots.

Creates a 5-player President room, joins 1 human, fills the rest with bots, and
starts the game. The server's bot driver plays the 4 bot seats (including the
between-round card exchange); this test only drives the human's own turns,
proving the generic action-envelope + bot driver works for a second game.

Usage: start the server, then `python tests/smoke_president.py`.
Fast mode: TAASHCLUB_BOT_THINK_MIN=0.01 TAASHCLUB_BOT_THINK_MAX=0.05
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
    return json.loads(urllib.request.urlopen(req).read())


async def main():
    code = post("/rooms", {"game_type": "president", "num_players": 5, "options": {"rounds": "3"}})["code"]
    human = post(f"/rooms/{code}/join", {"name": "Human"})["player_id"]

    ws = await websockets.connect(f"{WS}/ws/{code}?player_id={human}")
    latest = {}

    async def pump():
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "state_update":
                latest["state"] = msg["state"]
            elif msg.get("type") == "lobby_update":
                latest["lobby"] = msg["lobby"]
            elif msg.get("type") == "error":
                print(f"server error: {msg['message']}")

    task = asyncio.create_task(pump())

    await ws.send(json.dumps({"type": "add_bots"}))
    await ws.send(json.dumps({"type": "start_game"}))

    async def wait(cond, timeout=120):
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
            assert board and len(board) == 5
            assert s["num_players"] == 5
            bot_seats = sum(1 for p in s["players"] if p.get("is_bot"))
            assert bot_seats == 4, f"expected 4 bots, got {bot_seats}"
            print("PRESIDENT GAME OVER — final scoreboard:")
            for row in board:
                print(f"  {row['rank']}. {row['name']}: {row['total_score']}")
            print(f"OK: 1 human + 4 bots played {len(rounds_done)} round(s)")
            break

        cur = s.get("current_player_id")
        if phase == "playing" and cur == human:
            legal = s.get("your_legal_actions") or []
            # Pick the first legal action (any of play_combo / pass / bomb).
            if legal:
                a = legal[0]
                await ws.send(json.dumps({"type": "action", "action": a["action"], "params": {k: v for k, v in a.items() if k != "action"}}))
        elif phase == "exchange" and cur == human:
            # We're the receiver (President/VP): return our lowest card(s).
            es = s.get("exchange") or {}
            count = es.get("count", 0)
            me = next(p for p in s["players"] if p["id"] == human)
            hand = me.get("hand") or []
            if count and hand:
                # return the `count` lowest cards by rank (2 treated as highest).
                sorted_hand = sorted(hand, key=lambda c: (15 if c["rank"] == 2 else c["rank"]))
                ret = sorted_hand[:count]
                await ws.send(json.dumps({"type": "action", "action": "choose_return", "params": {"cards": ret}}))
        elif phase == "round_end":
            rounds_done.add(s.get("round_index"))
            # The server's bot auto-advance driver moves us to the next round
            # (deals + exchange); no client action needed.
        await asyncio.sleep(0.03)

    task.cancel()
    await ws.close()


asyncio.run(main())
