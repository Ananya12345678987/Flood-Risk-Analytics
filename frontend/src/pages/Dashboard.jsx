import { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import { Area, AreaChart, Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { LEVEL_COLOR, fmt, useApi } from "../api";
import { useFilters } from "../filters";

const Box = ({ title, children, right, cls = "" }) => <section className={`card ${cls}`}><div className="card-h"><h2>{title}</h2>{right}</div>{children}</section>;
const Status = ({ s, empty }) => (s.loading ? <p className="muted">Loading...</p> : s.error ? <p className="error-text">{s.error}</p> : empty ? <p className="muted">{empty}</p> : null);
const Badge = ({ level }) => <span className="badge" style={{ background: LEVEL_COLOR[level] || "#eee" }}>{level}</span>;

function Kpi({ label, k, d = 0, unavailable }) {
  const na = !k || k.value === null || unavailable;
  const up = k?.change_pct > 0;
  return (
    <div className="card kpi"><span className="muted">{label}</span>
      <b>{na ? "Data unavailable" : <>{fmt(k.value, d)} <small>{k.unit}</small></>}</b>
      <span className="muted small">{na ? unavailable || "No values in this period" : k.change_pct === null ? "no previous period" : `${up ? "up" : "down"} ${fmt(Math.abs(k.change_pct), 1)}% vs previous period`}</span></div>
  );
}

function Fit({ data }) {
  const map = useMap();
  useEffect(() => { const b = L.geoJSON(data).getBounds(); if (b.isValid()) map.fitBounds(b, { padding: [8, 8] }); }, [data]);
  return null;
}

function RiskMap({ applied }) {
  const geo = useApi("geo/districts");
  const risk = useApi("map", { date: applied.end, level: "district" });
  const byId = useMemo(() => Object.fromEntries((risk.data?.rows || []).map((r) => [r.district_id, r])), [risk.data]);
  const shown = useMemo(() => {
    if (!geo.data) return null;
    const keep = (f) => (applied.district ? f.properties.district_id === applied.district : !applied.state || f.properties.state === applied.state);
    return { type: "FeatureCollection", features: geo.data.features.filter(keep) };
  }, [geo.data, applied.state, applied.district]);
  const style = (f) => ({ color: "#5b6b82", weight: 0.8, fillOpacity: 0.75, fillColor: LEVEL_COLOR[byId[f.properties.district_id]?.level] || "#eef1f5" });
  const tip = (f, layer) => {
    const r = byId[f.properties.district_id];
    layer.bindTooltip(`${f.properties.district} (${f.properties.state})<br/>${r ? `${r.level}, score ${fmt(r.risk_score, 0)}` : "no data"}`);
  };
  return (
    <Box title={`District risk map, ${applied.end}`}>
      <Status s={geo.error ? geo : risk} empty={shown && !shown.features.length ? "No district boundaries for this selection." : null} />
      {shown && <div className="map"><MapContainer center={[18, 80]} zoom={5} scrollWheelZoom={false} style={{ height: "100%" }}>
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" opacity={0.55} />
        <GeoJSON key={`${applied.end}-${applied.state}-${applied.district}-${risk.data ? 1 : 0}`} data={shown} style={style} onEachFeature={tip} />
        <Fit data={shown} /></MapContainer></div>}
      <div className="legend">{Object.entries(LEVEL_COLOR).map(([k, c]) => <span key={k}><i style={{ background: c }} />{k}</span>)}</div>
    </Box>
  );
}

const tick = (v) => (v || "").slice(5);

export default function Dashboard() {
  const { applied } = useFilters();
  const [freq, setFreq] = useState("D");
  const on = !!applied;
  const p = applied ? { state: applied.state, district: applied.district, start: applied.start, end: applied.end } : {};
  const sum = useApi("summary", p, on);
  const ts = useApi("timeseries", { ...p, freq }, on);
  const warn = useApi("warning", { state: p.state, district: p.district, date: p.end }, on);
  if (!applied) return <p className="muted">Loading...</p>;
  const S = sum.data, W = warn.data, rows = ts.data?.rows || [];
  const toggle = <div className="seg">{[["D", "Daily"], ["W", "Weekly"], ["M", "Monthly"]].map(([k, l]) => <button key={k} className={freq === k ? "on" : ""} onClick={() => setFreq(k)}>{l}</button>)}</div>;
  const riverNone = S && !S.river_available ? "No river data for this selection" : null;
  return (
    <>
      <Status s={sum} />
      {S && <div className="kpis">
        <Kpi label="Total rainfall" k={S.rain_total} />
        <Kpi label="River discharge (modelled)" k={S.river_discharge} d={1} unavailable={riverNone} />
        <div className="card kpi"><span className="muted">Flood risk score (highest district)</span>
          <b>{S.risk?.risk_score == null ? "Data unavailable" : <>{fmt(S.risk.risk_score, 0)} <small>/ 100</small></>}</b>
          <span className="muted small">percentile-style index</span></div>
        <div className="card kpi"><span className="muted">Warning level</span>
          <b>{W?.available ? <Badge level={W.level} /> : "Data unavailable"}</b>
          <span className="muted small">{W?.available ? `class ${W.risk_class}; ML ${W.ml_class}` : ""}</span></div>
        <Kpi label="Temperature" k={S.temperature} d={1} />
        <Kpi label="Humidity" k={S.humidity} d={0} />
      </div>}
      <div className="grid2">
        <RiskMap applied={applied} />
        <Box title="Early-warning status" right={W?.available && <Badge level={W.level} />}>
          <Status s={warn} empty={W && !W.available ? W.message : null} />
          {W?.available && <>
            <p className="small muted">As of {W.date}. Driving district: <b>{W.driver_district}</b> ({W.state}). {W.districts_in_scope} districts in scope; {W.level_counts["HIGH RISK"] + W.level_counts.ALERT} at ALERT or above.</p>
            <h3>Why this level</h3><ul className="reasons">{W.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            <p className="small muted">{W.disclaimer}</p></>}
        </Box>
      </div>
      <div className="grid2">
        <Box title="Rainfall (district average)" right={toggle}>
          <Status s={ts} empty={!rows.length && !ts.loading && !ts.error ? "No rainfall data for this period." : null} />
          {rows.length > 0 && <ResponsiveContainer width="100%" height={250}><ComposedChart data={rows}>
            <CartesianGrid stroke="#e8ecf2" vertical={false} /><XAxis dataKey="date" tickFormatter={tick} fontSize={11} /><YAxis fontSize={11} unit=" mm" width={56} />
            <Tooltip formatter={(v) => `${fmt(v, 1)} mm`} /><Bar dataKey="rain_mm" name="Rainfall" fill="#7fa6dd" />
            {freq === "D" && <Line dataKey="rain_7d_avg_mm" name="7-day average" stroke="#14213d" dot={false} strokeWidth={2} />}</ComposedChart></ResponsiveContainer>}
        </Box>
        <Box title="River discharge (modelled, GloFAS)" right={toggle}>
          <Status s={ts} empty={riverNone} />
          {rows.length > 0 && !riverNone && <ResponsiveContainer width="100%" height={250}><AreaChart data={rows}>
            <CartesianGrid stroke="#e8ecf2" vertical={false} /><XAxis dataKey="date" tickFormatter={tick} fontSize={11} /><YAxis fontSize={11} width={56} unit=" m3/s" />
            <Tooltip formatter={(v) => `${fmt(v, 1)} m3/s`} /><Area dataKey="discharge_m3s" name="Median discharge" stroke="#1f5fbf" fill="#cfe0f7" /></AreaChart></ResponsiveContainer>}
          <p className="small muted">Modelled discharge at one point per district, not a measured gauge level. Regions with several districts show the median.</p>
        </Box>
      </div>
      <Box title="Risk factor contribution">
        <Status s={warn} empty={W && !W.contributions ? "Contribution data unavailable." : null} />
        {W?.contributions && W.contributions.map((c) => <div className="bar" key={c.key}><span>{c.factor}</span>
          <div><i style={{ width: `${c.percent}%` }} /></div><b>{fmt(c.percent, 0)}%</b></div>)}
        <p className="small muted">Share of the analytical score on the as-of date, using weights learned from 2000-2012 data. Humidity acts as a wet-season proxy, so read it as such.</p>
      </Box>
    </>
  );
}
