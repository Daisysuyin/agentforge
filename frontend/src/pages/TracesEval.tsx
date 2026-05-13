import { useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import { RUN_EVAL, TRACES_QUERY } from "../graphql/operations";

interface ToolCall {
  id: string;
  sequence: number;
  toolName: string;
  argumentsJson: string;
  resultJson: string | null;
  error: string | null;
  durationMs: number | null;
}

interface Trace {
  id: string;
  agentId: string;
  userInput: string;
  finalOutput: string | null;
  status: string;
  error: string | null;
  durationMs: number | null;
  tokensIn: number;
  tokensOut: number;
  createdAt: string;
  toolCalls: ToolCall[];
}

interface EvalCaseResult {
  caseId: string;
  userInput: string;
  finalText: string;
  toolCallsMade: string[];
  expectedTools: string[];
  toolsMatch: boolean;
  textMatch: boolean;
  judgeScore: number | null;
  error: string | null;
  durationMs: number;
}

interface EvalReport {
  n: number;
  toolAccuracy: number;
  textAccuracy: number;
  avgJudgeScore: number | null;
  p50LatencyMs: number;
  p95LatencyMs: number;
  errorRate: number;
  cases: EvalCaseResult[];
}

function formatPct(v: number): string {
  return (v * 100).toFixed(0) + "%";
}

function formatMs(v: number): string {
  return v < 1 ? "<1 ms" : `${Math.round(v)} ms`;
}

function shortDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function TracesEval() {
  const { data: tracesData, refetch: refetchTraces } = useQuery<{ traces: Trace[] }>(TRACES_QUERY, {
    variables: { limit: 50 },
    fetchPolicy: "cache-and-network",
  });
  const [runEval, { loading: evaling }] = useMutation<{ runEvalSuite: EvalReport }>(RUN_EVAL);
  const [report, setReport] = useState<EvalReport | null>(null);
  const [evalErr, setEvalErr] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const traces = tracesData?.traces ?? [];

  const onRunEval = async () => {
    setEvalErr(null);
    try {
      const r = await runEval({
        variables: { fixturePath: "../traces/sample_traces.json", useJudge: false },
      });
      if (r.data) setReport(r.data.runEvalSuite);
      await refetchTraces();
    } catch (e: unknown) {
      setEvalErr(e instanceof Error ? e.message : "eval failed");
    }
  };

  return (
    <>
      <div className="page-header">
        <div className="page-header__eyebrow">Module · Traces & Evals</div>
        <h1 className="page-header__title">Inspect and evaluate</h1>
        <p className="page-header__subtitle">
          Every agent run produces a structured trace (messages + tool calls + timing). The eval
          suite replays a fixture file end-to-end and scores tool-call accuracy and latency.
        </p>
      </div>

      <div className="page-body">
        <div className="traces-eval">
          {/* ---------- Eval Section ---------- */}
          <section>
            <div className="row row--between" style={{ marginBottom: 12 }}>
              <h2 className="mono" style={{ fontSize: 14, letterSpacing: 1.4, textTransform: "uppercase", color: "var(--text-dim)", margin: 0 }}>
                Evaluation Suite
              </h2>
              <button className="button button--primary" onClick={onRunEval} disabled={evaling}>
                {evaling ? <span className="spinner" /> : null}
                {evaling ? "Running suite…" : "▶ Run eval suite"}
              </button>
            </div>

            {evalErr && (
              <div className="stream-error" style={{ marginBottom: 12 }}>
                {evalErr}
              </div>
            )}

            {report && (
              <>
                <div className="eval-summary">
                  <div className="eval-stat">
                    <div className="eval-stat__label">Cases</div>
                    <div className="eval-stat__value">{report.n}</div>
                  </div>
                  <div className="eval-stat">
                    <div className="eval-stat__label">Tool accuracy</div>
                    <div className="eval-stat__value eval-stat__value--accent">
                      {formatPct(report.toolAccuracy)}
                    </div>
                  </div>
                  <div className="eval-stat">
                    <div className="eval-stat__label">Text match</div>
                    <div className="eval-stat__value">{formatPct(report.textAccuracy)}</div>
                  </div>
                  <div className="eval-stat">
                    <div className="eval-stat__label">Error rate</div>
                    <div
                      className={
                        "eval-stat__value " +
                        (report.errorRate > 0 ? "eval-stat__value--err" : "")
                      }
                    >
                      {formatPct(report.errorRate)}
                    </div>
                  </div>
                  <div className="eval-stat">
                    <div className="eval-stat__label">p50 latency</div>
                    <div className="eval-stat__value">{formatMs(report.p50LatencyMs)}</div>
                  </div>
                  <div className="eval-stat">
                    <div className="eval-stat__label">p95 latency</div>
                    <div className="eval-stat__value">{formatMs(report.p95LatencyMs)}</div>
                  </div>
                </div>

                <div className="eval-table" style={{ marginTop: 16 }}>
                  <div className="eval-row eval-row--head">
                    <div>Case</div>
                    <div>Input</div>
                    <div>Tools called</div>
                    <div>Match</div>
                    <div>Time</div>
                  </div>
                  {report.cases.map((c) => (
                    <div key={c.caseId} className="eval-row">
                      <div className="eval-row__case-id">{c.caseId}</div>
                      <div className="eval-row__input">{c.userInput}</div>
                      <div className="eval-row__tools">
                        {c.toolCallsMade.length === 0 ? (
                          <span className="dim">none</span>
                        ) : (
                          c.toolCallsMade.join(", ")
                        )}
                      </div>
                      <div>
                        {c.toolsMatch ? (
                          <span className="tag tag--ok">pass</span>
                        ) : (
                          <span className="tag tag--err">fail</span>
                        )}
                      </div>
                      <div className="eval-row__duration">{formatMs(c.durationMs)}</div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {!report && !evaling && (
              <div className="card" style={{ textAlign: "center", color: "var(--text-dim)" }}>
                <span className="mono" style={{ fontSize: 12 }}>
                  No report yet — run the suite to populate metrics.
                </span>
              </div>
            )}
          </section>

          {/* ---------- Traces Section ---------- */}
          <section>
            <h2 className="mono" style={{ fontSize: 14, letterSpacing: 1.4, textTransform: "uppercase", color: "var(--text-dim)", margin: "8px 0 12px 0" }}>
              Recent Traces · {traces.length}
            </h2>
            <div className="trace-table">
              <div className="trace-row trace-row--head">
                <div>User input</div>
                <div>Tools</div>
                <div>Status</div>
                <div>Duration</div>
                <div>Created</div>
              </div>
              {traces.length === 0 && (
                <div className="trace-row" style={{ color: "var(--text-dim)" }}>
                  <div className="dim">No traces yet — run an agent in the Playground.</div>
                  <div />
                  <div />
                  <div />
                  <div />
                </div>
              )}
              {traces.map((t) => {
                const open = expanded === t.id;
                return (
                  <div key={t.id}>
                    <div
                      className="trace-row"
                      onClick={() => setExpanded(open ? null : t.id)}
                    >
                      <div className="eval-row__input">{t.userInput}</div>
                      <div className="eval-row__tools">
                        {t.toolCalls.map((tc) => tc.toolName).join(", ") || (
                          <span className="dim">—</span>
                        )}
                      </div>
                      <div>
                        {t.status === "done" && <span className="tag tag--ok">done</span>}
                        {t.status === "error" && <span className="tag tag--err">error</span>}
                        {t.status === "running" && <span className="tag">running</span>}
                      </div>
                      <div className="eval-row__duration">
                        {t.durationMs != null ? formatMs(t.durationMs) : "—"}
                      </div>
                      <div className="eval-row__duration">{shortDate(t.createdAt)}</div>
                    </div>
                    {open && (
                      <div className="trace-detail">
                        <div className="dim mono" style={{ fontSize: 10, letterSpacing: 0.5 }}>
                          trace · {t.id} · {t.tokensIn} in / {t.tokensOut} out
                        </div>
                        {t.error && (
                          <div className="stream-error">{t.error}</div>
                        )}
                        {t.finalOutput && (
                          <div className="trace-detail__final">{t.finalOutput}</div>
                        )}
                        {t.toolCalls.map((tc) => (
                          <div key={tc.id} className="toolcall toolcall--ok toolcall--open">
                            <div className="toolcall__head">
                              <span className="toolcall__icon" />
                              <span className="toolcall__name">{tc.toolName}</span>
                              <span className="toolcall__meta">
                                {tc.durationMs != null ? formatMs(tc.durationMs) : ""}
                              </span>
                            </div>
                            <div className="toolcall__body">
                              <div>
                                <div className="toolcall__section-label">Arguments</div>
                                <pre className="toolcall__json">
                                  {JSON.stringify(JSON.parse(tc.argumentsJson || "{}"), null, 2)}
                                </pre>
                              </div>
                              {tc.resultJson && (
                                <div>
                                  <div className="toolcall__section-label">Result</div>
                                  <pre className="toolcall__json">
                                    {JSON.stringify(JSON.parse(tc.resultJson), null, 2)}
                                  </pre>
                                </div>
                              )}
                              {tc.error && (
                                <div>
                                  <div className="toolcall__section-label">Error</div>
                                  <div className="toolcall__error">{tc.error}</div>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
