"""SYNTHETIC revenue layer on top of the real Low Carbon London consumption (fixed seed).

The London households are real and honest; this script decides, with a fixed seed, what a prepaid utility would
also see, and plants theft on 3% of meters so detection can be scored. Written as Delta tables in data/lake:

  sim_meters         meter -> feeder (40 feeders by stable hash), tariff (flat 14.228p/kWh, the trial's own)
  sim_tamper         GROUND TRUTH: 3% of meters tampered from a date in March-September 2013, four ways:
                       bypass        metered energy drops to 30-50% of real use (customer buys what's metered)
                       credit_tamper meter is honest, but credit is only paid for ~30% of use (vends fall)
                       flatline      meter reports a constant low value
                       night_bypass  nothing metered from 00:00 to 06:00
  sim_vends          prepaid top-ups: £10-£40 when credit runs low, from METERED use (less, for credit_tamper)
  sim_feeder_supply  energy into each feeder per day: real use of its meters x (1 + 4-7% technical loss) + noise

What a meter REPORTS is applied in dbt (models/simulation), from the real readings and sim_tamper, so the real
data is never rewritten. Detection models read metered data, vends and feeder supply only (lineage-tested).

Usage: python ingestion/simulate.py --lake data/lake
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from deltalake import write_deltalake

SEED = 1717
FEEDERS = 40
TARIFF_P = 14.228  # pence per kWh: the trial's flat tariff
THEFT_SHARE = 0.03
TYPES = ["bypass", "credit_tamper", "flatline", "night_bypass"]


def feeder_of(meter_id: str) -> str:
    return f"F{int(hashlib.md5(meter_id.encode()).hexdigest(), 16) % FEEDERS + 1:02d}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lake", type=Path, default=Path("data/lake"))
    ap.add_argument("--start", default="2013-03-01", help="earliest tamper start")
    ap.add_argument("--end", default="2013-09-30", help="latest tamper start")
    ap.add_argument("--eligible-from", default="2012-10-01", help="tampered meters must report from here...")
    ap.add_argument("--eligible-to", default="2013-12-31", help="...to here")
    args = ap.parse_args()
    rng = np.random.default_rng(SEED)
    t0 = time.time()
    con = duckdb.connect()
    con.execute("install delta; load delta")
    readings = (args.lake / "readings").resolve().as_posix()
    daily = con.execute(f"""
        select meter_id, reading_date as day, sum(kwh) as kwh,
               sum(kwh) filter (where hour(reading_ts) < 6) as night_kwh, avg(kwh) as avg_hh_kwh
        from delta_scan('{readings}')
        group by 1, 2 order by 1, 2
    """).df()
    daily["day"] = pd.to_datetime(daily.day)

    meters = pd.DataFrame({"meter_id": sorted(daily.meter_id.unique())})
    meters["feeder_id"] = meters.meter_id.map(feeder_of)
    meters["tariff_p_per_kwh"] = TARIFF_P

    span = daily.groupby("meter_id").day.agg(["min", "max"])
    eligible = span[(span["min"] <= pd.Timestamp(args.eligible_from))
                    & (span["max"] >= pd.Timestamp(args.eligible_to))].index.to_numpy()
    n_theft = int(round(THEFT_SHARE * len(meters)))
    chosen = rng.choice(eligible, size=min(n_theft, len(eligible)), replace=False)
    starts = pd.Timestamp(args.start) + pd.to_timedelta(
        rng.integers(0, (pd.Timestamp(args.end) - pd.Timestamp(args.start)).days + 1, len(chosen)), unit="D")
    tamper = pd.DataFrame({"meter_id": chosen, "tamper_type": [TYPES[i % 4] for i in range(len(chosen))],
                           "start_date": starts.date})
    base = daily[daily.meter_id.isin(chosen)].groupby("meter_id").avg_hh_kwh.mean()
    tamper["factor"] = np.where(tamper.tamper_type == "bypass", rng.uniform(0.3, 0.5, len(tamper)),
                                np.where(tamper.tamper_type == "credit_tamper", rng.uniform(0.25, 0.35, len(tamper)), 1.0))
    tamper["flat_kwh"] = np.where(tamper.tamper_type == "flatline",
                                  (0.2 * tamper.meter_id.map(base)).round(3), np.nan)

    # metered daily energy, mirroring models/simulation/sim_metered_readings.sql, drives the prepaid vends
    d = daily.merge(tamper, on="meter_id", how="left")
    on = d.start_date.notna() & (d.day >= pd.to_datetime(d.start_date))
    metered = d.kwh.copy()
    metered[on & (d.tamper_type == "bypass")] = (d.kwh * d.factor)[on & (d.tamper_type == "bypass")]
    metered[on & (d.tamper_type == "flatline")] = (d.flat_kwh * 48)[on & (d.tamper_type == "flatline")]
    metered[on & (d.tamper_type == "night_bypass")] = (d.kwh - d.night_kwh.fillna(0))[on & (d.tamper_type == "night_bypass")]
    paid_for = metered.where(~(on & (d.tamper_type == "credit_tamper")), metered * d.factor)
    d["paid_kwh"] = paid_for

    vends = []
    amounts = np.array([10, 15, 20, 25, 30, 40])
    for meter_id, g in d.groupby("meter_id", sort=True):
        credit, threshold = float(rng.uniform(10, 40)), float(rng.uniform(3, 10))
        for day, use in zip(g.day.to_numpy(), g.paid_kwh.to_numpy()):
            credit -= use
            while credit < threshold:
                gbp = float(rng.choice(amounts))
                kwh = round(gbp * 100 / TARIFF_P, 3)
                vends.append((meter_id, pd.Timestamp(day) + pd.Timedelta(hours=int(rng.integers(8, 21)),
                                                                        minutes=int(rng.integers(0, 60))), gbp, kwh))
                credit += kwh
    vends = pd.DataFrame(vends, columns=["meter_id", "vend_ts", "amount_gbp", "kwh"])
    vends.insert(0, "vend_id", [f"V{i:08d}" for i in range(len(vends))])

    loss = pd.Series(rng.uniform(0.04, 0.07, FEEDERS), index=[f"F{i + 1:02d}" for i in range(FEEDERS)])
    feed = daily.assign(feeder_id=daily.meter_id.map(feeder_of)).groupby(["feeder_id", "day"]).kwh.sum().reset_index()
    feed["supply_kwh"] = (feed.kwh * (1 + feed.feeder_id.map(loss)) * rng.normal(1, 0.005, len(feed))).round(3)
    feed = feed.rename(columns={"day": "supply_date"})[["feeder_id", "supply_date", "supply_kwh"]]
    feed["supply_date"] = feed.supply_date.dt.date

    for name, df in [("sim_meters", meters), ("sim_tamper", tamper), ("sim_vends", vends), ("sim_feeder_supply", feed)]:
        write_deltalake(args.lake / name, df, mode="overwrite")
    summary = {"meters": len(meters), "feeders": FEEDERS, "tampered": len(tamper),
               "by_type": tamper.tamper_type.value_counts().to_dict(), "vends": len(vends),
               "feeder_days": len(feed), "seconds": round(time.time() - t0, 1)}
    (args.lake / "_simulation_report.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, default=str))


if __name__ == "__main__":
    main()
