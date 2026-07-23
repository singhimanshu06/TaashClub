"""Manual end-to-end smoke test against a running server (not a pytest test).

Usage: start `uvicorn app.main:app` then run `python tests/smoke_ws.py`.
"""
import asyncio
import json
import urllib.request

import websockets

BASE = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000"


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req).read())


async def main():
    code = post("/rooms", {"num_players": 4, "variant": "single_run"})["code"]
    print("room:", code)
    players = [post(f"/rooms/{code}/join", {"name": n}) for n in ["Alice", "Bob", "Cara", "Dan"]]

    sockets = []
    for p in players:
        ws = await websockets.connect(f"{WS}/ws/{code}?player_id={p['player_id']}")
        sockets.append(ws)
        await ws.recv()  # initial lobby/state

    async def recv_type(ws, wanted):
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") == wanted:
                return msg

    # Host starts the game.
    await sockets[0].send(json.dumps({"type": "start_game"}))
    msg = await recv_type(sockets[0], "state_update")
    state = msg["state"]
    assert state["phase"] == "bidding"
    assert state["cards_this_round"] == 13
    assert state["trump"] == "S"
    me = next(pl for pl in state["players"] if pl["id"] == players[0]["player_id"])
    assert me["hand"] is not None and len(me["hand"]) == 13
    other = next(pl for pl in state["players"] if pl["id"] != players[0]["player_id"])
    assert other["hand"] is None, "opponent hands must be redacted"
    print("OK: bidding started, 13 cards, trump=Spade, hands redacted correctly")

    for ws in sockets:
        await ws.close()


asyncio.run(main())
