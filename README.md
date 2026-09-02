# TaashClub

TaashClub is a real-time multiplayer card-game platform. Create a room, share the
4-character room code (or invite link), and play with friends on the same Wi-Fi
or across networks. Every game is server-authoritative: the Python engine owns
all rules and state, clients render a redacted per-player view and send intents
over a WebSocket.

Once all player seats are occupied, a room can also be watched by up to ten
read-only spectators. Spectators see public table cards and game state, but
never private hands or legal actions; they may use chat with a chosen display
name.

It started as a single Callbreak variant and has grown into a platform that
hosts several games behind one shared lobby/room/socket layer. AI bots can fill
empty seats so you can play solo too.

## Games

| Game | Players | Description |
| --- | --- | --- |
| LAKDI (Callbreak variant) | 4–6 | Decreasing-cards, exact-bid trick-taking. Trump cycles each round. |
| President | 5 | Shed your hand fastest. Bomb with a 2, skip same-rank repeats, card exchange between rounds. |
| Twenty-Eight | 4 | Partnership trick-taking with a hidden trump. Bid 14–28 card points, keep trump secret until revealed. |

## Tech stack

- **Backend:** Python 3.11+, FastAPI, WebSockets, Pydantic. In-memory rooms (no DB).
- **Frontend:** React 18, TypeScript, Vite, Zustand.
- **Deployment:** single Docker image (backend serves the built frontend on one origin), sized for Fly.io.

## Project structure

```
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI REST + WebSocket endpoints, bot driver
│   │   ├── protocol.py        # shared message/action definitions
│   │   └── game/
│   │       ├── base.py        # BaseGame / BotBrain / Player contracts
│   │       ├── registry.py    # GAME_REGISTRY — source of truth for available games
│   │       ├── room.py        # rooms + socket lifecycle
│   │       ├── names.py       # shared bot name pool
│   │       ├── callbreak/     # engine.py, models.py, bot.py
│   │       ├── president/     # engine.py, models.py, bot.py
│   │       └── twentyeight/   # engine.py, models.py, bot.py
│   ├── requirements.txt
│   └── tests/                 # unit tests + end-to-end smoke scripts
├── frontend/
│   ├── src/
│   │   ├── store.ts           # app state + WebSocket client
│   │   ├── api.ts, types.ts, sounds.ts
│   │   ├── components/        # shared UI: Home, Lobby, GameTable, Hand, Scorecard, Chat, …
│   │   └── games/
│   │       ├── registry.ts    # GameSlots — per-game UI plug-in points
│   │       ├── callbreak/     # per-game panels, scoreboards, home options
│   │       ├── president/
│   │       └── twentyeight/
│   └── public/                # card images, suit icons, sounds
├── scripts/share.sh           # build + serve + public Cloudflare tunnel
├── Dockerfile, fly.toml
└── .github/
```

Each game is self-contained: a backend package (`engine.py` = pure rules,
`models.py` = state, `bot.py` = AI brain) registered in
`backend/app/game/registry.py`, plus a frontend folder of React components
registered in `frontend/src/games/registry.ts`. Adding a game touches no
shared room/socket/UI code.

## Run locally

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

The frontend talks to the backend on the same hostname, port 8000 — so opening
the Vite **Network** URL on phones/other computers on the same Wi-Fi lets them
join too.

### Docker (single origin)

```bash
docker build -t taashclub .
docker run -p 8080:8080 taashclub     # app at http://localhost:8080
```


## Tests

```bash
cd backend
.venv/bin/python -m pytest -q                 # engine + bot unit tests
.venv/bin/python -m pytest tests/test_spectator.py -q # spectator/session checks
.venv/bin/python tests/smoke_full_game.py     # all-human game over the socket (server must be running)
.venv/bin/python tests/smoke_bots.py          # human + bots full game (server must be running)
.venv/bin/python tests/smoke_president.py     # President over the socket
.venv/bin/python tests/smoke_twentyeight.py   # Twenty-Eight over the socket
```

For fast smoke runs set `TAASHCLUB_TRICK_HOLD=0 TAASHCLUB_BOT_THINK_MIN=0.01
TAASHCLUB_BOT_THINK_MAX=0.05 TAASHCLUB_BOT_AUTO_ADVANCE=0.3` (and
`TAASHCLUB_PORT=8123` if the server isn't on the default 8000).

## Adding a new game

1. Create `backend/app/game/<name>/` with `models.py`, `engine.py` (subclass
   `BaseGame`), and `bot.py` (subclass `BotBrain`).
2. Register a `GameSpec` (engine factory, bot brain, player range, options
   schema) in `backend/app/game/registry.py`.
3. Create `frontend/src/games/<name>/` implementing the `GameSlots` components
   you need and register them in `frontend/src/games/registry.ts`.
4. Add unit tests plus a `tests/smoke_<name>.py` end-to-end script.

No changes to room/socket/main infrastructure or shared UI components.

## Current limitations

Guest play only (no accounts/DB — rooms live in memory and reset on server
restart), minimal disconnect handling (seats convert to bots after a grace
period), bots play a single heuristic level (no difficulty selection).
