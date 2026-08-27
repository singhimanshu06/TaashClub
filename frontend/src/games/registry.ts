import type { ComponentType } from "react";
import type { GameInfo, GameState, StatePlayer } from "../types";

/**
 * Extension slots a game plugs into the shared GameTable / Home / GameOver.
 *
 * The shared layout never forks per game; each game supplies React components
 * for the bits that are genuinely game-specific (status-bar extras, the action
 * panel above the hand, per-seat stats, round-end modal, detailed scores, and
 * the create-room options). Adding a game means implementing these slots and
 * registering them — no shared file changes.
 */
export interface GameSlots {
  /** Extra chips in the status bar (e.g. trump indicator). Optional. */
  StatusExtra?: ComponentType<{ game: GameState }>;

  /** Panel rendered above the hand when the viewer must act (e.g. bid picker).
   * For games that render their own Hand inside the ActionPanel (e.g. President's
   * combo selector), set ``rendersOwnHand`` so the shared GameTable doesn't
   * render a second Hand below. */
  ActionPanel?: ComponentType<{
    game: GameState;
    isMyTurn: boolean;
    sendAction: (action: string, params?: Record<string, unknown>) => void;
  }>;

  /** True if the ActionPanel renders its own Hand (President). When false/absent
   * the shared GameTable renders the Hand with click-to-play (Callbreak). */
  rendersOwnHand?: boolean;

  /** Per-seat stats line inside an opponent tile (e.g. "Bid 3 · Won 2"). */
  SeatStats?: ComponentType<{ game: GameState; player: StatePlayer; phase: string }>;

  /** Stats line inside the viewer's own chip (e.g. "Pts 12 · Bid 20").
   *  When absent, GameTable falls back to the generic "won X / bid Y". */
  SelfStats?: ComponentType<{ game: GameState; player: StatePlayer }>;

  /** Round-end modal. */
  RoundResult?: ComponentType<{
    game: GameState;
    sendAction: (action: string, params?: Record<string, unknown>) => void;
  }>;

  /** End-of-game detailed scorecard view. */
  DetailedScores?: ComponentType<{
    game: GameState;
    playerId: string;
    onBack: () => void;
  }>;

  /** Create-room options UI on the Home screen (player count, variants, ...). */
  HomeOptions?: ComponentType<{
    info: GameInfo;
    numPlayers: number;
    setNumPlayers: (n: number) => void;
    options: Record<string, unknown>;
    setOptions: (o: Record<string, unknown>) => void;
  }>;
}

export interface GameUIEntry {
  slots: GameSlots;
}

export const GAME_UI_REGISTRY: Record<string, GameUIEntry> = {};

export function registerGame(gameType: string, slots: GameSlots): void {
  GAME_UI_REGISTRY[gameType] = { slots };
}

export function getGameSlots(gameType: string | undefined | null): GameSlots {
  if (!gameType) return {};
  return GAME_UI_REGISTRY[gameType]?.slots ?? {};
}
