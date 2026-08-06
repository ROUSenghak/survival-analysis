from __future__ import annotations

import pandas as pd
import pytest

from boamp.status import (
    BLOCKED_BY_EXTERNAL_CLASSIFICATION,
    BLOCKED_BY_MANUAL_AUDIT,
    MANUAL_AUDIT_LABELS,
    ScientificGateError,
    classification_export_status,
    manual_audit_status,
    require_final_event_dataset_gate,
    require_technology_specific_gate,
)


def test_blank_manual_audit_labels_block_final_event_dataset(tmp_path):
    path = tmp_path / "audit.csv"
    pd.DataFrame({"reviewer_label": ["", None]}).to_csv(path, index=False)
    status = manual_audit_status(path)
    assert status.status == BLOCKED_BY_MANUAL_AUDIT
    with pytest.raises(ScientificGateError):
        require_final_event_dataset_gate(path)


def test_completed_manual_audit_label_passes_gate(tmp_path):
    path = tmp_path / "audit.csv"
    pd.DataFrame({"reviewer_label": ["CORRECT_LINK"]}).to_csv(path, index=False)
    assert manual_audit_status(path).status == "PASS"


def test_unknown_manual_audit_label_blocks(tmp_path):
    path = tmp_path / "audit.csv"
    pd.DataFrame({"reviewer_label": ["MODEL_CONFIDENT"]}).to_csv(path, index=False)
    assert manual_audit_status(path).status == BLOCKED_BY_MANUAL_AUDIT


def test_manual_audit_label_vocabulary_matches_project_plan():
    assert MANUAL_AUDIT_LABELS == {
        "CORRECT_LINK",
        "WRONG_LINK",
        "MISSED_LINK",
        "CORRECT_REJECTION",
        "INSUFFICIENT_INFORMATION",
        "NEEDS_SECOND_REVIEW",
    }


def test_missing_classification_export_blocks_technology_analysis(tmp_path):
    path = tmp_path / "missing.csv"
    status = classification_export_status(path)
    assert status.status == BLOCKED_BY_EXTERNAL_CLASSIFICATION
    with pytest.raises(ScientificGateError):
        require_technology_specific_gate(path)
