import { useEffect, useMemo } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { GeoJSON, MapContainer, useMap } from "react-leaflet";
import { LEVEL_COLOR, useApi } from "./api";

export const Box = ({ title, children, right, cls = "" }) => <section className={`card ${cls}`}><div className="card-h"><h2>{title}</h2>{right}</div>{children}</section>;
export const Status = ({ s, empty }) => (s.loading ? <p className="muted">Loading...</p> : s.error ? <p className="error-text">{s.error}</p> : empty ? <p className="muted">{empty}</p> : null);
export const Badge = ({ level }) => <span className="badge" style={{ background: LEVEL_COLOR[level] || "#eee" }}>{level}</span>;
export const Legend = () => <div className="legend">{Object.entries(LEVEL_COLOR).map(([k, c]) => <span key={k}><i style={{ background: c }} />{k}</span>)}</div>;

function Fit({ data }) {
  const map = useMap();
  useEffect(() => { const b = L.geoJSON(data).getBounds(); if (b.isValid()) map.fitBounds(b, { padding: [8, 8] }); }, [data]);
  return null;
}

// mode "district" = pilot districts coloured by warning level; mode "state" = all-India outlines, pilot states coloured.
export function RiskMap({ applied, mode = "district", height = 340 }) {
  const geo = useApi(`geo/${mode === "state" ? "states" : "districts"}`);
  const risk = useApi("map", { date: applied.end, level: mode });
  const key = mode === "state" ? "state" : "district_id";
  const byId = useMemo(() => Object.fromEntries((risk.data?.rows || []).map((r) => [r[key], r])), [risk.data, key]);
  const shown = useMemo(() => {
    if (!geo.data) return null;
    if (mode === "state") return geo.data;
    const keep = (f) => (applied.district ? f.properties.district_id === applied.district : !applied.state || f.properties.state === applied.state);
    return { type: "FeatureCollection", features: geo.data.features.filter(keep) };
  }, [geo.data, mode, applied.state, applied.district]);
  const idOf = (f) => (mode === "state" ? f.properties.ST_NM : f.properties.district_id);
  const style = (f) => ({ color: "#5b6b82", weight: 0.8, fillOpacity: 0.85, fillColor: LEVEL_COLOR[byId[idOf(f)]?.level] || "#e9edf3" });
  const tip = (f, layer) => {
    const r = byId[idOf(f)];
    const name = mode === "state" ? f.properties.ST_NM : `${f.properties.district} (${f.properties.state})`;
    const body = !r ? "no risk data (outside the 4 pilot states)" : mode === "state" ? `${r.level}; ${r.n_flagged} of ${r.n_districts} districts at ALERT or above` : `${r.level}, score ${Math.round(r.risk_score)}`;
    layer.bindTooltip(`${name}<br/>${body}`);
  };
  return (
    <>
      <Status s={geo.error ? geo : risk} empty={shown && !shown.features.length ? "No boundaries for this selection." : null} />
      {shown && <div className="map" style={{ height }}><MapContainer center={[22, 80]} zoom={4} scrollWheelZoom={false} zoomSnap={0.25} style={{ height: "100%", background: "#eef2f7" }}>
        <GeoJSON key={`${mode}-${applied.end}-${applied.state}-${applied.district}-${risk.data ? 1 : 0}`} data={shown} style={style} onEachFeature={tip} />
        <Fit data={shown} /></MapContainer></div>}
      <Legend />
    </>
  );
}
