"""Run after spark/meter_jobs.py (CI): the Spark outputs must equal dbt's to the watt-hour."""
from __future__ import annotations

import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = os.environ.get("METERS_DB", str(ROOT / "warehouse" / "fixture.duckdb"))
LAKE = Path(os.environ.get("METERS_LAKE", ROOT / "data" / "fixture" / "lake")).resolve().as_posix()


def con():
    c = duckdb.connect(DB, read_only=True)
    c.execute("install delta; load delta")
    return c


def test_daily_metered_energy_matches():
    diff, rows = con().execute(f"""
        select sum(abs(s.metered_kwh - d.metered_kwh)), count(*)
        from delta_scan('{LAKE}/spark_metered_daily') s
        join silver.sim_meter_daily_metered d using (meter_id, reading_date)
    """).fetchone()
    total = con().execute("select count(*) from silver.sim_meter_daily_metered").fetchone()[0]
    assert rows == total and diff < 0.001


def test_weekly_gap_matches():
    diff, rows = con().execute(f"""
        select sum(abs(s.gap_kwh - d.gap_kwh)), count(*)
        from delta_scan('{LAKE}/spark_meter_weekly') s
        join gold.fct_meter_weekly d using (meter_id, week_start)
    """).fetchone()
    assert rows == con().execute("select count(*) from gold.fct_meter_weekly").fetchone()[0] and diff < 0.001


def test_feeder_losses_match():
    diff = con().execute(f"""
        select max(abs(s.loss_share - d.loss_share))
        from delta_scan('{LAKE}/spark_feeder_weekly') s
        join gold.rpt_feeder_losses d using (feeder_id, week_start)
    """).fetchone()[0]
    assert diff < 1e-9
