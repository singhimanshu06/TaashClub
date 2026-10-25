import { useEffect, useId, useRef } from "react";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";

/** One exit control for every room screen, including overlays and reconnects. */
export default function LeaveControl() {
  const { open, leaving, role, game, error, requestLeave, cancelLeave, reset } = useStore(
    useShallow((s) => ({
      open: s.leaveConfirmationOpen,
      leaving: s.leaving,
      role: s.role,
      game: s.game,
      error: s.error,
      requestLeave: s.requestLeave,
      cancelLeave: s.cancelLeave,
      reset: s.reset,
    }))
  );
  const dialogRef = useRef<HTMLDialogElement>(null);
  const stayRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const activeGame = game && game.phase !== "lobby" && game.phase !== "game_end";

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // A native modal traps focus and makes the game underneath inert.
      dialog.showModal();
      stayRef.current?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <>
      <button
        type="button"
        className="leave-btn"
        onClick={requestLeave}
        disabled={leaving}
        title="Leave room"
        aria-label="Leave room"
        aria-haspopup="dialog"
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <path d="m16 17 5-5-5-5M21 12H9" />
        </svg>
      </button>

      <dialog
        ref={dialogRef}
        className="modal leave-dialog"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-busy={leaving}
        onCancel={(event) => {
          event.preventDefault();
          cancelLeave();
        }}
      >
        <h2 id={titleId}>Leave this room?</h2>
        <p id={descriptionId} className="modal-sub">
          {role === "spectator"
            ? "You’ll stop watching and return to the home screen."
            : activeGame
              ? "The game will continue without you. A bot may take over your seat."
              : game?.phase === "game_end"
                ? "You’ll return to the home screen."
                : "Your seat will be released for another player."}
        </p>
        {error && <p className="inline-error" role="alert">{error}</p>}
        <div className="leave-dialog-actions">
          <button ref={stayRef} type="button" className="btn-secondary" onClick={cancelLeave} disabled={leaving}>
            Stay
          </button>
          <button type="button" className="btn-primary" onClick={reset} disabled={leaving}>
            {leaving ? "Leaving…" : "Leave room"}
          </button>
        </div>
      </dialog>
    </>
  );
}
