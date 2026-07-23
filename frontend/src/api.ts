import type { Variant } from "./types";

// In dev (vite on :5173) the backend runs separately on :8000.
// In production the FastAPI server serves this bundle, so everything is
// same-origin — which is what makes a single shared tunnel URL work, and
// upgrades ws -> wss automatically when the tunnel is HTTPS.
const DEV = import.meta.env.DEV;
export const API_BASE = DEV ? `http://${location.hostname}:8000` : "";
export const WS_BASE = DEV
  ? `ws://${location.hostname}:8000`
  : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || "request failed");
  }
  return res.json();
}

export function createRoom(num_players: number, variant: Variant) {
  return post<{ code: string }>("/rooms", { num_players, variant });
}

export function joinRoom(code: string, name: string) {
  return post<{ player_id: string; join_order: number; code: string }>(
    `/rooms/${code.toUpperCase()}/join`,
    { name }
  );
}
