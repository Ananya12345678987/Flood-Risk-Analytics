import os, sys
from pyspark.sql import SparkSession


def get_spark(app="flood-risk", threads=2, driver_mem="3g", shuffle_partitions=8):
    """Laptop-friendly local Spark: 2 threads, 3 GB driver, few shuffle partitions."""
    os.environ["PYSPARK_PYTHON"] = sys.executable          # use the venv's Python
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
    b = (SparkSession.builder.appName(app).master(f"local[{threads}]")
         .config("spark.driver.memory", driver_mem)
         .config("spark.sql.shuffle.partitions", str(shuffle_partitions))
         .config("spark.sql.session.timeZone", "UTC")
         .config("spark.ui.enabled", "false"))
    if os.environ.get("SPARK_LOCAL_DIRS"):
        b = b.config("spark.local.dir", os.environ["SPARK_LOCAL_DIRS"])
    spark = b.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark
