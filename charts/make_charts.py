"""README charts from results/detection.json. Usage: python charts/make_charts.py [results_dir]"""
import json
import sys
from pathlib import Path

import style as st

ROOT = Path(__file__).resolve().parents[1]
RES = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results"
OUT = ROOT / "docs" / "charts"
d = json.loads((RES / "detection.json").read_text(encoding="utf-8"))
base = d["planted"] / d["meters_scored"]

pk = d["precision_at_k"]
ks = sorted({r["k"] for r in pk})
f, ax = st.fig(8, 3.5)
w = 0.26
for i, (m, lab, col) in enumerate([("rule_score", "Rules", st.S[0]), ("iforest_score", "Isolation forest", st.S[1]),
                                   ("combined_score", "Rules + isolation forest", st.S[2])]):
    v = [next(r["precision"] for r in pk if r["method"] == m and r["k"] == k) for k in ks]
    bars = ax.bar([j + (i - 1) * w for j in range(len(ks))], v, w * 0.9, color=col, label=lab)
    st.vbar_labels(ax, bars, lambda x: f"{x:.0%}")
ax.axhline(base, color=st.TEXT2, lw=1, ls="--", label=f"Random pick: {base:.1%}")
ax.set_xticks(range(len(ks)), [f"Top {k} meters" for k in ks])
st.fmt(ax, "y", "pct")
st.head(ax, f"More than half the top {ks[-1]} inspections are real tampering",
        f"Share of flagged meters that are planted cases, {d['meters_scored']:,} real London meters", legend=True, ncol=4)
st.save(f, OUT / "precision_at_k.png")

bt = d["by_type"]
names = {"flatline": "Flatline", "night_bypass": "Night bypass", "credit_tamper": "Credit tamper", "bypass": "Full bypass"}
bt.sort(key=lambda r: -r["in_top_k_combined"])
f, ax = st.fig(8, 3.2)
y = range(len(bt))
ax.barh([i - 0.2 for i in y], [r["caught_by_rules"] / r["planted"] for r in bt], 0.38, color=st.S[0], label="At least one rule fires")
ax.barh([i + 0.2 for i in y], [r["in_top_k_combined"] / r["planted"] for r in bt], 0.38, color=st.S[2], label=f"In the top {ks[-1]} inspection list")
for i, r in enumerate(bt):
    ax.text(r["in_top_k_combined"] / r["planted"] + 0.01, i + 0.2, f"{r['in_top_k_combined']} of {r['planted']}", va="center", fontsize=8.5, color=st.TEXT2)
ax.set_yticks(list(y), [names.get(r["tamper_type"], r["tamper_type"]) for r in bt])
ax.invert_yaxis()
ax.set_xlim(0, 1.12)
st.fmt(ax, "x", "pct")
ax.grid(axis="y", visible=False)
ax.grid(axis="x", visible=True)
st.head(ax, "Flatlines are easy; a full bypass looks like a household that really cut its use",
        "Share of planted meters found, by tamper type", legend=True)
st.save(f, OUT / "by_tamper_type.png")
print(f"wrote charts to {OUT}")
