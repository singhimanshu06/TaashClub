import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";

export default function Reconnecting() {
  const { code, reconnectAttempt, reconnect } = useStore(
    useShallow((s) => ({
      code: s.code,
      reconnectAttempt: s.reconnectAttempt,
      reconnect: s.reconnect,
    }))
  );

  const exhausted = reconnectAttempt === 0;

  return (
    <div className="screen center reconnecting-screen">
      <div className="spinner" />
      {!exhausted ? (
        <>
          <p className="reconnecting-title">Reconnecting to room {code}…</p>
          <p className="reconnecting-sub">Attempt {reconnectAttempt}</p>
        </>
      ) : (
        <>
          <p className="reconnecting-title">Connection lost</p>
          <p className="reconnecting-sub">Couldn't reach the room after several tries.</p>
          <button className="btn-primary" onClick={reconnect}>
            Try again
          </button>
        </>
      )}
    </div>
  );
}
