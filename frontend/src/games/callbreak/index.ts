import { registerGame } from "../registry";
import CallbreakStatusExtra from "./StatusExtra";
import CallbreakActionPanel from "./ActionPanel";
import CallbreakSeatStats from "./SeatStats";
import CallbreakRoundResult from "./RoundResult";
import CallbreakDetailedScores from "./DetailedScores";
import CallbreakHomeOptions from "./HomeOptions";

// Register Callbreak's UI slots with the platform. This is the single place a
// new game wires itself into the shared GameTable / Home / GameOver.
registerGame("callbreak", {
  StatusExtra: CallbreakStatusExtra,
  ActionPanel: CallbreakActionPanel,
  SeatStats: CallbreakSeatStats,
  RoundResult: CallbreakRoundResult,
  DetailedScores: CallbreakDetailedScores,
  HomeOptions: CallbreakHomeOptions,
});

export { RULES } from "./HomeOptions";
