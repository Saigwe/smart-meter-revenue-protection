"""Synthetic CSVs in the exact Low Carbon London file format, so CI runs the real Delta load, the simulation,
dbt, scoring and the Spark job. 200 households, half-hourly, September 2012 to January 2014, with the quirks
of the real files: " Null" readings, duplicated rows, a fixed-width timestamp, a header with trailing spaces.

Usage: python tests/fixtures/make_fixture.py --out "data/fixture/raw"
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

METERS = 200


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/fixture/raw"))
    args = ap.parse_args()
    rng = np.random.default_rng(17)
    ts = pd.date_range("2012-09-01 00:30", "2014-01-31 23:30", freq="30min")
    hour = ts.hour.to_numpy() + ts.minute.to_numpy() / 60
    daily_shape = 0.6 + 0.5 * np.exp(-((hour - 19) ** 2) / 8) + 0.3 * np.exp(-((hour - 8) ** 2) / 4)
    season = 1 + 0.25 * np.cos(2 * np.pi * (ts.day_of_year.to_numpy() - 15) / 365)
    args.out.mkdir(parents=True, exist_ok=True)
    for chunk in range(4):
        frames = []
        for m in range(chunk * METERS // 4, (chunk + 1) * METERS // 4):
            level = rng.lognormal(-1.8, 0.4)
            kwh = np.round(level * daily_shape * season * rng.lognormal(0, 0.35, len(ts)), 3)
            df = pd.DataFrame({"LCLid": f"MAC{m:06d}", "stdorToU": "ToU" if m % 5 == 0 else "Std",
                               "DateTime": ts.strftime("%Y-%m-%d %H:%M:%S.0000000"), "KWH/hh (per half hour) ": kwh.astype(str)})
            df.loc[rng.random(len(df)) < 0.0002, "KWH/hh (per half hour) "] = "Null"
            frames.append(pd.concat([df, df.sample(frac=0.0005, random_state=m)]))  # duplicated rows
        out = pd.concat(frames)
        out["KWH/hh (per half hour) "] = " " + out["KWH/hh (per half hour) "] + " "
        out.to_csv(args.out / f"LCL-June2015v2_{chunk}.csv", index=False)
    print(f"wrote {METERS} synthetic households x {len(ts):,} half-hours to {args.out}")


if __name__ == "__main__":
    main()
