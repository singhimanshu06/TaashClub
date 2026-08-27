import type { GameState, StatePlayer } from "../../types";

/** Stats inside the viewer's own chip: partnership card points captured this
 *  deal (same value both partners see) plus the standing bid. */
export default function TwentyEightSelfStats({
  game,
  player,
}: {
  game: GameState;
  player: StatePlayer;
}) {
  const myTeam = game.teams?.[player.id];
  const captured = myTeam != null ? (game.team_captured?.[String(myTeam)] ?? 0) : 0;
  return (
    <span className="your-stats">
      Pts <strong>{captured}</strong>/28
      {player.bid !== null && player.bid !== undefined && <> · bid {player.bid}</>}
    </span>
  );
}
