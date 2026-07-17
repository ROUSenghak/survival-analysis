"""
Step 8 & 9 - Run the initial M0 linkage (broad/balanced/strict) and produce
quality-check tables.

Inputs:
  data/processed/boamp_clean_m0_no_enrichment.csv
  data/processed/boamp_m0_sources.csv
  data/processed/boamp_m0_candidate_pairs.csv

Outputs:
  data/processed/boamp_m0_links_broad.csv
  data/processed/boamp_m0_links_balanced.csv
  data/processed/boamp_m0_links_strict.csv
  data/processed/boamp_survival_m0_balanced.csv
  reports/tables/m0_method_summary.csv
  reports/tables/m0_event_counts.csv
  reports/tables/m0_score_distribution_summary.csv
  reports/tables/m0_buyer_key_type_summary.csv
  reports/tables/m0_data_quality_summary.csv
  reports/tables/m0_preprocessing_quality_checks.csv

Thresholds are derived from the observed distribution of best-candidate
(rank 1) composite scores (25th/50th/75th percentile), not hardcoded a
priori - see reports/boamp_m0_preprocessing_report.md for the rationale and
resulting values.
"""

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
TABLES_DIR.mkdir(parents=True, exist_ok=True)


CODE_STR_COLS = ["buyer_siret_clean", "buyer_siren_clean", "cpv_clean",
                  "cpv_division", "cpv_group", "cpv_class", "cpv_category"]


def load_inputs():
    clean = pd.read_csv(PROCESSED_DIR / "boamp_clean_m0_no_enrichment.csv", low_memory=False,
                         dtype={c: str for c in CODE_STR_COLS},
                         parse_dates=["publication_date", "start_date"])
    sources = pd.read_csv(PROCESSED_DIR / "boamp_m0_sources.csv",
                           dtype={c: str for c in CODE_STR_COLS},
                           parse_dates=["publication_date", "start_date", "estimated_end_date", "study_end_date"])
    pairs = pd.read_csv(PROCESSED_DIR / "boamp_m0_candidate_pairs.csv",
                         parse_dates=["source_date", "candidate_date", "expected_end_date"])
    return clean, sources, pairs


def build_variant(pairs: pd.DataFrame, threshold: float, variant_name: str) -> pd.DataFrame:
    rank1 = pairs[pairs["candidate_rank"] == 1].copy()
    linked = rank1[rank1["m0_composite_score"] >= threshold].copy()
    linked["variant"] = variant_name
    linked["threshold_used"] = threshold
    cols = ["source_notice_id", "candidate_notice_id", "buyer_key", "buyer_key_type",
            "source_date", "candidate_date", "gap_months", "expected_end_date",
            "abs_gap_to_expected_end", "s_time", "s_text", "s_cpv", "s_buyer",
            "m0_composite_score", "cpv_missing", "cpv_generic_flag",
            "candidate_rank", "top1_top2_margin", "n_candidates_for_source",
            "variant", "threshold_used"]
    return linked[cols]


def build_survival_dataset(sources: pd.DataFrame, links: pd.DataFrame, variant_name: str) -> pd.DataFrame:
    eligible = sources[sources["buyer_key_type"] != "MISSING"].copy()
    link_map = links.set_index("source_notice_id")

    def row_to_survival(row):
        nid = row["notice_id"]
        study_end = row["study_end_date"]
        if nid in link_map.index:
            link = link_map.loc[nid]
            event = 1
            time_months = link["gap_months"]
            candidate_id = link["candidate_notice_id"]
            score = link["m0_composite_score"]
        else:
            event = 0
            time_months = (study_end - row["publication_date"]).total_seconds() / (3600 * 24 * 30.44)
            candidate_id = None
            score = None
        return pd.Series({
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
            "event": event,
            "time_to_event_or_censor_months": time_months,
            "linked_candidate_notice_id": candidate_id,
            "m0_composite_score": score,
            "variant": variant_name,
        })

    return eligible.apply(row_to_survival, axis=1)


def main():
    clean, sources, pairs = load_inputs()
    eligible_sources = sources[sources["buyer_key_type"] != "MISSING"]

    rank1 = pairs[pairs["candidate_rank"] == 1] if len(pairs) else pd.DataFrame(columns=pairs.columns)
    if len(rank1):
        p25, p50, p75 = rank1["m0_composite_score"].quantile([0.25, 0.5, 0.75]).tolist()
    else:
        p25 = p50 = p75 = 0.0
    thresholds = {"broad": p25, "balanced": p50, "strict": p75}
    print(f"Derived thresholds from rank-1 composite score distribution: {thresholds}")

    variants = {}
    for name, thr in thresholds.items():
        variants[name] = build_variant(pairs, thr, name)
        out_path = PROCESSED_DIR / f"boamp_m0_links_{name}.csv"
        variants[name].to_csv(out_path, index=False)
        print(f"Wrote {out_path} ({len(variants[name])} links)")

    survival = build_survival_dataset(sources, variants["balanced"], "balanced")
    survival_path = PROCESSED_DIR / "boamp_survival_m0_balanced.csv"
    survival.to_csv(survival_path, index=False)
    print(f"Wrote survival dataset -> {survival_path} ({len(survival)} rows, "
          f"{survival['event'].sum()} events)")

    # ---- m0_method_summary.csv ----
    method_rows = []
    for name, thr in thresholds.items():
        linked = variants[name]
        method_rows.append({
            "variant": name,
            "threshold_composite_score": thr,
            "n_sources_eligible": len(eligible_sources),
            "n_linked_events": len(linked),
            "event_rate": len(linked) / len(eligible_sources) if len(eligible_sources) else 0.0,
            "median_gap_months_linked": linked["gap_months"].median() if len(linked) else np.nan,
            "median_composite_score_linked": linked["m0_composite_score"].median() if len(linked) else np.nan,
        })
    pd.DataFrame(method_rows).to_csv(TABLES_DIR / "m0_method_summary.csv", index=False)

    # ---- m0_event_counts.csv (variant x publication year) ----
    sources_with_year = sources.assign(publication_year=sources["publication_date"].dt.year)
    event_rows = []
    for name in thresholds:
        linked_ids = set(variants[name]["source_notice_id"])
        for year, grp in sources_with_year[sources_with_year["buyer_key_type"] != "MISSING"].groupby("publication_year"):
            n_events = grp["notice_id"].isin(linked_ids).sum()
            event_rows.append({
                "variant": name, "publication_year": int(year),
                "n_sources": len(grp), "n_events": int(n_events),
                "event_rate": n_events / len(grp) if len(grp) else 0.0,
            })
    pd.DataFrame(event_rows).to_csv(TABLES_DIR / "m0_event_counts.csv", index=False)

    # ---- m0_score_distribution_summary.csv ----
    score_cols = ["m0_composite_score", "s_text", "s_cpv", "s_time", "s_buyer"]
    dist_rows = []
    for label, frame in [("all_candidate_pairs", pairs), ("rank1_best_candidate", rank1)]:
        for col in score_cols:
            if col not in frame.columns or not len(frame):
                continue
            desc = frame[col].describe(percentiles=[0.25, 0.5, 0.75])
            dist_rows.append({
                "population": label, "score": col,
                "count": desc.get("count"), "mean": desc.get("mean"), "std": desc.get("std"),
                "min": desc.get("min"), "p25": desc.get("25%"), "p50": desc.get("50%"),
                "p75": desc.get("75%"), "max": desc.get("max"),
            })
    pd.DataFrame(dist_rows).to_csv(TABLES_DIR / "m0_score_distribution_summary.csv", index=False)

    # ---- m0_buyer_key_type_summary.csv ----
    bkt_all = clean["buyer_key_type"].value_counts(dropna=False).rename("n_all_notices")
    bkt_sources = sources["buyer_key_type"].value_counts(dropna=False).rename("n_appel_offre_sources")
    bkt_events_balanced = sources[sources["notice_id"].isin(variants["balanced"]["source_notice_id"])]["buyer_key_type"].value_counts(dropna=False).rename("n_balanced_events")
    bkt_summary = pd.concat([bkt_all, bkt_sources, bkt_events_balanced], axis=1).fillna(0).astype(int)
    bkt_summary.index.name = "buyer_key_type"
    bkt_summary.reset_index().to_csv(TABLES_DIR / "m0_buyer_key_type_summary.csv", index=False)

    # ---- m0_data_quality_summary.csv (per-variant compact snapshot) ----
    top_buyers_balanced = (
        sources[sources["notice_id"].isin(variants["balanced"]["source_notice_id"])]
        .groupby("buyer_key").size().sort_values(ascending=False).head(10)
    )
    n_sources_with_candidates = pairs["source_notice_id"].nunique() if len(pairs) else 0
    dq_rows = [
        {"metric": "n_eligible_sources", "value": len(eligible_sources)},
        {"metric": "n_candidate_pairs_total", "value": len(pairs)},
        {"metric": "avg_candidates_per_source", "value": pairs.groupby("source_notice_id").size().mean() if len(pairs) else 0.0},
        {"metric": "sources_without_candidates", "value": len(eligible_sources) - n_sources_with_candidates},
        {"metric": "broad_event_count", "value": len(variants["broad"])},
        {"metric": "balanced_event_count", "value": len(variants["balanced"])},
        {"metric": "strict_event_count", "value": len(variants["strict"])},
        {"metric": "top_buyer_balanced_events_max", "value": int(top_buyers_balanced.iloc[0]) if len(top_buyers_balanced) else 0},
    ]
    pd.DataFrame(dq_rows).to_csv(TABLES_DIR / "m0_data_quality_summary.csv", index=False)

    # ---- Step 9: reports/tables/m0_preprocessing_quality_checks.csv ----
    dup_ids = clean["notice_id"].duplicated().sum()
    n_appel_offre = (clean["notice_type_normalized"] == "APPEL_OFFRE").sum()
    n_attribution = (clean["notice_type_normalized"] == "ATTRIBUTION").sum()
    n_other = (clean["notice_type_normalized"] == "OTHER").sum()
    missing_buyer_key_rate = (clean["buyer_key_type"] == "MISSING").mean()
    raw_siret_rate = (clean["buyer_key_type"] == "RAW_SIRET").mean()
    raw_siren_rate = (clean["buyer_key_type"] == "RAW_SIREN").mean()
    name_fallback_rate = (clean["buyer_key_type"] == "NAME_FALLBACK").mean()
    cpv_coverage = 1 - sources["cpv_clean"].isna().mean()
    generic_cpv_share = sources["cpv_generic_flag"].mean()
    duration_imputation_rate = sources["dur_was_imputed"].mean()
    text_missingness = clean["object_missing_flag"].mean()

    # A candidate notice being picked as the best match for two or more
    # DIFFERENT source notices (within the same variant) is the suspicious
    # case - one later tender can't plausibly be the recurrence of two
    # unrelated earlier ones. Checked on the balanced variant only: checking
    # across broad/balanced/strict together would trivially double count the
    # same (source, candidate) link once per variant it survives in.
    repeated_candidate_links = variants["balanced"]["candidate_notice_id"].value_counts()
    n_suspicious_repeated_candidates = int((repeated_candidate_links > 1).sum())

    top_buyers_events = (
        sources[sources["notice_id"].isin(variants["balanced"]["source_notice_id"])]
        .groupby("buyer_key").size().sort_values(ascending=False).head(5)
    )

    checks = [
        {"check": "raw_notice_count", "value": None, "note": "see reports/tables/boamp_download_summary.csv"},
        {"check": "cleaned_notice_count", "value": len(clean)},
        {"check": "appel_offre_count", "value": int(n_appel_offre)},
        {"check": "attribution_count", "value": int(n_attribution)},
        {"check": "other_notice_type_count", "value": int(n_other)},
        {"check": "date_range_min", "value": str(clean["publication_date"].min())},
        {"check": "date_range_max", "value": str(clean["publication_date"].max())},
        {"check": "duplicate_notice_ids", "value": int(dup_ids)},
        {"check": "missing_buyer_key_rate", "value": round(float(missing_buyer_key_rate), 4)},
        {"check": "buyer_key_type_raw_siret_rate", "value": round(float(raw_siret_rate), 4)},
        {"check": "buyer_key_type_raw_siren_rate", "value": round(float(raw_siren_rate), 4)},
        {"check": "buyer_key_type_name_fallback_rate", "value": round(float(name_fallback_rate), 4)},
        {"check": "cpv_coverage_sources", "value": round(float(cpv_coverage), 4)},
        {"check": "generic_cpv_share_sources", "value": round(float(generic_cpv_share), 4)},
        {"check": "duration_imputation_rate_sources", "value": round(float(duration_imputation_rate), 4)},
        {"check": "text_missingness_rate", "value": round(float(text_missingness), 4)},
        {"check": "candidate_pair_count", "value": len(pairs)},
        {"check": "avg_candidates_per_source", "value": round(float(pairs.groupby("source_notice_id").size().mean()), 3) if len(pairs) else 0.0},
        {"check": "sources_without_candidates", "value": len(eligible_sources) - n_sources_with_candidates},
        {"check": "m0_event_count_broad", "value": len(variants["broad"])},
        {"check": "m0_event_count_balanced", "value": len(variants["balanced"])},
        {"check": "m0_event_count_strict", "value": len(variants["strict"])},
        {"check": "m0_event_rate_broad", "value": round(len(variants["broad"]) / len(eligible_sources), 4) if len(eligible_sources) else 0.0},
        {"check": "m0_event_rate_balanced", "value": round(len(variants["balanced"]) / len(eligible_sources), 4) if len(eligible_sources) else 0.0},
        {"check": "m0_event_rate_strict", "value": round(len(variants["strict"]) / len(eligible_sources), 4) if len(eligible_sources) else 0.0},
        {"check": "top_buyer_by_event_count_balanced", "value": (top_buyers_events.index[0] if len(top_buyers_events) else None)},
        {"check": "top_buyer_event_count_balanced", "value": int(top_buyers_events.iloc[0]) if len(top_buyers_events) else 0},
        {"check": "candidate_notices_claimed_by_multiple_sources_balanced", "value": n_suspicious_repeated_candidates},
    ]
    pd.DataFrame(checks).to_csv(TABLES_DIR / "m0_preprocessing_quality_checks.csv", index=False)

    print("\n=== Linkage summary ===")
    for name, thr in thresholds.items():
        print(f"{name}: threshold={thr:.4f}, events={len(variants[name])}, "
              f"rate={len(variants[name]) / len(eligible_sources):.4f}")


if __name__ == "__main__":
    main()
