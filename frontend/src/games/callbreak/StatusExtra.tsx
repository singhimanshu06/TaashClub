import type { GameState } from "../../types";
import { suitSymbol, isRed } from "../../components/PlayingCard";

const TRUMP_NAME: Record<string, string> = { S: "Spades", H: "Hearts", C: "Clubs", D: "Diamonds" };

/** Trump indicator chip for the shared status bar. */
export default function CallbreakStatusExtra({ game }: { game: GameState }) {
  if (!game.trump) return null;
  return (
    <div className={`trump-chip ${isRed(game.trump) ? "red" : "black"}`}>
      Trump <span className="trump-symbol">{suitSymbol(game.trump)}</span>
      <small>{TRUMP_NAME[game.trump]}</small>
    </div>
  );
}
