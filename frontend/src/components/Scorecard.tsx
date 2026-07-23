import { useEffect, useRef, useState } from "react";
import type { GameState, StatePlayer } from "../types";

const MEDAL = ["🥇", "🥈", "🥉"];

export default function Scorecard({ game, playerId }: { game: GameState; playerId: string }) {
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
        </div>
      )}
    </div>
  );
}
