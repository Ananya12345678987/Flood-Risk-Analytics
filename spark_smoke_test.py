from pyspark.sql import SparkSession

spark = (SparkSession.builder.appName("smoke_test").master("local[2]")
         .config("spark.driver.memory", "3g")
         .config("spark.sql.shuffle.partitions", "8")
         .config("spark.ui.enabled", "false")
         .getOrCreate())
print("Spark version:", spark.version)

df = spark.range(1_000_000).withColumnRenamed("id", "n")
grouped = df.groupBy((df.n % 10).alias("bucket")).count().orderBy("bucket")
print("groupBy result (first 3):", [tuple(r) for r in grouped.collect()[:3]])

df.write.mode("overwrite").parquet("data/tmp_smoke.parquet")
print("Parquet rows read back:", spark.read.parquet("data/tmp_smoke.parquet").count())
spark.stop()
