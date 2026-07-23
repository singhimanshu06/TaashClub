import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import type { GameState, StatePlayer } from "../types";
import PlayingCard, { CardBack, suitSymbol, isRed } from "./PlayingCard";
import Hand from "./Hand";
import BidPanel from "./BidPanel";
import RoundResult from "./RoundResult";
import GameOver from "./GameOver";

const VARIANT_TRUMP_NAME: Record<string, string> = { S: "Spades", H: "Hearts", C: "Clubs", D: "Diamonds" };

function Seat({
  p,
  isCurrent,
  isStarter,
  isWinner,
  phase,
}: {
  p: StatePlayer;
  isCurrent: boolean;
  isStarter: boolean;
  isWinner: boolean;
  phase: string;
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
        {phase === "bidding" ? (
          <span className={p.bid !== null ? "bid-locked" : "bid-pending"}>
            {p.bid !== null ? `Bid ${p.bid}` : "bidding…"}
          </span>
        ) : (
          <span className="tricks">
            Won <strong>{p.tricks_won}</strong>
            {p.bid !== null && <> / bid {p.bid}</>}
          </span>
        )}
      </div>
      <div className="seat-cardcount" aria-hidden>
        {Array.from({ length: Math.min(p.hand_count, 6) }).map((_, i) => (
          <CardBack key={i} size="sm" />
        ))}
      </div>
    </div>
  );
}

export default function GameTable() {
  const { game, playerId, placeBid, playCard } = useStore(
    useShallow((s) => ({
      game: s.game as GameState,
      playerId: s.playerId!,
      placeBid: s.placeBid,
      playCard: s.playCard,
    }))
  );

  const me = game.players.find((p) => p.id === playerId)!;
  const others = game.players.filter((p) => p.id !== playerId);
  const isMyTurn = game.current_player_id === playerId;
  const nameById = (id: string) => game.players.find((p) => p.id === id)?.name ?? "";

  return (
    <div className="screen table-screen">
      {/* Top status bar */}
      <div className="status-bar">
        <div className="status-chip">
          Round <strong>{game.round_index + 1}</strong> / {game.total_rounds}
        </div>
        <div className="status-chip">
          <strong>{game.cards_this_round}</strong> cards
        </div>
        {game.trump && (
          <div className={`trump-chip ${isRed(game.trump) ? "red" : "black"}`}>
            Trump <span className="trump-symbol">{suitSymbol(game.trump)}</span>
            <small>{VARIANT_TRUMP_NAME[game.trump]}</small>
          </div>
        )}
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
          {game.current_trick.map((t) => (
            <div key={t.player_id} className="trick-slot">
              <PlayingCard
                card={t.card}
                size="md"
                highlight={game.awaiting_trick_clear && game.trick_winner_id === t.player_id}
              />
              <span className="trick-owner">{nameById(t.player_id)}</span>
            </div>
          ))}
        </div>
        {game.awaiting_trick_clear && game.trick_winner_id && (
          <p className="felt-hint winner-banner">🏆 {nameById(game.trick_winner_id)} wins the trick</p>
        )}
        {game.phase === "bidding" && (
          <p className="felt-hint">
            {isMyTurn ? "Your turn to bid" : `${nameById(game.current_player_id ?? "")} is bidding…`}
          </p>
        )}
      </div>

      {/* Your area */}
      <div className={`your-area${isMyTurn ? " active" : ""}`}>
        <div className="your-tag">
          {me.name} (you)
          {game.phase !== "bidding" && (
            <span className="your-stats">
              won {me.tricks_won}
              {me.bid !== null && ` / bid ${me.bid}`}
            </span>
          )}
        </div>
        {/* Bid panel sits ABOVE the hand so your cards stay readable below it. */}
        {game.phase === "bidding" && isMyTurn && game.cards_this_round !== null && (
          <BidPanel maxBid={game.cards_this_round} onBid={placeBid} />
        )}
        <Hand
          hand={me.hand ?? []}
          legal={game.phase === "playing" && isMyTurn ? game.your_legal_cards : null}
          onPlay={playCard}
        />
      </div>

      {/* Overlays */}
      {game.phase === "round_end" && <RoundResult game={game} />}
      {game.phase === "game_end" && <GameOver game={game} />}
    </div>
  );
}
