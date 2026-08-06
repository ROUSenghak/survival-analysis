from __future__ import annotations

import pandas as pd

from boamp.status import MANUAL_AUDIT_LABELS


def test_canonical_manual_audit_package_is_blank_and_labelled(cfg):
    path = cfg.paths.manual_audit_sample_30
    assert path.exists(), "run scripts/build_real_audit_sample.py"
    audit = pd.read_csv(path)
    assert 25 <= len(audit) <= 35
    assert "reviewer_label" in audit.columns
    labels = audit["reviewer_label"].dropna().astype(str).str.strip()
    assert labels[labels.ne("")].empty
    assert set(audit["audit_stratum"].dropna()).issubset(
        {
            "gbm_and_composite",
            "gbm_only",
            "composite_only",
            "gbm_borderline_score",
            "gbm_small_margin",
            "rejected_composite_top_candidate",
            "rejected_far_below",
            "censored_no_candidate",
        }
    )


def test_manual_audit_instructions_list_allowed_labels(cfg):
    path = cfg.paths.manual_audit_instructions
    assert path.exists(), "run scripts/build_real_audit_sample.py"
    text = path.read_text(encoding="utf-8")
    for label in MANUAL_AUDIT_LABELS:
        assert label in text
    assert "real precision and recall remain `UNKNOWN`" in text
