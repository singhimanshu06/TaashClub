import { create } from "zustand";
import { WS_BASE } from "./api";
import type { CardT, ChatMessage, GameState, Lobby } from "./types";

type Screen = "home" | "lobby" | "game";

interface Store {
  screen: Screen;
  code: string | null;
  playerId: string | null;
  lobby: Lobby | null;
  game: GameState | null;
  error: string | null;
  connected: boolean;
  messages: ChatMessage[];

  enterRoom: (code: string, playerId: string) => void;
  startGame: () => void;
  placeBid: (value: number) => void;
  playCard: (card: CardT) => void;
  advanceRound: () => void;
  sendChat: (text: string) => void;
  clearError: () => void;
  reset: () => void;
}

let socket: WebSocket | null = null;

function send(msg: object) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(msg));
  }
}

export const useStore = create<Store>((set) => ({
  screen: "home",
  code: null,
  playerId: null,
  lobby: null,
  game: null,
  error: null,
  connected: false,
  messages: [],

  enterRoom: (code, playerId) => {
    set({ code, playerId, screen: "lobby", messages: [] });
    if (socket) socket.close();
    socket = new WebSocket(`${WS_BASE}/ws/${code}?player_id=${playerId}`);

    socket.onopen = () => set({ connected: true });
    socket.onclose = () => set({ connected: false });
    socket.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "lobby_update") {
        set({ lobby: msg.lobby });
      } else if (msg.type === "state_update") {
        const game: GameState = msg.state;
        set({ game, screen: game.phase === "lobby" ? "lobby" : "game" });
      } else if (msg.type === "chat_history") {
        set({ messages: msg.messages as ChatMessage[] });
      } else if (msg.type === "chat") {
        set((s) => ({ messages: [...s.messages, msg.message as ChatMessage] }));
      } else if (msg.type === "error") {
        set({ error: msg.message });
      }
    };
  },

  startGame: () => send({ type: "start_game" }),
  placeBid: (value) => send({ type: "place_bid", value }),
  playCard: (card) => send({ type: "play_card", card }),
  advanceRound: () => send({ type: "advance_round" }),
  sendChat: (text) => {
    const t = text.trim();
    if (t) send({ type: "chat", text: t });
  },
  clearError: () => set({ error: null }),
  reset: () => {
    if (socket) socket.close();
    socket = null;
    set({
      screen: "home",
      code: null,
      playerId: null,
      lobby: null,
      game: null,
      error: null,
      connected: false,
      messages: [],
    });
  },
}));
