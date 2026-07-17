"""Enrichment-quality diagnostics for Layer 2.

Extracted from scripts/build_m1_buyer_siren_experiment.py
(agreement_diagnostics, experiment_breakdowns) with layer-neutral naming.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from boamp.data.identity_enriched import dept_key


def agreement_diagnostics(enriched_clean: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Native-vs-external SIREN agreement among notices holding both."""
    both = enriched_clean[
        enriched_clean["buyer_siren_from_boamp_siret"].notna()
        & enriched_clean["buyer_siren_enriched_valid"].fillna(False)
        & enriched_clean["buyer_siren_enriched"].notna()
    ].copy()
    both["agreement"] = both["buyer_siren_from_boamp_siret"] == both["buyer_siren_enriched"]
    both["publication_year"] = both["publication_date"].dt.year
    both["department_key"] = both["code_departement"].map(dept_key)

    def summarize(frame: pd.DataFrame, dimension: str, value: str) -> dict:
        return {
            "dimension": dimension, "value": value,
            "rows_with_boamp_siret_and_enriched_siren": len(frame),
            "agreement_count": int(frame["agreement"].sum()) if len(frame) else 0,
            "disagreement_count": int((~frame["agreement"]).sum()) if len(frame) else 0,
            "agreement_rate": float(frame["agreement"].mean()) if len(frame) else np.nan,
        }

    rows = [summarize(both, "overall", "all")]
    for dim, col in [("year", "publication_year"), ("notice_type", "notice_type_normalized"),
                     ("buyer_key_type", "buyer_key_type"), ("department", "department_key")]:
        for value, grp in both.groupby(col, dropna=False):
            rows.append(summarize(grp, dim, str(value)))

    missing_rows = []
    for label, frame in [
        ("all_clean_notices", enriched_clean),
        ("joined_enrichment_notices", enriched_clean[enriched_clean["enrichment_join_status"] == "JOINED"]),
    ]:
        missing_rows.append({
            "population": label,
            "row_count": len(frame),
            "boamp_siret_missing_rate": float(frame["buyer_siret_clean"].isna().mean()) if len(frame) else np.nan,
            "enriched_siren_missing_or_invalid_rate": float((~frame["buyer_siren_enriched_valid"].fillna(False)).mean()) if len(frame) else np.nan,
            "both_valid_boamp_siret_and_enriched_siren_count": len(frame[
                frame["buyer_siren_from_boamp_siret"].notna()
                & frame["buyer_siren_enriched_valid"].fillna(False)
                & frame["buyer_siren_enriched"].notna()
            ]),
        })
    return pd.DataFrame(rows), pd.DataFrame(missing_rows)


def identity_source_summary(l2_sources: pd.DataFrame) -> pd.DataFrame:
    out = (l2_sources.groupby(["buyer_identity_source", "buyer_identity_confidence"])
           .size().rename("n_sources").reset_index()
           .sort_values("n_sources", ascending=False))
    out["share"] = out["n_sources"] / len(l2_sources)
    return out


def unresolved_report(l2_sources: pd.DataFrame) -> pd.DataFrame:
    """Sources whose Layer 2 identity could NOT be upgraded (kept transparent)."""
    unresolved = l2_sources[l2_sources["buyer_siren_l2"].isna()]
    cols = [c for c in ["notice_id", "publication_date", "buyer_name_raw",
                        "buyer_name_normalized", "buyer_key", "buyer_key_type",
                        "buyer_identity_source", "buyer_identity_confidence",
                        "enrichment_join_status", "department_key"] if c in unresolved.columns]
    return unresolved[cols].copy()


def alias_recovery_summary(l2_sources: pd.DataFrame, bridge: pd.DataFrame,
                           incremental_links: pd.DataFrame, cfg) -> pd.DataFrame:
    hist_max_year = cfg.pipeline.enrichment.alias_bridge.historical_max_year
    historical = l2_sources[l2_sources["publication_date"].dt.year <= hist_max_year]
    source_gained = l2_sources[
        l2_sources["buyer_siren_boamp_effective"].isna() & l2_sources["buyer_siren_l2"].notna()
    ]
    hist_gained = historical[
        historical["buyer_siren_boamp_effective"].isna() & historical["buyer_siren_l2"].notna()
    ]
    name_to_siren = l2_sources[
        l2_sources["buyer_key_type"].eq("NAME_FALLBACK") & l2_sources["buyer_siren_l2"].notna()
    ]
    return pd.DataFrame([
        {"metric": f"historical_to_{hist_max_year}_notices_gaining_siren", "value": len(hist_gained)},
        {"metric": "source_notices_gaining_siren_any_year", "value": len(source_gained)},
        {"metric": "name_fallback_sources_become_siren_keyed", "value": len(name_to_siren)},
        {"metric": "automatic_historical_aliases", "value": int((bridge["confidence_status"] == "AUTO_PROPAGATE_ELIGIBLE").sum()) if len(bridge) else 0},
        {"metric": "ambiguous_or_review_only_aliases", "value": int((bridge["confidence_status"] != "AUTO_PROPAGATE_ELIGIBLE").sum()) if len(bridge) else 0},
        {"metric": "ambiguous_multiple_siren_aliases", "value": int((bridge["confidence_status"] == "AMBIGUOUS_MULTIPLE_SIREN").sum()) if len(bridge) else 0},
        {"metric": "incremental_links_from_historical_aliases", "value": int((incremental_links.get("buyer_match_mechanism", pd.Series(dtype=str)) == "HISTORICAL_ALIAS_RECONCILIATION").sum()) if len(incremental_links) else 0},
    ])
