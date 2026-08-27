import { useState } from "react";
import type { GameState, Suit } from "../../types";

const SUITS: Suit[] = ["S", "H", "C", "D"];
const SUIT_NAME: Record<Suit, string> = {
  S: "Spades",
  H: "Hearts",
  C: "Clubs",
  D: "Diamonds",
};

function nameOf(game: GameState, id: string | null | undefined): string {
  if (!id) return "";
  return game.players.find((p) => p.id === id)?.name ?? "";
}

/** Suit icon from the extracted sprite assets (public/suits/<SUIT>.png). */
function SuitIcon({ suit }: { suit: Suit }) {
  return (
    <img
      src={`/suits/${suit}.png`}
      alt={SUIT_NAME[suit]}
      className="suit-icon"
      draggable={false}
    />
  );
}

/** Suit picker shown to the winning bidder when they must name trump. */
function TrumpPicker({
  sendAction,
}: {
  sendAction: (action: string, params?: Record<string, unknown>) => void;
}) {
  return (
    <div className="bid-panel">
      <p className="panel-title">You won the bid — choose the hidden trump suit</p>
      <div className="chip-row">
        {SUITS.map((s) => (
          <button
            key={s}
            className="chip wide suit-chip"
            onClick={() => sendAction("set_trump", { suit: s })}
          >
            <SuitIcon suit={s} />
            {SUIT_NAME[s]}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Bid stepper (14–28) with pass. */
function AuctionPanel({
  game,
  sendAction,
}: {
  game: GameState;
  sendAction: (action: string, params?: Record<string, unknown>) => void;
}) {
  const minBid = 14;
  const maxBid = 28;
  const floor = game.high_bid != null ? game.high_bid + 1 : minBid;
  const [value, setValue] = useState(floor);
  const clamp = (v: number) => Math.max(floor, Math.min(maxBid, v));
  const canPass = game.high_bid != null;

  return (
    <div className="bid-panel">
      {game.high_bid != null && (
        <p className="panel-title">
          Current bid <strong>{game.high_bid}</strong> — {nameOf(game, game.bidder_id)}
        </p>
      )}
      <div className="bid-row">
        <div className="bid-stepper">
          <button
            className="step-btn"
            disabled={value <= floor}
            onClick={() => setValue((v) => clamp(v - 1))}
            aria-label="decrease bid"
          >
            −
          </button>
          <div className="step-value">
            <span className="step-num">{value}</span>
            <small>
              of {maxBid}
              {game.high_bid != null && floor > 20 ? " · partner ≥20" : ""}
            </small>
          </div>
          <button
            className="step-btn"
            disabled={value >= maxBid}
            onClick={() => setValue((v) => clamp(v + 1))}
            aria-label="increase bid"
          >
            +
          </button>
        </div>
        <button className="btn-primary bid-confirm" onClick={() => sendAction("place_bid", { value: clamp(value) })}>
          Bid {clamp(value)}
        </button>
        {canPass && (
          <button className="btn-secondary" onClick={() => sendAction("pass")}>
            Pass
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Twenty-Eight action panel:
 *  - bidding: bid stepper + pass, or the trump picker for the auction winner
 *  - playing: a "Reveal Trump" button when the viewer is eligible
 */
export default function TwentyEightActionPanel({
  game,
  isMyTurn,
  sendAction,
}: {
  game: GameState;
  isMyTurn: boolean;
  sendAction: (action: string, params?: Record<string, unknown>) => void;
}) {
  if (!isMyTurn) return null;

  if (game.phase === "bidding") {
    return game.awaiting_trump ? <TrumpPicker sendAction={sendAction} /> : <AuctionPanel game={game} sendAction={sendAction} />;
  }

  if (game.phase === "playing") {
    const canReveal = (game.your_legal_actions ?? []).some(
      (a) => (a as { action?: string })?.action === "expose_trump"
    );
    if (!canReveal) return null;
    return (
      <div className="bid-panel">
        <button className="btn-primary" onClick={() => sendAction("expose_trump")}>
          🂠 Reveal Trump
        </button>
        <p className="panel-title">You cannot follow suit — reveal the hidden trump or discard below.</p>
      </div>
    );
  }

  return null;
}
