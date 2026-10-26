"""Load the Low Carbon London half-hourly readings into a Delta table, partitioned by date and clustered by meter.

Source (London Datastore, no sign-in): UK Power Networks "SmartMeter Energy Consumption Data in London Households",
5,566 households, November 2011 to February 2014, the 168-file version.
https://data.london.gov.uk/dataset/smartmeter-energy-consumption-data-in-london-households-vqm0d

Cleaning, all counted in data/lake/_load_report.json:
  - kWh "Null" values dropped (5,560 in the full file)
  - duplicate (meter, timestamp) pairs collapsed to one reading, the lower value (115,453 in the full file)
Then `OPTIMIZE ... ZORDER BY (meter_id)` clusters each day's files by meter, so per-meter scans skip most data.

Usage: python ingestion/load_lcl.py --csv "data/raw/Small LCL Data/*.csv" --lake data/lake
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import duckdb
from deltalake import DeltaTable, write_deltalake


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="data/raw/Small LCL Data/*.csv")
    ap.add_argument("--lake", type=Path, default=Path("data/lake"))
    ap.add_argument("--no-optimize", action="store_true")
    args = ap.parse_args()
    target = args.lake / "readings"
    if target.exists():
        shutil.rmtree(target)  # a full reload: the source is a fixed historical release
    args.lake.mkdir(parents=True, exist_ok=True)

    timings, start = {}, time.time()
    con = duckdb.connect()
    con.execute(f"""
        create temp view raw as
        select * from read_csv('{args.csv}', all_varchar = true, header = true,
                               names = ['meter_id', 'tariff', 'ts', 'kwh'])
    """)
    raw_rows, nulls = con.execute(
        "select count(*), count(*) filter (where trim(kwh) in ('Null', '')) from raw").fetchone()
    timings["profile_s"] = round(time.time() - start, 1)

    t = time.time()
    # Type first, then de-duplicate with a hash aggregate (cheap), not a window over the whole table, and no
    # global sort: Delta partitions by date and Z-ordering sorts each partition by meter afterwards.
    reader = con.execute("""
        with typed as (
            select meter_id, tariff, cast(substr(ts, 1, 19) as timestamp) as reading_ts, cast(trim(kwh) as double) as kwh
            from raw
            where trim(kwh) not in ('Null', '')
        )
        select meter_id, any_value(tariff) as tariff, reading_ts, cast(reading_ts as date) as reading_date,
               min(kwh) as kwh
        from typed
        group by meter_id, reading_ts
    """).to_arrow_reader(1_000_000)
    write_deltalake(target, reader, partition_by=["reading_date"], mode="overwrite",
                    configuration={"delta.dataSkippingNumIndexedCols": "3"})
    timings["write_delta_s"] = round(time.time() - t, 1)

    table = DeltaTable(target)
    if not args.no_optimize:
        t = time.time()
        metrics = table.optimize.z_order(["meter_id"])
        timings["zorder_s"] = round(time.time() - t, 1)
        timings["zorder_files_added"] = metrics.get("numFilesAdded")
        timings["zorder_files_removed"] = metrics.get("numFilesRemoved")
        table = DeltaTable(target)
    rows = con.execute(f"select count(*) from delta_scan('{target.resolve().as_posix()}')").fetchone()[0] \
        if _has_delta(con) else sum(a.num_rows for a in [table.to_pyarrow_dataset().to_table(columns=["meter_id"])])
    report = {"raw_rows": raw_rows, "null_kwh_dropped": nulls, "duplicates_collapsed": raw_rows - nulls - rows,
              "rows": rows, "version": table.version(), "files": len(table.file_uris()),
              "partitions": len({Path(f).parent.name for f in table.file_uris()}), **timings,
              "total_s": round(time.time() - start, 1)}
    (args.lake / "_load_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report))


def _has_delta(con) -> bool:
    try:
        con.execute("install delta; load delta")
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
