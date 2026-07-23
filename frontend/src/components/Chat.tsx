import { useEffect, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";

export default function Chat() {
  const { messages, playerId, sendChat } = useStore(
    useShallow((s) => ({ messages: s.messages, playerId: s.playerId, sendChat: s.sendChat }))
  );
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [seen, setSeen] = useState(0);
  const bodyRef = useRef<HTMLDivElement>(null);
  const winRef = useRef<HTMLDivElement>(null);

  // Track unread count while the window is minimized.
  useEffect(() => {
    if (open) setSeen(messages.length);
  }, [open, messages.length]);

  // Auto-scroll to the newest message when open.
  useEffect(() => {
    if (open && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [messages, open]);

  // Close on outside click when the chat window is open.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (winRef.current && !winRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const unread = messages.length - seen;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    sendChat(text);
    setText("");
  }

  if (!open) {
    return (
      <button className="chat-fab" onClick={() => setOpen(true)} aria-label="Open chat">
        💬 Chat
        {unread > 0 && <span className="chat-unread">{unread > 9 ? "9+" : unread}</span>}
      </button>
    );
  }

  return (
    <div className="chat-window" ref={winRef}>
      <div className="chat-header">
        <span>Game chat</span>
        <button className="chat-min" onClick={() => setOpen(false)} aria-label="Minimize chat">
          —
        </button>
      </div>
      <div className="chat-body" ref={bodyRef}>
        {messages.length === 0 && <p className="chat-empty">No messages yet. Say hi 👋</p>}
        {messages.map((m, i) => {
          const mine = m.player_id === playerId;
          return (
            <div key={i} className={`chat-msg${mine ? " mine" : ""}`}>
              {!mine && <span className="chat-name">{m.name}</span>}
              <span className="chat-text">{m.text}</span>
            </div>
          );
        })}
      </div>
      <form className="chat-input" onSubmit={submit}>
        <input
          value={text}
          maxLength={300}
          placeholder="Type a message…"
          onChange={(e) => setText(e.target.value)}
        />
        <button type="submit" disabled={!text.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
