export type Suit = "S" | "H" | "C" | "D";
export type Variant = "single_run" | "down_and_up";
export type Phase = "lobby" | "bidding" | "playing" | "exchange" | "round_end" | "game_end";

export interface CardT {
  suit: Suit;
  rank: number; // 2-14
}

export interface LobbyPlayer {
  id: string;
  name: string;
  seat: number;
  connected: boolean;
  is_bot?: boolean;
}

export interface Lobby {
  code: string;
  game_type: string;
  game_name: string;
  num_players: number;
  options: Record<string, unknown>;
  host_id: string | null;
  started: boolean;
  players: LobbyPlayer[];
}

export interface StatePlayer {
  id: string;
  name: string;
  seat: number;
  bid: number | null;
  tricks_won: number;
  hand_count: number;
  hand: CardT[] | null; // only for the viewer
  connected: boolean;
  is_bot?: boolean;
  total_score: number; // cumulative through completed rounds (0 during round 1)
}

export interface TrickCard {
  player_id: string;
  card: CardT;
}

export interface RoundResultRow {
  player_id: string;
  name: string;
  // Callbreak fields:
  bid?: number;
  tricks_won?: number;
  points?: number;
  hit?: boolean;
  // President fields:
  finish?: number;
  role?: string;
  round_score?: number;
  total_score?: number;
}

export interface RoundHistoryEntry {
  round_index: number;
  trump: Suit | null;
  cards_this_round: number;
  results: RoundResultRow[];
}

export interface Standing {
  player_id: string;
  name: string;
  total_score: number;
  rank: number;
}

export interface GameState {
  game_type: string;
  phase: Phase;
  num_players: number;
  variant?: Variant;
  rounds_total?: number;
  round_index: number;
  total_rounds?: number;
  cards_this_round: number | null;
  trump: Suit | null;
  starter_id: string | null;
  current_player_id: string | null;
  awaiting_trick_clear: boolean;
  trick_winner_id: string | null;
  led_suit: Suit | null;
  current_trick: TrickCard[];
  players: StatePlayer[];
  your_legal_cards: CardT[] | null;
  your_legal_actions: unknown[] | null;
  last_round_result: RoundResultRow[] | null;
  round_history: RoundHistoryEntry[];
  final_standings: Standing[] | null;
  // President-specific (optional; absent for Callbreak):
  pile_top?: { rank: number; size: number; player_id: string } | null;
  roles?: Record<string, string>;
  exchange?: {
    step: string;
    giver_id: string | null;
    receiver_id: string | null;
    count: number;
  } | null;
  finish_order?: string[];
  skipped_player_ids?: string[];
}

export interface ChatMessage {
  player_id: string;
  name: string;
  text: string;
  ts: number;
}

export interface OptionSchema {
  type: string;
  values?: string[];
  default?: string;
  labels?: Record<string, string>;
}

export interface GameInfo {
  game_type: string;
  display_name: string;
  description: string;
  min_players: number;
  max_players: number;
  options_schema: Record<string, OptionSchema>;
}
