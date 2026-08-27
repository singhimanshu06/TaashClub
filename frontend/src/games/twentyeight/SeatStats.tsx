import type { GameState, StatePlayer } from "../../types";

/**
 * Per-seat stats for an opponent tile:
 *  - auction: pending / passed / standing bid
 *  - play: partnership card points captured this deal (identical for both
 *    partners — tricks won are not shown), plus "Bidder" badge
 */
export default function TwentyEightSeatStats({
  game,
  player,
  phase,
}: {
  game: GameState;
  player: StatePlayer;
  phase: string;
}) {
  const isBidder = game.bidder_id === player.id;

  if (phase === "bidding") {
    if (player.passed) return <span className="bid-locked">passed</span>;
    if (player.bid !== null) return <span className="bid-locked">Bid {player.bid}</span>;
    return <span className="bid-pending">bidding…</span>;
  }

  const team = game.teams?.[player.id];
  const captured = team != null ? (game.team_captured?.[String(team)] ?? 0) : 0;
  return (
    <span className="tricks">
      {isBidder && <em className="bidder-tag">Bid {game.high_bid} · </em>}
      Pts <strong>{captured}</strong>
    </span>
  );
}
