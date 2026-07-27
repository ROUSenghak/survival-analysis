from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
VERSION = "v0_3_temporal_candidate_revision"
sys.path.insert(0, str(REPO))

from scripts.build_mechanism_tradeoff_log import build_tradeoff_log, write_tradeoff_log  # noqa: E402


def test_mechanism_tradeoff_log_records_rejected_identity_repairs():
    rows = build_tradeoff_log(
        REPO / "reports" / "tables" / "synthetic_benchmark" / VERSION,
        VERSION,
    )
    statuses = {row["mechanism_id"]: row["status"] for row in rows}
    assert statuses["identity_persistence_retained_2026_07_27"] == "RETAINED"
    assert (
        statuses["identity_cache_split_by_schema_year_notice_type_rejected_2026_07_27"]
        == "REJECTED_LOCAL_AUDIT"
    )
    assert (
        statuses["identity_cache_split_by_notice_type_rejected_2026_07_27"]
        == "REJECTED_LOCAL_AUDIT"
    )
    assert {row["provenance_category"] for row in rows} == {"SCENARIO_UNIDENTIFIED"}
    assert all("not released benchmark artifacts" in row["limitations"] for row in rows)


def test_mechanism_tradeoff_log_writer_outputs_csv_and_json(tmp_path):
    base = tmp_path / "v0_3_temporal_candidate_revision"
    validation_dir = base / "validation_framework"
    validation_dir.mkdir(parents=True)
    (validation_dir / "validation_manifest.json").write_text(
        json.dumps({"overall_status": "PASS_WITH_WARNINGS", "n_metric_failures": 0}),
        encoding="utf-8",
    )
    (validation_dir / "replay_replicates.json").write_text(
        json.dumps({"overall_status": "PASS", "n_replicates": 51}),
        encoding="utf-8",
    )

    result = write_tradeoff_log(base, VERSION)
    assert result["row_count"] == 3
    csv_path = Path(result["csv"])
    json_path = Path(result["json"])
    assert csv_path.exists()
    assert json_path.exists()
    csv_rows = pd.read_csv(csv_path)
    json_rows = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(csv_rows) == 3
    assert json_rows["row_count"] == 3
    assert set(csv_rows["status"]) == {"RETAINED", "REJECTED_LOCAL_AUDIT"}
