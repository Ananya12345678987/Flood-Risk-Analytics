"""Spark job 3: finalise features (robust anomaly) + seasonal-fairness and label-shift checks."""
import sys, time
sys.path.insert(0, ".")
from pyspark.sql import functions as F
from spark.config.session import get_spark

BASE_END = 2015
FLOOR_7D_MM, FLOOR_30D_MM = 10.0, 25.0     # judgement floors on climatological std (mm)
P = "data/processed/"
spark = get_spark("finalize_features")
t0 = time.time()

df = spark.read.parquet(P + "features_daily")
base = (df.filter(F.col("year") <= BASE_END).groupBy("district_id", "month")
          .agg(F.avg("rain_7d_mm").alias("m7"), F.stddev("rain_7d_mm").alias("s7"),
               F.avg("rain_30d_mm").alias("m30"), F.stddev("rain_30d_mm").alias("s30")))
df = (df.drop("rain_7d_anomaly_z", "rain_30d_anomaly_z")
        .join(base, ["district_id", "month"], "left")
        .withColumn("rain_7d_anomaly_z", (F.col("rain_7d_mm") - F.col("m7")) /
                    F.greatest(F.coalesce(F.col("s7"), F.lit(0.0)), F.lit(FLOOR_7D_MM)))
        .withColumn("rain_30d_anomaly_z", (F.col("rain_30d_mm") - F.col("m30")) /
                    F.greatest(F.coalesce(F.col("s30"), F.lit(0.0)), F.lit(FLOOR_30D_MM)))
        .drop("m7", "s7", "m30", "s30"))

out = P + "features_model"
df.write.mode("overwrite").partitionBy("year").parquet(out)
print(f"written {out} in {time.time()-t0:.0f}s")

m = spark.read.parquet(out)
m.createOrReplaceTempView("m")

print("\n1) Highest 7-day anomalies after the std floor:")
spark.sql("""SELECT district_id, date, ROUND(rain_7d_mm,0) AS rain_7d, ROUND(rain_7d_anomaly_z,1) AS z7, label_status
             FROM m WHERE rain_7d_anomaly_z IS NOT NULL ORDER BY rain_7d_anomaly_z DESC LIMIT 8""").show(truncate=False)

print("2) Where do flood onsets fall in the year? (usable days)")
spark.sql("""SELECT season, COUNT(*) AS days, SUM(flood_onset) AS onsets,
             ROUND(100*SUM(flood_onset)/(SELECT SUM(flood_onset) FROM m WHERE ml_usable),1) AS pct_of_all_onsets,
             ROUND(100*SUM(flood_onset)/COUNT(*),3) AS onset_rate_pct
             FROM m WHERE ml_usable GROUP BY season ORDER BY onsets DESC""").show(truncate=False)

print("3) MONSOON DAYS ONLY (Jun-Sep): onset vs non-onset - fairer than the all-year comparison")
spark.sql("""SELECT flood_onset, COUNT(*) AS n, ROUND(AVG(rain_1d_mm),1) AS rain_1d, ROUND(AVG(rain_3d_mm),1) AS rain_3d,
             ROUND(AVG(rain_7d_mm),1) AS rain_7d, ROUND(AVG(rain_7d_anomaly_z),2) AS z7,
             ROUND(AVG(humidity_pct),1) AS humidity, ROUND(AVG(pressure_change_3d_kpa),3) AS dP3
             FROM m WHERE ml_usable AND month BETWEEN 6 AND 9 GROUP BY flood_onset ORDER BY flood_onset""").show()

print("4) Onset rate by 3-day rainfall band, split by era (checks the 2021+ recording shift):")
spark.sql("""SELECT CASE WHEN rain_3d_mm < 10 THEN '1: <10 mm' WHEN rain_3d_mm < 25 THEN '2: 10-25'
                  WHEN rain_3d_mm < 50 THEN '3: 25-50' WHEN rain_3d_mm < 100 THEN '4: 50-100' ELSE '5: 100+' END AS rain_3d_band,
             CASE WHEN year <= 2020 THEN 'A: 2000-2020' ELSE 'B: 2021-2023' END AS era,
             COUNT(*) AS days, SUM(flood_onset) AS onsets,
             ROUND(100*SUM(flood_onset)/COUNT(*),2) AS onset_rate_pct
             FROM m WHERE ml_usable AND rain_3d_mm IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2""").show(20, truncate=False)

print("5) Monsoon onset rate by state:")
spark.sql("""SELECT state, COUNT(*) AS days, SUM(flood_onset) AS onsets,
             ROUND(100*SUM(flood_onset)/COUNT(*),2) AS onset_rate_pct
             FROM m WHERE ml_usable AND month BETWEEN 6 AND 9 GROUP BY state ORDER BY onset_rate_pct DESC""").show()
print(f"total {time.time()-t0:.0f}s")
spark.stop()
