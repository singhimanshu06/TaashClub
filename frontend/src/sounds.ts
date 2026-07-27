/**
 * Sound-effects player using HTML5 Audio with preloaded mp3 files.
 *
 * Sounds (served from /public/sounds/):
 *  - "turn_to_play":  it's your turn to play a card
 *  - "turn_to_bid":    it's your turn to bid
 *  - "card_distribution": cards dealt at the start of a round / game
 */

const MUTE_KEY = "taashclub_muted";

export type SoundName = "turn_to_play" | "turn_to_bid" | "card_distribution" | "score_board";

const SRC: Record<SoundName, string> = {
  turn_to_play: "/sounds/turn_to_play.mp3",
  turn_to_bid: "/sounds/turn_to_bid.mp3",
  card_distribution: "/sounds/card_distribution.mp3",
  score_board: "/sounds/score_board.mp3",
};

let muted = false;
try {
  muted = localStorage.getItem(MUTE_KEY) === "1";
} catch {
  // localStorage may be unavailable (private mode) — defaults to unmuted.
}

// Preload one Audio element per sound so playback is instant (no network
// fetch on the critical first-play frame).
const clips: Record<SoundName, HTMLAudioElement> = (() => {
  const out = {} as Record<SoundName, HTMLAudioElement>;
  if (typeof document === "undefined") return out;
  (Object.keys(SRC) as SoundName[]).forEach((name) => {
    const a = new Audio(SRC[name]);
    a.preload = "auto";
    out[name] = a;
  });
  return out;
})();

let unlocked = false;

export function isMuted(): boolean {
  return muted;
}

export function setMuted(v: boolean): void {
  muted = v;
  try {
    localStorage.setItem(MUTE_KEY, v ? "1" : "0");
  } catch {
    // ignore
  }
}

/** Resume playback context — browsers block audio until a user gesture. */
export function unlockAudio(): void {
  if (unlocked) return;
  // Play (then immediately pause) each clip to satisfy autoplay policy and
  // warm the decoder. Actually just attempting a play+pause on one clip is
  // enough to unlock the rest.
  const any = clips.turn_to_play;
  if (any) {
    any.muted = true;
    const p = any.play();
    if (p && typeof p.then === "function") {
      p.then(() => {
        any.pause();
        any.currentTime = 0;
        any.muted = false;
        unlocked = true;
      }).catch(() => {
        any.muted = false;
      });
    }
  }
}

// One-time gesture listener to satisfy the browser autoplay policy.
if (typeof document !== "undefined") {
  const unlockOnce = () => {
    unlockAudio();
    document.removeEventListener("pointerdown", unlockOnce);
    document.removeEventListener("keydown", unlockOnce);
  };
  document.addEventListener("pointerdown", unlockOnce);
  document.addEventListener("keydown", unlockOnce);
}

export function playSound(name: SoundName): void {
  if (muted) return;
  const clip = clips[name];
  if (!clip) return;
  // Rewind to start so rapid repeat triggers (e.g. turn→bid) don't get cut.
  try {
    clip.currentTime = 0;
  } catch {
    // seek can throw if metadata not loaded yet — ignore
  }
  const p = clip.play();
  if (p && typeof p.then === "function") {
    p.catch(() => {
      // Autoplay still blocked (no gesture yet) — silently ignore.
    });
  }
}
