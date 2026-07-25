import { useEffect, useState } from "react";
import { createRoom, fetchGames, joinRoom } from "../api";
import { useStore } from "../store";
import type { GameInfo } from "../types";
import { getGameSlots } from "../games/registry";
import { RULES as CALLBREAK_RULES } from "../games/callbreak";
import { RULES as PRESIDENT_RULES } from "../games/president";

function roomFromUrl(): string {
  return new URLSearchParams(window.location.search).get("room")?.toUpperCase() ?? "";
}

// Per-game-type rules text for the info popup. A game may export its RULES from
// its slot package; fall back to the description from the registry.
function rulesFor(info: GameInfo): string[] {
  if (info.game_type === "callbreak") return CALLBREAK_RULES;
  if (info.game_type === "president") return PRESIDENT_RULES;
  return [info.description];
}

interface GridSlot {
  game_type?: string;
  display_name: string;
  description: string;
  available: boolean;
  info?: GameInfo;
}

const GRID_SIZE = 4;

function buildGrid(games: GameInfo[]): GridSlot[] {
  const slots: GridSlot[] = games.map((g) => ({
    game_type: g.game_type,
    display_name: g.display_name,
    description: g.description,
    available: true,
    info: g,
  }));
  while (slots.length < GRID_SIZE) {
    slots.push({ display_name: "Coming soon", description: "Stay tuned!", available: false });
  }
  return slots.slice(0, GRID_SIZE);
}

type Step = "pick" | "setup";
type SetupMode = "create" | "join";

export default function Home() {
  const enterRoom = useStore((s) => s.enterRoom);
  const initialRoom = roomFromUrl();

  // Two-step flow: "pick" (game grid) -> "setup" (name + params + create/join).
  const [step, setStep] = useState<Step>(initialRoom ? "setup" : "pick");
  const [setupMode, setSetupMode] = useState<SetupMode>(initialRoom ? "join" : "create");

  const [name, setName] = useState("");
  const [code, setCode] = useState(initialRoom);
  const [games, setGames] = useState<GameInfo[] | null>(null);
  const [gameType, setGameType] = useState<string>("");
  const [numPlayers, setNumPlayers] = useState(4);
  const [options, setOptions] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [rulesForInfo, setRulesForInfo] = useState<GameInfo | null>(null);

  useEffect(() => {
    fetchGames()
      .then((list) => setGames(list))
      .catch(() => {
        setGames([]);
        setErr("Couldn't reach the server. Is the backend running on port 8000?");
      });
  }, []);

  const selectedGame = games?.find((g) => g.game_type === gameType) ?? null;
  const HomeOptions = selectedGame ? getGameSlots(gameType).HomeOptions : undefined;

  function pickGame(info: GameInfo) {
    setGameType(info.game_type);
    setNumPlayers(info.min_players);
    const defs: Record<string, unknown> = {};
    for (const [key, schema] of Object.entries(info.options_schema)) {
      if (schema.default !== undefined) defs[key] = schema.default;
    }
    setOptions(defs);
    setSetupMode("create");
    setStep("setup");
    setErr(null);
  }

  function backToPick() {
    setStep("pick");
    setErr(null);
  }

  function gotoJoin() {
    setSetupMode("join");
    setStep("setup");
    setErr(null);
  }

  async function handleSubmit() {
    setErr(null);
    if (!name.trim()) return setErr("Please enter your name.");
    if (setupMode === "join" && !code.trim()) return setErr("Please enter a room code.");
    if (setupMode === "create" && !gameType) return setErr("Please pick a game first.");
    setBusy(true);
    try {
      let roomCode = code.trim().toUpperCase();
      if (setupMode === "create") {
        roomCode = (await createRoom(gameType, numPlayers, options)).code;
      }
      const joined = await joinRoom(roomCode, name.trim());
      enterRoom(joined.code, joined.player_id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  // ----- Rules modal -----
  function showRules(info: GameInfo) {
    setRulesForInfo(info);
  }

  // ===================== Step 1: Game picker =====================
  if (step === "pick") {
    const gridSlots = games ? buildGrid(games) : null;
    return (
      <div className="screen home-screen">
        <div className="home-card">
          <h1 className="logo">
            <span className="logo-tc">TC</span>
            <span className="logo-text">TaashClub</span>
          </h1>

          <p className="tagline">Pick a game to play</p>

          {/* 2x2 game grid */}
          <div className="game-grid">
            {gridSlots ? (
              gridSlots.map((slot, i) => (
                <div key={slot.game_type ?? `placeholder-${i}`} className="game-card-wrap">
                  <button
                    className={`game-card${slot.available ? "" : " disabled"}`}
                    onClick={() => slot.available && slot.info && pickGame(slot.info)}
                    disabled={!slot.available}
                  >
                    <span className="game-card-name">{slot.display_name}</span>
                    <span className="game-card-desc">{slot.description}</span>
                    {!slot.available && <span className="game-card-badge">Soon</span>}
                  </button>
                  {slot.available && slot.info && (
                    <button
                      className="game-card-info"
                      onClick={() => showRules(slot.info!)}
                      title="How to play"
                    >
                      i
                    </button>
                  )}
                </div>
              ))
            ) : (
              <div className="game-grid-loading">
                <div className="spinner" />
                <p>Loading games…</p>
              </div>
            )}
          </div>

          <button className="btn-link" onClick={gotoJoin}>
            Join with code →
          </button>

          {err && <div className="inline-error">{err}</div>}
        </div>

        {rulesForInfo && (
          <RulesModal info={rulesForInfo} onClose={() => setRulesForInfo(null)} />
        )}
      </div>
    );
  }

  // ===================== Step 2: Setup =====================
  return (
    <div className="screen home-screen">
      <div className="home-card">
        <div className="setup-header">
          <button className="btn-back" onClick={backToPick} title="Back to games">
            ←
          </button>
          {selectedGame && (
            <h2 className="setup-title">
              {selectedGame.display_name}
              <button
                className="info-btn"
                onClick={() => selectedGame && showRules(selectedGame)}
                title="How to play"
              >
                i
              </button>
            </h2>
          )}
        </div>

        <div className="segmented">
          <button
            className={setupMode === "create" ? "seg active" : "seg"}
            onClick={() => setSetupMode("create")}
          >
            Create Room
          </button>
          <button
            className={setupMode === "join" ? "seg active" : "seg"}
            onClick={() => setSetupMode("join")}
          >
            Join Room
          </button>
        </div>

        <label className="field">
          <span>Your name</span>
          <input
            value={name}
            maxLength={20}
            placeholder="e.g. Alex"
            onChange={(e) => setName(e.target.value)}
          />
        </label>

        {setupMode === "join" ? (
          <label className="field">
            <span>Room code</span>
            <input
              value={code}
              placeholder="ABCD"
              className="code-input"
              onChange={(e) => setCode(e.target.value.toUpperCase())}
            />
          </label>
        ) : (
          selectedGame && HomeOptions && (
            <HomeOptions
              info={selectedGame}
              numPlayers={numPlayers}
              setNumPlayers={setNumPlayers}
              options={options}
              setOptions={setOptions}
            />
          )
        )}

        {err && <div className="inline-error">{err}</div>}

        <button className="btn-primary" disabled={busy} onClick={handleSubmit}>
          {busy ? "Please wait…" : setupMode === "join" ? "Join Game" : "Create & Join"}
        </button>
      </div>

      {rulesForInfo && (
        <RulesModal info={rulesForInfo} onClose={() => setRulesForInfo(null)} />
      )}
    </div>
  );
}

/** Full-screen rules overlay (reuses .modal-backdrop / .modal styles). */
function RulesModal({ info, onClose }: { info: GameInfo; onClose: () => void }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal rules-modal" onClick={(e) => e.stopPropagation()}>
        <h2>How to play — {info.display_name}</h2>
        <ul className="rules-list">
          {rulesFor(info).map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
        <button className="btn-primary" onClick={onClose}>
          Got it
        </button>
      </div>
    </div>
  );
}
