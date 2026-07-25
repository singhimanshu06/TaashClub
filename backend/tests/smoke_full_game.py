"""End-to-end playthrough over WebSockets: 4 bots play a full game to game_end.

Usage: start the server, then `python tests/smoke_full_game.py`.
Verifies bidding, follow-suit legal play, round advancement, and final scoreboard.
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
    code = post("/rooms", {"game_type": "callbreak", "num_players": 4, "options": {"variant": "single_run"}})["code"]
    players = [post(f"/rooms/{code}/join", {"name": n})["player_id"]
               for n in ["Alice", "Bob", "Cara", "Dan"]]
    idx = {pid: i for i, pid in enumerate(players)}

    socks = []
    for pid in players:
        ws = await websockets.connect(f"{WS}/ws/{code}?player_id={pid}")
        socks.append(ws)

    latest = {}  # pid -> last state

    async def pump(pid, ws):
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "state_update":
                latest[pid] = msg["state"]
            elif msg.get("type") == "error":
                raise SystemExit(f"server error for {pid}: {msg['message']}")

    tasks = [asyncio.create_task(pump(pid, ws)) for pid, ws in zip(players, socks)]

    async def send(i, obj):
        await socks[i].send(json.dumps(obj))

    await send(0, {"type": "start_game"})

    async def wait(cond, timeout=5):
        for _ in range(int(timeout / 0.02)):
            if cond():
                return
            await asyncio.sleep(0.02)
        raise SystemExit("timeout waiting for game state")

    rounds_done = 0
    while True:
        await wait(lambda: len(latest) == 4)
        s = latest[players[0]]
        phase = s["phase"]

        if phase == "game_end":
            board = s["final_standings"]
            assert board and len(board) == 4
            print("GAME OVER — final scoreboard:")
            for row in board:
                print(f"  {row['rank']}. {row['name']}: {row['total_score']}")
            # 13 rounds total: round_end (advance_round) fires 12 times; the
            # final round goes straight to game_end.
            assert rounds_done == 12, f"expected 12 advances, got {rounds_done}"
            print("OK: played all 13 rounds through the socket layer")
            break

        cur = s["current_player_id"]
        if phase == "bidding" and cur:
            await send(idx[cur], {"type": "action", "action": "place_bid", "params": {"value": 1}})
        elif phase == "playing" and cur:
            me = latest[cur]
            legal = me["your_legal_cards"]
            if legal:
                await send(idx[cur], {"type": "action", "action": "play_card", "params": {"card": legal[0]}})
        elif phase == "round_end":
            rounds_done += 1
            await send(0, {"type": "action", "action": "advance_round"})
        await asyncio.sleep(0.03)

    for t in tasks:
        t.cancel()
    for ws in socks:
        await ws.close()


asyncio.run(main())
