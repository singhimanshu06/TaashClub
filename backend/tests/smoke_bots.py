"""End-to-end bot game over WebSockets: 1 human (driven by this test) + 3 bots.

Creates a 4-player room, joins 1 human (a real socket), asks the server to fill
the remaining 3 seats with bots, and starts the game. The server's bot driver
plays the 3 bot seats; this test only drives the human's own turns (bid + play),
proving the bot driver correctly interleaves with a participating human across a
full match to game_end.

Usage: start the server, then `python tests/smoke_bots.py`.
Set LAKDI_TRICK_HOLD=0 and a small LAKDI_BOT_AUTO_ADVANCE to run it fast.
"""
import asyncio
import json
import os
import urllib.request

import websockets

PORT = os.environ.get("LAKDI_PORT", "8000")
BASE = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}"


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req).read())


async def main():
    code = post("/rooms", {"num_players": 4, "variant": "single_run"})["code"]
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

    # Fill remaining seats with bots and start the game.
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
            assert s["num_players"] == 4
            bot_seats = sum(1 for p in s["players"] if p.get("is_bot"))
            assert bot_seats == 3, f"expected 3 bots, got {bot_seats}"
            # single_run of 4p has 13 rounds -> 12 round-end transitions.
            assert len(rounds_done) == 12, f"expected 12 round-ends, got {len(rounds_done)}"
            print("BOT GAME OVER — final scoreboard:")
            for row in board:
                print(f"  {row['rank']}. {row['name']}: {row['total_score']}")
            print(f"OK: 1 human + 3 bots played a full game ({len(rounds_done)} round-end(s))")
            break

        cur = s.get("current_player_id")
        if phase == "bidding" and cur == human:
            await ws.send(json.dumps({"type": "place_bid", "value": 1}))
        elif phase == "playing" and cur == human and not s.get("awaiting_trick_clear"):
            legal = s.get("your_legal_cards")
            if legal:
                await ws.send(json.dumps({"type": "play_card", "card": legal[0]}))
        elif phase == "round_end":
            rounds_done.add(s.get("round_index"))
        await asyncio.sleep(0.03)

    task.cancel()
    await ws.close()


asyncio.run(main())
