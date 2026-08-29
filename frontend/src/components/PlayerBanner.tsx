import { useEffect, useRef } from "react";
import { useStore } from "../store";

const BANNER_MS = 4000;

export default function PlayerBanner() {
  const banner = useStore((s) => s.playerBanner);
  const clearPlayerBanner = useStore((s) => s.clearPlayerBanner);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const ts = banner?.ts;

  useEffect(() => {
    if (!ts) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      clearPlayerBanner();
    }, BANNER_MS);
  }, [ts, clearPlayerBanner]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  if (!banner) return null;
  return (
    <div className={`player-banner ${banner.connected ? "on" : "off"}`}>
      {banner.connected ? `${banner.name} connected` : `${banner.name} disconnected`}
    </div>
  );
}
