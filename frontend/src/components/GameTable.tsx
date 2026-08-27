import { useEffect, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import type { CardT, GameState, StatePlayer } from "../types";
import PlayingCard from "./PlayingCard";
import Hand from "./Hand";
import GameOver from "./GameOver";
import Scorecard from "./Scorecard";
import { getGameSlots } from "../games/registry";
import { seatPositions } from "../table/seating";
import { playSound, isMuted, setMuted } from "../sounds";

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
  const SelfStats = slots.SelfStats;
  const RoundResult = slots.RoundResult;
  const rendersOwnHand = slots.rendersOwnHand ?? false;

  const me = game.players.find((p) => p.id === playerId);
  const isMyTurn = game.current_player_id === playerId;
  const nameById = (id: string) => game.players.find((p) => p.id === id)?.name ?? "";

  // Ring layout: everyone in play order (seat number ascending), viewer pinned
  // bottom-center. Even spacing preserves turn order around the table and puts
  // alternately-seated partners diametrically opposite in team games.
  const ordered = [...game.players].sort((a, b) => a.seat - b.seat);
  const viewerIndex = Math.max(
    ordered.findIndex((p) => p.id === playerId),
    0
  );
  const seatPos = seatPositions(ordered.length, viewerIndex);

  // Team tinting — inert until a future team game sends `teams`.
  const teamClass = (id: string) => {
    const t = game.teams?.[id];
    return t != null ? ` team-${String(t).replace(/\W/g, "")}` : "";
  };

  const [muted, setMutedState] = useState(isMuted());

  // Sound triggers — fire on transitions rather than absolute state. Refs
  // start at null so the very first round (where GameTable mounts already in
  // the "bidding" phase) is treated as a transition and still plays.
  const prevPhase = useRef<string | null>(null);
  const prevTurn = useRef<string | null>(null);
  useEffect(() => {
    const prevP = prevPhase.current;
    const curP = game.phase;
    const curTurn = game.current_player_id;
    const prevT = prevTurn.current;

    // Card distribution: when a new round is dealt (entering the bidding phase).
    if (prevP !== "bidding" && curP === "bidding") {
      playSound("card_distribution");
    }
    // Turn to bid: when it becomes my turn to bid.
    if (curP === "bidding" && curTurn === playerId && prevT !== playerId) {
      playSound("turn_to_bid");
    }
    // Turn to play: when it becomes my turn to play a card.
    if (curP === "playing" && curTurn === playerId && prevT !== playerId) {
      playSound("turn_to_play");
    }
    // Score board: when a round ends and the scoreboard appears.
    if (prevP !== "round_end" && curP === "round_end") {
      playSound("score_board");
    }

    prevPhase.current = curP;
    prevTurn.current = curTurn;
  }, [game.phase, game.current_player_id, playerId]);

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
          <button
            className="mute-btn"
            onClick={() => {
              const next = !muted;
              setMuted(next);
              setMutedState(next);
            }}
            title={muted ? "Unmute sound" : "Mute sound"}
            aria-label={muted ? "Unmute sound" : "Mute sound"}
          >
            {muted ? "🔇" : "🔊"}
          </button>
          <button className="leave-btn" onClick={reset} title="Leave game">
            ← Leave
          </button>
        </div>
      </div>

      {/* Oval table: seats around the rim, trick in the center */}
      <div className="table-stage">
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

        {/* Seats on the rim (positioned by play order; viewer bottom-center) */}
        {ordered.map((p, i) =>
          p.id === playerId ? null : (
            <div
              key={p.id}
              className={`seat-pos${game.current_player_id === p.id ? " seat-pos-current" : ""}`}
              style={{ left: `${seatPos[i].left}%`, top: `${seatPos[i].top}%` }}
            >
              <Seat
                p={p}
                isCurrent={game.current_player_id === p.id}
                isStarter={game.starter_id === p.id}
                isWinner={game.awaiting_trick_clear && game.trick_winner_id === p.id}
                phase={game.phase}
                Stats={SeatStats ?? (() => null)}
                game={game}
              />
            </div>
          )
        )}

        {/* Viewer's own chip sits above the hand strip */}
        <div
          className={`seat-pos self-pos${isMyTurn ? " seat-pos-current" : ""}`}
          style={{ left: "50%", top: "96%" }}
        >
          <div className={`self-chip${teamClass(playerId)}`}>
            <span className="seat-avatar">{me.name.charAt(0).toUpperCase()}</span>
            <span>{me.name} (you)</span>
            {SelfStats ? (
              <SelfStats game={game} player={me} />
            ) : (
              me.bid !== null &&
              me.bid !== undefined && (
                <span className="your-stats">
                  won {me.tricks_won} / bid {me.bid}
                </span>
              )
            )}
          </div>
        </div>
      </div>

      {/* Your area */}
      <div className={`your-area${isMyTurn ? " active" : ""}`}>
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
      <RotateHint active={game.num_players >= 5} />
      {game.phase === "round_end" && RoundResult && (
        <RoundResult game={game} sendAction={sendAction} />
      )}
      {game.phase === "game_end" && <GameOver game={game} />}
    </div>
  );
}

/**
 * Dismissible "rotate your phone" hint. Shown on portrait phones only when the
 * seat count is high enough that a landscape oval breathes better.
 */
function RotateHint({ active }: { active: boolean }) {
  const [dismissed, setDismissed] = useState(false);
  const [portrait, setPortrait] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(orientation: portrait)").matches
  );

  useEffect(() => {
    const mq = window.matchMedia("(orientation: portrait)");
    const onChange = (e: MediaQueryListEvent) => setPortrait(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  if (!active || dismissed || !portrait) return null;
  return (
    <div className="rotate-hint">
      <span>↻ Rotate your phone for a better view</span>
      <button onClick={() => setDismissed(true)} aria-label="Dismiss">
        ×
      </button>
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
