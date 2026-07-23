import type { CardT, Suit } from "../types";

const SUIT_SYMBOL: Record<Suit, string> = { S: "♠", H: "♥", C: "♣", D: "♦" };

export function rankLabel(rank: number): string {
  const labels: Record<number, string> = { 11: "J", 12: "Q", 13: "K", 14: "A" };
  return labels[rank] ?? String(rank);
}
export function suitSymbol(suit: Suit): string {
  return SUIT_SYMBOL[suit];
}
export function isRed(suit: Suit): boolean {
  return suit === "H" || suit === "D";
}

// deckofcardsapi naming: rank letter + suit letter
// Ranks: A, 2-9, 0 (=10), J, Q, K
// Suits: S, H, D, C
const RANK_CODE: Record<number, string> = {
  14: "A",
  2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
  7: "7", 8: "8", 9: "9", 10: "0",
  11: "J", 12: "Q", 13: "K",
};

function cardFilename(card: CardT): string {
  return `/cards/${RANK_CODE[card.rank]}${card.suit}.png`;
}

interface Props {
  card: CardT;
  size?: "sm" | "md" | "lg";
  playable?: boolean;
  disabled?: boolean;
  highlight?: boolean;
  onClick?: () => void;
}

export default function PlayingCard({
  card,
  size = "md",
  playable,
  disabled,
  highlight,
  onClick,
}: Props) {
  const cls = [
    "card",
    `card-${size}`,
    playable ? "card-playable" : "",
    disabled ? "card-disabled" : "",
    highlight ? "card-highlight" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls} onClick={!disabled ? onClick : undefined}>
      <img
        className="card-img"
        src={cardFilename(card)}
        alt={`${rankLabel(card.rank)} of ${card.suit}`}
        draggable={false}
      />
    </div>
  );
}

export function CardBack({ size = "sm" }: { size?: "sm" | "md" | "lg" }) {
  return (
    <div className={`card card-${size}`}>
      <img className="card-img" src="/cards/back.png" alt="card back" draggable={false} />
    </div>
  );
}
