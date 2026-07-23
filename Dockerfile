# ── Stage 1: build the React frontend ────────────────────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./
RUN npm run build


# ── Stage 2: Python backend + built frontend ──────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend into the location main.py expects
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Copy card images (served as static files by Vite in dev; bundled here for prod)
# They live in frontend/public/cards/ and Vite copies public/ into dist/ at build time.
# Nothing extra needed — already included via `npm run build` above.

# Railway injects PORT; default to 8000 for local docker runs
ENV PORT=8000

EXPOSE $PORT

CMD uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
