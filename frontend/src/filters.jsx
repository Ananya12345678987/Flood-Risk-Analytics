import { createContext, useContext, useEffect, useState } from "react";
import { useApi } from "./api";

const Ctx = createContext(null);
export const useFilters = () => useContext(Ctx);

export function FilterProvider({ children }) {
  const meta = useApi("meta");
  const regions = useApi("regions");
  const [applied, setApplied] = useState(null);
  useEffect(() => {
    if (meta.data && !applied) setApplied({ state: "", district: "", start: meta.data.default_start, end: meta.data.default_as_of });
  }, [meta.data]);
  return <Ctx.Provider value={{ meta, regions, applied, setApplied }}>{children}</Ctx.Provider>;
}

export function FilterBar() {
  const { meta, regions, applied, setApplied } = useFilters();
  const [f, setF] = useState(applied);
  useEffect(() => setF(applied), [applied]);
  if (meta.error || regions.error) return null;
  if (!meta.data || !regions.data || !f) return <div className="card muted">Loading filters...</div>;
  const states = regions.data.states;
  const districts = states.find((s) => s.state === f.state)?.districts || [];
  const m = meta.data;
  const reset = () => setApplied({ state: "", district: "", start: m.default_start, end: m.default_as_of });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value, ...(k === "state" ? { district: "" } : {}) });
  return (
    <div className="card filters">
      <label>State<select value={f.state} onChange={set("state")}><option value="">All pilot states</option>
        {states.map((s) => <option key={s.state}>{s.state}</option>)}</select></label>
      <label>District<select value={f.district} onChange={set("district")} disabled={!f.state}><option value="">All districts</option>
        {districts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      <label>From<input type="date" value={f.start} min={m.date_min} max={m.date_max} onChange={set("start")} /></label>
      <label>To (as-of date)<input type="date" value={f.end} min={m.date_min} max={m.date_max} onChange={set("end")} /></label>
      <button className="primary" onClick={() => setApplied(f)}>Apply</button>
      <button onClick={reset}>Reset</button>
    </div>
  );
}
