import { LEVEL_COLOR, fmt, useApi } from "../api";
import { useFilters } from "../filters";
import { Badge, Box, Status } from "../ui";

export default function EarlyWarning() {
  const { applied, setApplied } = useFilters();
  const on = !!applied;
  const p = { state: applied?.state, district: applied?.district };
  const warn = useApi("warning", { ...p, date: applied?.end }, on);
  const hist = useApi("warnings/history", { ...p, start: applied?.start, end: applied?.end, limit: 40 }, on);
  if (!applied) return <p className="muted">Loading...</p>;
  const W = warn.data;
  return (
    <>
      <Box title={`Active warning status, as of ${applied.end}`} right={W?.available && <Badge level={W.level} />}>
        <Status s={warn} empty={W && !W.available ? W.message : null} />
        {W?.available && <>
          <div className="tiles">{Object.entries(W.level_counts).map(([k, v]) => <div key={k} className="tile" style={{ borderTop: `4px solid ${LEVEL_COLOR[k]}` }}><b>{v}</b><span className="muted small">{k}</span></div>)}</div>
          <p className="small muted">Driving district: <b>{W.driver_district}</b> ({W.state}). Risk score {fmt(W.risk_score, 0)}; analytical class {W.risk_class}; ML class {W.ml_class}.</p>
        </>}
      </Box>
      {W?.available && <div className="grid2">
        <Box title="Why this level"><ul className="reasons">{W.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          <h3>Contributing factors</h3>{(W.contributions || []).map((c) => <div className="bar" key={c.key}><span>{c.factor}</span><div><i style={{ width: `${c.percent}%` }} /></div><b>{fmt(c.percent, 0)}%</b></div>)}
          <p className="small muted">{W.disclaimer}</p></Box>
        <Box title="Affected districts (ALERT or above)">
          {W.affected.length ? <div className="scroll"><table><thead><tr><th>District</th><th>State</th><th>Level</th><th>Score</th></tr></thead>
            <tbody>{W.affected.map((a) => <tr key={a.district_id}><td>{a.district}</td><td>{a.state}</td><td><Badge level={a.level} /></td><td>{fmt(a.risk_score, 0)}</td></tr>)}</tbody></table></div>
            : <p className="muted">No district is at ALERT or above on this date.</p>}
          <p className="small muted">Top 15 by level and score.</p></Box>
      </div>}
      <Box title="Warning history in the selected date range">
        <Status s={hist} empty={hist.data && !hist.data.rows.length ? "No ALERT or HIGH RISK days in this range." : null} />
        {hist.data?.rows.length > 0 && <div className="scroll"><table><thead><tr><th>Date</th><th>Level</th><th>Districts flagged</th><th>Top district</th><th>Score</th><th /></tr></thead>
          <tbody>{hist.data.rows.map((r) => <tr key={r.date}><td>{r.date}</td><td><Badge level={r.level} /></td><td>{r.n_flagged}</td><td>{r.district}</td><td>{fmt(r.risk_score, 0)}</td>
            <td><button onClick={() => setApplied({ ...applied, end: r.date })}>Show this date</button></td></tr>)}</tbody></table></div>}
        <p className="small muted">Most recent 40 flagged days. Warnings are recomputed from the data for each date (historical replay).</p>
      </Box>
    </>
  );
}
