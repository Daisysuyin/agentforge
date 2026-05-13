import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { ToolCallCard } from "./ToolCallCard";

type AssistantSegment =
  | { kind: "text"; text: string }
  | {
      kind: "tool";
      callId: string;
      name: string;
      args: unknown;
      status: "running" | "ok" | "err";
      result?: unknown;
      error?: string | null;
      durationMs?: number | null;
    };

interface Turn {
  id: number;
  userInput: string;
  segments: AssistantSegment[];
  status: "streaming" | "done" | "error";
  error?: string | null;
  traceId?: string | null;
}

export interface ChatStreamHandle {
  send: (message: string) => void;
  isStreaming: boolean;
}

export interface ChatStreamProps {
  /** If set, sends to /chat/{agentId}. Otherwise sends to /chat/orchestrate. */
  agentId: string | null;
  /** Disables sending while server is unreachable, etc. */
  disabled?: boolean;
}

/**
 * Builds the URL for the SSE stream. Vite dev server proxies /chat to the backend.
 */
function buildStreamUrl(agentId: string | null, message: string): string {
  const base = agentId ? `/chat/${encodeURIComponent(agentId)}` : "/chat/orchestrate";
  return `${base}?message=${encodeURIComponent(message)}`;
}

export function ChatStream({ agentId }: ChatStreamProps) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const streamEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const turnIdRef = useRef(0);

  // Auto-scroll to the bottom whenever a new event lands.
  useEffect(() => {
    streamEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  // Reset stream state when the agent changes.
  useEffect(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setTurns([]);
    setIsStreaming(false);
  }, [agentId]);

  const handleEvent = useCallback((turnId: number, type: string, raw: string) => {
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(raw);
    } catch {
      // ignore malformed events
      return;
    }

    setTurns((prev) =>
      prev.map((t) => {
        if (t.id !== turnId) return t;
        const next: Turn = { ...t, segments: [...t.segments] };

        if (type === "text_delta") {
          const text = String(payload.text ?? "");
          const last = next.segments[next.segments.length - 1];
          if (last && last.kind === "text") {
            next.segments[next.segments.length - 1] = {
              ...last,
              text: last.text + text,
            };
          } else {
            next.segments.push({ kind: "text", text });
          }
        } else if (type === "tool_call") {
          next.segments.push({
            kind: "tool",
            callId: String(payload.call_id ?? ""),
            name: String(payload.name ?? ""),
            args: payload.arguments ?? {},
            status: "running",
          });
        } else if (type === "tool_result") {
          const callId = String(payload.call_id ?? "");
          for (let i = next.segments.length - 1; i >= 0; i--) {
            const s = next.segments[i];
            if (s.kind === "tool" && s.callId === callId) {
              next.segments[i] = {
                ...s,
                status: payload.ok ? "ok" : "err",
                result: payload.data,
                error: payload.error as string | null | undefined,
                durationMs: (payload.duration_ms as number | undefined) ?? null,
              };
              break;
            }
          }
        } else if (type === "done") {
          next.status = "done";
          next.traceId = (payload.trace_id as string) ?? null;
        } else if (type === "error") {
          next.status = "error";
          next.error = String(payload.message ?? "stream error");
        }

        return next;
      }),
    );
  }, []);

  const send = useCallback(
    (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) return;
      eventSourceRef.current?.close();

      const turnId = ++turnIdRef.current;
      setTurns((prev) => [
        ...prev,
        { id: turnId, userInput: trimmed, segments: [], status: "streaming" },
      ]);
      setIsStreaming(true);

      const url = buildStreamUrl(agentId, trimmed);
      const es = new EventSource(url);
      eventSourceRef.current = es;

      const eventNames = ["text_delta", "tool_call", "tool_result", "done", "error"];
      eventNames.forEach((name) => {
        es.addEventListener(name, (ev) => {
          handleEvent(turnId, name, (ev as MessageEvent).data);
          if (name === "done" || name === "error") {
            setIsStreaming(false);
            es.close();
          }
        });
      });

      es.onerror = () => {
        // EventSource fires error on stream close from server; ignore if we're already done.
        setTurns((prev) =>
          prev.map((t) => {
            if (t.id !== turnId || t.status !== "streaming") return t;
            return { ...t, status: "error", error: "connection closed" };
          }),
        );
        setIsStreaming(false);
        es.close();
      };
    },
    [agentId, handleEvent],
  );

  const onSubmit = () => {
    if (!draft.trim() || isStreaming) return;
    send(draft);
    setDraft("");
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  const empty = turns.length === 0;
  const suggestions = [
    "Create a new lead for Sarah Chen at Northwind Solutions.",
    "Find the contact with email anna@globex.example",
    "Search the knowledge base for our refund policy.",
    "Advance the opportunity Globex Renewal to the next stage.",
  ];

  return (
    <>
      <div className="playground__stream">
        {empty && (
          <div className="playground__empty">
            <div>No messages yet — try one of these:</div>
            <div className="playground__empty-suggestions">
              {suggestions.map((s) => (
                <button
                  key={s}
                  className="playground__empty-suggestion"
                  onClick={() => send(s)}
                  disabled={isStreaming}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn) => (
          <Fragment key={turn.id}>
            <div className="stream-msg-user">{turn.userInput}</div>
            <div className="stream-msg-assistant">
              {turn.segments.map((seg, i) => {
                if (seg.kind === "text") {
                  const isLastTextStreaming =
                    turn.status === "streaming" &&
                    i === turn.segments.length - 1 &&
                    seg.kind === "text";
                  return (
                    <div
                      key={i}
                      className={
                        "stream-msg-assistant__text" +
                        (isLastTextStreaming ? " stream-msg-assistant__text--streaming" : "")
                      }
                    >
                      {seg.text}
                    </div>
                  );
                }
                return (
                  <ToolCallCard
                    key={i}
                    name={seg.name}
                    arguments={seg.args}
                    status={seg.status}
                    result={seg.result}
                    error={seg.error}
                    durationMs={seg.durationMs ?? null}
                  />
                );
              })}
              {turn.status === "error" && (
                <div className="stream-error">
                  Stream error: {turn.error || "unknown"}
                </div>
              )}
              {turn.status === "done" && turn.traceId && (
                <div className="dim mono" style={{ fontSize: 10, letterSpacing: 0.5 }}>
                  trace: {turn.traceId}
                </div>
              )}
            </div>
          </Fragment>
        ))}

        <div ref={streamEndRef} />
      </div>

      <div className="playground__composer">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={agentId ? "Ask the agent…" : "Ask the orchestrator (auto-routes to specialist)…"}
          rows={1}
        />
        <button
          className="button button--primary"
          onClick={onSubmit}
          disabled={!draft.trim() || isStreaming}
        >
          {isStreaming ? <span className="spinner" /> : null}
          {isStreaming ? "Streaming" : "Send ↵"}
        </button>
      </div>
    </>
  );
}
