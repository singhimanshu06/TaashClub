"""Socket-level checks for the post-trick hold and the chat channel.

Run against a server started with LAKDI_TRICK_HOLD=2 (see the runner below).
"""
import asyncio
import json
import os
import urllib.request

import websockets

PORT = os.environ.get("LAKDI_PORT", "8011")
HOLD = float(os.environ.get("LAKDI_TRICK_HOLD", "2"))
BASE = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}"


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

    socks = [await websockets.connect(f"{WS}/ws/{code}?player_id={pid}") for pid in players]
    latest = {}
    chat_seen = {pid: [] for pid in players}

    async def pump(pid, ws):
        try:
            async for raw in ws:
                m = json.loads(raw)
                if m.get("type") == "state_update":
                    latest[pid] = m["state"]
                elif m.get("type") == "chat":
                    chat_seen[pid].append(m["message"])
        except Exception:
            pass

    tasks = [asyncio.create_task(pump(pid, ws)) for pid, ws in zip(players, socks)]

    async def send(i, obj):
        await socks[i].send(json.dumps(obj))

    async def wait(cond, t=5):
        for _ in range(int(t / 0.02)):
            if cond():
                return True
            await asyncio.sleep(0.02)
        return False

    await send(0, {"type": "start_game"})
    await wait(lambda: len(latest) == 4 and latest[players[0]]["phase"] == "bidding")
    # Everyone bids.
    for _ in range(4):
        s = latest[players[0]]
        cur = s["current_player_id"]
        await send(idx[cur], {"type": "place_bid", "value": 1})
        await wait(lambda: latest[players[0]].get("current_player_id") != cur or
                   latest[players[0]]["phase"] != "bidding")
    await wait(lambda: latest[players[0]]["phase"] == "playing")

    # Play exactly one full trick (4 cards).
    for _ in range(4):
        s = latest[players[0]]
        cur = s["current_player_id"]
        assert cur is not None, "expected a player on turn"
        legal = latest[cur]["your_legal_cards"]
        await send(idx[cur], {"type": "play_card", "card": legal[0]})
        await wait(lambda: latest[players[0]].get("current_player_id") != cur)

    # Immediately after the 4th card: trick is HELD.
    held = await wait(lambda: latest[players[0]]["awaiting_trick_clear"] is True)
    s = latest[players[0]]
    assert held, "trick should be held after the last card"
    assert len(s["current_trick"]) == 4, "all 4 cards must stay on the table"
    assert s["trick_winner_id"] is not None, "winner must be marked during the hold"
    assert s["current_player_id"] is None, "nobody is on turn during the hold"
    print(f"OK: trick held with 4 cards, winner={s['trick_winner_id'][:4]}…, nobody on turn")

    # After the hold elapses, the trick clears and play resumes.
    cleared = await wait(lambda: latest[players[0]]["awaiting_trick_clear"] is False, t=HOLD + 3)
    assert cleared, "trick should clear after the hold"
    s = latest[players[0]]
    assert len(s["current_trick"]) in (0, 1), "table cleared (winner may have led next)"
    assert s["current_player_id"] is not None, "play resumes after the hold"
    print(f"OK: trick cleared after ~{HOLD}s hold, play resumed")

    # Chat: broadcast to everyone, then history on reconnect.
    await send(1, {"type": "chat", "text": "gg wp"})
    got = await wait(lambda: all(len(chat_seen[p]) >= 1 for p in players))
    assert got, "chat must reach all players"
    assert all(chat_seen[p][-1]["text"] == "gg wp" for p in players)
    assert chat_seen[players[0]][-1]["name"] == "Bob"
    print("OK: chat broadcast to all 4 players")

    # Reconnect Dan; expect chat history to include the earlier message.
    await socks[3].close()
    ws2 = await websockets.connect(f"{WS}/ws/{code}?player_id={players[3]}")
    hist = None
    for _ in range(100):
        m = json.loads(await ws2.recv())
        if m.get("type") == "chat_history":
            hist = m["messages"]
            break
    assert hist and any(x["text"] == "gg wp" for x in hist), "reconnect must receive chat history"
    print("OK: reconnecting player received chat history")
    await ws2.close()

    for t in tasks:
        t.cancel()
    for ws in socks[:3]:
        await ws.close()
    print("ALL HOLD + CHAT CHECKS PASSED")


asyncio.run(main())
