import type { GameInfo } from "../../types";

const RULES = [
  "4 players, fixed partnerships (opposite seats). 32-card deck: 7 through Ace.",
  "Card ranking is unusual: J > 9 > A > 10 > K > Q > 8 > 7. Points: J=3, 9=2, A=1, 10=1 — 28 per deal.",
  "Bid 14–28: the card points you promise your partnership will capture if you get to name trump. Opening bid is mandatory; passing locks you out; overcalling your partner needs ≥20.",
  "The winning bidder secretly names trump. Nobody sees it until it is revealed — the bidder can always see their own choice.",
  "Before the reveal, trump cards are ordinary cards and the bidder may not lead them.",
  "When a player who cannot follow suit reveals trump (or the bidder does), it becomes trump for the rest of the deal — the revealer must play trump on that trick if able.",
  "After the reveal: highest trump wins the trick, else highest card of the led suit. Void players may play any card; the revealer must play trump on that trick if they hold one.",
  "Scoring: bid made → +1 to both partners; bid failed → −1. Highest total after the chosen number of deals wins.",
];

/** Twenty-Eight create-room options: match length in deals. */
export default function TwentyEightHomeOptions({
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
  const deals = (options.deals as string) ?? "10";
  const setDeals = (v: string) => setOptions({ ...options, deals: v });
  const schema = info.options_schema.deals;
  const values = schema?.values ?? ["5", "10", "20"];
  const labels = schema?.labels ?? {};

  return (
    <>
      <div className="field">
        <span>Players</span>
        <div className="chip-row">
          <button className="chip active" disabled>
            4
            <small>partners, 8 cards each</small>
          </button>
        </div>
      </div>
      <div className="field">
        <span>Match length</span>
        <div className="chip-row">
          {values.map((v) => (
            <button
              key={v}
              className={deals === v ? "chip wide active" : "chip wide"}
              onClick={() => setDeals(v)}
            >
              {labels[v] ?? `${v} deals`}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

export { RULES };
