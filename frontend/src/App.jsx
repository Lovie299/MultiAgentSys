/**
 * App.jsx — FreeMAD Chat Interface
 *
 * This component is the entire React app. It:
 *   1. Renders a chat interface (input box + message history)
 *   2. Sends POST /api/chat/ when the user submits a message
 *   3. Reads the SSE stream from Django using the Fetch API
 *   4. Displays live progress (round/agent updates) while the debate runs
 *   5. Renders the final answer using simple markdown-like formatting
 *
 * SSE event types (from Django):
 *   {type: "progress", message: "..."}           — status text (spinner rows)
 *   {type: "agent", round, agent, text}          — one agent's live response
 *   {type: "final", message: "..."}              — the winning answer
 *   {type: "error", message: "..."}              — something went wrong
 *   "data: [DONE]"                               — stream closed
 */

import { useState, useRef, useEffect } from "react";
import "./index.css";

// ── Small helper: render plain text with newlines as <br> tags ─────────────
// Replace with react-markdown if you want full markdown support.
function FormattedText({ text }) {
  return (
    <span>
      {text.split("\n").map((line, i) => (
        <span key={i}>
          {line}
          {i < text.split("\n").length - 1 && <br />}
        </span>
      ))}
    </span>
  );
}

// ── Spinner icon ───────────────────────────────────────────────────────────
function Spinner() {
  return <span className="spinner" aria-hidden="true">⏳</span>;
}

// ── Individual agent response card (shown during debate) ──────────────────
function AgentCard({ round, agent, text }) {
  const [expanded, setExpanded] = useState(false);
  // Show only first 200 chars by default to keep the UI compact
  const preview = text.length > 200 ? text.slice(0, 200) + "…" : text;

  return (
    <div className="agent-card">
      <div className="agent-card-header">
        <span className="agent-badge">Round {round} · {agent}</span>
        {text.length > 200 && (
          <button
            className="expand-btn"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "Collapse ▲" : "Expand ▼"}
          </button>
        )}
      </div>
      <p className="agent-card-text">
        <FormattedText text={expanded ? text : preview} />
      </p>
    </div>
  );
}

// ── Main chat bubble component ─────────────────────────────────────────────
function ChatBubble({ role, content, agentEvents }) {
  const isUser = role === "user";

  return (
    <div className={`bubble-row ${isUser ? "user-row" : "assistant-row"}`}>
      <div className={`bubble ${isUser ? "user-bubble" : "assistant-bubble"}`}>

        {/* User message — plain text */}
        {isUser && <p><FormattedText text={content} /></p>}

        {/* Assistant message — final answer + optional debate details */}
        {!isUser && (
          <>
            <p className="final-answer"><FormattedText text={content} /></p>

            {/* Collapsible debate log */}
            {agentEvents && agentEvents.length > 0 && (
              <DebateLog events={agentEvents} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Collapsible debate log inside an assistant bubble ──────────────────────
function DebateLog({ events }) {
  const [open, setOpen] = useState(false);

  // 🧠 GROUP EVENTS BY ROUND
  const rounds = {};

  events.forEach((ev) => {
    if (!rounds[ev.round]) {
      rounds[ev.round] = [];
    }
    rounds[ev.round].push(ev);
  });

  return (
    <div className="debate-log">
      <button className="debate-toggle" onClick={() => setOpen(!open)}>
        {open ? "▲ Hide debate" : "▼ Show debate process"} ({events.length} agent turns)
      </button>

      {open && (
        <div className="debate-content">

          {/* 🔁 LOOP THROUGH ROUNDS */}
          {Object.keys(rounds).map((roundKey) => (
            <div key={roundKey} className="round-block">

              <h3 className="round-title">Round {roundKey}</h3>

              <div className="grid">
                {rounds[roundKey].map((ev, i) => (
                  <AgentCard
                    key={i}
                    round={ev.round}
                    agent={ev.agent}
                    text={ev.text}
                  />
                ))}
              </div>

            </div>
          ))}

        </div>
      )}
    </div>
  );
}

// ── Live status ticker (shown while the stream is active) ──────────────────
function StatusTicker({ messages }) {
  if (!messages.length) return null;
  // Show only the most recent status message
  const latest = messages[messages.length - 1];
  return (
    <div className="status-ticker">
      <Spinner /> <span>{latest}</span>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN APP COMPONENT
// ══════════════════════════════════════════════════════════════════════════════

export default function App() {
  // ── State ──────────────────────────────────────────────────────────────

  // Array of {role, content, agentEvents} objects — the full chat history
  const [messages, setMessages] = useState([]);

  // Current value of the text input
  const [inputValue, setInputValue] = useState("");

  // Optional guiding prompt (advanced, shown in a collapsible section)
  const [guidingPrompt, setGuidingPrompt] = useState(
    "Evaluate your peers' logic carefully. Correct any errors you find."
  );
  const [showAdvanced, setShowAdvanced] = useState(false);

  // True while the SSE stream is active — disables the send button
  const [isStreaming, setIsStreaming] = useState(false);

  // Live progress messages from the debate (shown in the status ticker)
  const [progressMessages, setProgressMessages] = useState([]);

  // Accumulates agent events for the current response before it's committed
  // to the messages array
  const pendingAgentEvents = useRef([]);

  // Auto-scroll to the latest message
  const bottomRef = useRef(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, progressMessages]);

  // ── Send message ───────────────────────────────────────────────────────
  async function handleSend() {
    const text = inputValue.trim();
    if (!text || isStreaming) return;

    // Add user bubble to chat
    setMessages(prev => [...prev, { role: "user", content: text }]);
    setInputValue("");
    setIsStreaming(true);
    setProgressMessages([]);
    pendingAgentEvents.current = [];

    try {
      // POST to Django SSE endpoint
      // During development with Vite proxy this hits http://localhost:8000/api/chat/
      // In production (single container) it's a same-origin request.
      const response = await fetch("/api/chat/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, guiding_prompt: guidingPrompt }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status} ${response.statusText}`);
      }

      // Read the SSE stream chunk by chunk using the Streams API.
      // We use fetch + ReadableStream instead of EventSource because
      // EventSource only supports GET requests.
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Decode the binary chunk into a string and add to buffer
        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by double newlines.
        // Split on \n\n and process each complete event.
        const parts = buffer.split("\n\n");
        // The last part may be incomplete — keep it in the buffer
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          // Each part is one SSE event: "data: <json>"
          const line = part.trim();
          if (!line.startsWith("data:")) continue;

          const raw = line.slice(5).trim(); // strip "data: " prefix

          // [DONE] sentinel — stream is finished
          if (raw === "[DONE]") break;

          let event;
          try {
            event = JSON.parse(raw);
          } catch {
            console.warn("Could not parse SSE event:", raw);
            continue;
          }

          // ── Handle each event type ─────────────────────────────────
          if (event.type === "progress") {
            // Update the status ticker
            setProgressMessages(prev => [...prev, event.message]);
          }

          else if (event.type === "agent") {
            // Store agent turn — will be attached to the final assistant bubble
            pendingAgentEvents.current.push(event);
          }

          else if (event.type === "final") {
            // The debate is done — add the winning response as an assistant bubble
            setMessages(prev => [
              ...prev,
              {
                role: "assistant",
                content: event.message,
                agentEvents: [...pendingAgentEvents.current],
              },
            ]);
            setProgressMessages([]);
            pendingAgentEvents.current = [];
          }

          else if (event.type === "error") {
            // Show error as an assistant bubble
            setMessages(prev => [
              ...prev,
              { role: "assistant", content: `⚠️ Error: ${event.message}` },
            ]);
            setProgressMessages([]);
          }
        }
      }

    } catch (err) {
      // Network error or failed fetch
      setMessages(prev => [
        ...prev,
        { role: "assistant", content: `⚠️ Could not connect to the server: ${err.message}` },
      ]);
      setProgressMessages([]);
    } finally {
      setIsStreaming(false);
    }
  }

  // Submit on Enter (but not Shift+Enter, which inserts a newline)
  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="app">

      {/* ── Header ────────────────────────────────────────────────────── */}
      <header className="header">
        <div className="header-inner">
          <h1 className="logo">🧠 FreeMAD</h1>
          <p className="tagline">Multi-agent debate · {" "}
            <span className="tagline-sub">powered by google-adk</span>
          </p>
        </div>
      </header>

      {/* ── Chat area ─────────────────────────────────────────────────── */}
      <main className="chat-area">

        {/* Empty state */}
        {messages.length === 0 && !isStreaming && (
          <div className="empty-state">
            <div className="empty-icon">💬</div>
            <h2>Ask anything</h2>
            <p>Multiple AI agents will debate your question and return the best-scored answer.</p>
          </div>
        )}

        {/* Message history */}
        {messages.map((msg, i) => (
          <ChatBubble
            key={i}
            role={msg.role}
            content={msg.content}
            agentEvents={msg.agentEvents}
          />
        ))}

        {/* Live status ticker (shown while streaming) */}
        {isStreaming && <StatusTicker messages={progressMessages} />}

        {/* Invisible scroll anchor */}
        <div ref={bottomRef} />
      </main>

      {/* ── Input area ────────────────────────────────────────────────── */}
      <footer className="input-area">

        {/* Advanced options toggle */}
        <div className="advanced-toggle-row">
          <button
            className="advanced-toggle"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            {showAdvanced ? "▲ Hide" : "▼ Guiding prompt"}
          </button>
        </div>

        {showAdvanced && (
          <div className="advanced-panel">
            <label htmlFor="guiding-prompt">
              Guiding prompt <span className="label-hint">(sent to all agents as meta-instruction)</span>
            </label>
            <textarea
              id="guiding-prompt"
              className="guiding-input"
              value={guidingPrompt}
              onChange={e => setGuidingPrompt(e.target.value)}
              rows={2}
            />
          </div>
        )}

        {/* Main input row */}
        <div className="input-row">
          <textarea
            className="message-input"
            placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
            rows={2}
          />
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={isStreaming || !inputValue.trim()}
          >
            {isStreaming ? "…" : "Send"}
          </button>
        </div>

      </footer>
    </div>
  );
}
