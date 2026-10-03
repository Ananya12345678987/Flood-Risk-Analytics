import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmt, useApi } from "../api";
import { useFilters } from "../filters";
import { Badge, Box, Status } from "../ui";

const MET = [["roc_auc", "ROC-AUC", 3], ["pr_auc", "PR-AUC", 3], ["prevalence", "Base rate (random PR-AUC)", 4], ["precision", "Precision", 3], ["recall", "Recall", 3],
  ["f1", "F1", 3], ["recall_in_top5pct_days", "Onsets caught in top 5% of days", 3], ["accuracy", "Accuracy (misleading)", 3]];
const classTable = (cs, title) => cs && <><h3>{title}</h3><table><thead><tr><th>Class</th><th>Days</th><th>Onset rate</th><th>Lift vs average</th></tr></thead><tbody>
  {["LOW", "MEDIUM", "HIGH"].filter((k) => cs[k]).map((k) => <tr key={k}><td>{k}</td><td>{fmt(cs[k].days)}</td><td>{cs[k].onset_rate_pct}%</td><td>{cs[k].lift}x</td></tr>)}</tbody></table></>;

export default function RiskPrediction() {
  const { applied } = useFilters();
  const on = !!applied;
  const a = applied || {};
  const warn = useApi("warning", { state: a.state, district: a.district, date: a.end }, on);
  const ts = useApi("timeseries", { state: a.state, district: a.district, start: a.start, end: a.end }, on);
  const mod = useApi("model", {}, on);
  if (!applied) return <p className="muted">Loading...</p>;
  const W = warn.data, M = mod.data, mt = M?.metrics;
  return (
    <>
      <div className="grid2">
        <Box title={`Current risk, ${a.end}`} right={W?.available && <Badge level={W.level} />}>
          <Status s={warn} empty={W && !W.available ? W.message : null} />
          {W?.available && <><div className="tiles"><div className="tile"><b>{fmt(W.risk_score, 0)}</b><span className="muted small">Analytical score (headline)</span></div>
            <div className="tile"><b>{W.risk_class}</b><span className="muted small">Score class</span></div><div className="tile"><b>{W.ml_class}</b><span className="muted small">ML class (cross-check)</span></div>
            <div className="tile"><b>{W.driver_district}</b><span className="muted small">Driving district</span></div></div>
            <p className="small muted">The score is the headline output because it can be explained factor by factor. The ML model is a second opinion on the same day. ML probabilities are tiny because floods are rare, so classes are shown and not raw probabilities.</p></>}
        </Box>
        <Box title="Risk score trend (recent history, not a forecast)">
          <Status s={ts} />
          {ts.data && <ResponsiveContainer width="100%" height={220}><LineChart data={ts.data.rows}><CartesianGrid stroke="#e8ecf2" vertical={false} />
            <XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} fontSize={11} /><YAxis domain={[0, 100]} fontSize={11} width={34} /><Tooltip formatter={(v) => fmt(v, 0)} />
            <Line dataKey="risk_score" name="Highest district score" stroke="#d64545" dot={false} strokeWidth={2} /></LineChart></ResponsiveContainer>}
          <p className="small muted">A 7-day flood forecast would need archived weather forecasts, which this project does not have, so none is shown.</p>
        </Box>
      </div>
      <Status s={mod} />
      {M && <>
        <div className="grid2">
          <Box title="Model performance on unseen years">
            {mt ? <table><thead><tr><th>Metric</th><th>Test 2016-2020</th><th>Check 2021-2023</th></tr></thead><tbody>
              {MET.map(([k, l, d]) => <tr key={k}><td>{l}</td><td>{fmt(mt.test?.[k], d)}</td><td>{fmt(mt.shift?.[k], d)}</td></tr>)}
              <tr><td>Confusion (TP / FP / FN)</td><td>{mt.test?.tp} / {mt.test?.fp} / {mt.test?.fn}</td><td>{mt.shift?.tp} / {mt.shift?.fp} / {mt.shift?.fn}</td></tr></tbody></table> : <p className="muted">Metrics not available.</p>}
            <ul className="reasons small">{M.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </Box>
          <Box title="What the classes mean historically (2013-2020)">
            {classTable(M.class_stats.score, "Analytical score classes")}{classTable(M.class_stats.ml, "ML classes")}
            <p className="small muted">Class cut-offs are percentiles of the 2013-2015 tuning years (my choice), not official thresholds. Even HIGH days usually see no recorded flood onset, so treat HIGH as raised attention.</p>
          </Box>
        </div>
        <div className="grid2">
          <Box title="Feature importance (permutation, test sample)">
            {M.importance && <ResponsiveContainer width="100%" height={380}><BarChart data={M.importance} layout="vertical" margin={{ left: 40 }}><CartesianGrid stroke="#e8ecf2" horizontal={false} />
              <XAxis type="number" fontSize={11} /><YAxis type="category" dataKey="feature" fontSize={11} width={150} /><Tooltip /><Bar dataKey="importance" name="PR-AUC drop" fill="#1f5fbf" /></BarChart></ResponsiveContainer>}
            <p className="small muted">Shows what the model relies on, not what causes floods. Humidity probably stands in for the wet season.</p>
          </Box>
          <Box title="Do extra feature groups help? (ablation)">
            {M.ablation && <table><thead><tr><th>Feature set</th><th>Test ROC</th><th>Test PR</th><th>2021-23 ROC</th></tr></thead><tbody>
              {M.ablation.map((r) => <tr key={r.feature_set}><td>{r.feature_set}</td><td>{fmt(r.test_roc, 3)}</td><td>{fmt(r.test_pr, 3)}</td><td>{fmt(r.shift_roc, 3)}</td></tr>)}</tbody></table>}
            <p className="small muted">Rainfall carries most of the signal. Other groups add little, and river features added a small but consistent gain.</p>
            <h3>Score weights learned from 2000-2012</h3>
            <p className="small">{Object.entries(M.weights.weights_5 || {}).map(([k, v]) => `${k} ${fmt(v, 2)}`).join(", ")} (districts with a river point)</p>
          </Box>
        </div>
      </>}
    </>
  );
}
