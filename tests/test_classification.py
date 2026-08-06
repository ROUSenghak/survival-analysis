from __future__ import annotations

import pandas as pd
import pytest

from boamp.data.classification import (
    REQUIRED_CLASSIFICATION_COLUMNS,
    merge_classification,
    validate_classification_export,
)
from boamp.status import UNCLASSIFIED


def _valid_export() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "notice_id": ["BOAMP-TEST-001", "BOAMP-TEST-002"],
            "technology_label": ["CLOUD", "CYBERSECURITY"],
            "prediction_confidence": [0.91, 0.73],
            "low_confidence_flag": [False, True],
            "classification_source": ["unit_test_fixture", "unit_test_fixture"],
            "taxonomy_version": ["test-taxonomy-v1", "test-taxonomy-v1"],
            "model_version": ["test-model-v1", "test-model-v1"],
            "classification_date": ["2026-08-06", "2026-08-06"],
        }
    )


def test_required_classification_columns_are_stable():
    assert REQUIRED_CLASSIFICATION_COLUMNS == [
        "notice_id",
        "technology_label",
        "prediction_confidence",
        "low_confidence_flag",
        "classification_source",
        "taxonomy_version",
        "model_version",
        "classification_date",
    ]


def test_valid_classification_export_passes():
    result = validate_classification_export(_valid_export())
    assert result.valid
    assert result.n_rows == 2
    assert result.n_unique_notice_ids == 2


def test_classification_rejects_duplicates_and_leakage_columns():
    df = _valid_export()
    df.loc[1, "notice_id"] = df.loc[0, "notice_id"]
    df["accepted_renewal_successor"] = ["x", "y"]
    result = validate_classification_export(df)
    assert not result.valid
    assert any("duplicate notice_id" in error for error in result.errors)
    assert any("outcome-leakage" in error for error in result.errors)


def test_classification_merge_keeps_unmatched_as_unclassified():
    notices = pd.DataFrame({"notice_id": ["BOAMP-TEST-001", "BOAMP-TEST-003"]})
    merged, report = merge_classification(notices, _valid_export())
    assert len(merged) == 2
    unmatched = merged.loc[merged["notice_id"].eq("BOAMP-TEST-003")].iloc[0]
    assert unmatched["technology_label"] == UNCLASSIFIED
    assert bool(unmatched["low_confidence_flag"])
    assert report["n_unmatched"] == 1


def test_classification_rejects_unknown_labels_when_taxonomy_supplied():
    with pytest.raises(ValueError):
        merge_classification(
            pd.DataFrame({"notice_id": ["BOAMP-TEST-001"]}),
            _valid_export().head(1),
            allowed_labels={"AI"},
        )
