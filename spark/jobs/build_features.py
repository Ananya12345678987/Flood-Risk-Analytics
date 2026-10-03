"""Spark job 2: one analysis-ready (district, day) feature table for the 106 pilot districts.

Operations: broadcast joins on small tables, window functions (lags, rolling counts),
baseline statistics (percentile_approx) from 2000-2015 only, partitioned Parquet write,
Spark SQL checks. Baselines use only years <= BASE_END to limit leakage into the test period.
"""
import sys, time
sys.path.insert(0, ".")
from pyspark.sql import functions as F, Window
from spark.config.session import get_spark

BASE_END = 2015
spark = get_spark("feature_table")
t0 = time.time()
P = "data/processed/"

pilot = spark.read.csv(P + "districts_pilot.csv", header=True, inferSchema=True).select("district_id")
rain = spark.read.parquet(P + "rainfall_district_daily").join(F.broadcast(pilot), "district_id")
weather = spark.read.parquet(P + "weather_daily.parquet").withColumn("date", F.to_date("date"))
river = spark.read.parquet(P + "river_daily.parquet").withColumn("date", F.to_date("date"))
labels = spark.read.parquet(P + "flood_labels_daily.parquet").withColumn("date", F.to_date("date"))
elev = (spark.read.csv(P + "district_elevation.csv", header=True, inferSchema=True)
        .select("district_id", "elev_mean_m", "elev_min_m", "elev_max_m", "elev_std_m", "relief_m"))
tiers = spark.read.csv(P + "river_tiers.csv", header=True, inferSchema=True).select("district_id", "river_tier")

df = (rain.join(weather, ["district_id", "date"], "left")
          .join(river, ["district_id", "date"], "left")
          .join(labels, ["district_id", "date"], "left")
          .join(F.broadcast(elev), "district_id", "left")
          .join(F.broadcast(tiers), "district_id", "left"))

w = Window.partitionBy("district_id").orderBy("date")

# ---- weather change features (surface pressure: only its CHANGE is comparable across districts)
df = (df.withColumn("pressure_change_1d_kpa", F.col("pressure_kpa") - F.lag("pressure_kpa", 1).over(w))
        .withColumn("pressure_change_3d_kpa", F.col("pressure_kpa") - F.lag("pressure_kpa", 3).over(w)))

# ---- river features, relative to each district's own 2000-2015 history
base = (df.filter(F.col("year") <= BASE_END).groupBy("district_id")
          .agg(F.percentile_approx("discharge_m3s", 0.5).alias("q50"),
               F.percentile_approx("discharge_m3s", 0.95).alias("q95")))
df = df.join(F.broadcast(base), "district_id", "left")
river_ok = F.col("river_tier").isin("minor", "major")


def pct_change(col, k):
    prev = F.lag(col, k).over(w)
    return F.when(river_ok & (prev > 0), (col - prev) / prev)


Q = F.col("discharge_m3s")
df = (df.withColumn("discharge_ratio_to_median", F.when(river_ok & (F.col("q50") > 0), Q / F.col("q50")))
        .withColumn("discharge_above_p95", F.when(river_ok & F.col("q95").isNotNull(), (Q > F.col("q95")).cast("int")))
        .withColumn("discharge_change_1d_pct", pct_change(Q, 1))
        .withColumn("discharge_change_3d_pct", pct_change(Q, 3))
        .drop("q50", "q95"))

# ---- labels and flood history (history uses ONLY earlier days -> no leakage)
df = (df.withColumn("flood_onset", (F.col("label_status") == "onset").cast("int"))
        .withColumn("flood_onset", F.coalesce(F.col("flood_onset"), F.lit(0)))
        .withColumn("label_status", F.coalesce(F.col("label_status"), F.lit("normal")))
        .withColumn("ml_usable", ~F.col("label_status").isin("ongoing", "ambiguous")))
rn = F.row_number().over(w)
df = df.withColumn("onsets_prev_3y",
                   F.when(rn > 1095, F.sum("flood_onset").over(w.rowsBetween(-1095, -1))))

out = P + "features_daily"
df.write.mode("overwrite").partitionBy("year").parquet(out)
print(f"written {out} in {time.time()-t0:.0f}s")

# ---------------------------------------------------------------- checks
res = spark.read.parquet(out)
res.createOrReplaceTempView("f")
print("\nrows:", f"{res.count():,}", "| districts:", res.select('district_id').distinct().count())

print("\nLabel status counts:")
spark.sql("SELECT label_status, COUNT(*) AS n FROM f GROUP BY label_status ORDER BY n DESC").show()

print("Positive rate among ML-usable days:")
spark.sql("""SELECT COUNT(*) AS usable_days, SUM(flood_onset) AS onsets,
             ROUND(100*SUM(flood_onset)/COUNT(*),3) AS pct FROM f WHERE ml_usable""").show()

print("FIRST SIGNAL CHECK - rainfall on flood-onset days vs normal days (usable days only):")
spark.sql("""SELECT flood_onset, COUNT(*) AS n,
             ROUND(AVG(rain_1d_mm),1) AS rain_1d, ROUND(AVG(rain_3d_mm),1) AS rain_3d,
             ROUND(AVG(rain_7d_mm),1) AS rain_7d, ROUND(AVG(rain_7d_anomaly_z),2) AS z7,
             ROUND(AVG(humidity_pct),1) AS humidity, ROUND(AVG(pressure_change_3d_kpa),3) AS dP3
             FROM f WHERE ml_usable GROUP BY flood_onset ORDER BY flood_onset""").show()

print("River signal (minor+major river districts only):")
spark.sql("""SELECT flood_onset, COUNT(*) AS n, ROUND(AVG(discharge_ratio_to_median),2) AS ratio_to_median,
             ROUND(AVG(discharge_above_p95),3) AS frac_above_p95, ROUND(AVG(discharge_change_3d_pct),3) AS chg3d
             FROM f WHERE ml_usable AND river_tier IN ('minor','major')
             GROUP BY flood_onset ORDER BY flood_onset""").show()

print("Onsets per year among usable days:")
spark.sql("SELECT year, SUM(flood_onset) AS onsets FROM f WHERE ml_usable GROUP BY year ORDER BY year").show(24)

print("Highest 7-day rainfall anomalies and what the flood record says:")
spark.sql("""SELECT district_id, date, ROUND(rain_7d_mm,0) AS rain_7d, ROUND(rain_7d_anomaly_z,1) AS z7, label_status
             FROM f WHERE rain_7d_anomaly_z IS NOT NULL ORDER BY rain_7d_anomaly_z DESC LIMIT 10""").show(truncate=False)

print("Null counts:")
cols = ["rain_1d_mm", "rain_30d_mm", "rain_7d_anomaly_z", "temp_c", "humidity_pct", "pressure_change_3d_kpa",
        "discharge_m3s", "discharge_ratio_to_median", "discharge_change_3d_pct", "elev_mean_m", "onsets_prev_3y"]
res.select([F.sum(F.col(c).isNull().cast("int")).alias(c) for c in cols]).show(truncate=False)
print(f"total {time.time()-t0:.0f}s")
spark.stop()
