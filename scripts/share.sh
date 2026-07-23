#!/usr/bin/env bash
# Build the frontend, run the backend, and expose it publicly via a free
# Cloudflare quick tunnel. Share the printed https URL with your friends.
#
# Usage:  ./scripts/share.sh
# Stop:   Ctrl-C (stops the tunnel; backend keeps running if already up)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Building frontend (so the backend can serve it single-origin)…"
(cd "$ROOT/frontend" && npm run build)

if ! curl -s -o /dev/null --max-time 2 http://127.0.0.1:8000/; then
  echo "==> Starting backend on :8000…"
  (cd "$ROOT/backend" && .venv/bin/python -m uvicorn app.main:app --port 8000 \
      >/tmp/lakdi-backend.log 2>&1 &)
  for _ in $(seq 1 20); do
    curl -s -o /dev/null --max-time 2 http://127.0.0.1:8000/ && break || sleep 0.5
  done
else
  echo "==> Backend already running on :8000."
fi

echo "==> Starting Cloudflare tunnel. Share the https://….trycloudflare.com URL below."
echo "    (Tip: the room's Invite link — shown in the lobby — already appends ?room=CODE.)"
exec cloudflared tunnel --url http://localhost:8000 --no-autoupdate
