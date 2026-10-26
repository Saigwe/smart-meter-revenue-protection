"""Score every meter, rank the inspection list, and measure detection against the planted (ground-truth) theft.

Scores, from gold.rpt_meter_features (metered data, vends and feeder supply only):
  rules     four explainable rules, one per theft pattern, combined as a weighted count
              drop      consumption fell to under 60% of last year's, relative to the feeder's median change
              unpaid    the customer bought under 60% of what was metered, having bought >= 80% a year before
              flat      the meter reported a near-constant value on most days
              night     night-time share of use fell to under 30% of last year's
  iforest   an Isolation Forest on the same features (unsupervised: it never sees a label)
  combined  the average of the two rank percentiles
Revenue at risk per year = estimated unbilled kWh per day x 365 x tariff, where unbilled is the larger of the
drop against last year (peer-adjusted) and the unpaid gap. For planted meters it is compared with the truth.

Usage: python analysis/score_meters.py --db warehouse/meters.duckdb --lake data/lake --out results
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

FEATURES = ["consumption_ratio_vs_feeder", "eval_purchase_ratio", "eval_flat_day_share", "night_share_ratio",
            "consumption_ratio", "eval_gap_kwh_per_day", "feeder_excess_loss_share"]


def rules(f: pd.DataFrame) -> pd.DataFrame:
    hits = pd.DataFrame(index=f.index)
    hits["drop"] = f.consumption_ratio_vs_feeder < 0.6
    hits["unpaid"] = (f.eval_purchase_ratio < 0.6) & (f.base_purchase_ratio >= 0.8)
    hits["flat"] = f.eval_flat_day_share > 0.5
    hits["night"] = (f.night_share_ratio < 0.3) & (f.base_night_share > 0.05)
    return hits.fillna(False)


def precision_recall(order: np.ndarray, truth: np.ndarray, k: int) -> tuple[float, float]:
    top = order[:k]
    tp = truth[top].sum()
    return float(tp / k), float(tp / truth.sum())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="warehouse/meters.duckdb")
    ap.add_argument("--lake", type=Path, default=Path("data/lake"))
    ap.add_argument("--out", type=Path, default=Path("results"))
    ap.add_argument("--tariff", type=float, default=14.228)
    args = ap.parse_args()
    con = duckdb.connect(args.db)
    con.execute("install delta; load delta")
    f = con.execute("select * from gold.rpt_meter_features").df().set_index("meter_id")

    hits = rules(f)
    f["rule_hits"] = hits.sum(axis=1)
    f["rules_matched"] = hits.apply(lambda r: ",".join(c for c in hits.columns if r[c]), axis=1)
    f["rule_score"] = hits.astype(float).mul({"drop": 1.0, "unpaid": 1.2, "flat": 1.5, "night": 1.0}).sum(axis=1) \
        + (1 - f.consumption_ratio_vs_feeder.clip(0, 1).fillna(1)) * 0.1  # tie-break: deeper drops first
    X = f[FEATURES].replace([np.inf, -np.inf], np.nan)
    X = X.fillna(X.median())
    forest = IsolationForest(n_estimators=400, contamination="auto", random_state=0).fit(X)
    f["iforest_score"] = -forest.score_samples(X)
    f["combined_score"] = (f.rule_score.rank(pct=True) + f.iforest_score.rank(pct=True)) / 2

    base_per_day = f.base_kwh_per_day * f.consumption_ratio / f.consumption_ratio_vs_feeder  # peer-adjusted expectation
    drop_kwh = (base_per_day - f.eval_kwh_per_day).clip(lower=0)
    f["unbilled_kwh_per_day_est"] = np.maximum(drop_kwh.fillna(0), f.eval_gap_kwh_per_day.clip(lower=0).fillna(0))
    f["revenue_at_risk_gbp_year"] = f.unbilled_kwh_per_day_est * 365 * args.tariff / 100

    truth = con.execute(f"select meter_id, tamper_type from delta_scan('{(args.lake / 'sim_tamper').resolve().as_posix()}')").df()
    f["planted"] = f.index.isin(truth.meter_id)
    f = f.join(truth.set_index("meter_id"))
    y = f.planted.to_numpy()
    n_planted = int(y.sum())

    rows, method_order = [], {}
    for method in ["rule_score", "iforest_score", "combined_score"]:
        order = np.argsort(-f[method].to_numpy(), kind="stable")
        method_order[method] = order
        for k in (50, 100, n_planted):
            p, r = precision_recall(order, y, k)
            rows.append({"method": method, "k": k, "precision": p, "recall": r})
    flagged = f.rule_hits > 0
    rule_flag = {"flagged": int(flagged.sum()), "precision": float(f.planted[flagged].mean()) if flagged.any() else 0.0,
                 "recall": float(f.planted[flagged].sum() / n_planted)}
    by_type = f[f.planted].groupby("tamper_type").apply(lambda g: pd.Series({
        "planted": len(g), "caught_by_rules": int((g.rule_hits > 0).sum()),
        "in_top_k_combined": int(g.index.isin(f.index[method_order["combined_score"][:n_planted]]).sum())}),
        include_groups=False)
    fp = f[flagged & ~f.planted]
    fp_tou_share = float((fp.tariff_group == "ToU").mean()) if len(fp) else 0.0
    pop_tou_share = float((f.tariff_group == "ToU").mean())

    # revenue at risk vs truth, for planted meters: truth = real use minus what was paid for, in the eval window
    e0, e1 = con.execute("select min(week_start), max(week_start) from gold.fct_meter_weekly").fetchone()
    actual = con.execute("""
        select t.meter_id, sum(t.true_kwh) / count(*) as true_per_day
        from silver.sim_meter_daily_truth t
        where t.reading_date between date '2013-10-01' and date '2013-12-31' group by 1
    """).df().set_index("meter_id")
    p = f[f.planted].join(actual)
    paid_per_day = p.eval_kwh_per_day * p.eval_purchase_ratio.fillna(1)
    p["true_unbilled_per_day"] = (p.true_per_day - paid_per_day).clip(lower=0)
    estimate_ratio = float(p.unbilled_kwh_per_day_est.sum() / p.true_unbilled_per_day.sum())

    ranked = f.sort_values("combined_score", ascending=False).reset_index()
    ranked["inspection_rank"] = np.arange(1, len(ranked) + 1)
    cols = ["inspection_rank", "meter_id", "feeder_id", "tariff_group", "combined_score", "rule_score", "iforest_score",
            "rules_matched", "unbilled_kwh_per_day_est", "revenue_at_risk_gbp_year"]
    con.execute("create schema if not exists gold")
    inspection = ranked[cols]
    con.execute("create or replace table gold.inspection_list as select * from inspection")

    args.out.mkdir(parents=True, exist_ok=True)
    top = ranked.head(n_planted)
    summary = {"meters_scored": len(f), "planted": n_planted, "rule_flags": rule_flag, "precision_at_k": rows,
               "by_type": by_type.reset_index().to_dict("records"),
               "false_positive_tou_share": fp_tou_share, "population_tou_share": pop_tou_share,
               "revenue_at_risk_top_k_gbp_year": float(top.revenue_at_risk_gbp_year.sum()),
               "revenue_at_risk_top_k_planted_gbp_year": float(top[top.planted].revenue_at_risk_gbp_year.sum()),
               "estimate_vs_true_unbilled_ratio": estimate_ratio}
    (args.out / "detection.json").write_text(json.dumps(summary, indent=1, default=float))
    lines = [
        "# Detection against planted theft", "",
        f"{len(f):,} meters scored (reporting in both Oct-Dec 2012 and Oct-Dec 2013); {n_planted} planted cases.", "",
        f"- Rules flag {rule_flag['flagged']} meters: precision {rule_flag['precision']:.1%}, recall {rule_flag['recall']:.1%}.",
        f"- False positives are {fp_tou_share:.0%} time-of-use customers (vs {pop_tou_share:.0%} of all meters).",
        f"- Revenue at risk, top {n_planted}: £{summary['revenue_at_risk_top_k_gbp_year']:,.0f} a year "
        f"(£{summary['revenue_at_risk_top_k_planted_gbp_year']:,.0f} from planted cases). "
        f"Estimated unbilled energy is {estimate_ratio:.2f}x the true amount for planted meters.", "",
        "| Method | k | Precision | Recall |", "|---|---:|---:|---:|",
    ] + [f"| {r['method']} | {r['k']} | {r['precision']:.1%} | {r['recall']:.1%} |" for r in rows] + [
        "", "| Theft type | Planted | Caught by a rule | In combined top k |", "|---|---:|---:|---:|",
    ] + [f"| {t} | {int(r.planted)} | {int(r.caught_by_rules)} | {int(r.in_top_k_combined)} |" for t, r in by_type.iterrows()]
    (args.out / "detection.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
