import { useState } from "react";
import { createRoom, joinRoom } from "../api";
import { useStore } from "../store";
import type { Variant } from "../types";

function roomFromUrl(): string {
  return new URLSearchParams(window.location.search).get("room")?.toUpperCase() ?? "";
}

export default function Home() {
  const enterRoom = useStore((s) => s.enterRoom);
  const initialRoom = roomFromUrl();
  const [mode, setMode] = useState<"create" | "join">(initialRoom ? "join" : "create");
  const [name, setName] = useState("");
  const [code, setCode] = useState(initialRoom);
  const [numPlayers, setNumPlayers] = useState(4);
  const [variant, setVariant] = useState<Variant>("single_run");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const startCardsFor = (n: number) => Math.floor(52 / n);

  async function handleSubmit() {
    setErr(null);
    if (!name.trim()) return setErr("Please enter your name.");
    if (mode === "join" && !code.trim()) return setErr("Please enter a room code.");
    setBusy(true);
    try {
      let roomCode = code.trim().toUpperCase();
      if (mode === "create") {
        roomCode = (await createRoom(numPlayers, variant)).code;
      }
      const joined = await joinRoom(roomCode, name.trim());
      enterRoom(joined.code, joined.player_id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="screen home-screen">
      <div className="home-card">
        <h1 className="logo">
          LAKDI <span className="logo-suits">♠♥♣♦</span>
        </h1>
        <p className="tagline">Callbreak — decreasing-cards, exact-bid card game</p>

        <div className="segmented">
          <button className={mode === "create" ? "seg active" : "seg"} onClick={() => setMode("create")}>
            Create Room
          </button>
          <button className={mode === "join" ? "seg active" : "seg"} onClick={() => setMode("join")}>
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

        {mode === "join" ? (
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
          <>
            <div className="field">
              <span>Players</span>
              <div className="chip-row">
                {[4, 5, 6].map((n) => (
                  <button
                    key={n}
                    className={numPlayers === n ? "chip active" : "chip"}
                    onClick={() => setNumPlayers(n)}
                  >
                    {n}
                    <small>{startCardsFor(n)} cards</small>
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <span>Game length</span>
              <div className="chip-row">
                <button
                  className={variant === "single_run" ? "chip wide active" : "chip wide"}
                  onClick={() => setVariant("single_run")}
                >
                  Single run
                  <small>{startCardsFor(numPlayers)} → 1</small>
                </button>
                <button
                  className={variant === "down_and_up" ? "chip wide active" : "chip wide"}
                  onClick={() => setVariant("down_and_up")}
                >
                  Down &amp; up
                  <small>{startCardsFor(numPlayers)} → 1 → {startCardsFor(numPlayers)}</small>
                </button>
              </div>
            </div>
          </>
        )}

        {err && <div className="inline-error">{err}</div>}

        <button className="btn-primary" disabled={busy} onClick={handleSubmit}>
          {busy ? "Please wait…" : mode === "create" ? "Create & Join" : "Join Game"}
        </button>
      </div>
    </div>
  );
}
