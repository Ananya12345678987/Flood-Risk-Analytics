import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmt, useApi } from "../api";
import { useFilters } from "../filters";
import { Box, Status } from "../ui";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const ROWS = [["rain_total", "Total rainfall", 0], ["river_discharge", "River discharge (modelled)", 1], ["temperature", "Temperature", 1],
  ["humidity", "Humidity", 0], ["pressure", "Surface pressure", 1], ["wind", "Wind speed", 1]];
const median = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : null; };

export default function RegionAnalysis() {
  const { applied } = useFilters();
  const on = !!applied;
  const a = applied || {};
  const p = { state: a.state, district: a.district, start: a.start, end: a.end };
  const sum = useApi("summary", p, on), ts = useApi("timeseries", p, on), warn = useApi("warning", { state: a.state, district: a.district, date: a.end }, on);
  const clim = useApi("climatology", { state: a.state }, on), tr = useApi("trends", { state: a.state }, on);
  const geo = useApi("geography", { state: a.state, district: a.district }, on), fr = useApi("floods/frequency", { state: a.state, district: a.district }, on);
  if (!applied) return <p className="muted">Loading...</p>;
  const S = sum.data, W = warn.data;
  const trows = (tr.data?.rows || []).filter((r) => !a.district || r.district_id === a.district);
  const sig = trows.filter((r) => r.trend_significant_5pct);
  const sorted = [...trows].sort((x, y) => y.annual_trend_mm_per_yr - x.annual_trend_mm_per_yr);
  const shownTrends = a.district ? sorted : [...sorted.slice(0, 5), ...sorted.slice(-5)];
  const onsets = (fr.data?.rows || []).reduce((t, r) => t + r.onsets, 0);
  return (
    <>
      <div className="grid2">
        <Box title={`Statistics: ${S?.scope || ""}, ${a.start} to ${a.end}`}>
          <Status s={sum} />
          {S && <table><thead><tr><th>Variable</th><th>This period</th><th>Previous period</th><th>Change</th></tr></thead><tbody>
            {ROWS.map(([k, l, d]) => <tr key={k}><td>{l}</td><td>{S[k].value === null ? "n/a" : `${fmt(S[k].value, d)} ${S[k].unit}`}</td>
              <td>{fmt(S[k].previous, d)}</td><td>{S[k].change_pct === null ? "n/a" : `${S[k].change_pct > 0 ? "+" : ""}${fmt(S[k].change_pct, 1)}%`}</td></tr>)}</tbody></table>}
          <p className="small muted">Rainfall is the sum of the district-average daily rainfall. River values need a district with a river point; pressure is surface pressure and depends on altitude.</p>
        </Box>
        <Box title="Temperature and humidity">
          <Status s={ts} />
          {ts.data && <ResponsiveContainer width="100%" height={240}><LineChart data={ts.data.rows}><CartesianGrid stroke="#e8ecf2" vertical={false} />
            <XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} fontSize={11} /><YAxis yAxisId="t" fontSize={11} width={40} /><YAxis yAxisId="h" orientation="right" fontSize={11} width={40} />
            <Tooltip /><Legend /><Line yAxisId="t" dataKey="temp_c" name="Temperature (degC)" stroke="#d1623b" dot={false} />
            <Line yAxisId="h" dataKey="humidity_pct" name="Humidity (%)" stroke="#1f5fbf" dot={false} /></LineChart></ResponsiveContainer>}
          <p className="small muted">Weather is NASA POWER reanalysis (~50 km), so neighbouring districts can share values.</p>
        </Box>
      </div>
      <div className="grid2">
        <Box title="Average monthly rainfall (2000-2023)">
          <Status s={clim} />
          {clim.data && <ResponsiveContainer width="100%" height={230}><BarChart data={clim.data.rows.map((r) => ({ ...r, m: MONTHS[r.month - 1] }))}>
            <CartesianGrid stroke="#e8ecf2" vertical={false} /><XAxis dataKey="m" fontSize={11} /><YAxis fontSize={11} width={44} unit=" mm" />
            <Tooltip formatter={(v) => `${fmt(v, 0)} mm`} /><Bar dataKey="mean_monthly_mm" name="Mean monthly rainfall" fill="#7fa6dd" /></BarChart></ResponsiveContainer>}
        </Box>
        <Box title="Annual rainfall trend, 2000-2023">
          <Status s={tr} empty={!trows.length && !tr.loading && !tr.error ? "No trend data." : null} />
          {trows.length > 0 && <>
            <p className="small">{trows.length} district{trows.length > 1 ? "s" : ""}: <b>{sig.length}</b> with a statistically notable trend (about 5% level); median trend {fmt(median(trows.map((r) => r.annual_trend_mm_per_yr)), 1)} mm per year.</p>
            <div className="scroll"><table><thead><tr><th>District</th><th>State</th><th>Mean mm/yr</th><th>Trend mm/yr</th><th>Notable</th></tr></thead><tbody>
              {shownTrends.map((r) => <tr key={r.district_id}><td>{r.district}</td><td>{r.state}</td><td>{fmt(r.mean_annual_mm, 0)}</td><td>{fmt(r.annual_trend_mm_per_yr, 1)}</td><td>{r.trend_significant_5pct ? "yes" : "no"}</td></tr>)}</tbody></table></div>
            <p className="small muted">{tr.data.note} {!a.district && "Showing the 5 largest increases and decreases."}</p></>}
        </Box>
      </div>
      <div className="grid2">
        <Box title="Risk factors on the as-of date">
          <Status s={warn} empty={W && !W.contributions ? "Not available." : null} />
          {W?.contributions?.map((c) => <div className="bar" key={c.key}><span>{c.factor}</span><div><i style={{ width: `${c.percent}%` }} /></div><b>{fmt(c.percent, 0)}%</b></div>)}
          <p className="small muted">Recorded flood-onset days in this scope, 2000-2023: <b>{fr.data ? fmt(onsets) : "..."}</b> (see Historical Data for caveats).</p>
        </Box>
        <Box title="Geographic characteristics">
          <Status s={geo} />
          {geo.data && <div className="scroll tall"><table><thead><tr><th>District</th><th>Area km2</th><th>Mean elev. m</th><th>Relief m</th><th>River point</th></tr></thead><tbody>
            {geo.data.rows.map((r) => <tr key={r.district_id}><td>{r.district}</td><td>{fmt(r.area_km2, 0)}</td><td>{fmt(r.elev_mean_m, 0)}</td><td>{fmt(r.relief_m, 0)}</td><td>{r.river_tier}</td></tr>)}</tbody></table></div>}
          <p className="small muted">{geo.data?.note} River point: none, minor or major, by long-term mean modelled discharge (under 1, 1-10, over 10 m3/s; my own cut-offs).</p>
        </Box>
      </div>
    </>
  );
}
