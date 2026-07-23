import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import type { GameState } from "../types";
import { suitSymbol } from "./PlayingCard";

export default function RoundResult({ game }: { game: GameState }) {
  const { playerId, advanceRound, isHost } = useStore(
    useShallow((s) => ({
      playerId: s.playerId,
      advanceRound: s.advanceRound,
      isHost: s.lobby?.host_id === s.playerId,
    }))
  );
  const rows = game.last_round_result ?? [];

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>Round {game.round_index + 1} results</h2>
        {game.trump && (
          <p className="modal-sub">
            Trump was <span className="trump-inline">{suitSymbol(game.trump)}</span>
          </p>
        )}
        <table className="result-table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Bid</th>
              <th>Won</th>
              <th>Points</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.player_id} className={r.player_id === playerId ? "you-row" : ""}>
                <td>{r.name}</td>
                <td>{r.bid}</td>
                <td>{r.tricks_won}</td>
                <td className={r.hit ? "pts-hit" : "pts-miss"}>{r.hit ? `+${r.points}` : "0"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {isHost ? (
          <button className="btn-primary" onClick={advanceRound}>
            Next round
          </button>
        ) : (
          <p className="waiting-text">Waiting for host to start the next round…</p>
        )}
      </div>
    </div>
  );
}
