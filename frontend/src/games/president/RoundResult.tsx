import { useShallow } from "zustand/react/shallow";
import { useStore } from "../../store";
import type { GameState } from "../../types";

/** Round-end modal: finishing order + roles + round scores + cumulative. */
export default function PresidentRoundResult({
  game,
  sendAction,
}: {
  game: GameState;
  sendAction: (action: string, params?: Record<string, unknown>) => void;
}) {
  const { playerId, isHost } = useStore(
    useShallow((s) => ({
      playerId: s.playerId,
      isHost: s.lobby?.host_id === s.playerId,
    }))
  );
  const rows = game.last_round_result ?? [];

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>Round {game.round_index + 1} results</h2>
        <table className="result-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Player</th>
              <th>Role</th>
              <th>Round</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const round = r.round_score ?? 0;
              const total = r.total_score ?? 0;
              return (
                <tr key={r.player_id} className={r.player_id === playerId ? "you-row" : ""}>
                  <td>{r.finish !== undefined ? r.finish + 1 : "—"}</td>
                  <td>{r.name}</td>
                  <td>{r.role ?? "—"}</td>
                  <td className={round >= 0 ? "pts-hit" : "pts-miss"}>
                    {round >= 0 ? "+" : ""}
                    {round}
                  </td>
                  <td className="total-score">{total}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {isHost ? (
          <button className="btn-primary" onClick={() => sendAction("advance_round")}>
            {game.round_index + 1 >= (game.rounds_total ?? 0) ? "See final results" : "Next round"}
          </button>
        ) : (
          <p className="waiting-text">Waiting for host to start the next round…</p>
        )}
      </div>
    </div>
  );
}
