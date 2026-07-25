import { useEffect, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import type { CardT, GameState, StatePlayer } from "../types";
import PlayingCard from "./PlayingCard";
import Hand from "./Hand";
import GameOver from "./GameOver";
import Scorecard from "./Scorecard";
import { getGameSlots } from "../games/registry";

/** Normalize a trick entry's cards: President sends ``cards`` (array), Callbreak
 *  sends ``card`` (single). Returns a flat list of cards. */
function trickCards(entry: { card?: CardT; cards?: CardT[] }): CardT[] {
  if (entry.cards) return entry.cards;
  if (entry.card) return [entry.card];
  return [];
}

function Seat({
  p,
  isCurrent,
  isStarter,
  isWinner,
  phase,
  Stats,
  game,
}: {
  p: StatePlayer;
  isCurrent: boolean;
  isStarter: boolean;
  isWinner: boolean;
  phase: string;
  Stats: NonNullable<ReturnType<typeof getGameSlots>["SeatStats"]>;
  game: GameState;
}) {
  return (
    <div
      className={`seat-tile${isCurrent ? " current" : ""}${isWinner ? " winner" : ""}`}
    >
      <div className="seat-head">
        <span className="seat-avatar">{p.name.charAt(0).toUpperCase()}</span>
        <span className="seat-label">
          {p.name}
          {isStarter && <span className="starter-star" title="Leads this round">★</span>}
        </span>
      </div>
      <div className="seat-stats">
        <Stats game={game} player={p} phase={phase} />
      </div>
    </div>
  );
}

export default function GameTable() {
  const { game, playerId, sendAction, reset } = useStore(
    useShallow((s) => ({
      game: s.game as GameState,
      playerId: s.playerId!,
      sendAction: s.sendAction,
      reset: s.reset,
    }))
  );

  const slots = getGameSlots(game.game_type);
  const StatusExtra = slots.StatusExtra;
  const ActionPanel = slots.ActionPanel;
  const SeatStats = slots.SeatStats;
  const RoundResult = slots.RoundResult;
  const rendersOwnHand = slots.rendersOwnHand ?? false;

  const me = game.players.find((p) => p.id === playerId);
  const others = game.players.filter((p) => p.id !== playerId);
  const isMyTurn = game.current_player_id === playerId;
  const nameById = (id: string) => game.players.find((p) => p.id === id)?.name ?? "";

  // Field name compatibility: Callbreak uses total_rounds/cards_this_round,
  // President uses rounds_total. cards_this_round is absent for President.
  const totalRounds = game.rounds_total ?? game.total_rounds;
  const cardsThisRound = game.cards_this_round;

  // Guard: if the viewer isn't in the player list (transient state), render
  // nothing to avoid crashing on `me.name`.
  if (!me) return null;

  return (
    <div className="screen table-screen">
      {/* Top status bar: Scores (left) | round info (center) | Leave (right) */}
      <div className="status-bar">
        <div className="status-left">
          <Scorecard game={game} playerId={playerId} />
        </div>
        <div className="status-center">
          {totalRounds != null && (
            <div className="status-chip">
              Round <strong>{game.round_index + 1}</strong> / {totalRounds}
            </div>
          )}
          {StatusExtra && <StatusExtra game={game} />}
          {cardsThisRound != null && (
            <div className="status-chip">
              <strong>{cardsThisRound}</strong> cards
            </div>
          )}
        </div>
        <div className="status-right">
          <button className="leave-btn" onClick={reset} title="Leave game">
            ← Leave
          </button>
        </div>
      </div>

      {/* Opponents */}
      <div className="opponents">
        {others.map((p) => (
          <Seat
            key={p.id}
            p={p}
            isCurrent={game.current_player_id === p.id}
            isStarter={game.starter_id === p.id}
            isWinner={game.awaiting_trick_clear && game.trick_winner_id === p.id}
            phase={game.phase}
            Stats={SeatStats ?? (() => null)}
            game={game}
          />
        ))}
      </div>

      {/* Felt center: current trick */}
      <div className="felt">
        {game.phase === "playing" && !game.awaiting_trick_clear && game.current_trick.length === 0 && (
          <p className="felt-hint">
            {isMyTurn ? "Your lead" : `${nameById(game.current_player_id ?? "")} to lead`}
          </p>
        )}
        <div className="trick-area">
          {game.current_trick.map((t, i) => {
            const cards = trickCards(t);
            return (
              <div key={`${t.player_id}-${i}`} className="trick-slot">
                {cards.map((c, j) => (
                  <PlayingCard
                    key={j}
                    card={c}
                    size="md"
                    highlight={game.awaiting_trick_clear && game.trick_winner_id === t.player_id}
                  />
                ))}
                <span className="trick-owner">{nameById(t.player_id)}</span>
              </div>
            );
          })}
        </div>
        {game.awaiting_trick_clear && game.trick_winner_id && (
          <p className="felt-hint winner-banner">🏆 {nameById(game.trick_winner_id)} wins the trick</p>
        )}
        {game.phase === "bidding" && (
          <p className="felt-hint">
            {isMyTurn ? "Your turn to bid" : `${nameById(game.current_player_id ?? "")} is bidding…`}
          </p>
        )}
        {game.phase === "exchange" && (
          <p className="felt-hint">
            Card exchange in progress…
          </p>
        )}
        <SkipPopup game={game} nameById={nameById} />
      </div>

      {/* Your area */}
      <div className={`your-area${isMyTurn ? " active" : ""}`}>
        <div className="your-tag">
          {me.name} (you)
          {me.bid !== null && me.bid !== undefined && (
            <span className="your-stats">
              won {me.tricks_won} / bid {me.bid}
            </span>
          )}
        </div>
        {/* Action panel (e.g. bid picker or combo selector) sits ABOVE the hand. */}
        {ActionPanel && (
          <ActionPanel game={game} isMyTurn={isMyTurn} sendAction={sendAction} />
        )}
        {/* Hand: rendered by GameTable for games that use click-to-play (Callbreak).
            Games whose ActionPanel renders its own Hand (President) set
            rendersOwnHand to skip this. */}
        {!rendersOwnHand && (
          <Hand
            hand={me.hand ?? []}
            legal={game.phase === "playing" && isMyTurn ? game.your_legal_cards : null}
            onPlay={(card) => sendAction("play_card", { card })}
          />
        )}
      </div>

      {/* Overlays */}
      {game.phase === "round_end" && RoundResult && (
        <RoundResult game={game} sendAction={sendAction} />
      )}
      {game.phase === "game_end" && <GameOver game={game} />}
    </div>
  );
}

/**
 * Centered popup that appears for 2s whenever a player is newly skipped
 * (two consecutive same-rank plays). Works for any game that sends
 * ``skipped_player_ids``; no-op for games that don't (Callbreak).
 */
function SkipPopup({
  game,
  nameById,
}: {
  game: GameState;
  nameById: (id: string) => string;
}) {
  const [popup, setPopup] = useState<{ name: string } | null>(null);
  const prevSkipped = useRef<Set<string>>(new Set());
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skippedIds = game.skipped_player_ids ?? [];
  const skippedKey = skippedIds.join(",");

  useEffect(() => {
    const skipped = new Set(skippedIds);
    // Find players who are newly skipped (in `skipped` but not in `prevSkipped`).
    const newlySkipped: string[] = [];
    for (const id of skipped) {
      if (!prevSkipped.current.has(id)) newlySkipped.push(id);
    }
    prevSkipped.current = skipped;

    if (newlySkipped.length === 0) return;

    // Show the first newly-skipped player.
    const name = nameById(newlySkipped[0]);
    setPopup({ name });
    // Clear any existing timer, then set a fresh 2s timer. Don't cancel this
    // timer on effect cleanup — state updates from bots playing would cancel
    // it before it fires, leaving the popup stuck on screen.
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setPopup(null);
      timerRef.current = null;
    }, 2000);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skippedKey, game.current_player_id, game.pile_top]);

  // Clear the timer on unmount.
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  if (!popup) return null;
  return (
    <div className="skip-popup">
      ⏭️ {popup.name} skipped!
    </div>
  );
}
