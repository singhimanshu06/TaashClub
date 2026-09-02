import type { GameInfo } from "./types";

// In dev (vite on :5173) the backend runs separately on :8000.
// In production the FastAPI server serves this bundle, so everything is
// same-origin — which is what makes a single shared tunnel URL work, and
// upgrades ws -> wss automatically when the tunnel is HTTPS.
const DEV = import.meta.env.DEV;
export const API_BASE = DEV ? `http://${location.hostname}:8000` : "";
export const WS_BASE = DEV
  ? `ws://${location.hostname}:8000`
  : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;

export class ApiError extends Error {
  code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    const value = detail.detail;
    if (value && typeof value === "object") {
      throw new ApiError(value.message || "request failed", value.code);
    }
    const message = value || "request failed";
    let code: string | undefined;
    if (message === "room is full") code = "ROOM_FULL";
    if (message === "game already started") code = "GAME_STARTED";
    throw new ApiError(message, code);
  }
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

export function fetchGames() {
  return get<GameInfo[]>("/games");
}

export function createRoom(gameType: string, numPlayers: number, options: Record<string, unknown>) {
  return post<{ code: string }>("/rooms", {
    game_type: gameType,
    num_players: numPlayers,
    options,
  });
}

export function joinRoom(code: string, name: string) {
  return post<{ player_id: string; join_order: number; code: string }>(
    `/rooms/${code.toUpperCase()}/join`,
    { name }
  );
}

export function spectateRoom(code: string, name: string) {
  return post<{ spectator_id: string; chat_id: string; code: string }>(
    `/rooms/${code.toUpperCase()}/spectate`,
    { name }
  );
}
