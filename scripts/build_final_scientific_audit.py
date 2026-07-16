"""
Build the final scientific audit package for the BOAMP recurrence study.

This script is deliberately additive. It reads the current M0/M1/sensitivity
outputs, creates consolidated audit/decision tables and reviewer-facing
validation files, and leaves all official linkage and survival datasets
unchanged.
"""

from __future__ import annotations

import hashlib
import math
import subprocess
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
R = ROOT / "reports"
T = R / "tables"
T.mkdir(parents=True, exist_ok=True)

DATE = "2026-07-16"
ID_DTYPE = {
    "notice_id": str,
    "source_notice_id": str,
    "candidate_notice_id": str,
    "linked_candidate_notice_id": str,
    "buyer_key": str,
    "buyer_key_type": str,
    "buyer_key_m0_source": str,
    "buyer_key_m0_candidate": str,
    "buyer_key_type_source": str,
    "buyer_key_type_candidate": str,
    "cpv_division": str,
    "cpv_category": str,
    "cpv_clean": str,
}


def read_csv(path: Path, **kwargs) -> pd.DataFrame:
    dtype = kwargs.pop("dtype", {})
    merged_dtype = {k: v for k, v in ID_DTYPE.items() if k not in dtype}
    merged_dtype.update(dtype)
    return pd.read_csv(path, dtype=merged_dtype, low_memory=False, **kwargs)


def sha256(path: Path) -> str | None:
    if not path.exists() or path.is_dir():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_shape(path: Path) -> tuple[int | None, int | None]:
    if not path.exists() or path.is_dir():
        return None, None
    try:
        df = pd.read_csv(path, nrows=0)
    except Exception:
        return None, None
    rows = sum(1 for _ in path.open("r", encoding="utf-8", errors="replace")) - 1
    return rows, len(df.columns)


def git_state() -> dict[str, str]:
    def run(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return ""

    return {
        "commit": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "short_status": run(["git", "status", "--short"]),
    }


def markdown_table(df: pd.DataFrame, columns: list[str] | None = None, max_rows: int | None = None) -> str:
    """Render a small GitHub-style markdown table without optional deps."""
    if columns is not None:
        df = df[columns]
    if max_rows is not None:
        df = df.head(max_rows)
    if df.empty:
        return "_No rows._"
    headers = list(df.columns)

    def fmt(value: object) -> str:
        if pd.isna(value):
            text = ""
        elif isinstance(value, float):
            text = f"{value:.6g}"
        else:
            text = str(value)
        return text.replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(fmt(row[col]) for col in headers) + " |")
    return "\n".join(lines)


def link_keys(df: pd.DataFrame) -> set[tuple[str, str]]:
    if df.empty:
        return set()
    return set(zip(df["source_notice_id"], df["candidate_notice_id"]))


def source_set(df: pd.DataFrame) -> set[str]:
    if df.empty:
        return set()
    return set(df["source_notice_id"])


def candidate_reuse_stats(links: pd.DataFrame) -> dict[str, float]:
    if links.empty:
        return {
            "unique_selected_candidates": 0,
            "reused_candidate_count": 0,
            "candidate_reuse_rate": 0.0,
            "maximum_candidate_multiplicity": 0,
        }
    counts = links["candidate_notice_id"].value_counts()
    return {
        "unique_selected_candidates": int(counts.size),
        "reused_candidate_count": int((counts > 1).sum()),
        "candidate_reuse_rate": float((counts > 1).mean()),
        "maximum_candidate_multiplicity": int(counts.max()),
    }


def load_core() -> dict[str, pd.DataFrame]:
    date_cols_sources = ["publication_date", "start_date", "estimated_end_date", "study_end_date"]
    date_cols_pairs = ["source_date", "candidate_date", "expected_end_date"]
    return {
        "sources": read_csv(P / "boamp_m0_sources.csv", parse_dates=date_cols_sources),
        "pairs_m0": read_csv(P / "boamp_m0_candidate_pairs.csv", parse_dates=date_cols_pairs),
        "links_m0": read_csv(P / "boamp_m0_links_balanced.csv", parse_dates=date_cols_pairs),
        "links_m0_broad": read_csv(P / "boamp_m0_links_broad.csv", parse_dates=date_cols_pairs),
        "links_m0_strict": read_csv(P / "boamp_m0_links_strict.csv", parse_dates=date_cols_pairs),
        "surv_m0": read_csv(P / "boamp_survival_m0_balanced.csv", parse_dates=date_cols_sources),
        "pairs_m1": read_csv(P / "boamp_m1_candidate_pairs.csv", parse_dates=date_cols_pairs),
        "links_m1": read_csv(P / "boamp_m1_links_balanced.csv", parse_dates=date_cols_pairs),
        "pairs_profile": read_csv(P / "boamp_m1_profile_audited_candidate_pairs.csv", parse_dates=date_cols_pairs),
        "links_profile": read_csv(P / "boamp_m1_profile_audited_links.csv", parse_dates=date_cols_pairs),
        "surv_m1": read_csv(P / "boamp_survival_m1_balanced.csv", parse_dates=date_cols_sources),
    }


def build_method_inventory(core: dict[str, pd.DataFrame]) -> pd.DataFrame:
    m0 = core["links_m0"]
    m1 = core["links_m1"]
    profile = core["links_profile"]
    pairs_m0 = core["pairs_m0"]
    pairs_m1 = core["pairs_m1"]
    sources = core["sources"]
    eligible = sources[sources["buyer_key_type"] != "MISSING"]
    n_eligible = len(eligible)
    m0_keys = link_keys(m0)
    m1_keys = link_keys(m1)

    rows = []

    def add_method(
        method_id: str,
        role: str,
        status: str,
        source_population: str,
        buyer_identity: str,
        candidate_generation: str,
        scoring: str,
        threshold: str,
        links: pd.DataFrame,
        pairs: pd.DataFrame | None,
        survival_path: str,
        notes: str,
    ) -> None:
        reuse = candidate_reuse_stats(links)
        rows.append(
            {
                "method_id": method_id,
                "role": role,
                "status": status,
                "source_population": source_population,
                "buyer_identity": buyer_identity,
                "candidate_generation": candidate_generation,
                "scoring": scoring,
                "threshold_or_selection": threshold,
                "eligible_sources": n_eligible,
                "sources_with_candidates": int(pairs["source_notice_id"].nunique()) if pairs is not None and not pairs.empty else np.nan,
                "candidate_pairs": len(pairs) if pairs is not None else np.nan,
                "accepted_links": len(links),
                "proxy_event_rate": len(links) / n_eligible if n_eligible else np.nan,
                "unique_selected_candidates": reuse["unique_selected_candidates"],
                "candidate_reuse_rate": reuse["candidate_reuse_rate"],
                "maximum_candidate_multiplicity": reuse["maximum_candidate_multiplicity"],
                "jaccard_vs_m0_balanced": len(link_keys(links) & m0_keys) / len(link_keys(links) | m0_keys)
                if (link_keys(links) | m0_keys)
                else np.nan,
                "jaccard_vs_m1_balanced": len(link_keys(links) & m1_keys) / len(link_keys(links) | m1_keys)
                if (link_keys(links) | m1_keys)
                else np.nan,
                "survival_dataset": survival_path,
                "notes": notes,
            }
        )

    add_method(
        "M0_BALANCED_OFFICIAL",
        "primary",
        "active_verified_proxy",
        "BOAMP APPEL_OFFRE digital/ICT sources in Pays de la Loire, nonmissing buyer key",
        "BOAMP-only raw SIRET/SIREN when present, otherwise normalized buyer-name fallback",
        "same buyer_key; later notice; 6-month window around estimated end date; max 30 temporally nearest candidates",
        "0.35 text TF-IDF + 0.30 CPV hierarchy + 0.25 temporal proximity + 0.10 buyer-key reliability",
        "rank-1 candidate with composite score >= current median rank-1 threshold",
        m0,
        pairs_m0,
        "data/processed/boamp_survival_m0_balanced.csv",
        "Official baseline. Proxy recurrence only, not legal renewal.",
    )
    add_method(
        "M1_BUYER_SIREN_ENRICHED",
        "sensitivity",
        "implemented_unvalidated_sensitivity",
        "same source population as M0",
        "M0 identity plus external SIREN/SIRET buyer reconciliation and conservative historical aliases",
        "same temporal design and candidate cap as M0, but buyer blocking can be reconciled across enriched identity",
        "same text, CPV, temporal and ranking components as M0; buyer score reflects reconciliation mechanism",
        "same M0 balanced threshold",
        m1,
        pairs_m1,
        "data/processed/boamp_survival_m1_balanced.csv",
        "Raises coverage but incremental links require manual validation.",
    )
    add_method(
        "M1_PROFILE_AUDITED",
        "sensitivity/audit",
        "implemented_profile_evidence_unvalidated",
        "same source population as M0/M1",
        "M1 buyer identity supplemented by procurement-profile domain evidence",
        "same M1 candidate universe after profile-evidence audit; not a new legal-identity source",
        "same M1 score; profile evidence annotates support/conflict",
        "same M0 balanced threshold",
        profile,
        core.get("pairs_profile"),
        "data/processed/boamp_survival_m1_profile_audited.csv",
        "Profile evidence classifies support/conflict; it is not verified ground truth.",
    )
    add_method(
        "M0_BROAD_THRESHOLD",
        "threshold_sensitivity",
        "implemented_sensitivity",
        "same as M0",
        "same as M0",
        "same as M0",
        "same as M0",
        "rank-1 score >= lower percentile threshold",
        core["links_m0_broad"],
        pairs_m0,
        "data/processed/boamp_survival_m0_broad.csv",
        "Lower-threshold sensitivity, not primary.",
    )
    add_method(
        "M0_STRICT_THRESHOLD",
        "threshold_sensitivity",
        "implemented_sensitivity",
        "same as M0",
        "same as M0",
        "same as M0",
        "same as M0",
        "rank-1 score >= upper percentile threshold",
        core["links_m0_strict"],
        pairs_m0,
        "data/processed/boamp_survival_m0_strict.csv",
        "Higher-threshold sensitivity, not primary.",
    )

    out = pd.DataFrame(rows)
    out.to_csv(T / "final_method_inventory.csv", index=False)
    return out


def build_authoritative_files() -> pd.DataFrame:
    rows = []
    files = [
        ("primary_clean_data", "data/processed/boamp_clean_m0_no_enrichment.csv", "authoritative M0 cleaned notice table"),
        ("primary_sources", "data/processed/boamp_m0_sources.csv", "authoritative M0 eligible source table"),
        ("primary_candidate_pairs", "data/processed/boamp_m0_candidate_pairs.csv", "authoritative M0 candidate-pair table"),
        ("primary_links", "data/processed/boamp_m0_links_balanced.csv", "authoritative M0 accepted proxy links"),
        ("primary_survival", "data/processed/boamp_survival_m0_balanced.csv", "official survival handoff"),
        ("m1_enriched_notices", "data/processed/boamp_clean_m1_buyer_enriched.csv", "M1 sensitivity cleaned notices"),
        ("m1_candidate_pairs", "data/processed/boamp_m1_candidate_pairs.csv", "M1 sensitivity candidate pairs"),
        ("m1_links", "data/processed/boamp_m1_links_balanced.csv", "M1 sensitivity accepted links"),
        ("m1_survival", "data/processed/boamp_survival_m1_balanced.csv", "M1 sensitivity survival handoff"),
        ("profile_audit_links", "data/processed/boamp_m1_profile_audited_links.csv", "M1 profile-evidence audit links"),
        ("source_level_diagnostics", "reports/tables/final_source_linkage_diagnostics.csv", "one-row-per-source linkage explanation"),
        ("linkage_funnel", "reports/tables/final_linkage_funnel.csv", "M0 funnel from eligible sources to accepted links"),
        ("method_inventory", "reports/tables/final_method_inventory.csv", "method terminology and status map"),
        ("decision_record", "reports/final_method_selection_record.md", "formal method-selection record"),
        ("repro_manifest", "reports/final_reproducibility_manifest.md", "final reproducibility manifest"),
        ("validation_template", "scripts/analyze_manual_validation_labels.py", "label-analysis code for completed reviews"),
    ]
    for role, rel, description in files:
        path = ROOT / rel
        nrows, ncols = file_shape(path)
        rows.append(
            {
                "role": role,
                "path": rel,
                "description": description,
                "exists": path.exists(),
                "row_count": nrows,
                "column_count": ncols,
                "sha256": sha256(path),
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(T / "final_authoritative_files.csv", index=False)
    return out


def build_source_diagnostics(core: dict[str, pd.DataFrame]) -> pd.DataFrame:
    sources = core["sources"].copy()
    pairs = core["pairs_m0"].copy()
    links_m0 = core["links_m0"].copy()
    pairs_m1 = core["pairs_m1"].copy()
    links_m1 = core["links_m1"].copy()
    profile = core["links_profile"].copy()

    eligible = sources[sources["buyer_key_type"] != "MISSING"].copy()
    candidate_counts = pairs.groupby("source_notice_id").size().rename("m0_candidate_count")
    best = (
        pairs.sort_values(["source_notice_id", "m0_composite_score"], ascending=[True, False])
        .groupby("source_notice_id")
        .head(1)
        .set_index("source_notice_id")
    )
    second_scores = pairs[pairs["candidate_rank"] == 2].set_index("source_notice_id")["m0_composite_score"]
    m1_candidate_counts = pairs_m1.groupby("source_notice_id").size().rename("m1_candidate_count")
    m0_links = links_m0.set_index("source_notice_id")
    m1_links = links_m1.set_index("source_notice_id")
    profile_links = profile.set_index("source_notice_id")
    candidate_multiplicity = links_m0["candidate_notice_id"].value_counts()
    m1_candidate_multiplicity = links_m1["candidate_notice_id"].value_counts()

    window_months = 6
    window_file = P / "_m0_window_months.txt"
    if window_file.exists():
        try:
            window_months = int(float(window_file.read_text().strip()))
        except ValueError:
            pass
    window_days = window_months * 30.44

    rows = []
    for buyer_key, group in eligible.sort_values(["buyer_key", "publication_date"]).groupby("buyer_key", dropna=False):
        dates = pd.to_datetime(group["publication_date"]).to_numpy()
        for _, row in group.iterrows():
            notice_id = row["notice_id"]
            publication_date = row["publication_date"]
            later = dates > np.datetime64(publication_date)
            later_count = int(later.sum())
            in_window_count = 0
            if pd.notna(row["estimated_end_date"]):
                lo = row["estimated_end_date"] - pd.Timedelta(days=window_days)
                hi = row["estimated_end_date"] + pd.Timedelta(days=window_days)
                in_window_count = int((later & (dates >= np.datetime64(lo)) & (dates <= np.datetime64(hi))).sum())

            m0_count = int(candidate_counts.get(notice_id, 0))
            m1_count = int(m1_candidate_counts.get(notice_id, 0))
            is_m0_linked = notice_id in m0_links.index
            is_m1_linked = notice_id in m1_links.index
            has_profile = notice_id in profile_links.index
            best_row = best.loc[notice_id] if notice_id in best.index else None

            flags = []
            if later_count == 0:
                flags.append("no_later_same_buyer_notice")
            if later_count > 0 and in_window_count == 0:
                flags.append("later_same_buyer_outside_m0_window")
            if m0_count == 0 and m1_count > 0:
                flags.append("candidate_pool_gained_under_m1")
            if is_m1_linked and not is_m0_linked:
                flags.append("m1_only_link")
            if is_m0_linked and not is_m1_linked:
                flags.append("m0_only_link")
            if is_m0_linked and is_m1_linked:
                m0_cand = str(m0_links.loc[notice_id, "candidate_notice_id"])
                m1_cand = str(m1_links.loc[notice_id, "candidate_notice_id"])
                flags.append("same_candidate_m0_m1" if m0_cand == m1_cand else "different_candidate_m0_m1")
            if best_row is not None and float(best_row.get("top1_top2_margin", np.nan)) < 0.05:
                flags.append("low_top1_top2_margin")
            if m0_count > 1:
                flags.append("ambiguous_multiple_candidates")
            if is_m0_linked:
                cand = str(m0_links.loc[notice_id, "candidate_notice_id"])
                if int(candidate_multiplicity.get(cand, 0)) > 1:
                    flags.append("selected_candidate_reused")

            if is_m0_linked:
                primary_reason = "linked_m0_balanced_proxy_event"
            elif m0_count > 0:
                primary_reason = "candidate_pool_below_balanced_threshold"
            elif later_count == 0:
                primary_reason = "no_later_same_buyer_notice_observed"
            elif in_window_count == 0:
                primary_reason = "later_same_buyer_notice_outside_m0_window"
            elif m1_count > 0:
                primary_reason = "possible_buyer_fragmentation_or_m1_reconciliation"
            else:
                primary_reason = "unresolved_blocking_or_candidate_generation_failure"

            selected_m0 = str(m0_links.loc[notice_id, "candidate_notice_id"]) if is_m0_linked else ""
            selected_m1 = str(m1_links.loc[notice_id, "candidate_notice_id"]) if is_m1_linked else ""
            rows.append(
                {
                    "source_notice_id": notice_id,
                    "publication_date": publication_date,
                    "publication_year": int(publication_date.year),
                    "cpv_division": row.get("cpv_division"),
                    "buyer_key": buyer_key,
                    "buyer_key_type": row.get("buyer_key_type"),
                    "buyer_key_provenance": row.get("buyer_key_type"),
                    "duration_months": row.get("declared_duration_months"),
                    "duration_imputation_status": "imputed" if bool(row.get("dur_was_imputed")) else "observed",
                    "estimated_end_date": row.get("estimated_end_date"),
                    "observable_followup_months": (row["study_end_date"] - publication_date).days / 30.44
                    if pd.notna(row.get("study_end_date")) and pd.notna(publication_date)
                    else np.nan,
                    "buyer_publication_frequency": len(group),
                    "later_same_buyer_notice_count": later_count,
                    "later_same_buyer_in_m0_window_count": in_window_count,
                    "m0_candidate_count": m0_count,
                    "m0_best_candidate_notice_id": str(best_row["candidate_notice_id"]) if best_row is not None else "",
                    "m0_best_score": float(best_row["m0_composite_score"]) if best_row is not None else np.nan,
                    "m0_second_best_score": float(second_scores.get(notice_id, np.nan)),
                    "m0_score_margin": float(best_row["top1_top2_margin"]) if best_row is not None else np.nan,
                    "m0_accepted": is_m0_linked,
                    "m0_selected_candidate_notice_id": selected_m0,
                    "m0_selected_candidate_reuse_count": int(candidate_multiplicity.get(selected_m0, 0)) if selected_m0 else 0,
                    "m1_candidate_count": m1_count,
                    "m1_accepted": is_m1_linked,
                    "m1_selected_candidate_notice_id": selected_m1,
                    "m1_selected_candidate_reuse_count": int(m1_candidate_multiplicity.get(selected_m1, 0)) if selected_m1 else 0,
                    "m1_buyer_match_mechanism": str(m1_links.loc[notice_id, "buyer_match_mechanism"]) if is_m1_linked else "",
                    "profile_audited_link_present": has_profile,
                    "profile_evidence_status": str(profile_links.loc[notice_id, "profile_evidence_status"]) if has_profile else "",
                    "primary_linkage_status_reason": primary_reason,
                    "secondary_diagnostic_flags": ";".join(sorted(set(flags))),
                }
            )

    out = pd.DataFrame(rows)
    out.to_csv(T / "final_source_linkage_diagnostics.csv", index=False)
    return out


def build_funnels(diag: pd.DataFrame, core: dict[str, pd.DataFrame]) -> None:
    m0_accepted = diag["m0_accepted"].astype(bool)
    adequate_followup = diag["observable_followup_months"] >= 6
    rows = [
        ("eligible_sources", len(diag), "nonmissing buyer key source notices"),
        ("adequate_followup_6m", int(adequate_followup.sum()), "at least 6 months observable follow-up"),
        ("later_same_buyer_evidence", int((diag["later_same_buyer_notice_count"] > 0).sum()), "later same M0 buyer_key notice exists"),
        ("inside_m0_temporal_block", int((diag["later_same_buyer_in_m0_window_count"] > 0).sum()), "later same-buyer notice inside M0 duration-centered window"),
        ("scored_candidate_pool", int((diag["m0_candidate_count"] > 0).sum()), "entered the scored candidate-pair table"),
        ("accepted_m0_balanced_proxy_link", int(m0_accepted.sum()), "rank-1 candidate accepted by balanced threshold"),
    ]
    funnel = pd.DataFrame(rows, columns=["stage", "n_sources", "definition"])
    funnel["share_of_eligible"] = funnel["n_sources"] / len(diag) if len(diag) else np.nan
    funnel.to_csv(T / "final_linkage_funnel.csv", index=False)

    strata_rows = []
    diag2 = diag.copy()
    diag2["followup_bin"] = pd.cut(
        diag2["observable_followup_months"],
        bins=[-math.inf, 6, 12, 24, 60, math.inf],
        labels=["<6m", "6-12m", "12-24m", "24-60m", "60m+"],
    )
    diag2["buyer_frequency_bin"] = pd.cut(
        diag2["buyer_publication_frequency"],
        bins=[0, 1, 2, 5, 10, 25, math.inf],
        labels=["1", "2", "3-5", "6-10", "11-25", "26+"],
    )
    for variable in [
        "publication_year",
        "followup_bin",
        "buyer_key_type",
        "duration_imputation_status",
        "buyer_frequency_bin",
        "cpv_division",
        "primary_linkage_status_reason",
    ]:
        for level, grp in diag2.groupby(variable, dropna=False, observed=False):
            n = len(grp)
            strata_rows.append(
                {
                    "breakdown": variable,
                    "level": str(level),
                    "n_sources": n,
                    "sources_with_later_same_buyer": int((grp["later_same_buyer_notice_count"] > 0).sum()),
                    "sources_in_m0_candidate_pool": int((grp["m0_candidate_count"] > 0).sum()),
                    "m0_accepted_links": int(grp["m0_accepted"].sum()),
                    "m0_link_rate": float(grp["m0_accepted"].mean()) if n else np.nan,
                    "m1_accepted_links": int(grp["m1_accepted"].sum()),
                    "m1_link_rate": float(grp["m1_accepted"].mean()) if n else np.nan,
                }
            )
    pd.DataFrame(strata_rows).to_csv(T / "final_linkage_funnel_stratified.csv", index=False)


def build_method_comparisons(core: dict[str, pd.DataFrame], inventory: pd.DataFrame) -> None:
    inventory.to_csv(T / "final_method_comparison.csv", index=False)

    temporal = read_csv(T / "m6d_temporal_window_sensitivity.csv") if (T / "m6d_temporal_window_sensitivity.csv").exists() else pd.DataFrame()
    leakage = read_csv(T / "duration_leakage_linkage_sensitivity.csv") if (T / "duration_leakage_linkage_sensitivity.csv").exists() else pd.DataFrame()
    if not temporal.empty:
        temporal = temporal.assign(variant_family="duration_centered_temporal_window")
    if not leakage.empty:
        leakage = leakage.assign(variant_family="duration_leakage_or_forward_design")
    pd.concat([temporal, leakage], ignore_index=True, sort=False).to_csv(
        T / "final_temporal_variant_comparison.csv", index=False
    )

    m0 = core["links_m0"]
    m1 = core["links_m1"]
    profile = core["links_profile"]
    m0_by_source = m0.set_index("source_notice_id")
    m1_by_source = m1.set_index("source_notice_id")
    profile_by_source = profile.set_index("source_notice_id")
    sources = sorted(set(m0_by_source.index) | set(m1_by_source.index) | set(profile_by_source.index))
    rows = []
    for source_id in sources:
        m0_cand = str(m0_by_source.loc[source_id, "candidate_notice_id"]) if source_id in m0_by_source.index else ""
        m1_cand = str(m1_by_source.loc[source_id, "candidate_notice_id"]) if source_id in m1_by_source.index else ""
        profile_cand = str(profile_by_source.loc[source_id, "candidate_notice_id"]) if source_id in profile_by_source.index else ""
        if m0_cand and m1_cand and m0_cand == m1_cand:
            status = "same_accepted_candidate_under_m0_and_m1"
        elif m0_cand and not m1_cand:
            status = "accepted_only_under_m0"
        elif m1_cand and not m0_cand:
            status = "accepted_only_under_m1"
        elif m0_cand and m1_cand and m0_cand != m1_cand:
            status = "accepted_by_both_different_candidates"
        else:
            status = "not_accepted_by_m0_or_m1"
        rows.append(
            {
                "source_notice_id": source_id,
                "m0_candidate_notice_id": m0_cand,
                "m1_candidate_notice_id": m1_cand,
                "profile_candidate_notice_id": profile_cand,
                "m0_m1_status": status,
                "m1_buyer_match_mechanism": str(m1_by_source.loc[source_id, "buyer_match_mechanism"]) if source_id in m1_by_source.index else "",
                "profile_evidence_status": str(profile_by_source.loc[source_id, "profile_evidence_status"]) if source_id in profile_by_source.index else "",
                "profile_conflict_flag": bool(profile_by_source.loc[source_id, "profile_conflict_flag"]) if source_id in profile_by_source.index else False,
            }
        )
    status = pd.DataFrame(rows)
    status.to_csv(T / "final_m0_m1_profile_source_comparison.csv", index=False)
    (
        status.groupby(["m0_m1_status", "m1_buyer_match_mechanism", "profile_evidence_status"], dropna=False)
        .size()
        .reset_index(name="n_sources")
        .to_csv(T / "final_m0_m1_profile_status_summary.csv", index=False)
    )


def build_validation_files(core: dict[str, pd.DataFrame], diag: pd.DataFrame) -> None:
    sources = core["sources"].set_index("notice_id")
    pairs = core["pairs_m0"].copy()
    m1_pairs = core["pairs_m1"].copy()
    m0_links = core["links_m0"].copy()
    m1_links = core["links_m1"].copy()
    profile_links = core["links_profile"].copy()

    rng = np.random.default_rng(20260716)
    sample_frames = []

    def add_sample(frame: pd.DataFrame, stratum: str, n: int, score_col: str | None = None) -> None:
        if frame.empty:
            return
        sort_col = score_col if score_col and score_col in frame.columns else None
        if sort_col:
            frame = frame.sort_values(sort_col, ascending=False)
        take = min(n, len(frame))
        if take == len(frame):
            out = frame.copy()
        else:
            out = frame.sample(take, random_state=int(rng.integers(1_000_000)))
        sample_frames.append(out.assign(validation_stratum=stratum))

    add_sample(m0_links, "accepted_high_confidence_m0", 30, "m0_composite_score")
    add_sample(m0_links[m0_links["top1_top2_margin"] < 0.05], "accepted_low_margin_m0", 30, "m0_composite_score")
    add_sample(pairs[pairs["candidate_rank"] == 1].merge(m0_links[["source_notice_id"]], on="source_notice_id", how="left", indicator=True).query("_merge == 'left_only'").drop(columns="_merge"), "rejected_rank1_m0", 30, "m0_composite_score")
    add_sample(pairs[pairs["candidate_rank"] == 2], "runner_up_m0", 30, "m0_composite_score")
    add_sample(m1_links[~m1_links["source_notice_id"].isin(m0_links["source_notice_id"])], "m1_only_link", 35, "m1_composite_score")
    add_sample(
        m1_links[m1_links["buyer_match_mechanism"].isin(["HISTORICAL_ALIAS_RECONCILIATION", "SAME_SIREN_RECONCILIATION"])],
        "buyer_reconciliation_m1",
        35,
        "m1_composite_score",
    )
    add_sample(profile_links[profile_links["profile_conflict_flag"].astype(bool)], "profile_conflict_case", 30, "m1_composite_score")
    add_sample(profile_links[profile_links["profile_evidence_status"].isin(["STRONG_SUPPORT", "WEAK_SUPPORT"])], "profile_supported_case", 30, "m1_composite_score")
    forward_path = P / "boamp_m0_links_forward_24m_no_duration.csv"
    if forward_path.exists():
        forward = read_csv(forward_path, parse_dates=["source_date", "candidate_date", "expected_end_date"])
        add_sample(forward[~forward["source_notice_id"].isin(m0_links["source_notice_id"])], "forward_24m_only_link", 35, "m0_composite_score")

    if not sample_frames:
        return

    sample = pd.concat(sample_frames, ignore_index=True, sort=False)
    sample = sample.drop_duplicates(["source_notice_id", "candidate_notice_id", "validation_stratum"])
    sample["validation_case_id"] = [f"VAL-{i:04d}" for i in range(1, len(sample) + 1)]

    def source_value(row: pd.Series, col: str) -> str:
        try:
            return str(sources.loc[str(row["source_notice_id"]), col])
        except Exception:
            return ""

    def candidate_value(row: pd.Series, col: str) -> str:
        try:
            return str(sources.loc[str(row["candidate_notice_id"]), col])
        except Exception:
            return ""

    reviewer = pd.DataFrame(
        {
            "validation_case_id": sample["validation_case_id"],
            "validation_stratum": sample["validation_stratum"],
            "source_notice_id": sample["source_notice_id"],
            "candidate_notice_id": sample["candidate_notice_id"],
            "source_publication_date": sample.apply(lambda r: source_value(r, "publication_date"), axis=1),
            "candidate_publication_date": sample.apply(lambda r: candidate_value(r, "publication_date"), axis=1),
            "time_gap_months": pd.to_numeric(sample.get("gap_months"), errors="coerce"),
            "source_buyer_key_type": sample.apply(lambda r: source_value(r, "buyer_key_type"), axis=1),
            "candidate_buyer_key_type": sample.apply(lambda r: candidate_value(r, "buyer_key_type"), axis=1),
            "source_buyer_name_normalized": sample.apply(lambda r: source_value(r, "buyer_name_normalized"), axis=1),
            "candidate_buyer_name_normalized": sample.apply(lambda r: candidate_value(r, "buyer_name_normalized"), axis=1),
            "source_cpv": sample.apply(lambda r: source_value(r, "cpv_clean"), axis=1),
            "candidate_cpv": sample.apply(lambda r: candidate_value(r, "cpv_clean"), axis=1),
            "source_cpv_division": sample.apply(lambda r: source_value(r, "cpv_division"), axis=1),
            "candidate_cpv_division": sample.apply(lambda r: candidate_value(r, "cpv_division"), axis=1),
            "source_object": sample.apply(lambda r: source_value(r, "objet_clean"), axis=1),
            "candidate_object": sample.apply(lambda r: candidate_value(r, "objet_clean"), axis=1),
            "source_boamp_url": "",
            "candidate_boamp_url": "",
            "reviewer_label": "",
            "reviewer_confidence": "",
            "buyer_identity_confidence": "",
            "evidence_category": "",
            "likely_error_mechanism": "",
            "external_evidence_consulted": "",
            "ai_assisted_summary_used": "",
            "short_justification": "",
        }
    )
    reviewer.to_csv(T / "final_blinded_single_reviewer_sample.csv", index=False)

    join_cols = [
        "validation_case_id",
        "validation_stratum",
        "source_notice_id",
        "candidate_notice_id",
        "m0_composite_score",
        "m1_composite_score",
        "score_forward_no_duration",
        "candidate_rank",
        "top1_top2_margin",
        "buyer_match_mechanism",
        "profile_evidence_status",
        "profile_conflict_flag",
        "variant",
        "threshold_used",
    ]
    for col in join_cols:
        if col not in sample.columns:
            sample[col] = ""
    sample[join_cols].to_csv(T / "final_validation_technical_join_table.csv", index=False)

    guide = textwrap.dedent(
        """
        # Final Single-Reviewer Plausibility Audit Guide

        This audit is a single-reviewer evidence-based plausibility audit, not
        verified expert ground truth. Labels should not be inferred from method
        names, composite scores, thresholds, or acceptance status. The reviewer
        file hides those technical fields; the join table keeps them separate
        for analysis after labels are recorded.

        Allowed labels:

        - `credible_recurrence`
        - `likely_not_recurrence`
        - `uncertain`
        - `insufficient_evidence`

        Also record confidence, buyer-identity confidence, evidence category,
        likely error mechanism, whether external evidence was consulted, whether
        AI-assisted summarization was used, and a short justification.

        A disguised repeat subset should be reviewed after a delay and stored
        with the same schema plus a repeat-round marker before calculating
        intra-reviewer agreement. Do not overwrite disagreements.
        """
    ).strip() + "\n"
    (R / "final_single_reviewer_audit_guide.md").write_text(guide, encoding="utf-8")


def write_validation_analysis_script() -> None:
    script = '''"""Analyze completed BOAMP manual-validation labels.

Input should be the completed reviewer file produced by
reports/tables/final_blinded_single_reviewer_sample.csv. This script keeps
credible, likely-not, and uncertain/insufficient labels separate and does not
call accepted-link precision "accuracy".
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"

POSITIVE = {"credible_recurrence", "credible"}
NEGATIVE = {"likely_not_recurrence", "not_recurrence"}
UNCERTAIN = {"uncertain", "insufficient_evidence"}


def norm_label(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def summarize(group: pd.DataFrame, label: str) -> dict:
    labels = group["reviewer_label_normalized"]
    c = int(labels.isin(POSITIVE).sum())
    n = int(labels.isin(NEGATIVE).sum())
    u = int(labels.isin(UNCERTAIN).sum())
    total = c + n + u
    decided = c + n
    lo, hi = proportion_confint(c, decided, method="wilson") if decided else (np.nan, np.nan)
    return {
        "breakdown": label,
        "n_reviewed": total,
        "credible": c,
        "likely_not": n,
        "uncertain_or_insufficient": u,
        "p_decided": c / decided if decided else np.nan,
        "p_decided_ci_low": lo,
        "p_decided_ci_high": hi,
        "p_lower": c / total if total else np.nan,
        "p_upper": (c + u) / total if total else np.nan,
        "uncertainty_rate": u / total if total else np.nan,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default=str(TABLES / "final_blinded_single_reviewer_sample.csv"))
    parser.add_argument("--join", default=str(TABLES / "final_validation_technical_join_table.csv"))
    parser.add_argument("--out", default=str(TABLES / "final_manual_validation_label_analysis.csv"))
    args = parser.parse_args()

    labels = pd.read_csv(args.labels, dtype=str)
    if "reviewer_label" not in labels.columns:
        raise SystemExit("Missing reviewer_label column")
    labels["reviewer_label_normalized"] = labels["reviewer_label"].map(norm_label)
    completed = labels[labels["reviewer_label_normalized"].isin(POSITIVE | NEGATIVE | UNCERTAIN)].copy()
    if completed.empty:
        pd.DataFrame([{"breakdown": "overall", "n_reviewed": 0, "note": "no completed labels"}]).to_csv(args.out, index=False)
        return

    rows = [summarize(completed, "overall")]
    if Path(args.join).exists():
        join = pd.read_csv(args.join, dtype=str)
        completed = completed.merge(join, on=["validation_case_id", "source_notice_id", "candidate_notice_id"], how="left")
    for col in [
        "validation_stratum",
        "buyer_match_mechanism",
        "profile_evidence_status",
        "candidate_rank",
        "variant",
    ]:
        if col in completed.columns:
            for value, grp in completed.groupby(col, dropna=False):
                rows.append(summarize(grp, f"{col}={value}"))
    pd.DataFrame(rows).to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
'''
    (ROOT / "scripts" / "analyze_manual_validation_labels.py").write_text(script, encoding="utf-8")


def build_consistency_audit(core: dict[str, pd.DataFrame], diag: pd.DataFrame) -> pd.DataFrame:
    rows = []

    def check(name: str, passed: bool, value: object, expected: str, severity: str = "error") -> None:
        rows.append({"check": name, "passed": bool(passed), "value": value, "expected": expected, "severity": severity})

    sources = core["sources"]
    surv_m0 = core["surv_m0"]
    m0 = core["links_m0"]
    m1 = core["links_m1"]
    profile = core["links_profile"]
    check("m0_sources_unique_notice_id", sources["notice_id"].is_unique, int(sources["notice_id"].duplicated().sum()), "0 duplicates")
    check("m0_survival_one_row_per_source", surv_m0["notice_id"].is_unique and len(surv_m0) == len(sources[sources["buyer_key_type"] != "MISSING"]), len(surv_m0), "one row per nonmissing-buyer source")
    check("m0_survival_events_equal_balanced_links", int(surv_m0["event"].sum()) == len(m0), int(surv_m0["event"].sum()), f"{len(m0)}")
    check("m0_event_rows_have_candidate", int(((surv_m0["event"] == 1) & surv_m0["linked_candidate_notice_id"].isna()).sum()) == 0, int(((surv_m0["event"] == 1) & surv_m0["linked_candidate_notice_id"].isna()).sum()), "0")
    check("m0_no_nonpositive_survival_time", int((surv_m0["time_to_event_or_censor_months"] <= 0).sum()) == 0, int((surv_m0["time_to_event_or_censor_months"] <= 0).sum()), "0")
    check("m1_same_source_population_size", len(core["surv_m1"]) == len(surv_m0), len(core["surv_m1"]), f"{len(surv_m0)}")
    check("profile_audit_does_not_change_link_count", len(profile) == len(m1), len(profile), f"{len(m1)}", "warning")
    check("final_source_diagnostics_one_row_per_source", diag["source_notice_id"].is_unique and len(diag) == len(surv_m0), len(diag), f"{len(surv_m0)}")
    label_file = T / "final_blinded_single_reviewer_sample.csv"
    label_values = []
    if label_file.exists():
        label_values = pd.read_csv(label_file, dtype=str)["reviewer_label"].dropna().str.strip()
        label_values = label_values[label_values != ""].tolist()
    check("manual_labels_not_fabricated", len(label_values) == 0, len(label_values), "0 completed labels in generated reviewer file", "info")
    out = pd.DataFrame(rows)
    out.to_csv(T / "final_consistency_audit.csv", index=False)
    return out


def write_reports(
    core: dict[str, pd.DataFrame],
    inventory: pd.DataFrame,
    files: pd.DataFrame,
    diag: pd.DataFrame,
    consistency: pd.DataFrame,
) -> None:
    state = git_state()
    comp = read_csv(T / "m0_m1_linkage_comparison.csv") if (T / "m0_m1_linkage_comparison.csv").exists() else pd.DataFrame()
    mechanisms = read_csv(T / "m1_incremental_recovery_mechanisms.csv") if (T / "m1_incremental_recovery_mechanisms.csv").exists() else pd.DataFrame()
    temporal = read_csv(T / "final_temporal_variant_comparison.csv") if (T / "final_temporal_variant_comparison.csv").exists() else pd.DataFrame()

    m0_row = inventory[inventory["method_id"] == "M0_BALANCED_OFFICIAL"].iloc[0]
    m1_row = inventory[inventory["method_id"] == "M1_BUYER_SIREN_ENRICHED"].iloc[0]
    low_rate_drivers = diag["primary_linkage_status_reason"].value_counts().rename_axis("reason").reset_index(name="n_sources")
    top_reason_lines = "\n".join(
        f"- {r.reason}: {int(r.n_sources)} sources" for r in low_rate_drivers.head(6).itertuples(index=False)
    )

    mech_lines = "No incremental-mechanism table was found."
    if not mechanisms.empty:
        mech_lines = "\n".join(
            f"- {r.recovery_mechanism}: {int(r.incremental_links)} incremental links"
            for r in mechanisms.itertuples(index=False)
        )

    temporal_lines = "No temporal-variant table was found."
    if not temporal.empty:
        cols = [c for c in ["variant", "window_months", "n_links", "event_rate", "jaccard_vs_reference", "event_status_changes_vs_reference", "median_event_time"] if c in temporal.columns]
        temporal_lines = markdown_table(temporal, cols)

    decision = f"""# Final Method-Selection Record

Generated: {DATE}

Repository state:

- Branch: `{state['branch']}`
- Commit: `{state['commit']}`
- Short status at audit generation: `{state['short_status'] or 'clean'}`

## Decision

The primary event definition remains **M0 balanced**, the BOAMP-only proxy
recurrence baseline. M1 buyer enrichment and profile-audited M1 are retained as
sensitivity/audit specifications, not replacements.

This decision is evidence-limited: no completed manual labels exist in the
repository. Therefore the study can select a reproducible primary proxy event
definition for exploratory survival analysis, but it cannot claim verified
renewal precision, legal renewal status, or operational accuracy.

## Exact Definitions

**M0 balanced.** BOAMP-only APPEL_OFFRE digital/ICT sources in Pays de la
Loire; candidate generation requires a nonmissing BOAMP-derived buyer key, a
later notice with the same buyer key, and publication inside the duration-
centered temporal window. Scoring is transparent TF-IDF text, CPV hierarchy,
temporal proximity, and buyer-key reliability. The balanced variant accepts the
rank-1 candidate at or above the current rank-1 median threshold. Current links:
{int(m0_row.accepted_links)} / {int(m0_row.eligible_sources)}
({m0_row.proxy_event_rate:.1%}).

**M1 buyer-enriched.** Same source population, temporal design, text/CPV/time
logic, and M0 balanced threshold, but buyer identity is reconciled using direct
BOAMP identifiers, same-SIREN reconciliation, and conservative historical
aliases. Current links: {int(m1_row.accepted_links)} / {int(m1_row.eligible_sources)}
({m1_row.proxy_event_rate:.1%}).

**Profile-audited M1.** M1 links annotated with procurement-profile domain
evidence. Domains are supporting/conflict evidence, not legal identifiers and
not ground truth.

**Temporal variants.** Window variants alter the duration-centered candidate
window (6, 9, 12, 18 months). The no-temporal-score reference-pool variant
reranks the same reference candidate pool without the temporal score. The
forward-24m no-duration variant uses a forward publication horizon and avoids
duration-centered blocking/scoring; it is a sensitivity check for duration
circularity and rapid related procurement activity, not an adopted replacement.

## End-to-End M1 Data Preprocessing

M1 preprocessing is an additive branch over frozen M0 outputs. It begins with
the official M0 cleaned notices, source table, balanced links, candidate-pair
table, and survival handoff. It then loads and audits the external 2024--2026
buyer SIREN/SIRET Parquet files, verifies the one-to-one
`B_17_idweb -> notice_id` join key, and left-joins enrichment fields to the
cleaned BOAMP notices without overwriting BOAMP-provided identifiers.

The preprocessing cleans BOAMP and enriched SIREN/SIRET values separately,
flags BOAMP/enriched identifier conflicts, builds a conservative
name--department historical alias bridge from directly enriched non-conflicting
rows, and applies a priority rule: preserve BOAMP SIRET/SIREN first, then use
valid direct enrichment, then use an automatic historical alias only for older
rows with no BOAMP identifier, otherwise keep the original name fallback. The
result is the M1 source table with buyer identity, provenance, confidence, and
conflict fields attached to the same 3,159 source notices as M0.

Only after this preprocessing step does M1 generate candidate pairs. It reuses
M0 duration, estimated end dates, temporal window, TF-IDF text score, CPV score,
temporal score, score weights, candidate cap, and balanced threshold. The
controlled change is buyer compatibility through exact SIRET, same SIREN,
historical alias, or M0 name fallback. The profile-domain audit is a later
evidence overlay; it does not create legal identifiers or new buyer matches.

## Evidence Used

- `reports/tables/final_method_inventory.csv`
- `reports/tables/final_source_linkage_diagnostics.csv`
- `reports/tables/final_linkage_funnel.csv`
- `reports/tables/final_m0_m1_profile_source_comparison.csv`
- `reports/tables/final_temporal_variant_comparison.csv`
- `reports/tables/final_consistency_audit.csv`

## Why M0 Remains Primary

M0 is conservative, BOAMP-only, reproducible, internally coherent, and already
used for the official survival handoff. M1 improves candidate coverage and link
yield, but higher yield is not validation. Its incremental evidence still
requires single-reviewer plausibility review and, ideally, adjudication.

## Enrichment Gains

Current incremental M1 links are concentrated in:

{mech_lines}

Thus the gain is not mainly from directly observed new identifiers alone; a
large share comes from historical-alias reconciliation, which is plausible but
manual-review sensitive.

## Why The Linkage Rate Is Low

The low M0 linkage rate is scientifically plausible for a conservative proxy
because most sources never enter the scored candidate pool. Primary source-level
diagnostic reasons:

{top_reason_lines}

This does not prove the true renewal rate is low. It shows that under the
observable BOAMP-only M0 design, many sources have no usable later same-buyer
candidate inside the temporal rule.

## Temporal And Duration Sensitivity

{temporal_lines}

Stable: the M0 handoff is internally consistent and the event is heavy-censored.
Design-dependent: event counts, event timing, and especially duration effects.
The forward no-duration variant is too different to replace M0 without
validation; it likely captures rapid related procurement activity as well as
recurrence.

## Validation Status

Manual labels are pending. Prepared files:

- `reports/tables/final_blinded_single_reviewer_sample.csv`
- `reports/tables/final_validation_technical_join_table.csv`
- `reports/final_single_reviewer_audit_guide.md`
- `scripts/analyze_manual_validation_labels.py`

The validation analysis will compute decided precision, lower and upper
credibility bounds, uncertainty rate, and breakdowns by method/stratum once
labels are complete. Until then, accepted-link precision must not be described
as overall accuracy.

## Unsupported Claims

- M0 or M1 links are verified legal renewals.
- `event = 0` means confirmed non-renewal.
- M1 is better because it has more links.
- Duration is a stable substantive predictor independent of event definition.
- Fellegi-Sunter, corruption recovery, or agreement with M0 is external ground truth.
"""
    (R / "final_method_selection_record.md").write_text(decision, encoding="utf-8")

    auth_table = markdown_table(files, ["role", "path", "exists", "row_count", "column_count", "sha256"])
    manifest = f"""# Final Reproducibility Manifest

Generated: {DATE}

Repository state:

- Branch: `{state['branch']}`
- Commit: `{state['commit']}`
- Short status at audit generation: `{state['short_status'] or 'clean'}`

## Authoritative Files

{auth_table}

## Reproduction Commands

Run from the repository root:

```bash
python3 scripts/download_boamp.py
python3 scripts/parse_boamp.py
python3 scripts/preprocess_boamp_m0.py
python3 scripts/build_m0_candidate_pairs.py
python3 scripts/run_m0_linkage.py
python3 scripts/audit_current_project.py
python3 scripts/build_m1_buyer_siren_experiment.py
python3 scripts/build_m1_profile_domain_audit.py
python3 scripts/eval_m6d_temporal_window_sensitivity.py
python3 scripts/eval_duration_leakage.py
python3 scripts/run_survival_analysis.py
python3 scripts/make_figures.py
python3 scripts/make_evaluation_figures.py
python3 scripts/make_report_figures.py
python3 scripts/build_final_scientific_audit.py
```

External downloads are only needed if raw BOAMP or M1 enrichment/profile files
are absent. The final audit script itself is additive and reads existing
outputs.

## Consistency Checks

{markdown_table(consistency)}
"""
    (R / "final_reproducibility_manifest.md").write_text(manifest, encoding="utf-8")


def main() -> None:
    core = load_core()
    inventory = build_method_inventory(core)
    diag = build_source_diagnostics(core)
    build_funnels(diag, core)
    build_method_comparisons(core, inventory)
    build_validation_files(core, diag)
    write_validation_analysis_script()
    files = build_authoritative_files()
    consistency = build_consistency_audit(core, diag)
    write_reports(core, inventory, files, diag, consistency)
    files = build_authoritative_files()
    write_reports(core, inventory, files, diag, consistency)
    print("Wrote final scientific audit package.")


if __name__ == "__main__":
    main()
