import pandas as pd
import pytest

from boamp.linkage.links import assign_confidence_tier, build_links
from boamp.survival.datasets import build_survival_dataset


def _pairs():
    return pd.DataFrame({
        "source_notice_id": ["a", "a", "b", "c"],
        "candidate_notice_id": ["x", "y", "z", "w"],
        "source_date": pd.to_datetime(["2020-01-01"] * 4),
        "candidate_date": pd.to_datetime(["2020-07-01"] * 4),
        "gap_months": [6.0, 6.5, 7.0, 5.0],
        "expected_end_date": pd.to_datetime(["2020-06-01"] * 4),
        "abs_gap_to_expected_end": [1.0] * 4,
        "s_time": [0.8] * 4, "s_text": [0.5] * 4, "s_cpv": [1.0] * 4, "s_buyer": [1.0] * 4,
        "composite_score": [0.60, 0.55, 0.40, 0.20],
        "cpv_missing": [False] * 4, "cpv_generic_flag": [False] * 4,
        "candidate_rank": [1, 2, 1, 1],
        "top1_top2_margin": [0.05, 0.05, 0.40, 0.20],
        "n_candidates_for_source": [2, 2, 1, 1],
        "buyer_key": ["K1", "K1", "K2", "K3"],
        "buyer_key_type": ["RAW_SIRET"] * 4,
    })


def test_build_links_rank1_and_threshold(cfg):
    links = build_links(_pairs(), 0.35, "balanced", cfg)
    # only rank-1 rows above threshold: a (0.60) and b (0.40); c is below
    assert set(links["source_notice_id"]) == {"a", "b"}
    assert (links["candidate_rank"] == 1).all()
    assert (links["threshold_used"] == 0.35).all()


def test_confidence_tiers(cfg):
    links = build_links(_pairs(), 0.35, "balanced", cfg)
    tiers = links.set_index("source_notice_id")["confidence_tier"]
    # a: margin 0.05 is NOT < 0.05 -> not POTENTIAL; score 0.60 >= 0.50 -> HIGH
    assert tiers["a"] == "HIGH"
    # b: margin 0.40, score 0.40 < 0.50 -> MEDIUM
    assert tiers["b"] == "MEDIUM"
    low = _pairs()
    low.loc[low["source_notice_id"] == "b", "top1_top2_margin"] = 0.01
    links2 = build_links(low, 0.35, "balanced", cfg)
    assert links2.set_index("source_notice_id")["confidence_tier"]["b"] == "POTENTIAL"


def _sources():
    return pd.DataFrame({
        "notice_id": ["a", "b", "c"],
        "buyer_key": ["K1", "K2", "K3"],
        "buyer_key_type": ["RAW_SIRET", "RAW_SIRET", "NAME_FALLBACK"],
        "publication_date": pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]),
        "start_date": pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]),
        "estimated_end_date": pd.to_datetime(["2020-07-01", "2020-08-01", "2020-09-01"]),
        "study_end_date": pd.to_datetime(["2021-01-01"] * 3),
        "cpv_division": ["48", "72", "48"],
        "cpv_category": ["48151", "72151", "48151"],
        "category_label": ["DIGITAL_ICT"] * 3,
        "is_digital_scope": [True] * 3,
        "declared_duration_months": [6.0, 6.0, 6.0],
        "dur_was_imputed": [False, True, True],
    })


def test_survival_event_and_censoring(cfg):
    links = build_links(_pairs(), 0.35, "balanced", cfg)
    surv = build_survival_dataset(_sources(), links, "balanced", cfg)
    surv = surv.set_index("notice_id")
    assert surv.loc["a", "event"] == 1
    assert surv.loc["a", "time_to_event_or_censor_months"] == pytest.approx(6.0)
    # c is censored: time = (study_end - publication)/30.44 days-per-month
    assert surv.loc["c", "event"] == 0
    expected = (pd.Timestamp("2021-01-01") - pd.Timestamp("2020-03-01")).total_seconds() / (3600 * 24 * 30.44)
    assert surv.loc["c", "time_to_event_or_censor_months"] == pytest.approx(expected)
    assert pd.isna(surv.loc["c", "linked_candidate_notice_id"])
