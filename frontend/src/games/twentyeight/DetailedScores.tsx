import type { GameState, RoundHistoryEntry } from "../../types";

const MEDAL = ["🥇", "🥈"];

/** End-of-game grid: partnership deltas (±1) per deal, with bid vs captured. */
export default function TwentyEightDetailedScores({
  game,
  playerId,
  onBack,
}: {
  game: GameState;
  playerId: string;
  onBack: () => void;
}) {
  const history: RoundHistoryEntry[] = game.round_history ?? [];
  const teamsMap = game.teams ?? {};
  const teamIds = [...new Set(Object.values(teamsMap).map(String))].sort();

  const teams = teamIds.map((t) => {
    const members = game.players
      .filter((p) => String(teamsMap[p.id]) === t)
      .sort((a, b) => a.seat - b.seat);
    return {
      id: t,
      label: `Team ${Number(t) + 1}`,
      members,
      names: members.map((m) => m.name).join(" & "),
      mine: members.some((m) => m.id === playerId),
    };
  });

  // Per-deal partnership delta (both partners share the same value).
  const deltaByRound: Record<number, Record<string, number>> = {};
  for (const r of history) {
    const byTeam: Record<string, number> = {};
    for (const t of teamIds) {
      const member = game.players.find(
        (p) => String(teamsMap[p.id]) === t && r.results.some((row) => row.player_id === p.id)
      );
      byTeam[t] = r.results.find((row) => row.player_id === member?.id)?.points ?? 0;
    }
    deltaByRound[r.round_index] = byTeam;
  }

  const totals = game.final_standings ?? [];
  const teamTotals = teams.map((t) => ({
    ...t,
    total: totals.find((s) => s.player_id === t.members[0]?.id)?.total_score ?? 0,
  }));
  const maxTotal = Math.max(...teamTotals.map((t) => t.total));
  const minTotal = Math.min(...teamTotals.map((t) => t.total));
  const sameTotal = maxTotal === minTotal;

  function totalClass(t: number) {
    if (sameTotal) return "";
    if (t === maxTotal) return "score-hi";
    if (t === minTotal) return "score-lo";
    return "";
  }

  function cellText(v: number) {
    return v > 0 ? `+${v}` : v < 0 ? String(v) : "0";
  }

  return (
    <div className="modal-backdrop">
      <div className="modal detailed-modal">
        <h2>Detailed Scorecard</h2>
        <p className="modal-sub">+1 bid made · −1 bid failed — per deal</p>
        <div className="detailed-scroll">
          <table className="result-table detailed-table">
            <thead>
              <tr>
                <th>Deal</th>
                <th>Bid</th>
                <th>Got</th>
                {teams.map((t) => (
                  <th key={t.id}>
                    {t.label}
                    <small className="team-members">{t.names}</small>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map((r) => (
                <tr key={r.round_index}>
                  <td className="round-cell">D{r.round_index + 1}</td>
                  <td>
                    {r.high_bid}
                    <small className={r.bid_made ? "pts-hit" : "pts-miss"}>
                      {r.bid_made ? " ✓" : " ✗"}
                    </small>
                  </td>
                  <td>{r.captured_points}</td>
                  {teamIds.map((t) => {
                    const v = deltaByRound[r.round_index]?.[t] ?? 0;
                    return (
                      <td key={t} className={v > 0 ? "score-hi" : v < 0 ? "score-lo" : ""}>
                        {cellText(v)}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="total-row">
                <td className="round-cell" colSpan={3}>
                  Total
                </td>
                {teamTotals.map((t) => (
                  <td key={t.id} className={`${totalClass(t.total)} total-score`}>
                    {t.total}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        <div className="detailed-standings">
          {[...teamTotals]
            .sort((a, b) => b.total - a.total)
            .map((t, i) => (
              <span key={t.id} className={t.mine ? "you-row" : ""}>
                {MEDAL[i] ?? i + 1} {t.label} ({t.names}): {t.total}
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
