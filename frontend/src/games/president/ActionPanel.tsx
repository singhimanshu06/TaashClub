import { useEffect, useState } from "react";
import type { CardT, GameState, StatePlayer } from "../../types";
import Hand from "../../components/Hand";

const RANK: Record<number, string> = { 11: "J", 12: "Q", 13: "K", 14: "A" };

function cardKey(c: CardT) {
  return `${c.suit}${c.rank}`;
}

function rankLabel(r: number) {
  return RANK[r] ?? String(r);
}

/** Find the viewer's player object (the one whose hand is populated by the backend). */
function findViewer(game: GameState): StatePlayer | undefined {
  return game.players.find((p) => p.hand !== null && p.hand !== undefined);
}

/**
 * President action panel. Always shows the viewer's hand. When it's the viewer's
 * turn, the hand is selectable and Play/Pass/Bomb buttons appear. When it's
 * not their turn, the hand is shown read-only.
 *
 * During the exchange phase, shows the exchange sub-panel (receiver picks cards
 * to return; others see a waiting message + their hand read-only).
 */
export default function PresidentActionPanel({
  game,
  isMyTurn,
  sendAction,
}: {
  game: GameState;
  isMyTurn: boolean;
  sendAction: (action: string, params?: Record<string, unknown>) => void;
}) {
  const viewer = findViewer(game);
  const myHand = viewer?.hand ?? [];

  if (game.phase === "exchange") {
    return <ExchangePanel game={game} isMyTurn={isMyTurn} sendAction={sendAction} viewer={viewer} />;
  }

  if (game.phase !== "playing") {
    return (
      <div className="president-panel">
        <Hand hand={myHand} legal={null} onPlay={() => {}} />
      </div>
    );
  }

  return (
    <PlayPanel
      game={game}
      isMyTurn={isMyTurn}
      sendAction={sendAction}
      myHand={myHand}
    />
  );
}

/** Playing-phase panel: hand + (when our turn) Play/Pass/Bomb buttons. */
function PlayPanel({
  game,
  isMyTurn,
  sendAction,
  myHand,
}: {
  game: GameState;
  isMyTurn: boolean;
  sendAction: (action: string, params?: Record<string, unknown>) => void;
  myHand: CardT[];
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Clear selection whenever the turn moves or the pile changes.
  useEffect(() => {
    setSelected(new Set());
  }, [game.current_player_id, game.pile_top, game.phase]);

  const legalActions = isMyTurn
    ? ((game.your_legal_actions as Array<Record<string, unknown>>) ?? [])
    : [];
  const hasPass = legalActions.some((a) => a.action === "pass");
  const bombLeads = legalActions.filter((a) => a.action === "bomb") as Array<Record<string, unknown>>;

  // Selected cards — must all share one rank.
  const selectedCards = myHand.filter((c) => selected.has(cardKey(c)));
  const selectedRank = selectedCards.length ? selectedCards[0].rank : null;
  const comboSize = selectedCards.length;

  // Legal combos are identified by RANK + SIZE (suit is irrelevant in President).
  // The backend returns one representative card per combo, but any card of the
  // same rank is equally legal — so we track legal (rank, size) pairs.
  const legalCombos = new Set<string>();
  for (const a of legalActions) {
    if (a.action === "play_combo" && Array.isArray(a.cards)) {
      const cards = a.cards as CardT[];
      if (cards.length > 0) {
        legalCombos.add(`${cards[0].rank}-${cards.length}`);
      }
    }
  }
  const selectionIsLegal =
    comboSize >= 1 &&
    comboSize <= 4 &&
    selectedRank !== null &&
    legalCombos.has(`${selectedRank}-${comboSize}`);

  function toggle(c: CardT) {
    setSelected((prev) => {
      const k = cardKey(c);
      const next = new Set(prev);
      if (next.has(k)) {
        next.delete(k);
      } else {
        if (comboSize >= 4) return prev;
        if (selectedRank !== null && c.rank !== selectedRank) return prev;
        next.add(k);
      }
      return next;
    });
  }

  function playCombo() {
    if (!selectionIsLegal) return;
    sendAction("play_combo", { cards: selectedCards });
  }

  function doPass() {
    sendAction("pass");
  }

  function doBomb() {
    if (!bombLeads.length) return;
    const best = [...bombLeads].sort(
      (a, b) =>
        ((a.lead as CardT[])[0]?.rank ?? 99) - ((b.lead as CardT[])[0]?.rank ?? 99),
    )[0];
    sendAction("bomb", { lead: best.lead });
  }

  return (
    <div className="president-panel">
      <Hand
        hand={myHand}
        legal={isMyTurn ? myHand : null}
        onPlay={() => {}}
        selectMode={isMyTurn}
        selectedKeys={selected}
        onToggle={isMyTurn ? toggle : undefined}
      />
      {isMyTurn && (
        <div className="president-actions">
          <button
            className="btn-primary president-btn"
            disabled={!selectionIsLegal}
            onClick={playCombo}
          >
            {comboSize > 0
              ? `Play ${rankLabel(selectedRank!)}${comboSize > 1 ? ` ×${comboSize}` : ""}`
              : "Pick cards"}
          </button>
          <button
            className="btn-secondary president-btn"
            disabled={!hasPass}
            onClick={doPass}
          >
            Pass
          </button>
          <button
            className="btn-secondary president-btn bomb"
            disabled={bombLeads.length === 0}
            onClick={doBomb}
            title="Play a 2 to clear the pile and lead a fresh combo"
          >
            💣 Bomb
          </button>
        </div>
      )}
    </div>
  );
}

/** Exchange sub-panel: receiver picks N cards to return. */
function ExchangePanel({
  game,
  sendAction,
  viewer,
}: {
  game: GameState;
  isMyTurn: boolean;
  sendAction: (action: string, params?: Record<string, unknown>) => void;
  viewer?: StatePlayer;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const exchange = game.exchange;
  const myHand = (viewer?.hand ?? []).filter(Boolean) as CardT[];
  const count = exchange?.count ?? 0;
  const isReceiver = exchange?.receiver_id === viewer?.id;
  const canAct = isReceiver && exchange?.step === "choose_return";

  useEffect(() => {
    setSelected(new Set());
  }, [exchange?.receiver_id, exchange?.step]);

  function toggle(c: CardT) {
    setSelected((prev) => {
      const k = cardKey(c);
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else if (next.size < count) next.add(k);
      return next;
    });
  }

  function confirm() {
    const cards = myHand.filter((c) => selected.has(cardKey(c)));
    if (cards.length !== count) return;
    sendAction("choose_return", { cards });
  }

  // If the viewer is the receiver, show the return-card picker.
  if (canAct) {
    return (
      <div className="president-panel exchange">
        <p className="exchange-prompt">
          You're exchanging with{" "}
          <strong>{game.players.find((p) => p.id === exchange?.giver_id)?.name}</strong>. Pick{" "}
          <strong>{count}</strong> card(s) to send back.
        </p>
        <Hand
          hand={myHand}
          legal={myHand}
          onPlay={() => {}}
          selectMode
          selectedKeys={selected}
          onToggle={toggle}
        />
        <button
          className="btn-primary"
          disabled={selected.size !== count}
          onClick={confirm}
        >
          Return {selected.size}/{count} cards
        </button>
      </div>
    );
  }

  // Not the receiver — show hand read-only + a waiting message.
  const receiverName = exchange?.receiver_id
    ? game.players.find((p) => p.id === exchange.receiver_id)?.name
    : null;
  return (
    <div className="president-panel">
      {receiverName && (
        <p className="exchange-waiting-msg">
          Waiting for {receiverName} to choose return card(s)…
        </p>
      )}
      <Hand hand={myHand} legal={null} onPlay={() => {}} />
    </div>
  );
}
