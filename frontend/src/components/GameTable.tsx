import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
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

/** The viewer's identity pill. Rendered in two spots (bottom of the table on
 *  tall screens, next to the hand on short ones); CSS shows the right one. */
function SelfChip({
  me,
  isMyTurn,
  teamClass,
  SelfStats,
  game,
  variant,
}: {
  me: StatePlayer;
  isMyTurn: boolean;
  teamClass: string;
  SelfStats: ReturnType<typeof getGameSlots>["SelfStats"];
  game: GameState;
  variant: "table" | "strip";
}) {
  return (
    <div className={`self-pos self-pos-${variant}${isMyTurn ? " seat-turn" : ""}`}>
      <div className={`self-chip${teamClass}`}>
        <span className="seat-avatar">{me.name.charAt(0).toUpperCase()}</span>
        <span className="self-meta">
          <span className="seat-label">{me.name} (you)</span>
          <span className="seat-stats">
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
          </span>
        </span>
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
  const trickWraps = slots.trickWraps ?? false;

  const me = game.players.find((p) => p.id === playerId);
  const isMyTurn = game.current_player_id === playerId;
  const nameById = (id: string) => game.players.find((p) => p.id === id)?.name ?? "";

  // Ring layout: everyone in play order (seat number ascending), viewer pinned
  // bottom-center. Equal angular spacing puts neighbours equidistant from each
  // other and from the table rim, preserves turn order around the ring, and
  // seats partnership teammates opposite (4p) / alternating (6p) for free.
  const ordered = [...game.players].sort((a, b) => a.seat - b.seat);
  const viewerIndex = Math.max(
    ordered.findIndex((p) => p.id === playerId),
    0
  );
  const seatPos = seatPositions(ordered.length, viewerIndex);

  // Team tinting — inert until a team game sends `teams`.
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

  const seatNode = (p: StatePlayer, i: number) => {
    const isCurrent = game.current_player_id === p.id;
    return (
      <div
        key={p.id}
        className={`seat-pos seat-rim-${seatPos[i].rim}${isCurrent ? " seat-turn" : ""}`}
        style={{ left: `${seatPos[i].left}%`, top: `${seatPos[i].top}%` }}
      >
        <Seat
          p={p}
          isCurrent={isCurrent}
          isStarter={game.starter_id === p.id}
          isWinner={game.awaiting_trick_clear && game.trick_winner_id === p.id}
          phase={game.phase}
          Stats={SeatStats ?? (() => null)}
          game={game}
        />
      </div>
    );
  };

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

      {/* Ring table: seats equidistant around the rim (viewer bottom-center),
          played cards in a centered row in the middle. */}
      <div className="table-stage">
        <div className="table-mid">
          <div className="felt" />

          {/* Opponents on the ring (play order clockwise from the viewer) */}
          {ordered.map((p, i) => (p.id === playerId ? null : seatNode(p, i)))}

          {/* Status pill + played cards, stacked in the middle of the table */}
          <div className="trick-col">
            {game.phase === "playing" && !game.awaiting_trick_clear && game.current_trick.length === 0 && (
              <p className="trick-hint">
                {isMyTurn ? "Your lead" : `${nameById(game.current_player_id ?? "")} to lead`}
              </p>
            )}
            {game.awaiting_trick_clear && game.trick_winner_id && (
              <p className="trick-hint winner-banner">
                🏆 {nameById(game.trick_winner_id)} wins the trick
              </p>
            )}
            {game.phase === "bidding" && (
              <p className="trick-hint">
                {isMyTurn ? "Your turn to bid" : `${nameById(game.current_player_id ?? "")} is bidding…`}
              </p>
            )}
            {game.phase === "exchange" && (
              <p className="trick-hint">Card exchange in progress…</p>
            )}
            {game.current_trick.length > 0 && (
              <div
                className={`trick-row${trickWraps ? " trick-row-wrap" : ""}`}
                style={{ "--n": game.current_trick.length } as CSSProperties}
              >
                {game.current_trick.map((t, i) => {
                  const cards = trickCards(t);
                  return (
                    <div key={`${t.player_id}-${i}`} className="trick-slot">
                      <div className="trick-cards">
                        {cards.map((c, j) => (
                          <PlayingCard
                            key={j}
                            card={c}
                            size="md"
                            highlight={game.awaiting_trick_clear && game.trick_winner_id === t.player_id}
                          />
                        ))}
                      </div>
                      <span className="trick-owner">{nameById(t.player_id)}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <SkipPopup game={game} nameById={nameById} />

          {/* Viewer's own chip sits just below the table, top edge touching
              the felt's bottom rim (tall screens; on short screens the copy
              in the self-strip shows) */}
          <SelfChip
            me={me}
            isMyTurn={isMyTurn}
            teamClass={teamClass(playerId)}
            SelfStats={SelfStats}
            game={game}
            variant="table"
          />
        </div>
      </div>

      {/* Your area: action panel (bid picker / combo selector) above the hand.
          Games whose ActionPanel renders its own Hand (President) set
          rendersOwnHand so this doesn't render a second Hand. */}
      <div className={`self-strip${isMyTurn ? " active" : ""}`}>
        <SelfChip
          me={me}
          isMyTurn={isMyTurn}
          teamClass={teamClass(playerId)}
          SelfStats={SelfStats}
          game={game}
          variant="strip"
        />
        {ActionPanel && (
          <ActionPanel game={game} isMyTurn={isMyTurn} sendAction={sendAction} />
        )}
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
