# LAKDI — Callbreak (decreasing-cards, exact-bid variant)

A real-time multiplayer web game. A Callbreak variant where the hand size shrinks
each round, players bid the **exact** number of tricks they'll win, and the trump
suit cycles every round.

## Rules

- **Players:** 4, 5, or 6 (chosen at room creation). Starting hand = `floor(52 / players)` → 13 / 10 / 8.
- **Rounds:** cards dealt decrease by one each round down to 1.
  - **Single run:** `start → 1`.
  - **Down & up:** `start → 1 → start` (the 1-card round is played twice back-to-back).
- **Bidding:** each player announces an exact target (0 allowed). Hit it exactly → `10 + bid` points; over or under → `0`.
- **Trump:** cycles Spade → Heart → Club → Diamond by round.
- **Play:** follow the led suit if you can; otherwise play any card. Highest trump wins the trick, else highest of the led suit.
- **First bidder:** rotates by join order each round (R1 = 1st joiner, R2 = 2nd, …), cycling through all seats.
- **Scoreboard:** revealed only at the end of the game.

## Run it

### Backend (Python 3.11+)
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --port 8000
```

### Frontend (Node 18+)
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

The frontend talks to the backend on the same hostname, port 8000 — so opening the
Vite **Network** URL on phones/other computers on the same Wi-Fi lets them join too.

### Play
Open the app, **Create Room** (pick players + variant + your name), share the 4-char
room code. Everyone else opens the app, **Join Room**, enters the code and their name.
When all seats are filled the host presses **Start Game**.

## Play with friends on other networks (public link)

The FastAPI server also serves the built frontend, so the whole app lives on one
origin (port 8000). Expose that port with a free **Cloudflare quick tunnel** and
share the resulting HTTPS link — no account, no router config.

```bash
cd frontend && npm run build           # produce the bundle the backend serves
cd ../backend && .venv/bin/python -m uvicorn app.main:app --port 8000
cloudflared tunnel --url http://localhost:8000 --no-autoupdate
```

…or just run `./scripts/share.sh`, which does all three. Install cloudflared once
with `brew install cloudflared`.

Share the printed `https://<random>.trycloudflare.com` URL. The host opens it,
creates a room, and shares the lobby's **Invite link** (it appends `?room=CODE`,
so friends land straight on the join screen). The app is origin-aware, so the
WebSocket automatically uses `wss://` over the HTTPS tunnel.

**Notes**
- Your laptop is the host — keep it awake and the two commands running. The free
  URL changes each time you restart the tunnel.
- A quick tunnel is public; room codes are only 4 characters, so don't post the
  link somewhere public.
- If your **own** browser can't open the `trycloudflare.com` URL (some home
  routers negative-cache brand-new subdomains), either set your Mac's DNS to
  `1.1.1.1`, or just host from `http://localhost:8000` and share the public URL +
  room code manually — remote players on their own networks resolve it fine.

## Tests
```bash
cd backend
.venv/bin/python -m pytest -q                 # pure engine unit tests
.venv/bin/python tests/smoke_full_game.py     # full game over the socket (server must be running)
```

## Architecture
Server-authoritative. The Python engine (`backend/app/game/engine.py`) owns all
rules and state; the React client renders a **redacted** per-player view (you only
see your own hand) and sends intents over a WebSocket.

- `backend/app/game/` — `models.py`, `engine.py` (pure rules), `room.py` (rooms + sockets)
- `backend/app/main.py` — FastAPI REST + WebSocket endpoints
- `frontend/src/` — `store.ts` (state + socket), `components/` (Home, Lobby, GameTable, …)

### MVP scope / not yet included
Guest play only (no accounts/DB — rooms live in memory and reset on server restart),
no chat, no AI bots, minimal disconnect handling.
