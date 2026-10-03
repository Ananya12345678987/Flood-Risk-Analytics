"""Spark job 1: cell-level daily rainfall -> district daily rainfall + rolling features.

Big-data operations used: Parquet read with partition discovery, broadcast join,
groupBy/agg, calendar cross-join (gap handling), window functions (rolling sums),
climatology via groupBy + stddev, Spark SQL sanity queries, partitioned Parquet write.
"""
import sys, time
sys.path.insert(0, ".")
from pyspark.sql import functions as F, Window
from spark.config.session import get_spark

CLIM_END_YEAR = 2015     # climatology baseline 2000-2015 only (avoids leaking test-period info)
HEAVY_MM = 64.5          # IMD 'heavy rain' lower bound (mm/day)

spark = get_spark("district_rainfall")
print("Spark", spark.version)
t0 = time.time()

cells = spark.read.parquet("data/processed/rain_cells").withColumn("date", F.to_date("date"))
mapping = (spark.read.csv("data/processed/cell_district.csv", header=True, inferSchema=True)
           .select("cell_id", "district_id", "state", "district"))
print("cell-day rows read:", f"{cells.count():,}")

# 1) join each grid cell to its district (small table -> broadcast, no shuffle of the big side)
joined = cells.join(F.broadcast(mapping), "cell_id")

# 2) district-day aggregation
daily = (joined.groupBy("district_id", "state", "district", "date")
         .agg(F.avg("rain_mm").alias("rain_mean_mm"),
              F.max("rain_mm").alias("rain_max_cell_mm"),
              F.count("*").alias("n_cells"),
              F.avg((F.col("rain_mm") >= HEAVY_MM).cast("double")).alias("heavy_cell_frac")))

# 3) full calendar x district grid, so rolling windows are contiguous even if a day is missing
dates = spark.sql("SELECT explode(sequence(to_date('2000-01-01'), to_date('2023-12-31'), "
                  "interval 1 day)) AS date")
dists = daily.select("district_id", "state", "district").distinct()
grid = (dists.crossJoin(dates)
        .join(daily.select("district_id", "date", "rain_mean_mm", "rain_max_cell_mm",
                           "n_cells", "heavy_cell_frac"), ["district_id", "date"], "left"))
grid = grid.cache()      # reused several times below (count, windows, climatology)
n_missing = grid.filter(F.col("rain_mean_mm").isNull()).count()
print("district-days with no rainfall value (kept as null):", n_missing)

# 4) rolling accumulations with window functions
w = Window.partitionBy("district_id").orderBy("date")


def rolling_sum(k):
    s = F.sum("rain_mean_mm").over(w.rowsBetween(-(k - 1), 0))
    return F.when(F.row_number().over(w) >= k, s)       # null until a full window exists


m = F.month("date")
feat = (grid
        .withColumn("rain_1d_mm", F.col("rain_mean_mm"))
        .withColumn("rain_3d_mm", rolling_sum(3))
        .withColumn("rain_7d_mm", rolling_sum(7))
        .withColumn("rain_30d_mm", rolling_sum(30))
        .withColumn("month", m)
        .withColumn("season", F.when(m.isin(1, 2), "winter").when(m.isin(3, 4, 5), "pre-monsoon")
                              .when(m.isin(6, 7, 8, 9), "monsoon").otherwise("post-monsoon")))

# 5) anomaly vs per-district, per-month climatology (baseline years only)
clim = (feat.filter(F.year("date") <= CLIM_END_YEAR)
        .groupBy("district_id", "month")
        .agg(F.avg("rain_7d_mm").alias("c7_mean"), F.stddev("rain_7d_mm").alias("c7_std"),
             F.avg("rain_30d_mm").alias("c30_mean"), F.stddev("rain_30d_mm").alias("c30_std")))
feat = (feat.join(clim, ["district_id", "month"], "left")
        .withColumn("rain_7d_anomaly_z", F.when(F.col("c7_std") > 0, (F.col("rain_7d_mm") - F.col("c7_mean")) / F.col("c7_std")))
        .withColumn("rain_30d_anomaly_z", F.when(F.col("c30_std") > 0, (F.col("rain_30d_mm") - F.col("c30_mean")) / F.col("c30_std")))
        .drop("c7_mean", "c7_std", "c30_mean", "c30_std")
        .withColumn("year", F.year("date")))

# 6) write partitioned Parquet
out = "data/processed/rainfall_district_daily"
feat.write.mode("overwrite").partitionBy("year").parquet(out)
print(f"written {out} in {time.time()-t0:.0f}s")

# ---- verification with Spark SQL ----
res = spark.read.parquet(out)
res.createOrReplaceTempView("rain")
print("\nrows:", f"{res.count():,}", "| districts:", res.select('district_id').distinct().count())
res.agg(F.min("date"), F.max("date")).show()

print("Top 8 district-days by mean rainfall (sanity check - are these plausible events?):")
spark.sql("""SELECT state, district, date, ROUND(rain_mean_mm,1) AS rain_mean_mm,
                    ROUND(rain_max_cell_mm,1) AS max_cell_mm
             FROM rain ORDER BY rain_mean_mm DESC LIMIT 8""").show(truncate=False)

print("Mean annual rainfall by state (mm/yr) - highest and lowest (sanity check):")
ann = spark.sql("""SELECT state, ROUND(SUM(rain_mean_mm)/24,0) AS mm_per_year FROM
                   (SELECT state, district_id, rain_mean_mm FROM rain) GROUP BY state""")
# note: sum over districts double-counts; divide by district count for a state mean
cnt = spark.sql("SELECT state, COUNT(DISTINCT district_id) AS nd FROM rain GROUP BY state")
st = ann.join(cnt, "state").withColumn("mm_per_year_state_mean", F.round(F.col("mm_per_year") / F.col("nd"), 0))
st.select("state", "mm_per_year_state_mean").orderBy(F.desc("mm_per_year_state_mean")).show(6, truncate=False)
st.select("state", "mm_per_year_state_mean").orderBy("mm_per_year_state_mean").show(6, truncate=False)

print("Null counts in key features:")
res.select([F.sum(F.col(c).isNull().cast("int")).alias(c) for c in
            ["rain_1d_mm", "rain_3d_mm", "rain_7d_mm", "rain_30d_mm", "rain_7d_anomaly_z"]]).show()
print(f"total time {time.time()-t0:.0f}s")
spark.stop()
