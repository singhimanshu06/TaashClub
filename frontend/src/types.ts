export type Suit = "S" | "H" | "C" | "D";
export type Variant = "single_run" | "down_and_up";
export type Phase = "lobby" | "bidding" | "playing" | "round_end" | "game_end";

export interface CardT {
  suit: Suit;
  rank: number; // 2-14
}

export interface LobbyPlayer {
  id: string;
  name: string;
  seat: number;
  connected: boolean;
}

export interface Lobby {
  code: string;
  num_players: number;
  variant: Variant;
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
}

export interface TrickCard {
  player_id: string;
  card: CardT;
}

export interface RoundResultRow {
  player_id: string;
  name: string;
  bid: number;
  tricks_won: number;
  points: number;
  hit: boolean;
}

export interface Standing {
  player_id: string;
  name: string;
  total_score: number;
  rank: number;
}

export interface GameState {
  phase: Phase;
  num_players: number;
  variant: Variant;
  round_index: number;
  total_rounds: number;
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
  last_round_result: RoundResultRow[] | null;
  final_standings: Standing[] | null;
}

export interface ChatMessage {
  player_id: string;
  name: string;
  text: string;
  ts: number;
}
