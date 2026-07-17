"""Link selection: rank-1 candidate + threshold, plus three-way confidence tiers.

Extracted from scripts/run_m0_linkage.py (build_variant), extended with the
explicit match / potential-match classification the record-linkage design
calls for: a linked pair whose top1-top2 margin is below
cfg.pipeline.confidence_tiers.potential_margin_max is kept but tiered
POTENTIAL, so downstream analyses can test robustness to ambiguous links.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LINK_COLUMNS_BASE = [
    "source_notice_id", "candidate_notice_id",
    "source_date", "candidate_date", "gap_months", "expected_end_date",
    "abs_gap_to_expected_end", "s_time", "s_text", "s_cpv", "s_buyer",
    "composite_score", "cpv_missing", "cpv_generic_flag",
    "candidate_rank", "top1_top2_margin", "n_candidates_for_source",
    "confidence_tier", "variant", "threshold_used",
]


def assign_confidence_tier(links: pd.DataFrame, cfg) -> pd.Series:
    tiers = cfg.pipeline.confidence_tiers
    return pd.Series(
        np.select(
            [
                links["top1_top2_margin"] < tiers.potential_margin_max,
                links["composite_score"] >= tiers.high_score_min,
            ],
            ["POTENTIAL", "HIGH"],
            default="MEDIUM",
        ),
        index=links.index,
    )


def build_links(pairs: pd.DataFrame, threshold: float, variant_name: str, cfg,
                extra_columns: list[str] | None = None) -> pd.DataFrame:
    """Select rank-1 candidates with composite_score >= threshold."""
    rank1 = pairs[pairs["candidate_rank"] == 1].copy()
    linked = rank1[rank1["composite_score"] >= threshold].copy()
    linked["variant"] = variant_name
    linked["threshold_used"] = threshold
    linked["confidence_tier"] = assign_confidence_tier(linked, cfg)
    cols = list(LINK_COLUMNS_BASE)
    for c in (extra_columns or []):
        if c in linked.columns and c not in cols:
            cols.append(c)
    for c in ["buyer_key", "buyer_key_type"]:
        if c in linked.columns and c not in cols:
            cols.insert(2, c)
    return linked[[c for c in cols if c in linked.columns]]


def link_selection_summary(links: pd.DataFrame, n_eligible: int) -> dict:
    reuse = links["candidate_notice_id"].value_counts() if len(links) else pd.Series(dtype=int)
    return {
        "n_links": len(links),
        "linking_rate": len(links) / n_eligible if n_eligible else 0.0,
        "median_gap_months": float(links["gap_months"].median()) if len(links) else np.nan,
        "median_composite_score": float(links["composite_score"].median()) if len(links) else np.nan,
        "median_margin": float(links["top1_top2_margin"].median()) if len(links) else np.nan,
        "n_potential_tier": int((links["confidence_tier"] == "POTENTIAL").sum()) if len(links) else 0,
        "n_high_tier": int((links["confidence_tier"] == "HIGH").sum()) if len(links) else 0,
        "n_medium_tier": int((links["confidence_tier"] == "MEDIUM").sum()) if len(links) else 0,
        "unique_candidates": int(links["candidate_notice_id"].nunique()) if len(links) else 0,
        "n_reused_candidates": int((reuse > 1).sum()),
        "max_candidate_multiplicity": int(reuse.max()) if len(reuse) else 0,
    }
