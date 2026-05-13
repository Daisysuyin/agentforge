import { useState } from "react";

export interface ToolCallCardProps {
  name: string;
  arguments: unknown;
  status: "running" | "ok" | "err";
  result?: unknown;
  error?: string | null;
  durationMs?: number | null;
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function ToolCallCard({
  name,
  arguments: args,
  status,
  result,
  error,
  durationMs,
}: ToolCallCardProps) {
  const [open, setOpen] = useState(true);

  const cls =
    "toolcall " +
    (status === "running"
      ? "toolcall--running"
      : status === "ok"
        ? "toolcall--ok"
        : "toolcall--err") +
    (open ? " toolcall--open" : "");

  return (
    <div className={cls}>
      <div className="toolcall__head" onClick={() => setOpen(!open)}>
        <span className="toolcall__icon" />
        <span className="toolcall__name">{name}</span>
        <span className="toolcall__meta">
          {status === "running"
            ? "running…"
            : durationMs != null
              ? `${durationMs.toFixed(1)}ms`
              : ""}
        </span>
        <span className="toolcall__caret">›</span>
      </div>
      {open && (
        <div className="toolcall__body">
          <div>
            <div className="toolcall__section-label">Arguments</div>
            <pre className="toolcall__json">{formatJson(args)}</pre>
          </div>
          {status === "ok" && result !== undefined && (
            <div>
              <div className="toolcall__section-label">Result</div>
              <pre className="toolcall__json">{formatJson(result)}</pre>
            </div>
          )}
          {status === "err" && (
            <div>
              <div className="toolcall__section-label">Error</div>
              <div className="toolcall__error">{error || "tool failed"}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
