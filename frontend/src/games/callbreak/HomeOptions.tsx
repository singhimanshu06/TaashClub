import type { GameInfo, Variant } from "../../types";

const RULES = [
  "4–6 players. Hand size shrinks each round down to 1 card (Single run) or down-and-up.",
  "Each round, bid the EXACT number of tricks you'll win. Hit it → 10 + bid points; miss (over or under) → 0.",
  "Trump cycles every round: Spades → Hearts → Clubs → Diamonds.",
  "Follow the led suit if you can; otherwise play any card. Highest trump wins, else highest of the led suit.",
  "First bidder rotates each round. Final scoreboard revealed only at game end.",
];

/** Callbreak create-room options: player count, game length variant, rules popup. */
export default function CallbreakHomeOptions({
  info,
  numPlayers,
  setNumPlayers,
  options,
  setOptions,
}: {
  info: GameInfo;
  numPlayers: number;
  setNumPlayers: (n: number) => void;
  options: Record<string, unknown>;
  setOptions: (o: Record<string, unknown>) => void;
}) {
  const startCardsFor = (n: number) => Math.floor(52 / n);
  const variant = (options.variant as Variant) ?? "single_run";
  const setVariant = (v: Variant) => setOptions({ ...options, variant: v });

  return (
    <>
      <div className="field">
        <span>Players</span>
        <div className="chip-row">
          {Array.from(
            { length: info.max_players - info.min_players + 1 },
            (_, i) => info.min_players + i,
          ).map((n) => (
            <button
              key={n}
              className={numPlayers === n ? "chip active" : "chip"}
              onClick={() => setNumPlayers(n)}
            >
              {n}
              <small>{startCardsFor(n)} cards</small>
            </button>
          ))}
        </div>
      </div>
      <div className="field">
        <span>Game length</span>
        <div className="chip-row">
          <button
            className={variant === "single_run" ? "chip wide active" : "chip wide"}
            onClick={() => setVariant("single_run")}
          >
            Single run
            <small>{startCardsFor(numPlayers)} → 1</small>
          </button>
          <button
            className={variant === "down_and_up" ? "chip wide active" : "chip wide"}
            onClick={() => setVariant("down_and_up")}
          >
            Down &amp; up
            <small>{startCardsFor(numPlayers)} → 1 → {startCardsFor(numPlayers)}</small>
          </button>
        </div>
      </div>
    </>
  );
}

export { RULES };
