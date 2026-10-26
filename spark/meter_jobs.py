"""The same meter pipeline as dbt, as Spark jobs on the Delta lake, with timings:

  1. metered_daily   real half-hourly readings -> what each meter reports per day (tampering applied)
  2. meter_weekly    weekly metered energy, prepaid purchases and the gap
  3. feeder_weekly   feeder supply vs metered energy, loss share

Outputs go to Delta tables data/lake/spark_*; timings to results/spark_timings.json. CI runs this on the fixture
and checks the results equal dbt's, and on a 20M-row sample of the real data for the timings.

Usage: python spark/meter_jobs.py --lake data/lake --out results/spark_timings.json
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def spark_session() -> SparkSession:
    builder = (SparkSession.builder.appName("smart-meter-revenue-protection")
               .master(os.environ.get("SPARK_MASTER", "local[*]"))
               .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
               .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
               .config("spark.sql.session.timeZone", "UTC")
               .config("spark.sql.shuffle.partitions", os.environ.get("SPARK_SHUFFLE_PARTITIONS", "64"))
               .config("spark.driver.memory", os.environ.get("SPARK_DRIVER_MEMORY", "6g")))
    return configure_spark_with_delta_pip(builder).getOrCreate()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lake", type=Path, default=Path("data/lake"))
    ap.add_argument("--out", type=Path, default=Path("results/spark_timings.json"))
    args = ap.parse_args()
    lake = str(args.lake.resolve())
    spark = spark_session()
    read = lambda name: spark.read.format("delta").load(f"{lake}/{name}")
    timings: dict[str, float] = {}

    def run(name: str, df):
        t = time.time()
        df.write.format("delta").mode("overwrite").save(f"{lake}/spark_{name}")
        timings[f"{name}_s"] = round(time.time() - t, 1)
        return read(f"spark_{name}")

    readings, tamper = read("readings"), read("sim_tamper")
    timings["input_rows"] = readings.count()
    hour = F.hour("reading_ts")
    on = F.col("start_date").isNotNull() & (F.col("reading_date") >= F.col("start_date"))
    metered = (readings.join(F.broadcast(tamper), "meter_id", "left")
               .withColumn("kwh", F.when(~on, F.col("kwh"))
                           .when(F.col("tamper_type") == "bypass", F.col("kwh") * F.col("factor"))
                           .when(F.col("tamper_type") == "flatline", F.col("flat_kwh"))
                           .when((F.col("tamper_type") == "night_bypass") & (hour < 6), F.lit(0.0))
                           .otherwise(F.col("kwh"))))
    daily = run("metered_daily", metered.groupBy("meter_id", "reading_date").agg(
        F.count("*").alias("readings"), F.sum("kwh").alias("metered_kwh"),
        F.sum(F.when(hour < 6, F.col("kwh"))).alias("metered_night_kwh"),
        F.countDistinct(F.round("kwh", 3)).alias("distinct_values")))

    meters = read("sim_meters")
    week = lambda c: F.to_date(F.date_trunc("week", F.col(c)))
    weekly_metered = (daily.join(F.broadcast(meters), "meter_id")
                      .groupBy("meter_id", "feeder_id", week("reading_date").alias("week_start"))
                      .agg(F.sum("metered_kwh").alias("metered_kwh")))
    bought = (read("sim_vends").groupBy("meter_id", week("vend_ts").alias("week_start"))
              .agg(F.sum("kwh").alias("purchased_kwh")))
    weekly = run("meter_weekly", weekly_metered.join(bought, ["meter_id", "week_start"], "left")
                 .fillna({"purchased_kwh": 0.0})
                 .withColumn("gap_kwh", F.col("metered_kwh") - F.col("purchased_kwh")))

    supply = (read("sim_feeder_supply").groupBy("feeder_id", week("supply_date").alias("week_start"))
              .agg(F.sum("supply_kwh").alias("supply_kwh")))
    feeder_metered = weekly.groupBy("feeder_id", "week_start").agg(F.sum("metered_kwh").alias("metered_kwh"))
    run("feeder_weekly", supply.join(feeder_metered, ["feeder_id", "week_start"])
        .withColumn("loss_share", (F.col("supply_kwh") - F.col("metered_kwh")) / F.col("supply_kwh")))

    timings["cores"] = spark.sparkContext.defaultParallelism
    timings["spark_version"] = spark.version
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(timings, indent=1))
    print(json.dumps(timings))
    spark.stop()


if __name__ == "__main__":
    main()
