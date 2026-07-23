import PlayingCard from "./PlayingCard";
import type { CardT } from "../types";

interface Props {
  hand: CardT[];
  legal: CardT[] | null; // null = not your turn to play
  onPlay: (card: CardT) => void;
}

function key(c: CardT) {
  return `${c.suit}${c.rank}`;
}

export default function Hand({ hand, legal, onPlay }: Props) {
  const legalSet = legal ? new Set(legal.map(key)) : null;

  return (
    <div className="hand">
      {hand.map((c) => {
        const isLegal = legalSet ? legalSet.has(key(c)) : false;
        const canPlay = legalSet !== null && isLegal;
        return (
          <PlayingCard
            key={key(c)}
            card={c}
            size="lg"
            playable={canPlay}
            disabled={legalSet !== null && !isLegal}
            onClick={() => canPlay && onPlay(c)}
          />
        );
      })}
    </div>
  );
}
