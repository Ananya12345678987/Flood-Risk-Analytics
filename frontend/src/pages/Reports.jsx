import { fmt, get, useApi } from "../api";
import { useFilters } from "../filters";
import { Badge, Box, Status } from "../ui";

const ROWS = [["rain_total", "Total rainfall", 0], ["river_discharge", "River discharge (modelled)", 1], ["temperature", "Temperature", 1], ["humidity", "Humidity", 0]];

export default function Reports() {
  const { applied, meta } = useFilters();
  const on = !!applied;
  const a = applied || {};
  const p = { state: a.state, district: a.district, start: a.start, end: a.end };
  const sum = useApi("summary", p, on), warn = useApi("warning", { state: a.state, district: a.district, date: a.end }, on);
  const mod = useApi("model", {}, on);
  if (!applied) return <p className="muted">Loading...</p>;
  const S = sum.data, W = warn.data, mt = mod.data?.metrics;
  const csv = async () => {
    const { rows } = await get("timeseries", p);
    const cols = Object.keys(rows[0] || {});
    const text = [cols.join(","), ...rows.map((r) => cols.map((c) => r[c] ?? "").join(","))].join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    link.download = `flood-risk-timeseries_${a.start}_${a.end}.csv`;
    link.click();
  };
  return (
    <>
      <div className="card noprint"><div className="card-h"><h2>Report generator</h2></div>
        <p className="small muted">The report below uses the current filters. Print it (choose "Save as PDF" in the print dialog) or download the underlying daily series as CSV.</p>
        <button className="primary" onClick={() => window.print()}>Print / save as PDF</button> <button onClick={csv}>Download daily data (CSV)</button></div>
      <Box title="Flood Risk Assessment Report" cls="report">
        <Status s={sum} />
        {S && <>
          <p><b>Region:</b> {S.scope} &nbsp; <b>Period:</b> {S.start} to {S.end} ({S.days} days) &nbsp; <b>As-of date:</b> {S.end}</p>
          <h3>Warning status</h3>
          {W?.available ? <><p><Badge level={W.level} /> Highest-risk district: <b>{W.driver_district}</b>, score {fmt(W.risk_score, 0)}/100 (class {W.risk_class}; ML class {W.ml_class}).</p>
            <ul className="reasons">{W.reasons.map((r) => <li key={r}>{r}</li>)}</ul></> : <p className="muted">No warning data for this date.</p>}
          <h3>Key indicators</h3>
          <table><thead><tr><th>Indicator</th><th>Value</th><th>Change vs previous period</th></tr></thead><tbody>
            {ROWS.map(([k, l, d]) => <tr key={k}><td>{l}</td><td>{S[k].value === null ? "n/a" : `${fmt(S[k].value, d)} ${S[k].unit}`}</td><td>{S[k].change_pct === null ? "n/a" : `${fmt(S[k].change_pct, 1)}%`}</td></tr>)}</tbody></table>
          {mt && <><h3>Model quality (test years 2016-2020)</h3>
            <p className="small">ROC-AUC {fmt(mt.test.roc_auc, 3)}; PR-AUC {fmt(mt.test.pr_auc, 3)} against a random-guess level of {fmt(mt.test.prevalence, 4)}; the top 5% of days by score contained {fmt(100 * mt.test.recall_in_top5pct_days, 0)}% of recorded flood onsets.</p></>}
          <h3>Data sources</h3>
          <ul className="small">{meta.data?.sources.map((s) => <li key={s.variable}><b>{s.variable}:</b> {s.source} ({s.type})</li>)}</ul>
          <h3>Limitations</h3>
          <p className="small">{meta.data?.disclaimer} {meta.data?.notice} River values are modelled discharge at one point per district. Flood labels come from a record of reported events and are incomplete, with a recording-style change from 2021. Report generated {new Date().toLocaleString()}.</p>
        </>}
      </Box>
    </>
  );
}
