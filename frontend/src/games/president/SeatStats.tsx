import type { GameState, StatePlayer } from "../../types";

const ROLE_LABELS: Record<number, string> = {
  0: "President",
  1: "VP",
  2: "Neutral",
  3: "V-Asshole",
  4: "Asshole",
};

/** Per-seat stats: cards remaining + role badge (after roles assigned). */
export default function PresidentSeatStats({
  game,
  player,
}: {
  game: GameState;
  player: StatePlayer;
  phase: string;
}) {
  const cards = player.tricks_won; // reused as "cards remaining"
  // roles maps finish_index -> player_id; find this player's finish index.
  let role: string | null = null;
  if (game.roles) {
    for (const [finishIdx, pid] of Object.entries(game.roles)) {
      if (pid === player.id) {
        role = ROLE_LABELS[Number(finishIdx)] ?? null;
        break;
      }
    }
  }
  return (
    <span className="tricks">
      Cards <strong>{cards}</strong>
      {role && <small className="role-badge">{role}</small>}
    </span>
  );
}
