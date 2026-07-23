import { useEffect } from "react";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "./store";
import Home from "./components/Home";
import Lobby from "./components/Lobby";
import GameTable from "./components/GameTable";
import Chat from "./components/Chat";

export default function App() {
  const { screen, error, clearError } = useStore(
    useShallow((s) => ({
      screen: s.screen,
      error: s.error,
      clearError: s.clearError,
    }))
  );

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
      {(screen === "lobby" || screen === "game") && <Chat />}
      {error && (
        <div className="toast" onClick={clearError}>
          {error}
        </div>
      )}
    </div>
  );
}
