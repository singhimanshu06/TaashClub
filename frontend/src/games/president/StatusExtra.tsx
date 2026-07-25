import type { GameState } from "../../types";

const RANK_LABEL: Record<number, string> = { 11: "J", 12: "Q", 13: "K", 14: "A", 2: "2" };

/** Status-bar extra: shows the current combo to beat (rank × size). */
export default function PresidentStatusExtra({ game }: { game: GameState }) {
  const pile = game.pile_top;
  if (!pile) {
    return <div className="status-chip">Fresh lead</div>;
  }
  const label = RANK_LABEL[pile.rank] ?? String(pile.rank);
  return (
    <div className="status-chip beat-chip">
      <span className="beat-label">Beat</span>
      <strong className="beat-rank">{label}</strong>
      {pile.size > 1 && <small className="beat-size">×{pile.size}</small>}
    </div>
  );
}
