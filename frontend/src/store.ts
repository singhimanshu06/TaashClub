import { create } from "zustand";
import { WS_BASE } from "./api";
import type { CardT, ChatMessage, GameState, Lobby } from "./types";

type Screen = "home" | "lobby" | "game" | "reconnecting";

const SESSION_KEY = "lakdi_session";
const MAX_RECONNECT_ATTEMPTS = 5;
const BACKOFF_BASE_MS = 1000; // 1s, 2s, 4s, 8s, 16s

interface Session {
  code: string;
  playerId: string;
}

interface Store {
  screen: Screen;
  code: string | null;
  playerId: string | null;
  lobby: Lobby | null;
  game: GameState | null;
  error: string | null;
  connected: boolean;
  reconnecting: boolean;
  reconnectAttempt: number; // 0 when idle, 1..N when retrying
  messages: ChatMessage[];

  enterRoom: (code: string, playerId: string, botMode?: boolean) => void;
  reconnect: () => void;
  startGame: () => void;
  addBots: () => void;
  placeBid: (value: number) => void;
  playCard: (card: CardT) => void;
  advanceRound: () => void;
  sendChat: (text: string) => void;
  clearError: () => void;
  reset: () => void;
}

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectAttempts = 0;
let intendedClose = false; // true when we close the socket on purpose (reset/leave)

function send(msg: object) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(msg));
  }
}

function saveSession(code: string, playerId: string) {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify({ code, playerId }));
  } catch {
    // localStorage may be unavailable (private mode); reconnection just won't persist.
  }
}

function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Session;
    return s.code && s.playerId ? s : null;
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
    set({ lobby: msg.lobby });
  } else if (msg.type === "state_update") {
    const game: GameState = msg.state;
    set({ game, screen: game.phase === "lobby" ? "lobby" : "game", reconnecting: false });
  } else if (msg.type === "chat_history") {
    set({ messages: msg.messages as ChatMessage[] });
  } else if (msg.type === "chat") {
    set((s) => ({ messages: [...s.messages, msg.message as ChatMessage] }));
  } else if (msg.type === "error") {
    set({ error: msg.message });
  }
}

function openSocket(
  set: (partial: Partial<Store> | ((s: Store) => Partial<Store>)) => void,
  get: () => Store,
  code: string,
  playerId: string,
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

  socket = new WebSocket(`${WS_BASE}/ws/${code}?player_id=${playerId}`);

  socket.onopen = () => {
    reconnectAttempts = 0;
    set({ connected: true, reconnecting: false, reconnectAttempt: 0 });
    onOpenExtra?.();
  };

  socket.onclose = (ev) => {
    set({ connected: false });
    if (intendedClose) return; // we closed it on purpose (reset/leave)

    // 4004 = room gone, 4003 = player invalid — session is dead, give up.
    if (ev.code === 4004 || ev.code === 4003) {
      clearSession();
      set({
        screen: "home",
        code: null,
        playerId: null,
        lobby: null,
        game: null,
        reconnecting: false,
        reconnectAttempt: 0,
        error: ev.code === 4004 ? "Your game has ended." : "You are no longer in this room.",
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
    // Exhausted retries — stay on reconnecting screen with a manual retry prompt.
    set({ reconnecting: true, reconnectAttempt: 0 });
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
    openSocket(set, get, session.code, session.playerId);
  }, delay);
}

export const useStore = create<Store>((set, get) => ({
  screen: "home",
  code: null,
  playerId: null,
  lobby: null,
  game: null,
  error: null,
  connected: false,
  reconnecting: false,
  reconnectAttempt: 0,
  messages: [],

  enterRoom: (code, playerId, botMode) => {
    saveSession(code, playerId);
    set({ code, playerId, screen: "lobby", messages: [], reconnecting: false, reconnectAttempt: 0 });
    openSocket(set, get, code, playerId, () => {
      if (botMode) {
        send({ type: "add_bots" });
        send({ type: "start_game" });
      }
    });
  },

  reconnect: () => {
    const session = loadSession();
    if (!session) {
      set({ screen: "home" });
      return;
    }
    set({
      code: session.code,
      playerId: session.playerId,
      screen: "reconnecting",
      reconnecting: true,
      reconnectAttempt: 1,
    });
    reconnectAttempts = 1;
    openSocket(set, get, session.code, session.playerId);
  },

  startGame: () => send({ type: "start_game" }),
  addBots: () => send({ type: "add_bots" }),
  placeBid: (value) => send({ type: "place_bid", value }),
  playCard: (card) => send({ type: "play_card", card }),
  advanceRound: () => send({ type: "advance_round" }),
  sendChat: (text) => {
    const t = text.trim();
    if (t) send({ type: "chat", text: t });
  },
  clearError: () => set({ error: null }),
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
      playerId: null,
      lobby: null,
      game: null,
      error: null,
      connected: false,
      reconnecting: false,
      reconnectAttempt: 0,
      messages: [],
    });
  },
}));

// When the tab becomes visible again (user returns from WhatsApp / phone wake),
// immediately attempt reconnection if we're in a disconnected/reconnecting state.
if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    const state = useStore.getState();
    if (!state.code || !state.playerId) return; // no session to restore
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
    openSocket(useStore.setState, useStore.getState, state.code, state.playerId);
  });
}
