import { NavLink, Route, Routes } from "react-router-dom";
import { FilterBar, FilterProvider, useFilters } from "./filters";
import Dashboard from "./pages/Dashboard.jsx";

const NAV = [["/", "Dashboard"], ["/region", "Region Analysis"], ["/prediction", "Risk Prediction"], ["/map", "Maps & Visualization"],
  ["/history", "Historical Data"], ["/warning", "Early Warning"], ["/reports", "Reports"], ["/about", "About & Methodology"]];

const Soon = ({ title }) => <div className="card"><h2>{title}</h2><p className="muted">This page is built in the next stage.</p></div>;

function Shell() {
  const { meta } = useFilters();
  return (
    <div className="shell">
      <aside><div className="brand">Flood Risk<br />Analytics</div>
        <nav>{NAV.map(([to, label]) => <NavLink key={to} to={to} end={to === "/"}>{label}</NavLink>)}</nav>
        <p className="foot">Big Data Analytics mini-project. Data: IMD, NASA POWER, GloFAS, India Flood Inventory.</p></aside>
      <main>
        <header><h1>Flood Risk Analytics</h1><p className="muted">Flood-risk assessment and early-warning support for Assam, Kerala, Karnataka and Maharashtra</p></header>
        {meta.error && <div className="card error">{meta.error}</div>}
        {meta.data && <div className="notice"><b>Historical replay.</b> {meta.data.notice} {meta.data.disclaimer}</div>}
        <FilterBar />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          {NAV.slice(1).map(([to, label]) => <Route key={to} path={to} element={<Soon title={label} />} />)}
        </Routes>
      </main>
    </div>
  );
}
export default function App() { return <FilterProvider><Shell /></FilterProvider>; }
