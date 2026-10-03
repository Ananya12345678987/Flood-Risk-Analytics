import { useState } from "react";
import { useFilters } from "../filters";
import { Box } from "../ui";
import { RiskMap } from "../ui";

export default function MapView() {
  const { applied } = useFilters();
  const [mode, setMode] = useState("district");
  if (!applied) return <p className="muted">Loading...</p>;
  const toggle = <div className="seg">{[["state", "State view"], ["district", "District view"]].map(([k, l]) => <button key={k} className={mode === k ? "on" : ""} onClick={() => setMode(k)}>{l}</button>)}</div>;
  return (
    <Box title={`Warning level by ${mode}, ${applied.end}`} right={toggle}>
      <RiskMap applied={applied} mode={mode} height={560} />
      <p className="small muted">{mode === "state" ? "State view shows India's state outlines; only the four pilot states have risk data, the rest are grey. A state takes the highest level among its districts."
        : "District view covers the pilot states. Use the filters above to focus on one state or district. Boundaries are Census 2011 districts and are approximate; newer districts sit inside their 2011 parent."} The map shows the warning level for the as-of date in the filter bar.</p>
    </Box>
  );
}
