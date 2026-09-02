import type { GameState, RoundHistoryEntry } from "../../types";

const MEDAL = ["🥇", "🥈", "🥉"];

export default function CallbreakDetailedScores({
  game,
  playerId,
  onBack,
}: {
  game: GameState;
  playerId: string | null;
  onBack: () => void;
}) {
  // Players in seat order (stable columns across all rounds).
  const players = [...game.players].sort((a, b) => a.seat - b.seat);
  const history: RoundHistoryEntry[] = game.round_history ?? [];

  // Map round_index -> player_id -> points for quick cell lookup.
  const pointsByRound: Record<number, Record<string, number>> = {};
  const hitByRound: Record<number, Record<string, boolean>> = {};
  for (const r of history) {
    const pts: Record<string, number> = {};
    const hit: Record<string, boolean> = {};
    for (const row of r.results) {
      pts[row.player_id] = row.points ?? 0;
      hit[row.player_id] = row.hit ?? false;
    }
    pointsByRound[r.round_index] = pts;
    hitByRound[r.round_index] = hit;
  }

  // Totals for highlight (highest green, lowest red).
  const totals = game.final_standings ?? [];
  const totalById = new Map(totals.map((t) => [t.player_id, t.total_score]));
  const allTotals = players.map((p) => totalById.get(p.id) ?? 0);
  const maxTotal = allTotals.length ? Math.max(...allTotals) : 0;
  const minTotal = allTotals.length ? Math.min(...allTotals) : 0;
  const sameTotal = maxTotal === minTotal;

  function totalClass(pid: string) {
    if (sameTotal) return "";
    const v = totalById.get(pid) ?? 0;
    if (v === maxTotal) return "score-hi";
    if (v === minTotal) return "score-lo";
    return "";
  }

  function roundCellClass(roundIndex: number, pid: string) {
    // Highlight the highest/lowest *points* within that single round.
    const rows = pointsByRound[roundIndex];
    if (!rows) return "";
    const pts = Object.values(rows);
    if (pts.length < 2) return "";
    const mx = Math.max(...pts);
    const mn = Math.min(...pts);
    if (mx === mn) return "";
    const v = rows[pid];
    if (v === mx) return "score-hi";
    if (v === mn) return "score-lo";
    return "";
  }

  return (
    <div className="modal-backdrop">
      <div className="modal detailed-modal">
        <h2>Detailed Scorecard</h2>
        <p className="modal-sub">Points per round — highest green, lowest red</p>
        <div className="detailed-scroll">
          <table className="result-table detailed-table">
            <thead>
              <tr>
                <th>Round</th>
                {players.map((p) => (
                  <th key={p.id}>{p.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map((r) => (
                <tr key={r.round_index}>
                  <td className="round-cell">R{r.round_index + 1}</td>
                  {players.map((p) => {
                    const pts = pointsByRound[r.round_index]?.[p.id] ?? 0;
                    const hit = hitByRound[r.round_index]?.[p.id];
                    return (
                      <td
                        key={p.id}
                        className={`${roundCellClass(r.round_index, p.id)} ${hit ? "" : "pts-miss"}`}
                      >
                        {hit ? pts : 0}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="total-row">
                <td className="round-cell">Total</td>
                {players.map((p) => (
                  <td key={p.id} className={`${totalClass(p.id)} total-score`}>
                    {totalById.get(p.id) ?? 0}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        <div className="detailed-standings">
          {totals.map((s) => (
            <span key={s.player_id} className={s.player_id === playerId ? "you-row" : ""}>
              {MEDAL[s.rank - 1] ?? s.rank} {s.name}: {s.total_score}
            </span>
          ))}
        </div>
        <button className="btn-primary" onClick={onBack}>
          Back to summary
        </button>
      </div>
    </div>
  );
}
