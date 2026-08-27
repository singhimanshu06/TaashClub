import { registerGame } from "../registry";
import TwentyEightStatusExtra from "./StatusExtra";
import TwentyEightActionPanel from "./ActionPanel";
import TwentyEightSeatStats from "./SeatStats";
import TwentyEightSelfStats from "./SelfStats";
import TwentyEightRoundResult from "./RoundResult";
import TwentyEightDetailedScores from "./DetailedScores";
import TwentyEightHomeOptions from "./HomeOptions";

// Register Twenty-Eight's UI slots with the platform. This is the single place
// a new game wires itself into the shared GameTable / Home / GameOver.
registerGame("twentyeight", {
  StatusExtra: TwentyEightStatusExtra,
  ActionPanel: TwentyEightActionPanel,
  SeatStats: TwentyEightSeatStats,
  SelfStats: TwentyEightSelfStats,
  RoundResult: TwentyEightRoundResult,
  DetailedScores: TwentyEightDetailedScores,
  HomeOptions: TwentyEightHomeOptions,
});

export { RULES } from "./HomeOptions";
