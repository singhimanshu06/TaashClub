import { create } from "zustand";
import { WS_BASE } from "./api";
import type { ChatMessage, GameState, Lobby } from "./types";

type Screen = "home" | "lobby" | "game" | "reconnecting";

const SESSION_KEY = "taashclub_session";
const MAX_RECONNECT_ATTEMPTS = 5;
const BACKOFF_BASE_MS = 1000; // 1s, 2s, 4s, 8s, 16s

interface Session {
  role: "player" | "spectator";
  code: string;
  playerId?: string;
  spectatorId?: string;
  chatId?: string;
  spectatorName?: string;
}

interface Store {
  screen: Screen;
  code: string | null;
  role: "player" | "spectator" | null;
  playerId: string | null;
  spectatorId: string | null;
  chatId: string | null;
  spectatorName: string | null;
  lobby: Lobby | null;
  game: GameState | null;
  error: string | null;
  connected: boolean;
  reconnecting: boolean;
  reconnectAttempt: number; // 0 when idle, 1..N when retrying
  messages: ChatMessage[];
  playerBanner: { name: string; connected: boolean; ts: number } | null;

  enterRoom: (code: string, playerId: string) => void;
  enterSpectator: (code: string, spectatorId: string, chatId: string, name: string) => void;
  reconnect: () => void;
  startGame: () => void;
  addBot: () => void;
  addBots: () => void;
  sendAction: (action: string, params?: Record<string, unknown>) => void;
  sendChat: (text: string) => void;
  clearError: () => void;
  clearPlayerBanner: () => void;
  reset: () => void;
}

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectAttempts = 0;
let intendedClose = false; // true when we close the socket on purpose (reset/leave)
// Players we have seen disconnect in this session. Used to only banner
// "connected" on reconnection, never on the initial join at game start.
const disconnectedPlayers = new Set<string>();

function send(msg: object) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(msg));
  }
}

function saveSession(session: Session) {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    // localStorage may be unavailable (private mode); reconnection just won't persist.
  }
}

function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Partial<Session> & { code?: string; playerId?: string };
    // Accept the pre-spectator session shape so existing players can reload.
    if (s.role === "spectator" && s.code && s.spectatorId && s.chatId && s.spectatorName) {
      return {
        role: "spectator",
        code: s.code,
        spectatorId: s.spectatorId,
        chatId: s.chatId,
        spectatorName: s.spectatorName,
      };
    }
    if (s.code && s.playerId) return { role: "player", code: s.code, playerId: s.playerId };
    return null;
  } catch {
    return null;
  }
}

function clearSession() {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    // ignore
  }
}

function handleMessage(set: (partial: Partial<Store> | ((s: Store) => Partial<Store>)) => void, ev: MessageEvent) {
  const msg = JSON.parse(ev.data);
  if (msg.type === "lobby_update") {
    set({ lobby: msg.lobby, screen: "lobby", reconnecting: false, reconnectAttempt: 0 });
  } else if (msg.type === "state_update") {
    const game: GameState = msg.state;
    set({ game, screen: game.phase === "lobby" ? "lobby" : "game", reconnecting: false });
  } else if (msg.type === "chat_history") {
    set({ messages: msg.messages as ChatMessage[] });
  } else if (msg.type === "chat") {
    set((s) => ({ messages: [...s.messages, msg.message as ChatMessage] }));
  } else if (msg.type === "player_status") {
    const name = msg.name as string;
    const isConnected = !!msg.connected;
    // Suppress the "connected" banner for first-time joins (e.g. at game
    // start); only show it when the player is coming back after a drop.
    if (isConnected && !disconnectedPlayers.has(name)) return;
    if (isConnected) {
      disconnectedPlayers.delete(name);
    } else {
      disconnectedPlayers.add(name);
    }
    set({
      playerBanner: { name, connected: isConnected, ts: Date.now() },
    });
  } else if (msg.type === "error") {
    set({ error: msg.message });
  }
}

function openSocket(
  set: (partial: Partial<Store> | ((s: Store) => Partial<Store>)) => void,
  get: () => Store,
  session: Session,
  onOpenExtra?: () => void,
) {
  if (socket) {
    intendedClose = true;
    socket.close();
    socket = null;
  }
  intendedClose = false;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  reconnectAttempts = 0;

  const query = session.role === "player"
    ? `player_id=${encodeURIComponent(session.playerId!)}`
    : `spectator_id=${encodeURIComponent(session.spectatorId!)}`;
  socket = new WebSocket(`${WS_BASE}/ws/${encodeURIComponent(session.code)}?${query}`);

  socket.onopen = () => {
    reconnectAttempts = 0;
    set({ connected: true, reconnecting: false, reconnectAttempt: 0 });
    onOpenExtra?.();
  };

  socket.onclose = (ev) => {
    set({ connected: false });
    if (intendedClose) return; // we closed it on purpose (reset/leave)

    // Invalid room/session and the spectator capacity limit are terminal for
    // this browser session. The user can start a fresh watch attempt.
    if (ev.code === 4004 || ev.code === 4003 || ev.code === 4005 || ev.code === 4008 || ev.code === 4009) {
      clearSession();
      set({
        screen: "home",
        code: null,
        role: null,
        playerId: null,
        spectatorId: null,
        chatId: null,
        spectatorName: null,
        lobby: null,
        game: null,
        reconnecting: false,
        reconnectAttempt: 0,
        error:
          ev.code === 4004
            ? "Your game has ended."
            : ev.code === 4008
              ? "This room already has 10 spectators."
              : ev.code === 4009
                ? "This spectator session was opened elsewhere."
                : session.role === "spectator"
                  ? "Your spectator session has expired."
                  : "You are no longer in this room.",
      });
      socket = null;
      return;
    }

    // Transient drop (WhatsApp call, phone sleep, network blip) — retry.
    scheduleReconnect(set, get);
  };

  socket.onmessage = (ev) => handleMessage(set, ev);
}

function scheduleReconnect(
  set: (partial: Partial<Store> | ((s: Store) => Partial<Store>)) => void,
  get: () => Store,
) {
  if (intendedClose) return;
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    // Exhausted retries — session is unreachable. Clear it and return to home
    // so the user isn't trapped on a dead reconnecting screen.
    clearSession();
    set({
      screen: "home",
      code: null,
      role: null,
      playerId: null,
      spectatorId: null,
      chatId: null,
      spectatorName: null,
      lobby: null,
      game: null,
      reconnecting: false,
      reconnectAttempt: 0,
      error: "Connection lost. Please create or join a new room.",
    });
    socket = null;
    return;
  }
  reconnectAttempts += 1;
  const delay = BACKOFF_BASE_MS * 2 ** (reconnectAttempts - 1);
  set({ reconnecting: true, reconnectAttempt: reconnectAttempts });
  socket = null;

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (intendedClose) return;
    // Re-read in case reset() cleared the session while we were waiting.
    const session = loadSession();
    if (!session) {
      set({ screen: "home", reconnecting: false, reconnectAttempt: 0 });
      return;
    }
    openSocket(set, get, session);
  }, delay);
}

export const useStore = create<Store>((set, get) => ({
  screen: "home",
  code: null,
  role: null,
  playerId: null,
  spectatorId: null,
  chatId: null,
  spectatorName: null,
  lobby: null,
  game: null,
  error: null,
  connected: false,
  reconnecting: false,
  reconnectAttempt: 0,
  messages: [],
  playerBanner: null,

  enterRoom: (code, playerId) => {
    const session: Session = { role: "player", code, playerId };
    saveSession(session);
    disconnectedPlayers.clear();
    set({
      code,
      role: "player",
      playerId,
      spectatorId: null,
      chatId: null,
      spectatorName: null,
      screen: "lobby",
      messages: [],
      reconnecting: false,
      reconnectAttempt: 0,
    });
    openSocket(set, get, session);
  },

  enterSpectator: (code, spectatorId, chatId, name) => {
    const session: Session = {
      role: "spectator",
      code,
      spectatorId,
      chatId,
      spectatorName: name,
    };
    saveSession(session);
    disconnectedPlayers.clear();
    set({
      code,
      role: "spectator",
      playerId: null,
      spectatorId,
      chatId,
      spectatorName: name,
      screen: "lobby",
      messages: [],
      reconnecting: false,
      reconnectAttempt: 0,
    });
    openSocket(set, get, session);
  },

  reconnect: () => {
    const session = loadSession();
    if (!session) {
      set({ screen: "home" });
      return;
    }
    set({
      code: session.code,
      role: session.role,
      playerId: session.playerId ?? null,
      spectatorId: session.spectatorId ?? null,
      chatId: session.chatId ?? null,
      spectatorName: session.spectatorName ?? null,
      screen: "reconnecting",
      reconnecting: true,
      reconnectAttempt: 1,
    });
    reconnectAttempts = 1;
    openSocket(set, get, session);
  },

  startGame: () => send({ type: "start_game" }),
  addBot: () => send({ type: "add_bot" }),
  addBots: () => send({ type: "add_bots" }),
  sendAction: (action, params = {}) => send({ type: "action", action, params }),
  sendChat: (text) => {
    const t = text.trim();
    if (t) send({ type: "chat", text: t });
  },
  clearError: () => set({ error: null }),
  clearPlayerBanner: () => set({ playerBanner: null }),
  reset: () => {
    intendedClose = true;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (socket) socket.close();
    socket = null;
    reconnectAttempts = 0;
    clearSession();
    set({
      screen: "home",
      code: null,
      role: null,
      playerId: null,
      spectatorId: null,
      chatId: null,
      spectatorName: null,
      lobby: null,
      game: null,
      error: null,
      connected: false,
      reconnecting: false,
      reconnectAttempt: 0,
      messages: [],
      playerBanner: null,
    });
  },
}));

// When the tab becomes visible again (user returns from WhatsApp / phone wake),
// immediately attempt reconnection if we're in a disconnected/reconnecting state.
if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    const state = useStore.getState();
    if (!state.code || (!state.playerId && !state.spectatorId)) return; // no session to restore
    if (socket && socket.readyState === WebSocket.OPEN) return; // already connected
    if (intendedClose) return; // user left on purpose
    // Reset attempt counter so a fresh page-focus gets a clean retry sequence.
    reconnectAttempts = 0;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    useStore.setState({ reconnecting: true, reconnectAttempt: 1 });
    reconnectAttempts = 1;
    const session = loadSession();
    if (session) openSocket(useStore.setState, useStore.getState, session);
  });
}
