import pandas as pd
import pytest

from boamp.linkage.scoring import add_rank_and_margin, cpv_pair_score, derive_thresholds


def _score(cfg, src, cand):
    """Helper: score a (source, candidate) CPV pair from full 8-digit codes."""
    def levels(c):
        if c is None:
            return (None, None, None, None, None)
        return (c, c[:5], c[:4], c[:3], c[:2])
    s_main, s_cat, s_cls, s_grp, s_div = levels(src)
    c_main, c_cat, c_cls, c_grp, c_div = levels(cand)
    return cpv_pair_score(s_main, c_main, s_cat, c_cat, s_cls, c_cls,
                          s_grp, c_grp, s_div, c_div, cfg.pipeline.cpv_score)


def test_cpv_ladder_values(cfg):
    assert _score(cfg, "48000000", "48000000") == 1.0   # exact
    assert _score(cfg, "48151000", "48151999") == 0.8   # category (5 digits)
    assert _score(cfg, "48151000", "48159999") == 0.6   # class (4 digits)
    assert _score(cfg, "48151000", "48199999") == 0.4   # group (3 digits)
    assert _score(cfg, "48151000", "48999999") == 0.2   # division (2 digits)
    assert _score(cfg, "48151000", "72999999") == 0.0   # different
    assert _score(cfg, None, "48000000") == 0.1          # missing = weak-neutral


def test_cpv_missing_above_different(cfg):
    assert _score(cfg, None, "48000000") > _score(cfg, "48151000", "72999999")


def test_rank_and_margin():
    pairs = pd.DataFrame({
        "source_notice_id": ["a", "a", "a", "b"],
        "candidate_notice_id": ["x", "y", "z", "w"],
        "composite_score": [0.5, 0.4, 0.1, 0.7],
    })
    out = add_rank_and_margin(pairs)
    a = out[out["source_notice_id"] == "a"].sort_values("candidate_rank")
    assert list(a["candidate_rank"]) == [1, 2, 3]
    assert a["top1_top2_margin"].iloc[0] == pytest.approx(0.1)
    b = out[out["source_notice_id"] == "b"]
    # single candidate: margin falls back to the top-1 score itself
    assert b["top1_top2_margin"].iloc[0] == pytest.approx(0.7)


def test_derive_thresholds_percentiles(cfg):
    pairs = pd.DataFrame({
        "source_notice_id": list("abcde"),
        "candidate_rank": [1] * 5,
        "composite_score": [0.1, 0.2, 0.3, 0.4, 0.5],
    })
    thr = derive_thresholds(pairs, cfg)
    assert thr["broad"] == pytest.approx(0.2)
    assert thr["balanced"] == pytest.approx(0.3)
    assert thr["strict"] == pytest.approx(0.4)
