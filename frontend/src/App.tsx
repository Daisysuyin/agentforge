import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Playground } from "./pages/Playground";
import { AgentBuilder } from "./pages/AgentBuilder";
import { TracesEval } from "./pages/TracesEval";

interface NavItemSpec {
  to: string;
  label: string;
  glyph: string;
}

const NAV: NavItemSpec[] = [
  { to: "/playground", label: "Playground", glyph: ">_" },
  { to: "/builder", label: "Agent Builder", glyph: "{}" },
  { to: "/traces", label: "Traces & Evals", glyph: "≡" },
];

function Sidebar() {
  return (
    <nav className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__brand-mark">AgentForge</span>
        <span className="sidebar__brand-version">v0.1</span>
      </div>

      <div className="sidebar__section-label">Workbench</div>
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            "sidebar__nav-item" + (isActive ? " sidebar__nav-item--active" : "")
          }
        >
          <span className="sidebar__nav-icon">{item.glyph}</span>
          {item.label}
        </NavLink>
      ))}

      <div className="sidebar__footer">
        <span className="sidebar__status-dot" />
        runtime · ready
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <div className="app">
      <Sidebar />
      <div className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/playground" replace />} />
          <Route path="/playground" element={<Playground />} />
          <Route path="/builder" element={<AgentBuilder />} />
          <Route path="/traces" element={<TracesEval />} />
          <Route path="*" element={<Navigate to="/playground" replace />} />
        </Routes>
      </div>
    </div>
  );
}
