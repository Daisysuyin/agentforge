import { useMemo, useState } from "react";
import { useQuery } from "@apollo/client";
import { ChatStream } from "../components/ChatStream";
import { AGENTS_QUERY, TOOLS_QUERY } from "../graphql/operations";

interface Agent {
  id: string;
  name: string;
  description: string | null;
  role: string;
  systemPrompt: string;
  toolNames: string[];
  guardrailsJson: string;
}

interface Tool {
  name: string;
  description: string;
}

const ORCHESTRATOR_VALUE = "__orchestrator__";

export function Playground() {
  const { data: agentsData, loading: agentsLoading } = useQuery<{ agents: Agent[] }>(AGENTS_QUERY);
  const { data: toolsData } = useQuery<{ tools: Tool[] }>(TOOLS_QUERY);

  const [selected, setSelected] = useState<string>(ORCHESTRATOR_VALUE);

  const agents = agentsData?.agents ?? [];
  const tools = toolsData?.tools ?? [];

  const activeAgent = useMemo(
    () => (selected === ORCHESTRATOR_VALUE ? null : agents.find((a) => a.id === selected) ?? null),
    [selected, agents],
  );

  const guardrails = useMemo(() => {
    if (!activeAgent) return null;
    try {
      return JSON.parse(activeAgent.guardrailsJson);
    } catch {
      return null;
    }
  }, [activeAgent]);

  const toolByName = useMemo(() => {
    const m = new Map<string, Tool>();
    for (const t of tools) m.set(t.name, t);
    return m;
  }, [tools]);

  return (
    <>
      <div className="page-header">
        <div className="page-header__eyebrow">Module · Playground</div>
        <h1 className="page-header__title">Run an agent</h1>
        <p className="page-header__subtitle">
          Pick an agent (or let the orchestrator route automatically). Messages stream live over SSE
          — text deltas, tool invocations, and tool results appear as they happen.
        </p>
      </div>

      <div className="page-body" style={{ overflow: "hidden", display: "flex" }}>
        <div className="playground" style={{ flex: 1 }}>
          <div className="playground__main">
            <div className="playground__toolbar">
              <span className="label" style={{ margin: 0, marginRight: 4 }}>
                Agent
              </span>
              <select
                className="select"
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                disabled={agentsLoading}
              >
                <option value={ORCHESTRATOR_VALUE}>
                  Orchestrator — auto-route to specialist
                </option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} · {a.role}
                  </option>
                ))}
              </select>
              <span style={{ marginLeft: "auto" }} className="tag tag--accent">
                SSE · live
              </span>
            </div>

            <ChatStream agentId={activeAgent?.id ?? null} />
          </div>

          <aside className="playground__sidepanel">
            <section className="panel">
              <div className="panel__title">
                {activeAgent ? "System Prompt" : "Routing Mode"}
              </div>
              <pre className="panel__prompt">
                {activeAgent
                  ? activeAgent.systemPrompt
                  : "The orchestrator picks the right specialist (sales / service / marketing) for each message based on intent classification, then runs that agent's full tool loop."}
              </pre>
            </section>

            {activeAgent && (
              <section className="panel">
                <div className="panel__title">Available Tools</div>
                <div className="panel__tool-list">
                  {activeAgent.toolNames.length === 0 && (
                    <span className="dim mono" style={{ fontSize: 11 }}>
                      no tools assigned
                    </span>
                  )}
                  {activeAgent.toolNames.map((tn) => {
                    const t = toolByName.get(tn);
                    return (
                      <span
                        key={tn}
                        className="tag tag--tool"
                        title={t?.description || ""}
                      >
                        {tn}
                      </span>
                    );
                  })}
                </div>
              </section>
            )}

            {activeAgent && guardrails && Object.keys(guardrails).length > 0 && (
              <section className="panel">
                <div className="panel__title">Guardrails</div>
                <pre className="panel__prompt">{JSON.stringify(guardrails, null, 2)}</pre>
              </section>
            )}
          </aside>
        </div>
      </div>
    </>
  );
}
