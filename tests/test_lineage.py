"""Detection must only see what a utility sees. Reads dbt's manifest (after `dbt build` or `dbt parse`):
  - no detection model depends on the ground truth (sim_tamper) except through sim_meter_daily_metered,
    the one model that turns real use into what a tampered meter reports
  - no detection model depends on the household's real, unmetered use (sim_meter_daily_truth)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dbt" / "target" / "manifest.json"
DETECTION = ["fct_meter_weekly", "rpt_feeder_losses", "rpt_meter_features"]


@pytest.fixture(scope="module")
def graph():
    if not MANIFEST.exists():
        pytest.skip("run dbt first")
    m = json.loads(MANIFEST.read_text())
    return {uid: node["depends_on"]["nodes"] for uid, node in m["nodes"].items() if "depends_on" in node}


def ancestors(graph: dict, uid: str, stop_at: set[str]) -> set[str]:
    seen, todo = set(), [uid]
    while todo:
        for parent in graph.get(todo.pop(), []):
            if parent not in seen:
                seen.add(parent)
                if parent not in stop_at:
                    todo.append(parent)
    return seen


@pytest.mark.parametrize("model", DETECTION)
def test_detection_never_reads_ground_truth_directly(graph, model):
    uid = f"model.smart_meter_revenue_protection.{model}"
    boundary = {"model.smart_meter_revenue_protection.sim_meter_daily_metered"}
    reached = ancestors(graph, uid, stop_at=boundary)
    assert "source.smart_meter_revenue_protection.lake.sim_tamper" not in reached
    assert "model.smart_meter_revenue_protection.sim_meter_daily_truth" not in reached
    assert "source.smart_meter_revenue_protection.lake.readings" not in reached  # only via the metered boundary
