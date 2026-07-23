"""Test: when one human disconnects, their seat converts to a bot and game continues.

4-player friends game. After the game starts, disconnect one non-host player.
After the grace period, that seat should be a bot (is_bot=True) and the game
should continue to completion (driven by the remaining humans + the converted bot).
"""
import asyncio
import json
import os
import urllib.request

import websockets

PORT = os.environ.get("LAKDI_PORT", "8000")
BASE = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}"
GRACE = float(os.environ.get("LAKDI_BOT_CONVERSION_GRACE", "30"))


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req).read())


async def main():
    code = post("/rooms", {"num_players": 4, "variant": "single_run"})["code"]
    players = [post(f"/rooms/{code}/join", {"name": n})["player_id"]
               for n in ["Alice", "Bob", "Cara", "Dan"]]
    idx = {pid: i for i, pid in enumerate(players)}

    socks = []
    for pid in players:
        ws = await websockets.connect(f"{WS}/ws/{code}?player_id={pid}")
        socks.append(ws)

    latest = {}

    async def pump(pid, ws):
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "state_update":
                latest[pid] = msg["state"]
            elif msg.get("type") == "error":
                raise SystemExit(f"server error for {pid}: {msg['message']}")

    tasks = [asyncio.create_task(pump(pid, ws)) for pid, ws in zip(players, socks)]

    await socks[0].send(json.dumps({"type": "start_game"}))

    async def wait(cond, timeout=10):
        for _ in range(int(timeout / 0.05)):
            if cond():
                return
            await asyncio.sleep(0.05)
        raise SystemExit("timeout")

    await wait(lambda: all(pid in latest for pid in players))

    # Wait for bidding to start, then disconnect Dan (player 3, non-host).
    await wait(lambda: latest[players[0]].get("phase") in ("bidding", "playing"))
    print(f"Phase={latest[players[0]]['phase']}. Disconnecting Dan (player 3)...")
    await socks[3].close()
    tasks[3].cancel()

    # Wait for the grace period + conversion.
    print(f"Waiting {GRACE + 5}s for conversion...")
    await asyncio.sleep(GRACE + 5)

    # Check Dan's seat is now a bot.
    state = latest.get(players[0])
    if state is None:
        # Re-read from Alice's stream.
        await asyncio.sleep(0.2)
        state = latest.get(players[0])

    dan_player = next((p for p in state["players"] if p["id"] == players[3]), None)
    print(f"Dan after grace: is_bot={dan_player['is_bot']}, connected={dan_player['connected']}")
    assert dan_player["is_bot"], "Dan should have been converted to a bot"
    print("OK: disconnected player converted to bot after grace period")

    # Now drive the remaining 3 humans + 1 bot to game completion.
    async def send(i, obj):
        await socks[i].send(json.dumps(obj))

    rounds_done = set()
    while True:
        await wait(lambda: any(pid in latest for pid in players[:3]))
        # Use the latest state from any connected human.
        s = None
        for pid in players[:3]:
            if pid in latest:
                s = latest[pid]
                break
        if s is None:
            raise SystemExit("no state available")

        if s["phase"] == "game_end":
            board = s["final_standings"]
            assert board and len(board) == 4
            print("GAME OVER — final scoreboard:")
            for row in board:
                print(f"  {row['rank']}. {row['name']}: {row['total_score']}")
            print(f"OK: 3 humans + 1 converted bot played to game_end ({len(rounds_done)} round-ends)")
            break

        cur = s.get("current_player_id")
        if s["phase"] == "bidding" and cur in players[:3]:
            await send(idx[cur], {"type": "place_bid", "value": 1})
        elif s["phase"] == "playing" and cur in players[:3] and not s.get("awaiting_trick_clear"):
            legal = latest.get(cur, {}).get("your_legal_cards")
            if legal:
                await send(idx[cur], {"type": "play_card", "card": legal[0]})
        elif s["phase"] == "round_end":
            rounds_done.add(s.get("round_index"))
        await asyncio.sleep(0.03)

    for t in tasks[:3]:
        t.cancel()
    for ws in socks[:3]:
        await ws.close()


asyncio.run(main())
