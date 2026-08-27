import type { GameState } from "../../types";
import { suitSymbol, isRed } from "../../components/PlayingCard";
import { useEffect, useRef, useState } from "react";

const TRUMP_NAME: Record<string, string> = {
  S: "Spades",
  H: "Hearts",
  C: "Clubs",
  D: "Diamonds",
};

/**
 * Trump indicator chip for the shared status bar.
 *
 * The server redacts the trump suit per viewer: non-bidders receive null until
 * it is exposed, the bidder always sees it. Chips:
 *  - auction still running -> nothing
 *  - trump hidden from this viewer -> "?" chip
 *  - trump known -> coloured chip (marked "hidden" until exposed)
 * A transient "Trump revealed!" banner pops for everyone on the exposure edge.
 */
export default function TwentyEightStatusExtra({ game }: { game: GameState }) {
  const [toast, setToast] = useState(false);
  const wasExposed = useRef(false);

  useEffect(() => {
    if (game.trump_exposed && !wasExposed.current) {
      wasExposed.current = true;
      setToast(true);
      const t = setTimeout(() => setToast(false), 2500);
      return () => clearTimeout(t);
    }
    wasExposed.current = !!game.trump_exposed;
  }, [game.trump_exposed]);

  // Auction still in progress (trump not named yet) -> no chip.
  const auctionDone =
    game.phase === "playing" || game.phase === "round_end" || game.phase === "game_end";
  if (!auctionDone) return null;

  return (
    <>
      {game.trump ? (
        <div className={`trump-chip ${isRed(game.trump) ? "red" : "black"}`}>
          Trump <span className="trump-symbol">{suitSymbol(game.trump)}</span>
          <small>{TRUMP_NAME[game.trump]}</small>
          {!game.trump_exposed && <small title="Only the bidder can see this">· hidden</small>}
        </div>
      ) : (
        <div className="trump-chip" title="Hidden trump — chosen by the bidder">
          Trump <span className="trump-symbol">?</span>
          <small>hidden</small>
        </div>
      )}
      {toast && <div className="skip-popup">🂠 Trump revealed!</div>}
    </>
  );
}
