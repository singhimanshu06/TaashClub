import { useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import type { GameState } from "../types";
import { getGameSlots } from "../games/registry";

const MEDAL = ["🥇", "🥈", "🥉"];

export default function GameOver({ game }: { game: GameState }) {
  const { playerId, reset } = useStore(
    useShallow((s) => ({ playerId: s.playerId, reset: s.reset }))
  );
  const [showDetailed, setShowDetailed] = useState(false);
  const standings = game.final_standings ?? [];
  const DetailedScores = getGameSlots(game.game_type).DetailedScores;

  // Team games (Twenty-Eight): score per partnership, member names underneath.
  const teamsMap = game.teams ?? {};
  const teamIds = game.teams
    ? [...new Set(Object.values(teamsMap).map(String))].sort()
    : null;
  const teamRows =
    teamIds?.map((t) => {
      const members = game.players.filter((p) => String(teamsMap[p.id]) === t);
      return {
        id: t,
        label: `Team ${Number(t) + 1}`,
        members,
        total: members.reduce((s, m) => s + m.total_score, 0) / (members.length || 1),
      };
    }) ?? null;
  const teamWinner =
    teamRows && teamRows.length === 2
      ? teamRows[0].total === teamRows[1].total
        ? null
        : teamRows[0].total > teamRows[1].total
          ? teamRows[0]
          : teamRows[1]
      : null;

  if (showDetailed && DetailedScores) {
    return <DetailedScores game={game} playerId={playerId!} onBack={() => setShowDetailed(false)} />;
  }

  return (
    <div className="modal-backdrop">
      <div className="modal gameover">
        <h2>🏆 Game Over</h2>
        {teamRows ? (
          <>
            <p className="winner-line">
              {teamWinner ? `${teamWinner.label} wins!` : "It's a tie!"}
            </p>
            <div className="scoreboard">
              <h3>Final Scoreboard</h3>
              <table className="result-table">
                <thead>
                  <tr>
                    <th>Team</th>
                    <th>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {teamRows.map((t) => (
                    <tr key={t.id} className={t.members.some((m) => m.id === playerId) ? "you-row" : ""}>
                      <td>{t.members.map((m) => m.name).join(" & ")}</td>
                      <td className="total-score">{t.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <>
            {standings[0] && (
              <p className="winner-line">
                {standings.length > 1 && standings[0].total_score === standings[1].total_score
                  ? "It's a tie!"
                  : `${standings[0].name} wins!`}
              </p>
            )}
            <div className="scoreboard">
              <h3>Final Scoreboard</h3>
              <table className="result-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Player</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {standings.map((s) => (
                    <tr key={s.player_id} className={s.player_id === playerId ? "you-row" : ""}>
                      <td>{MEDAL[s.rank - 1] ?? s.rank}</td>
                      <td>{s.name}</td>
                      <td className="total-score">{s.total_score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {DetailedScores && (
          <button className="btn-primary" onClick={() => setShowDetailed(true)}>
            Detailed scores
          </button>
        )}
        <button className="btn-primary" onClick={reset}>
          Back to Home
        </button>
      </div>
    </div>
  );
}
