import type { GameState } from "../../types";
import BidPanel from "./BidPanel";

/**
 * Callbreak action panel: shows the bid picker when it's the viewer's turn to
 * bid. During play no panel is needed (cards are clicked directly).
 */
export default function CallbreakActionPanel({
  game,
  isMyTurn,
  sendAction,
}: {
  game: GameState;
  isMyTurn: boolean;
  sendAction: (action: string, params?: Record<string, unknown>) => void;
}) {
  if (game.phase !== "bidding" || !isMyTurn || game.cards_this_round === null) return null;
  return (
    <BidPanel
      maxBid={game.cards_this_round}
      onBid={(value) => sendAction("place_bid", { value })}
    />
  );
}
