import { Box } from "../ui";
import { useFilters } from "../filters";

const Sec = ({ t, children }) => <Box title={t}>{children}</Box>;

export default function About() {
  const { meta } = useFilters();
  return (
    <>
      <Sec t="What this system is">
        <p>An early-warning <b>decision-support</b> prototype that estimates flood-risk indications for 106 districts in Assam, Kerala, Karnataka and Maharashtra from 24 years (2000-2023) of rainfall, weather, modelled river discharge and recorded flood events. It does not predict floods and is not an official warning.</p>
      </Sec>
      <Sec t="Pipeline">
        <ol className="reasons"><li><b>Ingest:</b> IMD rainfall grids (about 40.6 million cell-day values), NASA POWER weather, GloFAS discharge, flood inventory, district boundaries.</li>
          <li><b>PySpark (local mode, 2 threads, 3 GB):</b> grid cells joined to districts, daily aggregation, rolling 3/7/30-day rainfall with window functions, anomalies against a 2000-2015 baseline, feature table, dashboard analytics.</li>
          <li><b>Parquet:</b> compact columnar storage between stages.</li>
          <li><b>Risk model:</b> five-component analytical score plus a gradient-boosting classifier, evaluated on years the model never saw.</li>
          <li><b>FastAPI</b> serves precomputed tables; <b>React</b> shows them. Spark is not needed at serving time.</li></ol>
      </Sec>
      <Sec t="How the risk score works">
        <p>Each component (3-day rainfall, river discharge relative to the district's own median, flood history in the previous 3 years, low elevation, humidity) is converted to a percentile against 2000-2012. Weights come from a non-negative logistic regression on that period, not from opinion. Classes use percentile cut-offs on 2013-2015 (MEDIUM from the 90th, HIGH from the 98th). These are not official thresholds.</p>
        <p>Warning levels: <b>HIGH RISK</b> = HIGH class plus ML HIGH or discharge above the district's own 95th percentile; <b>ALERT</b> = HIGH on score or ML; <b>WATCH</b> = MEDIUM on either; otherwise <b>NORMAL</b>. Reasons are generated from the actual values for the selected date.</p>
      </Sec>
      <Sec t="Machine learning, honestly">
        <p>Target: a <i>recorded</i> flood onset in a district on a day. Split by time: fit 2000-2012, tune 2013-2015, test 2016-2020. Flood onsets are rare (about 0.5% of days), so accuracy is meaningless and precision-recall and lift are reported. Performance is moderate: useful for ranking days, with many false alarms.</p>
      </Sec>
      <Sec t="Known limitations">
        <ul className="reasons"><li>River data is modelled (GloFAS) at one point per district; not a measured gauge level, and several districts have no meaningful river.</li>
          <li>Flood events are reported events: no severity or coordinates, large known floods are stored as long records excluded from training, and 2021 onward is recorded one district per row.</li>
          <li>Rainfall is a 25 km grid, so small districts have 1-2 cells; weather is about 50 km.</li>
          <li>District boundaries are Census 2011; newer districts are attributed to their parent. A few name matches are approximations.</li>
          <li>Data ends December 2023, so the dashboard replays history and is not live. IMD rain days may end at 08:30 the next morning, so event timing can be off by a day.</li>
          <li>Feature importance shows what the model uses, not causes. Humidity probably acts as a wet-season proxy.</li></ul>
      </Sec>
      <Sec t="Data sources">
        <table><thead><tr><th>Variable</th><th>Source</th><th>Nature</th></tr></thead><tbody>{meta.data?.sources.map((s) => <tr key={s.variable}><td>{s.variable}</td><td>{s.source}</td><td>{s.type}</td></tr>)}</tbody></table>
      </Sec>
    </>
  );
}
