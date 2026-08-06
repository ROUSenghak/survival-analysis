"""Write canonical BOAMP corpus data-quality and freeze evidence tables."""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.config import ensure_output_dirs, load_config


def git_value(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def month_range(start: str, end: str) -> list[str]:
    cur = pd.Period(start, freq="M")
    last = pd.Period(end, freq="M")
    out = []
    while cur <= last:
        out.append(str(cur).replace("-", ""))
        cur += 1
    return out


def pct(series: pd.Series) -> float:
    return float(series.mean()) if len(series) else 0.0


def main() -> None:
    cfg = load_config(ROOT)
    ensure_output_dirs(cfg)
    out = cfg.paths.reports_data_quality
    out.mkdir(parents=True, exist_ok=True)

    clean = pd.read_csv(cfg.paths.interim_common_prepared, low_memory=False)
    sources = pd.read_csv(cfg.paths.processed_boamp_only / "boamp_only_sources.csv", low_memory=False)
    pairs = pd.read_csv(cfg.paths.processed_boamp_only / "boamp_only_candidate_pairs.csv", low_memory=False)
    links = pd.read_csv(cfg.paths.processed_boamp_only / "boamp_only_links_balanced.csv", low_memory=False)

    for df in [clean, sources, pairs, links]:
        for c in ["publication_date", "start_date", "estimated_end_date", "study_end_date"]:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce")

    raw_months = sorted(
        re.search(r"boamp_(\d{6})\.json$", p.name).group(1)
        for p in cfg.paths.raw_boamp_dir.glob("boamp_*.json")
        if re.search(r"boamp_(\d{6})\.json$", p.name)
    )
    expected_months = month_range(raw_months[0], raw_months[-1]) if raw_months else []
    missing_months = sorted(set(expected_months) - set(raw_months))

    funnel = pd.DataFrame(
        [
            {"step": "raw_monthly_json_files", "records": len(raw_months), "notes": f"{raw_months[0]}..{raw_months[-1]}" if raw_months else ""},
            {"step": "prepared_common_rows", "records": len(clean), "notes": "data/interim/boamp_common_prepared.csv"},
            {"step": "unique_notice_ids_prepared", "records": clean["notice_id"].nunique(), "notes": "notice_id grain check"},
            {"step": "appel_offre_rows", "records": int(clean["notice_type_normalized"].eq("APPEL_OFFRE").sum()), "notes": "notice-type selection"},
            {"step": "digital_ict_appel_offre_rows", "records": int(((clean["notice_type_normalized"].eq("APPEL_OFFRE")) & clean["is_digital_scope"]).sum()), "notes": "digital CPV or keyword scope"},
            {"step": "canonical_boamp_only_sources", "records": len(sources), "notes": "frozen source table"},
            {"step": "sources_with_nonmissing_buyer_key", "records": int(sources["buyer_key_type"].ne("MISSING").sum()), "notes": "eligible for linkage/censoring"},
            {"step": "candidate_pairs", "records": len(pairs), "notes": "dur_w6_same_buyer_expected_end_window_top30"},
            {"step": "balanced_composite_links", "records": len(links), "notes": "transparent baseline, not ground truth"},
        ]
    )
    funnel.to_csv(out / "filtering_funnel.csv", index=False)

    missingness_cols = [
        "notice_id", "publication_date", "buyer_name_normalized", "buyer_siret_clean",
        "buyer_siren_clean", "objet_clean", "cpv_clean", "declared_duration_months",
        "duration_quality_flag", "notice_type_normalized", "is_digital_scope",
    ]
    miss_rows = []
    for c in [c for c in missingness_cols if c in clean.columns]:
        miss_rows.append(
            {
                "column": c,
                "n_missing": int(clean[c].isna().sum()),
                "missing_rate": pct(clean[c].isna()),
                "n_distinct": int(clean[c].nunique(dropna=True)),
            }
        )
    pd.DataFrame(miss_rows).to_csv(out / "missingness_summary.csv", index=False)

    buyer_quality = (
        sources.groupby("buyer_key_type", dropna=False)
        .agg(
            n_sources=("notice_id", "count"),
            n_buyers=("buyer_key", "nunique"),
            median_sources_per_buyer=("buyer_key", lambda s: float(s.value_counts().median())),
            candidate_pair_count=("notice_id", lambda ids: int(pairs["source_notice_id"].isin(set(ids)).sum())),
            link_count=("notice_id", lambda ids: int(links["source_notice_id"].isin(set(ids)).sum())),
        )
        .reset_index()
    )
    buyer_quality["source_share"] = buyer_quality["n_sources"] / len(sources)
    buyer_quality.to_csv(out / "buyer_identifier_quality.csv", index=False)

    name_variation = (
        sources.groupby("buyer_key", dropna=False)
        .agg(
            n_sources=("notice_id", "count"),
            n_names=("buyer_name_normalized", "nunique"),
            buyer_key_type=("buyer_key_type", "first"),
        )
        .sort_values(["n_names", "n_sources"], ascending=False)
        .head(200)
        .reset_index()
    )
    name_variation.to_csv(out / "buyer_name_variation_top200.csv", index=False)

    activity = sources["buyer_key"].value_counts().rename_axis("buyer_key").reset_index(name="n_sources")
    activity["rank"] = range(1, len(activity) + 1)
    activity["cumulative_source_share"] = activity["n_sources"].cumsum() / activity["n_sources"].sum()
    activity.to_csv(out / "buyer_activity_concentration.csv", index=False)

    cpv_quality = (
        sources.assign(cpv_present=sources["cpv_clean"].notna())
        .groupby("cpv_division", dropna=False)
        .agg(
            n_sources=("notice_id", "count"),
            cpv_present_rate=("cpv_present", "mean"),
            generic_rate=("cpv_generic_flag", "mean"),
            link_count=("notice_id", lambda ids: int(links["source_notice_id"].isin(set(ids)).sum())),
        )
        .reset_index()
        .sort_values("n_sources", ascending=False)
    )
    cpv_quality["link_rate"] = cpv_quality["link_count"] / cpv_quality["n_sources"]
    cpv_quality.to_csv(out / "cpv_quality_by_division.csv", index=False)

    text = clean[["notice_id", "objet_clean", "notice_type_normalized", "publication_year"]].copy()
    text["text_length"] = text["objet_clean"].fillna("").str.len()
    text["token_count"] = text["objet_clean"].fillna("").str.split().map(len)
    text["text_exact_reuse_count"] = text.groupby("objet_clean")["notice_id"].transform("count")
    text_summary = pd.DataFrame(
        [
            {
                "population": "prepared_common",
                "n": len(text),
                "text_missing_rate": pct(text["objet_clean"].isna()),
                "text_length_p25": float(text["text_length"].quantile(0.25)),
                "text_length_p50": float(text["text_length"].quantile(0.50)),
                "text_length_p75": float(text["text_length"].quantile(0.75)),
                "token_count_p50": float(text["token_count"].quantile(0.50)),
                "exact_text_reuse_rate": pct(text["text_exact_reuse_count"].gt(1)),
            }
        ]
    )
    text_summary.to_csv(out / "text_quality_summary.csv", index=False)

    duration = (
        sources.groupby("duration_quality_flag", dropna=False)
        .agg(n_sources=("notice_id", "count"), median_duration=("declared_duration_months", "median"))
        .reset_index()
    )
    duration["source_share"] = duration["n_sources"] / len(sources)
    duration.to_csv(out / "duration_quality.csv", index=False)

    exclusions = pd.DataFrame(
        [
            {
                "exclusion": "non_appel_offre_or_non_digital_scope",
                "n_records": int(len(clean) - len(sources)),
                "consequence": "not eligible as source notices",
            },
            {
                "exclusion": "missing_buyer_key",
                "n_records": int(sources["buyer_key_type"].eq("MISSING").sum()),
                "consequence": "excluded from event/censoring dataset",
            },
            {
                "exclusion": "sources_with_no_candidates",
                "n_records": int(len(set(sources["notice_id"]) - set(pairs["source_notice_id"]))),
                "consequence": "operationally censored, not confirmed non-renewal",
            },
            {
                "exclusion": "rank1_below_balanced_threshold",
                "n_records": int(pairs[pairs["candidate_rank"].eq(1)]["composite_score"].lt(cfg.pipeline.thresholds.balanced).sum()),
                "consequence": "candidate rejected by transparent baseline",
            },
        ]
    )
    exclusions.to_csv(out / "exclusions_summary.csv", index=False)

    manifest = {
        "run_id": "canonical_boamp_corpus_quality_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "git_head": git_value("rev-parse", "HEAD"),
        "git_status_porcelain": git_value("status", "--short"),
        "raw_month_coverage": {
            "n_raw_month_files": len(raw_months),
            "first_month": raw_months[0] if raw_months else None,
            "last_month": raw_months[-1] if raw_months else None,
            "n_expected_months_between_first_last": len(expected_months),
            "missing_months_between_first_last": missing_months,
        },
        "canonical_layer": "boamp_only",
        "counts": {
            "prepared_common_rows": int(len(clean)),
            "prepared_unique_notice_ids": int(clean["notice_id"].nunique()),
            "sources": int(len(sources)),
            "candidate_pairs": int(len(pairs)),
            "balanced_composite_links": int(len(links)),
        },
        "outputs": [
            "reports/tables/data_quality/filtering_funnel.csv",
            "reports/tables/data_quality/missingness_summary.csv",
            "reports/tables/data_quality/buyer_identifier_quality.csv",
            "reports/tables/data_quality/buyer_name_variation_top200.csv",
            "reports/tables/data_quality/buyer_activity_concentration.csv",
            "reports/tables/data_quality/cpv_quality_by_division.csv",
            "reports/tables/data_quality/text_quality_summary.csv",
            "reports/tables/data_quality/duration_quality.csv",
            "reports/tables/data_quality/exclusions_summary.csv",
        ],
    }
    (out / "corpus_freeze_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"WROTE {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
