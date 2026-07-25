import type { GameState, StatePlayer } from "../../types";

/** Per-seat stats for an opponent tile: bid status during bidding, tricks otherwise. */
export default function CallbreakSeatStats({
  player,
  phase,
}: {
  game: GameState;
  player: StatePlayer;
  phase: string;
}) {
  if (phase === "bidding") {
    return (
      <span className={player.bid !== null ? "bid-locked" : "bid-pending"}>
        {player.bid !== null ? `Bid ${player.bid}` : "bidding…"}
      </span>
    );
  }
  return (
    <span className="tricks">
      Won <strong>{player.tricks_won}</strong>
      {player.bid !== null && <> / bid {player.bid}</>}
    </span>
  );
}
