import PlayingCard from "./PlayingCard";
import type { CardT } from "../types";

interface Props {
  hand: CardT[];
  /** null = not your turn; otherwise the set of playable card keys. When
   * `selectMode` is false, clicking a legal card fires onPlay immediately
   * (Callbreak behaviour). */
  legal: CardT[] | null;
  onPlay: (card: CardT) => void;
  /** When true, taps toggle selection among `legal` cards instead of immediately
   * playing. Used by games that group cards into combos (President). */
  selectMode?: boolean;
  /** Keys (suit+rank) currently selected in selectMode. */
  selectedKeys?: Set<string>;
  /** Toggle a card's membership in the selection (selectMode only). */
  onToggle?: (card: CardT) => void;
}

function key(c: CardT) {
  return `${c.suit}${c.rank}`;
}

export default function Hand({ hand, legal, onPlay, selectMode, selectedKeys, onToggle }: Props) {
  const legalSet = legal ? new Set(legal.map(key)) : null;

  return (
    <div className="hand">
      {hand.map((c) => {
        const k = key(c);
        const isLegal = legalSet ? legalSet.has(k) : false;
        const canPlay = legalSet !== null && isLegal;
        const isSelected = selectedKeys?.has(k) ?? false;
        return (
          <PlayingCard
            key={k}
            card={c}
            size="lg"
            playable={canPlay}
            disabled={legalSet !== null && !isLegal}
            highlight={isSelected}
            onClick={() => {
              if (!canPlay) return;
              if (selectMode && onToggle) onToggle(c);
              else onPlay(c);
            }}
          />
        );
      })}
    </div>
  );
}
