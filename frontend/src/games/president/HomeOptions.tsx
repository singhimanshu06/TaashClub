import type { GameInfo } from "../../types";

const RULES = [
  "5 players. Goal: empty your hand fastest. Last one holding cards is the Asshole.",
  "50-card deck (two 2s removed). 10 cards each. Ace is high (2 is bomb-only).",
  "Play singles, pairs, triples or quads of one rank. Follow with the same size, ≥ rank, or pass.",
  "Drop a 2 to bomb: clears the pile and you lead a fresh combo. Next player must beat it.",
  "Two consecutive same-rank plays (singles/doubles) skip the next player.",
  "Between rounds: Asshole gives 2 best cards to President, Vice-Asshole gives 1 to VP; they return cards of their choice.",
  "Scoring: President +5, VP +3, Neutral +1, Vice-Asshole 0, Asshole −2. Highest total wins the match.",
];

/** President create-room options: round count chips. */
export default function PresidentHomeOptions({
  info,
  options,
  setOptions,
}: {
  info: GameInfo;
  numPlayers: number;
  setNumPlayers: (n: number) => void;
  options: Record<string, unknown>;
  setOptions: (o: Record<string, unknown>) => void;
}) {
  const rounds = (options.rounds as string) ?? "10";
  const setRounds = (r: string) => setOptions({ ...options, rounds: r });
  const schema = info.options_schema.rounds;
  const values = schema?.values ?? ["5", "10", "15"];
  const labels = schema?.labels ?? {};

  return (
    <>
      <div className="field">
        <span>Players</span>
        <div className="chip-row">
          <button className="chip active" disabled>
            5
            <small>10 cards each</small>
          </button>
        </div>
      </div>
      <div className="field">
        <span>Rounds</span>
        <div className="chip-row">
          {values.map((v) => (
            <button
              key={v}
              className={rounds === v ? "chip wide active" : "chip wide"}
              onClick={() => setRounds(v)}
            >
              {labels[v] ?? `${v} rounds`}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

export { RULES };
