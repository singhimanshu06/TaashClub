"""Test: when all humans disconnect, the game ends after the grace period.

Creates a 4-player friends game (4 real sockets), starts it, then disconnects
all 4 players. After LAKDI_BOT_CONVERSION_GRACE seconds the server should
convert seats to bots and — finding no humans left — force_end the game.
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

    socks = []
    for pid in players:
        ws = await websockets.connect(f"{WS}/ws/{code}?player_id={pid}")
        socks.append(ws)

    latest = {}
    # Only track Alice's state — she's the host who starts the game.
    async def pump_alice(ws):
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "state_update":
                latest["state"] = msg["state"]

    pump_task = asyncio.create_task(pump_alice(socks[0]))

    await socks[0].send(json.dumps({"type": "start_game"}))

    async def wait(cond, timeout=10):
        for _ in range(int(timeout / 0.05)):
            if cond():
                return
            await asyncio.sleep(0.05)
        raise SystemExit("timeout")

    await wait(lambda: "state" in latest and latest["state"].get("phase") in ("bidding", "playing"))

    print(f"Game started, phase={latest['state']['phase']}. Disconnecting all 4 players...")

    # Disconnect everyone.
    for ws in socks:
        await ws.close()

    pump_task.cancel()

    print(f"Waiting {GRACE + 10}s for grace period + conversion + game end...")
    await asyncio.sleep(GRACE + 10)

    # Reconnect Alice to check the final state.
    ws = await websockets.connect(f"{WS}/ws/{code}?player_id={players[0]}")
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        if msg.get("type") == "chat_history":
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)
        if msg.get("type") == "state_update":
            state = msg["state"]
            print(f"Phase after reconnect: {state['phase']}")
            assert state["phase"] == "game_end", f"expected game_end, got {state['phase']}"
            board = state["final_standings"]
            assert board and len(board) == 4
            print("GAME ENDED — all humans disconnected. Final standings:")
            for row in board:
                print(f"  {row['rank']}. {row['name']}: {row['total_score']}")
            print("OK: game ended after all humans left")
        else:
            raise SystemExit(f"unexpected message: {msg.get('type')}")
    finally:
        await ws.close()


asyncio.run(main())
