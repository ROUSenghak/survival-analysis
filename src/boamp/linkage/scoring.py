"""Shared scoring math for both layers - single source of truth.

Notation (defined once, used by notebooks and reports):
  For a source contract i and candidate j from the same buyer block:
    t_i   publication date of i        t_j   publication date of j
    d_i   declared duration of i (months, possibly imputed)
    e_i   estimated end date  = start_date_i + d_i
    W     temporal window (months)
    gap_months     = (t_j - t_i) in months (30.44 days/month)
    abs_gap        = |t_j - e_i| in months
    s_time  = max(0, 1 - abs_gap / W)
    s_text  = cosine(TF-IDF(objet_i), TF-IDF(objet_j))
    s_cpv   = hierarchy rung (exact > category > class > group > division > different; missing = weak-neutral)
    s_buyer = reliability of the identity mechanism that formed the block
    S_ij    = w_text*s_text + w_cpv*s_cpv + w_time*s_time + w_buyer*s_buyer
  margin_i = S_i,(1) - S_i,(2)  (best minus second-best candidate score)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer


def cpv_pair_score(src_main, cand_main, src_cat, cand_cat, src_cls, cand_cls,
                   src_grp, cand_grp, src_div, cand_div, cpv_cfg) -> float:
    if pd.isna(src_main) or pd.isna(cand_main):
        return cpv_cfg.missing
    if src_main == cand_main:
        return cpv_cfg.exact
    if src_cat == cand_cat:
        return cpv_cfg.category
    if src_cls == cand_cls:
        return getattr(cpv_cfg, "class")
    if src_grp == cand_grp:
        return cpv_cfg.group
    if src_div == cand_div:
        return cpv_cfg.division
    return cpv_cfg.different


def composite_score(s_text, s_cpv, s_time, s_buyer, weights) -> float:
    return (weights.text * s_text + weights.cpv * s_cpv
            + weights.time * s_time + weights.buyer * s_buyer)


def build_tfidf_matrix(texts, cfg):
    tm = cfg.pipeline.text_model
    vectorizer = TfidfVectorizer(
        max_features=tm.max_features,
        ngram_range=tuple(tm.ngram_range),
        min_df=tm.min_df,
    )
    return vectorizer, vectorizer.fit_transform(list(texts))


def estimate_window_months(eligible: pd.DataFrame, cfg) -> tuple[int, float]:
    """window = clip(round(factor * median observed duration), floor, cap).

    Returns (window_months, median_observed_duration). With the current
    corpus (median 6 months) this collapses to the floor of 6 - the
    derivation is kept so future data can move it.
    """
    tw = cfg.pipeline.temporal_window
    dur = eligible.loc[~eligible["dur_was_imputed"].astype(bool), "declared_duration_months"].dropna()
    median_dur = dur.median() if len(dur) else eligible["declared_duration_months"].median()
    window = int(np.clip(round(median_dur * tw.factor), tw.floor_months, tw.cap_months))
    return window, float(median_dur)


def derive_thresholds(pairs: pd.DataFrame, cfg, score_col: str = "composite_score") -> dict:
    """Rank-1 composite-score p25/p50/p75 -> broad/balanced/strict.

    The frozen values in config were derived this way from the Layer 1 run;
    assert_thresholds_frozen() checks a re-derivation stays within tolerance.
    """
    rank1 = pairs[pairs["candidate_rank"] == 1]
    if not len(rank1):
        return {"broad": 0.0, "balanced": 0.0, "strict": 0.0}
    p25, p50, p75 = rank1[score_col].quantile([0.25, 0.5, 0.75]).tolist()
    return {"broad": p25, "balanced": p50, "strict": p75}


def assert_thresholds_frozen(derived: dict, cfg) -> None:
    thr = cfg.pipeline.thresholds
    tol = thr.tolerance
    for name, frozen in [("broad", thr.broad), ("balanced", thr.balanced), ("strict", thr.strict)]:
        if abs(derived[name] - frozen) > tol:
            raise AssertionError(
                f"Re-derived {name} threshold {derived[name]:.6f} differs from frozen "
                f"config value {frozen:.6f} by more than tolerance {tol}. The corpus "
                f"changed - update config/pipeline.yaml deliberately, do not ignore this."
            )


def add_rank_and_margin(pairs: pd.DataFrame, score_col: str = "composite_score") -> pd.DataFrame:
    """Sort, rank candidates per source, and compute the top1-top2 margin."""
    if not len(pairs):
        return pairs
    pairs = pairs.sort_values(["source_notice_id", score_col], ascending=[True, False]).reset_index(drop=True)
    pairs["candidate_rank"] = pairs.groupby("source_notice_id").cumcount() + 1
    pairs["n_candidates_for_source"] = pairs.groupby("source_notice_id")["candidate_notice_id"].transform("count")
    top2 = (
        pairs[pairs["candidate_rank"] <= 2]
        .pivot(index="source_notice_id", columns="candidate_rank", values=score_col)
        # A corpus where no source has a second candidate produces no rank-2
        # column at all; reindex so the margin below is NaN-filled per source
        # instead of raising on a missing column.
        .reindex(columns=[1, 2])
    )
    margin = (top2[1] - top2[2]).fillna(top2[1])
    pairs["top1_top2_margin"] = pairs["source_notice_id"].map(margin)
    return pairs
