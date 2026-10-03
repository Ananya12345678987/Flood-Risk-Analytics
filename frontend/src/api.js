import { useEffect, useState } from "react";

export async function get(path, params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  let r;
  try { r = await fetch(`/api/${path}${q ? "?" + q : ""}`); }
  catch { throw new Error("Cannot reach the API. Start it with: uvicorn backend.app.main:app --port 8000"); }
  if (!r.ok) {
    let m = r.statusText;
    try { m = (await r.json()).detail || m; } catch { /* keep status text */ }
    throw new Error(m);
  }
  return r.json();
}

export function useApi(path, params, enabled = true) {
  const [s, set] = useState({ data: null, error: null, loading: enabled });
  const key = JSON.stringify([path, params, enabled]);
  useEffect(() => {
    if (!enabled) return undefined;
    let live = true;
    set((x) => ({ ...x, loading: true, error: null }));
    get(path, params)
      .then((data) => live && set({ data, error: null, loading: false }))
      .catch((e) => live && set({ data: null, error: e.message, loading: false }));
    return () => { live = false; };
  }, [key]);
  return s;
}

export const fmt = (v, d = 0) => (v === null || v === undefined ? "n/a" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d }));
export const LEVEL_COLOR = { NORMAL: "#cfd8e3", WATCH: "#f2c94c", ALERT: "#f2994a", "HIGH RISK": "#d64545" };
