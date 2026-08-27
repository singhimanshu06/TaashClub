import { useShallow } from "zustand/react/shallow";
import { useStore } from "../../store";
import type { GameState } from "../../types";
import { suitSymbol } from "../../components/PlayingCard";

/**
 * Deal-end modal: per partnership — the bid, card points made, and game points
 * earned this deal. No cumulative score (see the Scorecard popup for that).
 */
export default function TwentyEightRoundResult({
  game,
  sendAction,
}: {
  game: GameState;
  sendAction: (action: string, params?: Record<string, unknown>) => void;
}) {
  const { playerId, isHost } = useStore(
    useShallow((s) => ({
      playerId: s.playerId,
      isHost: (s.game?.host_id ?? s.lobby?.host_id) === s.playerId,
    }))
  );
  const history = game.round_history ?? [];
  const entry = history[game.round_index];
  const made = entry?.bid_made ?? false;
  const captured = entry?.captured_points ?? 0;
  const bid = entry?.high_bid ?? 0;
  const bidderName = game.players.find((p) => p.id === entry?.bidder_id)?.name ?? "";

  // One row per partnership. The 28 card points are split between the teams,
  // so the opposition made 28 minus the bidder team's capture.
  const teamsMap = game.teams ?? {};
  const bidderTeam = entry?.bidder_id != null ? String(teamsMap[entry.bidder_id]) : null;
  const teamRows = [...new Set(Object.values(teamsMap).map(String))]
    .sort()
    .map((t) => {
      const members = game.players.filter((p) => String(teamsMap[p.id]) === t);
      const row = entry?.results.find((r) => r.player_id === members[0]?.id);
      const isBidderTeam = t === bidderTeam;
      return {
        id: t,
        names: members.map((m) => m.name).join(" & "),
        bid: isBidderTeam ? bid : null,
        made: isBidderTeam ? captured : 28 - captured,
        earned: row?.points ?? 0,
        mine: members.some((m) => m.id === playerId),
      };
    });

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>Deal {game.round_index + 1} results</h2>
        <p className="modal-sub">
          {bidderName} bid {bid}
          {game.trump && (
            <>
              {" · trump "}
              <span className="trump-inline">{suitSymbol(game.trump)}</span>
            </>
          )}{" "}
          —{" "}
          <span className={made ? "pts-hit" : "pts-miss"}>
            {made ? "bid made" : "bid failed"}
          </span>
        </p>
        <table className="result-table">
          <thead>
            <tr>
              <th>Team</th>
              <th>Bid</th>
              <th>Made</th>
              <th>Earned</th>
            </tr>
          </thead>
          <tbody>
            {teamRows.map((t) => (
              <tr key={t.id} className={t.mine ? "you-row" : ""}>
                <td>{t.names}</td>
                <td>{t.bid ?? "—"}</td>
                <td>{t.made}</td>
                <td className={t.earned > 0 ? "pts-hit" : t.earned < 0 ? "pts-miss" : ""}>
                  {t.earned > 0 ? `+${t.earned}` : t.earned < 0 ? t.earned : "0"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isHost ? (
          <button className="btn-primary" onClick={() => sendAction("advance_round")}>
            Next deal
          </button>
        ) : (
          <p className="waiting-text">Waiting for host to start the next deal…</p>
        )}
      </div>
    </div>
  );
}
