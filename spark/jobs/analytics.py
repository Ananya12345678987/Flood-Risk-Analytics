"""Spark job 4: dashboard analytics tables + event-timing (lead/lag) check."""
import sys, time
from pathlib import Path
sys.path.insert(0, ".")
import pandas as pd
from pyspark.sql import functions as F, Window
from spark.config.session import get_spark

P = "data/processed/"
A = P + "analytics/"
Path(A).mkdir(parents=True, exist_ok=True)
HEAVY_MM = 64.5          # IMD 'heavy rain' lower bound; applied to single grid cells here
R_CRIT_24 = 0.404        # approx. critical |r| for n=24 at 5% (ignores autocorrelation)
spark = get_spark("analytics")
t0 = time.time()


def save_small(sdf, name):
    pdf = sdf.toPandas()
    pdf.to_csv(A + name + ".csv", index=False)
    print(f"  saved {name}.csv ({len(pdf):,} rows)", flush=True)
    return pdf


# ---------------------------------------------------------------- rainfall (India-wide, 636 districts)
rain = spark.read.parquet(P + "rainfall_district_daily").withColumn("year", F.col("year").cast("int"))
monthly = (rain.groupBy("district_id", "state", "district", "year", "month")
           .agg(F.sum("rain_mean_mm").alias("rain_total_mm"),
                F.max("rain_mean_mm").alias("rain_max_day_mm"),
                F.sum((F.col("rain_max_cell_mm") >= HEAVY_MM).cast("int")).alias("heavy_cell_days"),
                F.count("rain_mean_mm").alias("days_with_data")))
monthly.write.mode("overwrite").parquet(A + "rain_monthly")
monthly = spark.read.parquet(A + "rain_monthly").cache()
print("rain_monthly rows:", f"{monthly.count():,}")

annual = (monthly.groupBy("district_id", "state", "district", "year")
          .agg(F.sum("rain_total_mm").alias("annual_mm"),
               F.sum(F.when(F.col("month").between(6, 9), F.col("rain_total_mm")).otherwise(0.0)).alias("monsoon_mm"),
               F.sum("heavy_cell_days").alias("heavy_cell_days")))
trend = (annual.groupBy("district_id", "state", "district")
         .agg(F.avg("annual_mm").alias("mean_annual_mm"),
              (F.covar_samp("year", "annual_mm") / F.var_samp("year")).alias("annual_trend_mm_per_yr"),
              (F.covar_samp("year", "monsoon_mm") / F.var_samp("year")).alias("monsoon_trend_mm_per_yr"),
              F.corr("year", "annual_mm").alias("trend_r")))
tp = save_small(trend, "rain_trend_district")
tp["trend_significant_5pct"] = tp["trend_r"].abs() > R_CRIT_24
tp.to_csv(A + "rain_trend_district.csv", index=False)
save_small(annual, "rain_annual_district")
save_small(monthly.groupBy("state", "month").agg(F.avg("rain_total_mm").alias("mean_monthly_mm")), "rain_climatology_state")

# ---------------------------------------------------------------- pilot features
feat = spark.read.parquet(P + "features_model").withColumn("year", F.col("year").cast("int"))
save_small(feat.groupBy("district_id", "month")
           .agg(F.avg("temp_c").alias("temp_c"), F.avg("humidity_pct").alias("humidity_pct"),
                F.avg("pressure_kpa").alias("pressure_kpa"), F.avg("wind_ms").alias("wind_ms")),
           "weather_climatology_district")
save_small(feat.groupBy("district_id", "state", "year")
           .agg(F.sum("flood_onset").alias("onsets"),
                F.sum((F.col("label_status") == "ambiguous").cast("int")).alias("ambiguous_days")),
           "flood_freq_district_year")
save_small(feat.groupBy("state", "month").agg(F.sum("flood_onset").alias("onsets")), "flood_freq_state_month")

# ---------------------------------------------------------------- rainfall -> river relationship
w = Window.partitionBy("district_id").orderBy("date")
rv = (feat.select("district_id", "state", "date", "month", "river_tier", "rain_1d_mm", "discharge_m3s")
          .filter(F.col("river_tier").isin("minor", "major"))
          .withColumn("lq", F.log1p("discharge_m3s")))
for k in range(5):
    e = F.col("rain_1d_mm") if k == 0 else F.lag("rain_1d_mm", k).over(w)
    rv = rv.withColumn(f"lag{k}", F.log1p(e))
rv = rv.filter(F.col("month").between(6, 9))
cor = rv.groupBy("district_id", "state", "river_tier").agg(
    *[F.corr("lq", f"lag{k}").alias(f"corr_lag{k}") for k in range(5)])
cp = save_small(cor, "rain_river_corr")
print("\nRain -> river discharge: median correlation across river districts (monsoon, log scale)")
print("  by rainfall lag in days (0 = same day):")
print(cp[[f"corr_lag{k}" for k in range(5)]].median().round(3).to_string())

# ---------------------------------------------------------------- TIMING CHECK around recorded onsets
offs = [2, 1, 0, -1, -2, -3, -4, -5, -6, -7]      # rainfall day relative to onset date; + = AFTER onset
ev = feat.select("district_id", "date", "month", "flood_onset", "ml_usable", "rain_1d_mm")
names = []
for o in offs:
    n = f"off_{o}".replace("-", "m")
    e = F.col("rain_1d_mm") if o == 0 else (F.lead("rain_1d_mm", o).over(w) if o > 0 else F.lag("rain_1d_mm", -o).over(w))
    ev = ev.withColumn(n, e)
    names.append(n)
sel = ev.filter(F.col("ml_usable") & F.col("month").between(6, 9))
agg = sel.groupBy("flood_onset").agg(*[F.avg(c).alias(c) for c in names], F.count("*").alias("n"))
tm = agg.toPandas().set_index("flood_onset")
print("\nTIMING CHECK - mean district rainfall (mm/day) on days around the recorded onset date (monsoon, usable):")
print("  rows: onsets =", int(tm.loc[1, "n"]), "| non-onset days =", int(tm.loc[0, "n"]))
tab = tm[names].T
tab.index = offs
tab.columns = ["normal_days", "onset_days"]
tab["ratio"] = (tab.onset_days / tab.normal_days).round(2)
tab = tab.round(2)
tab.index.name = "rain_day_offset (+ = after onset)"
print(tab.to_string())
tab.to_csv(A + "onset_timing_check.csv")

# ---------------------------------------------------------------- summaries to eyeball
print("\nMean annual rainfall and trend, pilot states (mm/yr; trend = mm per year):")
pilot = tp[tp.state.isin(["Assam", "Kerala", "Karnataka", "Maharashtra"])]
print(pilot.groupby("state").agg(mean_annual_mm=("mean_annual_mm", "mean"),
                                 median_trend=("annual_trend_mm_per_yr", "median"),
                                 districts_sig_trend=("trend_significant_5pct", "sum"),
                                 districts=("district_id", "count")).round(1).to_string())
print("\nIndia-wide: districts with a significant (approx.) trend:",
      int(tp.trend_significant_5pct.sum()), "of", len(tp),
      "| increasing:", int(((tp.annual_trend_mm_per_yr > 0) & tp.trend_significant_5pct).sum()),
      "| decreasing:", int(((tp.annual_trend_mm_per_yr < 0) & tp.trend_significant_5pct).sum()))
print(f"\ntotal {time.time()-t0:.0f}s")
spark.stop()
