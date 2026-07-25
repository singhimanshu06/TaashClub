import { useEffect } from "react";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "./store";
import Home from "./components/Home";
import Lobby from "./components/Lobby";
import GameTable from "./components/GameTable";
import Reconnecting from "./components/Reconnecting";
import Chat from "./components/Chat";

export default function App() {
  const { screen, error, clearError, reconnect } = useStore(
    useShallow((s) => ({
      screen: s.screen,
      error: s.error,
      clearError: s.clearError,
      reconnect: s.reconnect,
    }))
  );

  // On first load, check for a saved session and attempt reconnection instead
  // of showing Home. This handles refresh, phone-sleep, power-button, etc.
  useEffect(() => {
    const saved = localStorage.getItem("taashclub_session");
    if (saved) reconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(clearError, 3500);
    return () => clearTimeout(t);
  }, [error, clearError]);

  return (
    <div className="app">
      {screen === "home" && <Home />}
      {screen === "lobby" && <Lobby />}
      {screen === "game" && <GameTable />}
      {screen === "reconnecting" && <Reconnecting />}
      {(screen === "lobby" || screen === "game") && <Chat />}
      {error && (
        <div className="toast" onClick={clearError}>
          {error}
        </div>
      )}
    </div>
  );
}
