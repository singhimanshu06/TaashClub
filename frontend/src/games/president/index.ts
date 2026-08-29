import { registerGame } from "../registry";
import PresidentStatusExtra from "./StatusExtra";
import PresidentActionPanel from "./ActionPanel";
import PresidentSeatStats from "./SeatStats";
import PresidentRoundResult from "./RoundResult";
import PresidentDetailedScores from "./DetailedScores";
import PresidentHomeOptions from "./HomeOptions";

// Register President's UI slots with the platform. Adding a game means
// implementing these slots and calling registerGame — no shared file changes.
registerGame("president", {
  StatusExtra: PresidentStatusExtra,
  ActionPanel: PresidentActionPanel,
  rendersOwnHand: true,
  trickWraps: true,
  SeatStats: PresidentSeatStats,
  RoundResult: PresidentRoundResult,
  DetailedScores: PresidentDetailedScores,
  HomeOptions: PresidentHomeOptions,
});

export { RULES } from "./HomeOptions";
