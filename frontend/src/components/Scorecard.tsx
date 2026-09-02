import { useEffect, useRef, useState } from "react";
import type { GameState, StatePlayer } from "../types";

const MEDAL = ["🥇", "🥈", "🥉"];

export default function Scorecard({ game, playerId }: { game: GameState; playerId: string | null }) {
  const [open, setOpen] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (popRef.current && !popRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Cumulative totals through completed rounds, sorted descending.
  const ranked = [...game.players].sort((a, b) => b.total_score - a.total_score);
  const scores = ranked.map((p) => p.total_score);
  const max = scores.length ? Math.max(...scores) : 0;
  const min = scores.length ? Math.min(...scores) : 0;
  const anyDone = ranked.some((p) => p.total_score > 0) || game.round_index > 0;

  // Team games (Twenty-Eight): one row per partnership, member names beneath.
  const teamsMap = game.teams;
  const teamRows = teamsMap
    ? [...new Set(Object.values(teamsMap).map(String))]
        .sort()
        .map((t) => {
          const members = game.players.filter((p) => String(teamsMap[p.id]) === t);
          return {
            id: t,
            label: `Team ${Number(t) + 1}`,
            names: members.map((m) => m.name).join(" & "),
            total: members.reduce((s, m) => s + m.total_score, 0) / (members.length || 1),
            mine: members.some((m) => m.id === playerId),
          };
        })
        .sort((a, b) => b.total - a.total)
    : null;

  function teamCellClass(t: { total: number }) {
    if (!teamRows || teamRows.length < 2) return "";
    const totals = teamRows.map((r) => r.total);
    if (Math.max(...totals) === Math.min(...totals)) return "";
    if (t.total === Math.max(...totals)) return "score-hi";
    if (t.total === Math.min(...totals)) return "score-lo";
    return "";
  }

  function cellClass(p: StatePlayer) {
    if (scores.length < 2 || max === min) return "";
    if (p.total_score === max) return "score-hi";
    if (p.total_score === min) return "score-lo";
    return "";
  }

  return (
    <div className="scorecard-wrap" ref={popRef}>
      <button
        className={`status-chip score-toggle${open ? " active" : ""}`}
        onClick={() => setOpen((v) => !v)}
        title="Cumulative scoreboard"
      >
        Scores
      </button>
      {open && (
        <div className="scorecard-pop">
          <div className="scorecard-head">
            <span>Cumulative · through round {Math.max(game.round_index, 0)}</span>
            {!anyDone && <em className="scorecard-empty">No rounds completed yet</em>}
          </div>
          {teamRows ? (
            <table className="result-table scorecard-table">
              <thead>
                <tr>
                  <th>Team</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {teamRows.map((t) => (
                  <tr key={t.id} className={t.mine ? "you-row" : ""}>
                    <td>{t.names}</td>
                    <td className={`${teamCellClass(t)} total-score`}>{t.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="result-table scorecard-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Player</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {ranked.map((p, i) => (
                  <tr key={p.id} className={p.id === playerId ? "you-row" : ""}>
                    <td>{MEDAL[i] ?? i + 1}</td>
                    <td>{p.name}</td>
                    <td className={`${cellClass(p)} total-score`}>{p.total_score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
