import { useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";

const VARIANT_LABEL: Record<string, string> = {
  single_run: "Single run",
  down_and_up: "Down & up",
};

function InviteLink({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const host = window.location.hostname;
  const isLocal = host === "localhost" || host === "127.0.0.1";
  const url = `${window.location.origin}/?room=${code}`;

  // When hosting from localhost, a localhost invite link is useless to remote
  // players — tell the host to share their public URL + the room code instead.
  if (isLocal) {
    return (
      <div className="invite">
        <span className="invite-label">Invite friends</span>
        <p className="invite-local">
          You're hosting locally. Share your public link (e.g. your{" "}
          <code>trycloudflare.com</code> URL) plus the room code{" "}
          <strong>{code}</strong> above — friends pick “Join Room” and enter it.
        </p>
      </div>
    );
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      /* clipboard may be blocked on insecure origins; the text is still selectable */
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className="invite">
      <span className="invite-label">Invite link</span>
      <div className="invite-row">
        <input className="invite-url" readOnly value={url} onFocus={(e) => e.target.select()} />
        <button className="copy-btn" onClick={copy}>
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
    </div>
  );
}

export default function Lobby() {
  const { lobby, playerId, code, connected, startGame, addBot, reset } = useStore(
    useShallow((s) => ({
      lobby: s.lobby,
      playerId: s.playerId,
      code: s.code,
      connected: s.connected,
      startGame: s.startGame,
      addBot: s.addBot,
      reset: s.reset,
    }))
  );

  if (!lobby) {
    return (
      <div className="screen center">
        <div className="spinner" /> <p>Connecting to room {code}…</p>
      </div>
    );
  }

  const isHost = lobby.host_id === playerId;
  const full = lobby.players.length >= lobby.num_players;
  const seats = Array.from({ length: lobby.num_players });

  return (
    <div className="screen lobby-screen">
      <button className="leave-btn" onClick={reset} title="Leave room">
        ← Leave
      </button>
      <div className="lobby-card">
        <div className="room-code-badge">
          <span>Room code</span>
          <strong>{lobby.code}</strong>
        </div>
        <p className="lobby-meta">
          {lobby.game_name} · {lobby.num_players} players
          {lobby.options.variant ? ` · ${VARIANT_LABEL[lobby.options.variant as string] ?? lobby.options.variant}` : ""} ·{" "}
          <span className={connected ? "dot-ok" : "dot-bad"}>{connected ? "connected" : "offline"}</span>
        </p>

        <InviteLink code={lobby.code} />

        <p className="lobby-hint">Playing &amp; bidding order is shuffled randomly when the game starts, then fixed for the whole game.</p>

        <ol className="seat-list">
          {seats.map((_, i) => {
            const p = lobby.players[i];
            return (
              <li key={i} className={p ? "seat filled" : "seat empty"}>
                <span className="seat-num">{i + 1}</span>
                {p ? (
                  <>
                    <span className="seat-name">
                      {p.name}
                      {p.id === playerId && <em> (you)</em>}
                    </span>
                    {p.id === lobby.host_id && <span className="host-tag">HOST</span>}
                  </>
                ) : (
                  <span className="seat-waiting">waiting…</span>
                )}
              </li>
            );
          })}
        </ol>

        {isHost ? (
          <>
            {!full && (
              <button className="btn-secondary" onClick={addBot}>
                + Add Bot
              </button>
            )}
            <button className="btn-primary" disabled={!full} onClick={startGame}>
              {full ? "Start Game" : `Waiting for ${lobby.num_players - lobby.players.length} more…`}
            </button>
          </>
        ) : (
          <p className="waiting-text">Waiting for the host to start…</p>
        )}
      </div>
    </div>
  );
}
