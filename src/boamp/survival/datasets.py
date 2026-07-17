"""Survival-dataset construction (event/censoring), shared by both layers.

Extracted from scripts/run_m0_linkage.py::build_survival_dataset. Event = 1
when the source has an accepted link (time = gap to the linked candidate);
otherwise censored at the study end. The month conversion comes from config
(run.month_days), replacing the repeated 30.44 literal.
"""

from __future__ import annotations

import pandas as pd


def build_survival_dataset(sources: pd.DataFrame, links: pd.DataFrame,
                           variant_name: str, cfg,
                           extra_source_cols: list[str] | None = None,
                           extra_link_cols: list[str] | None = None) -> pd.DataFrame:
    month_days = cfg.pipeline.run.month_days
    eligible = sources[sources["buyer_key_type"] != "MISSING"].copy()
    link_map = links.set_index("source_notice_id")
    extra_source_cols = extra_source_cols or []
    extra_link_cols = extra_link_cols or []

    def row_to_survival(row):
        nid = row["notice_id"]
        study_end = row["study_end_date"]
        out = {
            "notice_id": nid,
            "buyer_key": row["buyer_key"],
            "buyer_key_type": row["buyer_key_type"],
            "publication_date": row["publication_date"],
            "start_date": row["start_date"],
            "estimated_end_date": row["estimated_end_date"],
            "study_end_date": study_end,
            "cpv_division": row["cpv_division"],
            "cpv_category": row["cpv_category"],
            "category_label": row["category_label"],
            "is_digital_scope": row["is_digital_scope"],
            "declared_duration_months": row["declared_duration_months"],
            "dur_was_imputed": row["dur_was_imputed"],
        }
        for c in extra_source_cols:
            out[c] = row.get(c)
        if nid in link_map.index:
            link = link_map.loc[nid]
            out["event"] = 1
            out["time_to_event_or_censor_months"] = link["gap_months"]
            out["linked_candidate_notice_id"] = link["candidate_notice_id"]
            out["composite_score"] = link["composite_score"]
            out["confidence_tier"] = link.get("confidence_tier")
            for c in extra_link_cols:
                out[c] = link.get(c)
        else:
            out["event"] = 0
            out["time_to_event_or_censor_months"] = (
                (study_end - row["publication_date"]).total_seconds() / (3600 * 24 * month_days)
            )
            out["linked_candidate_notice_id"] = None
            out["composite_score"] = None
            out["confidence_tier"] = None
            for c in extra_link_cols:
                out[c] = None
        out["variant"] = variant_name
        return pd.Series(out)

    return eligible.apply(row_to_survival, axis=1)
