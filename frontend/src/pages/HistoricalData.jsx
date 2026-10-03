import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api";
import { useFilters } from "../filters";
import { Box, Status } from "../ui";

export default function HistoricalData() {
  const { applied } = useFilters();
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [useDates, setUseDates] = useState(false);
  const on = !!applied;
  const base = { state: applied?.state, district: applied?.district };
  const ev = useApi("floods", { ...base, q: term, ...(useDates ? { start: applied?.start, end: applied?.end } : {}), limit: 300 }, on);
  const fr = useApi("floods/frequency", base, on);
  if (!applied) return <p className="muted">Loading...</p>;
  return (
    <>
      <Box title="Recorded flood-onset days per year">
        <Status s={fr} />
        {fr.data && <ResponsiveContainer width="100%" height={230}><BarChart data={fr.data.rows}>
          <CartesianGrid stroke="#e8ecf2" vertical={false} /><XAxis dataKey="year" fontSize={11} /><YAxis fontSize={11} width={40} />
          <Tooltip /><Bar dataKey="onsets" name="Onset days" fill="#1f5fbf" /></BarChart></ResponsiveContainer>}
        <p className="small muted">{fr.data?.note} Scope: {applied.district || applied.state || "all pilot states"}.</p>
      </Box>
      <Box title="Flood event records" right={<div className="search"><input placeholder="Search district or cause" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && setTerm(q)} /><button onClick={() => setTerm(q)}>Search</button></div>}>
        <label className="small"><input type="checkbox" checked={useDates} onChange={(e) => setUseDates(e.target.checked)} /> Only events overlapping {applied.start} to {applied.end}</label>
        <Status s={ev} empty={ev.data && !ev.data.rows.length ? "No events match these filters." : null} />
        {ev.data?.rows.length > 0 && <>
          <p className="small muted">Showing {ev.data.shown} of {ev.data.total} event-district records.</p>
          <div className="scroll tall"><table><thead><tr><th>Start</th><th>End</th><th>Days</th><th>State</th><th>District</th><th>Cause (from record text)</th></tr></thead>
            <tbody>{ev.data.rows.map((r, i) => <tr key={`${r.event_id}-${r.district_id}-${i}`}><td>{r.start_date}</td><td>{r.end_date}</td><td>{r.duration_days}</td><td>{r.state}</td><td>{r.district}</td><td>{r.cause_class}</td></tr>)}</tbody></table></div>
          <p className="small muted">{ev.data.note} Source: India Flood Inventory v3 (IIT Delhi, CC BY 4.0).</p></>}
      </Box>
    </>
  );
}
