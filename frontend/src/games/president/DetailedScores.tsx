import type { GameState, RoundHistoryEntry } from "../../types";

const MEDAL = ["🥇", "🥈", "🥉"];

type RoundRow = {
  player_id: string;
  name: string;
  finish?: number;
  role?: string;
  round_score?: number;
  total_score?: number;
};

/** End-of-game detailed scorecard: round-by-round points matrix. */
export default function PresidentDetailedScores({
  game,
  playerId,
  onBack,
}: {
  game: GameState;
  playerId: string | null;
  onBack: () => void;
}) {
  const players = [...game.players].sort((a, b) => a.seat - b.seat);
  const history: RoundHistoryEntry[] = game.round_history ?? [];

  // round_index -> player_id -> round_score
  const scoreByRound: Record<number, Record<string, number>> = {};
  for (const r of history) {
    const pts: Record<string, number> = {};
    for (const row of r.results as unknown as RoundRow[]) {
      pts[row.player_id] = row.round_score ?? 0;
    }
    scoreByRound[r.round_index] = pts;
  }

  const totals = game.final_standings ?? [];
  const totalById = new Map(totals.map((t) => [t.player_id, t.total_score]));

  return (
    <div className="modal-backdrop">
      <div className="modal detailed-modal">
        <h2>Detailed Scorecard</h2>
        <p className="modal-sub">Points per round</p>
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
                    const pts = scoreByRound[r.round_index]?.[p.id] ?? 0;
                    return (
                      <td key={p.id} className={pts < 0 ? "pts-miss" : pts > 0 ? "pts-hit" : ""}>
                        {pts > 0 ? `+${pts}` : pts}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="total-row">
                <td className="round-cell">Total</td>
                {players.map((p) => (
                  <td key={p.id} className="total-score">
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
