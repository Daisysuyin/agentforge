import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import {
  AGENTS_QUERY,
  CREATE_AGENT,
  DELETE_AGENT,
  TOOLS_QUERY,
  UPDATE_AGENT,
} from "../graphql/operations";

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

interface FormState {
  id: string | null;
  name: string;
  description: string;
  role: string;
  systemPrompt: string;
  toolNames: Set<string>;
  guardrailsText: string;
}

const NEW_AGENT_FORM: FormState = {
  id: null,
  name: "",
  description: "",
  role: "sales",
  systemPrompt: "You are a helpful AgentForge agent. ...",
  toolNames: new Set(),
  guardrailsText: "{}",
};

const ROLES = ["sales", "service", "marketing", "generalist"];

function formFromAgent(a: Agent): FormState {
  return {
    id: a.id,
    name: a.name,
    description: a.description ?? "",
    role: a.role,
    systemPrompt: a.systemPrompt,
    toolNames: new Set(a.toolNames),
    guardrailsText: a.guardrailsJson || "{}",
  };
}

export function AgentBuilder() {
  const { data: agentsData } = useQuery<{ agents: Agent[] }>(AGENTS_QUERY);
  const { data: toolsData } = useQuery<{ tools: Tool[] }>(TOOLS_QUERY);
  const [createAgent, { loading: creating }] = useMutation(CREATE_AGENT, {
    refetchQueries: [{ query: AGENTS_QUERY }],
  });
  const [updateAgent, { loading: updating }] = useMutation(UPDATE_AGENT, {
    refetchQueries: [{ query: AGENTS_QUERY }],
  });
  const [deleteAgent, { loading: deleting }] = useMutation(DELETE_AGENT, {
    refetchQueries: [{ query: AGENTS_QUERY }],
  });

  const agents = agentsData?.agents ?? [];
  const tools = toolsData?.tools ?? [];

  const [form, setForm] = useState<FormState>(NEW_AGENT_FORM);
  const [statusMsg, setStatusMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [guardrailsErr, setGuardrailsErr] = useState<string | null>(null);

  // Default to first agent on initial load
  useEffect(() => {
    if (form.id === null && agents.length > 0 && form.name === NEW_AGENT_FORM.name) {
      setForm(formFromAgent(agents[0]));
    }
  }, [agents, form]);

  const isNew = form.id === null;
  const busy = creating || updating || deleting;

  const validateGuardrails = useMemo(
    () => () => {
      try {
        const parsed = JSON.parse(form.guardrailsText || "{}");
        if (typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("guardrails must be a JSON object");
        }
        setGuardrailsErr(null);
        return true;
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        setGuardrailsErr(msg);
        return false;
      }
    },
    [form.guardrailsText],
  );

  const onSelect = (id: string) => {
    const a = agents.find((x) => x.id === id);
    if (a) {
      setForm(formFromAgent(a));
      setStatusMsg(null);
      setGuardrailsErr(null);
    }
  };

  const onNew = () => {
    setForm(NEW_AGENT_FORM);
    setStatusMsg(null);
    setGuardrailsErr(null);
  };

  const onToggleTool = (name: string) => {
    setForm((f) => {
      const next = new Set(f.toolNames);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return { ...f, toolNames: next };
    });
  };

  const onSave = async () => {
    if (!validateGuardrails()) return;
    if (!form.name.trim()) {
      setStatusMsg({ kind: "err", text: "Name is required" });
      return;
    }
    try {
      if (isNew) {
        const r = await createAgent({
          variables: {
            input: {
              name: form.name,
              description: form.description || null,
              role: form.role,
              systemPrompt: form.systemPrompt,
              toolNames: [...form.toolNames],
              guardrailsJson: form.guardrailsText || "{}",
            },
          },
        });
        const created = r.data?.createAgent as Agent | undefined;
        if (created) setForm(formFromAgent(created));
        setStatusMsg({ kind: "ok", text: "Agent created" });
      } else {
        await updateAgent({
          variables: {
            input: {
              id: form.id,
              name: form.name,
              description: form.description || null,
              role: form.role,
              systemPrompt: form.systemPrompt,
              toolNames: [...form.toolNames],
              guardrailsJson: form.guardrailsText || "{}",
            },
          },
        });
        setStatusMsg({ kind: "ok", text: "Saved" });
      }
    } catch (e: unknown) {
      setStatusMsg({ kind: "err", text: e instanceof Error ? e.message : "save failed" });
    }
  };

  const onDelete = async () => {
    if (!form.id) return;
    if (!confirm(`Delete agent "${form.name}"? This also deletes its traces.`)) return;
    try {
      await deleteAgent({ variables: { id: form.id } });
      setForm(NEW_AGENT_FORM);
      setStatusMsg({ kind: "ok", text: "Deleted" });
    } catch (e: unknown) {
      setStatusMsg({ kind: "err", text: e instanceof Error ? e.message : "delete failed" });
    }
  };

  return (
    <>
      <div className="page-header">
        <div className="page-header__eyebrow">Module · Agent Builder</div>
        <h1 className="page-header__title">Define your agents</h1>
        <p className="page-header__subtitle">
          An agent is a system prompt + a set of tools + guardrails. Changes take effect immediately
          — open the Playground in another tab to test as you iterate.
        </p>
      </div>

      <div className="page-body" style={{ overflow: "hidden", display: "flex" }}>
        <div className="builder" style={{ flex: 1 }}>
          <div className="builder__list">
            <div className="builder__list-head">
              <div className="builder__list-title">Agents · {agents.length}</div>
              <button className="button button--small" onClick={onNew}>
                + new
              </button>
            </div>
            <div className="builder__list-items">
              {agents.map((a) => {
                const active = a.id === form.id;
                return (
                  <div
                    key={a.id}
                    className={"builder__list-item" + (active ? " builder__list-item--active" : "")}
                    onClick={() => onSelect(a.id)}
                  >
                    <div className="builder__list-item-name">{a.name}</div>
                    <div className="builder__list-item-meta">
                      {a.role} · {a.toolNames.length} tools
                    </div>
                  </div>
                );
              })}
              {isNew && (
                <div className="builder__list-item builder__list-item--active">
                  <div className="builder__list-item-name">{form.name || "New agent"}</div>
                  <div className="builder__list-item-meta">unsaved · {form.toolNames.size} tools</div>
                </div>
              )}
            </div>
          </div>

          <div className="builder__form">
            <h2 className="builder__form-title">
              {isNew ? "New agent" : form.name}
              <span className="tag tag--accent">{form.role}</span>
            </h2>

            <div>
              <label className="label">Name</label>
              <input
                className="input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Sales SDR"
              />
            </div>

            <div>
              <label className="label">Description</label>
              <input
                className="input"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="One-line summary"
              />
            </div>

            <div>
              <label className="label">Role</label>
              <select
                className="select"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="label">System prompt</label>
              <textarea
                className="textarea textarea--prompt"
                value={form.systemPrompt}
                onChange={(e) => setForm({ ...form, systemPrompt: e.target.value })}
              />
            </div>

            <div>
              <label className="label">Tools · {form.toolNames.size} selected</label>
              <div className="tool-grid">
                {tools.map((t) => {
                  const checked = form.toolNames.has(t.name);
                  return (
                    <label
                      key={t.name}
                      className={"tool-checkbox" + (checked ? " tool-checkbox--checked" : "")}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => onToggleTool(t.name)}
                      />
                      <div>
                        <div className="tool-checkbox__name">{t.name}</div>
                        <div className="tool-checkbox__desc">{t.description}</div>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>

            <div>
              <label className="label">Guardrails (JSON)</label>
              <textarea
                className="textarea"
                value={form.guardrailsText}
                onChange={(e) => setForm({ ...form, guardrailsText: e.target.value })}
                onBlur={() => validateGuardrails()}
                spellCheck={false}
              />
              {guardrailsErr && (
                <div className="tag tag--err" style={{ marginTop: 6 }}>
                  {guardrailsErr}
                </div>
              )}
              <div className="dim mono" style={{ fontSize: 11, marginTop: 6 }}>
                Examples: <code>{'{"max_amount": 50000}'}</code>,{" "}
                <code>{'{"blocked_companies": ["Hooli"]}'}</code>
              </div>
            </div>

            <div className="builder__form-actions">
              {statusMsg && (
                <span
                  className={"tag " + (statusMsg.kind === "ok" ? "tag--ok" : "tag--err")}
                  style={{ marginRight: "auto" }}
                >
                  {statusMsg.text}
                </span>
              )}
              {!isNew && (
                <button className="button button--danger" onClick={onDelete} disabled={busy}>
                  Delete
                </button>
              )}
              <button className="button button--primary" onClick={onSave} disabled={busy}>
                {busy ? <span className="spinner" /> : null}
                {isNew ? "Create agent" : "Save changes"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
