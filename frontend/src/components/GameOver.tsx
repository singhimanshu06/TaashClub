import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import type { GameState } from "../types";

const MEDAL = ["🥇", "🥈", "🥉"];

export default function GameOver({ game }: { game: GameState }) {
  const { playerId, reset } = useStore(
    useShallow((s) => ({ playerId: s.playerId, reset: s.reset }))
  );
  const standings = game.final_standings ?? [];
  const winner = standings[0];

  return (
    <div className="modal-backdrop">
      <div className="modal gameover">
        <h2>🏆 Game Over</h2>
        {winner && <p className="winner-line">{winner.name} wins!</p>}

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

        <button className="btn-primary" onClick={reset}>
          Back to Home
        </button>
      </div>
    </div>
  );
}
