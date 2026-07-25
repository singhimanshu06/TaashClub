# TaashClub — Callbreak (decreasing-cards, exact-bid variant)

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
- **Scoreboard:** a cumulative scorecard is available behind a **Scores** toggle on
  the game screen (totals through the last completed round). At game end the final
  standings are shown, with a **Detailed scores** button revealing a round-by-round
  breakdown (one row per round, one column per player, points only; the highest
  score in each row/column is green, the lowest is red).

## Bots
Don't have enough friends online? Toggle **Play with bots** on the home screen
and the room fills the remaining 3 seats with AI bots (bot games are always
4-player: 1 human + 3 bots). Bots are server-driven — they bid and play on
their own with a short "thinking" delay, and the round auto-advances so the
match keeps moving without you clicking through every scoreboard.

Bot behavior:
- **Bidding:** heuristic that counts likely winners (high trumps, off-suit
  aces, borderline trump face cards), clamped to `[0, cards_this_round]`, with
  small jitter so identical hands don't all bid the same.
- **Play:** always follows the led suit when held. When still chasing tricks
  (`tricks_won < bid`) it tries to win cheaply (lowest winning legal card, trump
  only when it actually wins and is needed); otherwise it dumps the lowest legal
  card, preserving trumps.
- **Names:** bots pick from a pool of ~25 short quirky names (e.g. `SirTrump`,
  `Trumpzilla`, `QueenBee`, `Diamondog`), no duplicates within a game.

Bot timing is tunable via env vars (defaults shown):
```
TAASHCLUB_BOT_THINK_MIN=0.6      # min "thinking" delay per bot action (seconds)
TAASHCLUB_BOT_THINK_MAX=1.2      # max delay
TAASHCLUB_BOT_AUTO_ADVANCE=6     # ROUND_END auto-advance grace period
```

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

To play solo against bots, tick **Play with bots** when creating a room — the 3
remaining seats fill with AI and the game starts immediately. See **Bots** below.

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
.venv/bin/python -m pytest -q                 # pure engine + bot unit tests
.venv/bin/python tests/smoke_full_game.py     # full all-human game over the socket (server must be running)
.venv/bin/python tests/smoke_bots.py          # 1 human + 3 bots full game (server must be running)
```

For fast smoke runs set `TAASHCLUB_TRICK_HOLD=0 TAASHCLUB_BOT_THINK_MIN=0.01
TAASHCLUB_BOT_THINK_MAX=0.05 TAASHCLUB_BOT_AUTO_ADVANCE=0.3` (and `TAASHCLUB_PORT=8123` if
the server isn't on the default 8000).

## Architecture
Server-authoritative. The Python engine (`backend/app/game/engine.py`) owns all
rules and state; the React client renders a **redacted** per-player view (you only
see your own hand) and sends intents over a WebSocket.

- `backend/app/game/` — `models.py`, `engine.py` (pure rules + `round_history`), `room.py` (rooms + sockets), `bot.py` (bot brain + name pool)
- `backend/app/main.py` — FastAPI REST + WebSocket endpoints; hosts the bot driver (schedules bot turns and auto-advance)
- `frontend/src/` — `store.ts` (state + socket), `components/` (Home, Lobby, GameTable, Scorecard, DetailedScores, …)

### How bots are driven
Bots are plain `Player` objects flagged `is_bot=True` with no WebSocket of their
own — the server applies their decisions directly to the engine. A single
`_after_state_change(room)` coroutine is the hub for every state mutation
(client events, bot actions, trick commit): it broadcasts, schedules the
post-trick hold, and — if the current turn belongs to a bot — spawns one
"think then act" task per bot turn. Guards (`bot_busy`, `auto_advance_busy`)
prevent duplicate scheduling, and a strong-ref set (`room._bot_tasks`) keeps
in-flight tasks from being garbage-collected mid-flight.

### MVP scope / not yet included
Guest play only (no accounts/DB — rooms live in memory and reset on server restart),
no chat, minimal disconnect handling. Bots play a single "normal" heuristic level
(no difficulty selection, no per-seat mixing of humans + bots beyond the 4-player
bot mode).
