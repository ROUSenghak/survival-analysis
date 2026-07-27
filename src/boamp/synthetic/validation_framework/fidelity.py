"""Minimum-suite real-vs-synthetic fidelity and difficulty diagnostics."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from boamp.config import load_config
from boamp.data.prepare import tag_digital_scope
from boamp.linkage.candidates import generate_pairs_single_key
from boamp.synthetic.compatibility import adapt_observed_notices_to_sources
from boamp.synthetic.validation_framework.loaders import BenchmarkData
from boamp.synthetic.validation_framework.models import (
    MetricResult,
    Status,
    classify_abs,
    classify_range,
    classify_upper,
)
from utils.text_clean import normalize_objet


TOLERANCES = {
    "categorical_tv": 0.05,
    "categorical_js": 0.05,
    "numeric_quantile_rel_p50_p90": 0.10,
    "numeric_quantile_rel_p95_p99": 0.20,
    "w1_scaled": 0.10,
    "conditional_wmae_pp": 3.0,
    "conditional_max_warning_pp": 10.0,
    "temporal_year_tvd": 0.20,
    "temporal_month_tvd": 0.20,
    "temporal_calendar_month_tvd": 0.10,
    "temporal_schema_by_year_wmae_pp": 3.0,
    "temporal_notice_type_by_year_wmae_pp": 5.0,
    "runway_12_24_abs_pp": 3.0,
    "runway_36_60_abs_pp": 5.0,
    "candidate_source_count_ratio_min": 0.80,
    "candidate_source_count_ratio_max": 1.20,
    "candidate_zero_abs_pp": 5.0,
    "candidate_p75_abs_count": 3.0,
    "candidate_p90_abs_count": 5.0,
    "candidate_p95_abs_count": 8.0,
    "candidate_p99_abs_count_warning": 20.0,
    "candidate_cap_rate": 0.01,
    "candidate_by_key_zero_abs_pp": 10.0,
    "missingness_rate_pp": 2.0,
    "text_length_quantile_rel": 0.10,
    "identifier_rate_pp": 2.0,
}

MIN_VALID_DURATION_MONTHS = 1.0
MAX_VALID_DURATION_MONTHS = 120.0


def _metric(
    data: BenchmarkData,
    scope: str,
    subgroup: str,
    prop: str,
    metric: str,
    real,
    synthetic,
    diff,
    effect,
    tolerance,
    status: Status | str,
    provenance: str = "observable_real_vs_synthetic",
    notes: str = "",
) -> MetricResult:
    return MetricResult(
        benchmark_version=data.benchmark_version,
        scenario=data.scenario,
        seed=data.seed_label,
        scope=scope,
        subgroup=subgroup,
        property=prop,
        metric=metric,
        real_estimate=real,
        synthetic_estimate=synthetic,
        difference=diff,
        effect_size=effect,
        ci_low=None,
        ci_high=None,
        tolerance=tolerance,
        status=status,
        provenance=provenance,
        notes=notes,
    )


def _shares(s: pd.Series) -> pd.Series:
    counts = s.fillna("__MISSING__").astype(str).value_counts()
    return counts / counts.sum() if counts.sum() else counts


def _primary_department(series: pd.Series) -> pd.Series:
    return series.fillna("__MISSING__").astype(str).str.split(";").str[0]


def _tv(real: pd.Series, synthetic: pd.Series) -> float:
    idx = real.index.union(synthetic.index)
    return float(0.5 * (real.reindex(idx, fill_value=0) - synthetic.reindex(idx, fill_value=0)).abs().sum())


def _js(real: pd.Series, synthetic: pd.Series) -> float:
    idx = real.index.union(synthetic.index)
    p = real.reindex(idx, fill_value=0).astype(float).to_numpy()
    q = synthetic.reindex(idx, fill_value=0).astype(float).to_numpy()
    m = 0.5 * (p + q)

    def kl(a, b):
        mask = a > 0
        return float((a[mask] * np.log2(a[mask] / b[mask])).sum())

    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").dropna()


def _valid_raw_duration(series: pd.Series) -> pd.Series:
    values = _numeric(series)
    return values.loc[values.between(MIN_VALID_DURATION_MONTHS, MAX_VALID_DURATION_MONTHS)]


def _scaled_w1(real: pd.Series, synthetic: pd.Series) -> float:
    real = _numeric(real)
    synthetic = _numeric(synthetic)
    if real.empty or synthetic.empty:
        return float("nan")
    grid = np.linspace(0.01, 0.99, 99)
    rq = real.quantile(grid).to_numpy()
    sq = synthetic.quantile(grid).to_numpy()
    iqr = real.quantile(0.75) - real.quantile(0.25)
    scale = iqr if iqr and math.isfinite(float(iqr)) else real.std()
    scale = scale if scale and math.isfinite(float(scale)) else 1.0
    return float(np.mean(np.abs(rq - sq)) / scale)


def run_marginal_metrics(data: BenchmarkData) -> list[MetricResult]:
    metrics: list[MetricResult] = []
    real = data.real.copy()
    syn = data.observed.copy()
    syn["publication_year"] = pd.to_datetime(syn["publication_date"]).dt.year
    syn["text_length"] = syn["objet_clean"].fillna("").astype(str).str.len()

    categorical = [
        ("schema_family", "schema_family"),
        ("notice_type_normalized", "notice_type"),
        ("cpv_division", "cpv_division"),
        ("code_departement", "department_primary"),
    ]
    for col, prop in categorical:
        if col not in real.columns or col not in syn.columns:
            continue
        real_values = _primary_department(real[col]) if prop == "department_primary" else real[col]
        syn_values = _primary_department(syn[col]) if prop == "department_primary" else syn[col]
        real_shares = _shares(real_values)
        syn_shares = _shares(syn_values)
        tv = _tv(real_shares, syn_shares)
        js = _js(real_shares, syn_shares)
        metrics.append(_metric(data, "marginals", "overall", prop, "TV", None, None, tv, tv, TOLERANCES["categorical_tv"], classify_upper(tv, TOLERANCES["categorical_tv"])))
        metrics.append(_metric(data, "marginals", "overall", prop, "JS", None, None, js, js, TOLERANCES["categorical_js"], classify_upper(js, TOLERANCES["categorical_js"])))

    numeric_pairs = [
        ("duration_raw", "declared_duration_months", "duration"),
        ("text_length", "text_length", "text_length"),
    ]
    for real_col, syn_col, prop in numeric_pairs:
        if real_col not in real.columns or syn_col not in syn.columns:
            continue
        r = _valid_raw_duration(real[real_col]) if prop == "duration" else _numeric(real[real_col])
        s = _numeric(syn[syn_col])
        if r.empty or s.empty:
            metrics.append(_metric(data, "marginals", "overall", prop, "W1_scaled", None, None, None, None, TOLERANCES["w1_scaled"], Status.INCONCLUSIVE))
            continue
        w1 = _scaled_w1(r, s)
        duration_notes = (
            "Real reference uses valid raw observed BOAMP duration_raw values within 1-120 months, "
            "excluding prepared source-scope imputation."
            if prop == "duration"
            else ""
        )
        metrics.append(_metric(data, "marginals", "overall", prop, "W1_scaled", None, None, w1, w1, TOLERANCES["w1_scaled"], classify_upper(w1, TOLERANCES["w1_scaled"]), notes=duration_notes))
        for q in [0.50, 0.75, 0.90, 0.95, 0.99]:
            rq = float(r.quantile(q))
            sq = float(s.quantile(q))
            denom = abs(rq) if abs(rq) > 1e-9 else 1.0
            rel = abs(sq - rq) / denom
            tol = TOLERANCES["numeric_quantile_rel_p95_p99"] if q >= 0.95 else TOLERANCES["numeric_quantile_rel_p50_p90"]
            metrics.append(
                _metric(
                    data,
                    "marginals",
                    "overall",
                    prop,
                    f"q{int(q * 100)}_relative_error",
                    rq,
                    sq,
                    sq - rq,
                    rel,
                    tol,
                    classify_upper(rel, tol),
                    notes=duration_notes,
                )
            )
    return metrics


def _add_common_flags(frame: pd.DataFrame, id_col: str) -> pd.DataFrame:
    out = frame.copy()
    if "buyer_key" in out.columns:
        counts = out.groupby("buyer_key", dropna=False)[id_col].transform("size")
    else:
        counts = pd.Series(np.ones(len(out)), index=out.index)
    out["buyer_activity_tier"] = pd.cut(
        counts,
        bins=[0, 1, 5, 20, np.inf],
        labels=["1 (single)", "2-5", "6-20", "21+"],
        right=True,
    ).astype(str)
    if "objet_normalized" not in out.columns:
        out["objet_normalized"] = out["objet_clean"].map(normalize_objet)
    text_stats = (
        out.dropna(subset=["objet_normalized"])
        .groupby("objet_normalized")
        .agg(n_notices=("objet_normalized", "size"), n_buyers=("buyer_key", "nunique") if "buyer_key" in out.columns else ("objet_normalized", "size"))
    )
    generic_texts = set(text_stats.query("n_notices >= 2 and n_buyers >= 2").index)
    out["generic_text"] = out["objet_normalized"].isin(generic_texts)
    out["siret_present"] = out.get("buyer_siret_clean", out.get("buyer_siret_raw")).notna()
    out["cpv_missing"] = out["cpv_clean"].isna()
    duration_col = "duration_raw" if "duration_raw" in out.columns else "declared_duration_months"
    out["duration_present"] = out[duration_col].notna()
    return out


def _rate_table(frame: pd.DataFrame, outcome: str, group_cols: list[str]) -> pd.DataFrame:
    return frame.groupby(group_cols, dropna=False)[outcome].agg(successes="sum", n="count").assign(
        rate=lambda x: x["successes"] / x["n"]
    ).reset_index()


def _conditional_wmae(real: pd.DataFrame, syn: pd.DataFrame, outcome: str, group_cols: list[str]) -> tuple[float, int, int]:
    r = _rate_table(real, outcome, group_cols)
    s = _rate_table(syn, outcome, group_cols)
    comp = r.merge(s, on=group_cols, how="outer", suffixes=("_real", "_synthetic"))
    comp["abs_diff_pp"] = (comp["rate_synthetic"] - comp["rate_real"]).abs() * 100
    eligible = comp[comp["n_real"].fillna(0).ge(30) & comp["n_synthetic"].fillna(0).ge(30)].copy()
    if eligible.empty:
        return float("nan"), 0, len(comp)
    weights = eligible["n_real"] / eligible["n_real"].sum()
    return float((weights * eligible["abs_diff_pp"]).sum()), int(len(eligible)), int(len(comp))


def run_conditional_metrics(data: BenchmarkData) -> list[MetricResult]:
    real = _add_common_flags(data.real.copy(), "notice_id")
    synthetic = adapt_observed_notices_to_sources(data.observed)
    synthetic["publication_year"] = pd.to_datetime(synthetic["publication_date"]).dt.year
    synthetic["duration_raw"] = data.observed["declared_duration_months"].to_numpy()
    synthetic["objet_normalized"] = synthetic["objet_clean"].map(normalize_objet)
    synthetic = _add_common_flags(synthetic, "notice_id")
    targets = {
        "siret_present": ("siret_present", ["schema_family", "publication_year", "notice_type_normalized"]),
        "duration_present": ("duration_present", ["schema_family", "publication_year", "notice_type_normalized"]),
        "cpv_missing": ("cpv_missing", ["schema_family", "notice_type_normalized"]),
        "generic_repeated_text": ("generic_text", ["notice_type_normalized", "buyer_activity_tier"]),
    }
    metrics = []
    for prop, (outcome, groups) in targets.items():
        wmae, eligible, total = _conditional_wmae(real, synthetic, outcome, groups)
        metrics.append(
            _metric(
                data,
                "conditionals",
                ",".join(groups),
                prop,
                "WMAE_pp",
                None,
                None,
                wmae,
                wmae,
                TOLERANCES["conditional_wmae_pp"],
                classify_upper(wmae, TOLERANCES["conditional_wmae_pp"], TOLERANCES["conditional_max_warning_pp"]),
                notes=f"eligible_cells={eligible}; total_cells={total}",
            )
        )
    return metrics


def _distribution_comparison(real_keys: pd.Series, synthetic_keys: pd.Series) -> pd.DataFrame:
    real_counts = real_keys.fillna("__MISSING__").astype(str).value_counts()
    syn_counts = synthetic_keys.fillna("__MISSING__").astype(str).value_counts()
    idx = real_counts.index.union(syn_counts.index)
    out = pd.DataFrame(
        {
            "n_real": real_counts.reindex(idx, fill_value=0),
            "n_synthetic": syn_counts.reindex(idx, fill_value=0),
        }
    )
    out["real_share"] = out["n_real"] / out["n_real"].sum()
    out["synthetic_share"] = out["n_synthetic"] / out["n_synthetic"].sum()
    return out


def _conditional_share_wmae(real_df: pd.DataFrame, syn_df: pd.DataFrame, outer_col: str, category_col: str) -> float:
    rows = []
    outers = sorted(set(real_df[outer_col].dropna().astype(str)) | set(syn_df[outer_col].dropna().astype(str)))
    for outer in outers:
        real_group = real_df.loc[real_df[outer_col].astype(str).eq(outer)]
        syn_group = syn_df.loc[syn_df[outer_col].astype(str).eq(outer)]
        cats = sorted(set(real_group[category_col].dropna().astype(str)) | set(syn_group[category_col].dropna().astype(str)))
        for cat in cats:
            real_share = float(real_group[category_col].astype(str).eq(cat).mean()) if len(real_group) else 0.0
            syn_share = float(syn_group[category_col].astype(str).eq(cat).mean()) if len(syn_group) else 0.0
            rows.append({"n_real_outer": len(real_group), "abs_diff_pp": abs(syn_share - real_share) * 100})
    table = pd.DataFrame(rows)
    return float((table["n_real_outer"] * table["abs_diff_pp"]).sum() / table["n_real_outer"].sum())


def run_temporal_metrics(data: BenchmarkData, strict_60m: bool = False) -> list[MetricResult]:
    real = data.real.copy()
    syn = data.observed.copy()
    real["publication_year"] = pd.to_datetime(real["publication_date"]).dt.year
    syn["publication_year"] = pd.to_datetime(syn["publication_date"]).dt.year
    real["publication_month_period"] = pd.to_datetime(real["publication_date"]).dt.to_period("M").astype(str)
    syn["publication_month_period"] = pd.to_datetime(syn["publication_date"]).dt.to_period("M").astype(str)
    real["publication_calendar_month"] = pd.to_datetime(real["publication_date"]).dt.month.astype("Int64")
    syn["publication_calendar_month"] = pd.to_datetime(syn["publication_date"]).dt.month.astype("Int64")

    year_tvd = _tv(
        _distribution_comparison(real["publication_year"], syn["publication_year"])["real_share"],
        _distribution_comparison(real["publication_year"], syn["publication_year"])["synthetic_share"],
    )
    month_period_tvd = _tv(
        _distribution_comparison(real["publication_month_period"], syn["publication_month_period"])["real_share"],
        _distribution_comparison(real["publication_month_period"], syn["publication_month_period"])["synthetic_share"],
    )
    calendar_month_tvd = _tv(
        _distribution_comparison(real["publication_calendar_month"], syn["publication_calendar_month"])["real_share"],
        _distribution_comparison(real["publication_calendar_month"], syn["publication_calendar_month"])["synthetic_share"],
    )
    schema_wmae = _conditional_share_wmae(real, syn, "publication_year", "schema_family")
    type_wmae = _conditional_share_wmae(real, syn, "publication_year", "notice_type_normalized")

    metrics = [
        _metric(data, "temporal", "overall", "publication_year", "TVD", None, None, year_tvd, year_tvd, TOLERANCES["temporal_year_tvd"], classify_upper(year_tvd, TOLERANCES["temporal_year_tvd"])),
        _metric(
            data,
            "temporal",
            "overall",
            "publication_month_period",
            "TVD",
            None,
            None,
            month_period_tvd,
            month_period_tvd,
            TOLERANCES["temporal_month_tvd"],
            classify_upper(month_period_tvd, TOLERANCES["temporal_month_tvd"]),
            notes="chronological YYYY-MM publication periods; not calendar-month seasonality",
        ),
        _metric(
            data,
            "temporal",
            "overall",
            "publication_calendar_month",
            "TVD",
            None,
            None,
            calendar_month_tvd,
            calendar_month_tvd,
            TOLERANCES["temporal_calendar_month_tvd"],
            classify_upper(calendar_month_tvd, TOLERANCES["temporal_calendar_month_tvd"]),
            notes="calendar month-of-year seasonality, computed after explicit datetime parsing",
        ),
        _metric(data, "temporal", "publication_year", "schema_family", "WMAE_pp", None, None, schema_wmae, schema_wmae, TOLERANCES["temporal_schema_by_year_wmae_pp"], classify_upper(schema_wmae, TOLERANCES["temporal_schema_by_year_wmae_pp"])),
        _metric(data, "temporal", "publication_year", "notice_type", "WMAE_pp", None, None, type_wmae, type_wmae, TOLERANCES["temporal_notice_type_by_year_wmae_pp"], classify_upper(type_wmae, TOLERANCES["temporal_notice_type_by_year_wmae_pp"])),
    ]

    cfg = load_config(data.project_root)
    study_end = pd.to_datetime(data.real_sources["study_end_date"].dropna().iloc[0])
    for months in [12, 24, 36, 60]:
        days = int(round(months * cfg.pipeline.run.month_days))
        real_rate = float(((study_end - pd.to_datetime(real["publication_date"])).dt.days >= days).mean())
        syn_rate = float(((study_end - pd.to_datetime(syn["publication_date"])).dt.days >= days).mean())
        diff_pp = (syn_rate - real_rate) * 100
        tol = TOLERANCES["runway_12_24_abs_pp"] if months in [12, 24] else TOLERANCES["runway_36_60_abs_pp"]
        status = classify_abs(diff_pp, tol)
        if months == 60 and status == Status.FAIL and not strict_60m:
            status = Status.WARNING
        metrics.append(_metric(data, "temporal", f"{months}m", "followup_runway", "abs_diff_pp", real_rate, syn_rate, diff_pp, abs(diff_pp), tol, status))
    return metrics


def candidate_count_frame(sources: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    eligible = sources.loc[sources["buyer_key_type"] != "MISSING"].copy()
    counts = pairs.groupby("source_notice_id").size() if len(pairs) else pd.Series(dtype=int)
    keep_cols = [c for c in ["notice_id", "publication_date", "buyer_key_type", "cpv_division"] if c in eligible.columns]
    out = eligible[keep_cols].copy()
    out["candidate_count"] = out["notice_id"].map(counts).fillna(0).astype(int)
    return out


def candidate_summary(counts: pd.DataFrame, max_candidates: int) -> dict:
    return {
        "n_sources": int(len(counts)),
        "zero_candidate_rate": float((counts["candidate_count"] == 0).mean()),
        "p50_candidate_count": float(counts["candidate_count"].quantile(0.50)),
        "p75_candidate_count": float(counts["candidate_count"].quantile(0.75)),
        "p90_candidate_count": float(counts["candidate_count"].quantile(0.90)),
        "p95_candidate_count": float(counts["candidate_count"].quantile(0.95)),
        "p99_candidate_count": float(counts["candidate_count"].quantile(0.99)),
        "cap_reached_rate": float((counts["candidate_count"] >= max_candidates).mean()),
    }


def _synthetic_candidate_counts(data: BenchmarkData) -> pd.DataFrame:
    cfg = load_config(data.project_root)
    sources = adapt_observed_notices_to_sources(data.observed)
    sources["objet_normalized"] = sources["objet_clean"].map(normalize_objet)
    sources["is_digital_scope"] = sources.apply(
        lambda row: tag_digital_scope(row["cpv_division"], row["objet_normalized"], cfg),
        axis=1,
    )
    scoped = sources.loc[sources["notice_type_normalized"].eq("APPEL_OFFRE") & sources["is_digital_scope"]].copy()
    pairs, _window = generate_pairs_single_key(scoped, cfg, verbose=False)
    return candidate_count_frame(scoped, pairs)


def run_candidate_metrics(data: BenchmarkData) -> list[MetricResult]:
    cfg = load_config(data.project_root)
    real_counts = candidate_count_frame(data.real_sources, data.real_pairs)
    syn_counts = _synthetic_candidate_counts(data)
    real_summary = candidate_summary(real_counts, cfg.pipeline.candidates.max_candidates_per_source)
    syn_summary = candidate_summary(syn_counts, cfg.pipeline.candidates.max_candidates_per_source)
    expected_scaled_sources = real_summary["n_sources"] * len(data.observed) / len(data.real)
    source_ratio = syn_summary["n_sources"] / expected_scaled_sources if expected_scaled_sources else float("nan")

    metrics = [
        _metric(data, "candidate_environment", "algorithm_scope", "source_count_ratio", "ratio", 1.0, source_ratio, source_ratio - 1.0, source_ratio, "0.80-1.20", classify_range(source_ratio, TOLERANCES["candidate_source_count_ratio_min"], TOLERANCES["candidate_source_count_ratio_max"])),
        _metric(data, "candidate_environment", "algorithm_scope", "zero_candidate_rate", "abs_diff_pp", real_summary["zero_candidate_rate"], syn_summary["zero_candidate_rate"], (syn_summary["zero_candidate_rate"] - real_summary["zero_candidate_rate"]) * 100, abs(syn_summary["zero_candidate_rate"] - real_summary["zero_candidate_rate"]) * 100, TOLERANCES["candidate_zero_abs_pp"], classify_abs((syn_summary["zero_candidate_rate"] - real_summary["zero_candidate_rate"]) * 100, TOLERANCES["candidate_zero_abs_pp"])),
        _metric(data, "candidate_environment", "algorithm_scope", "cap_reached_rate", "synthetic_rate", 0.0, syn_summary["cap_reached_rate"], syn_summary["cap_reached_rate"], syn_summary["cap_reached_rate"], TOLERANCES["candidate_cap_rate"], classify_upper(syn_summary["cap_reached_rate"], TOLERANCES["candidate_cap_rate"])),
    ]
    for q, tol_key in [("p50", "candidate_p75_abs_count"), ("p75", "candidate_p75_abs_count"), ("p90", "candidate_p90_abs_count"), ("p95", "candidate_p95_abs_count")]:
        prop = f"{q}_candidate_count"
        diff = syn_summary[prop] - real_summary[prop]
        metrics.append(_metric(data, "candidate_environment", "algorithm_scope", prop, "abs_count_diff", real_summary[prop], syn_summary[prop], diff, abs(diff), TOLERANCES[tol_key], classify_abs(diff, TOLERANCES[tol_key])))
    diff99 = syn_summary["p99_candidate_count"] - real_summary["p99_candidate_count"]
    metrics.append(_metric(data, "candidate_environment", "algorithm_scope", "p99_candidate_count", "abs_count_diff", real_summary["p99_candidate_count"], syn_summary["p99_candidate_count"], diff99, abs(diff99), TOLERANCES["candidate_p99_abs_count_warning"], classify_abs(diff99, TOLERANCES["candidate_p99_abs_count_warning"])))

    for key in ["NAME_FALLBACK", "RAW_SIRET"]:
        real_key = real_counts.loc[real_counts["buyer_key_type"].eq(key), "candidate_count"]
        syn_key = syn_counts.loc[syn_counts["buyer_key_type"].eq(key), "candidate_count"]
        if len(syn_key) < 30 or len(real_key) < 30:
            status = Status.INCONCLUSIVE
            diff = float("nan")
            real_rate = float((real_key == 0).mean()) if len(real_key) else float("nan")
            syn_rate = float((syn_key == 0).mean()) if len(syn_key) else float("nan")
        else:
            real_rate = float((real_key == 0).mean())
            syn_rate = float((syn_key == 0).mean())
            diff = (syn_rate - real_rate) * 100
            status = classify_abs(diff, TOLERANCES["candidate_by_key_zero_abs_pp"])
        metrics.append(_metric(data, "candidate_environment", key, "zero_candidate_rate_by_key", "abs_diff_pp", real_rate, syn_rate, diff, abs(diff) if pd.notna(diff) else None, TOLERANCES["candidate_by_key_zero_abs_pp"], status))
    return metrics


def run_missingness_text_identifier_metrics(data: BenchmarkData) -> list[MetricResult]:
    real = data.real
    syn = data.observed.copy()
    syn["text_length"] = syn["objet_clean"].fillna("").astype(str).str.len()
    metrics: list[MetricResult] = []

    missing_fields = [
        ("buyer_siret_clean", "buyer_siret_raw", "siret_missing"),
        ("buyer_siren_clean", "buyer_siren_raw", "siren_missing"),
        ("cpv_clean", "cpv_clean", "cpv_missing"),
        ("declared_duration_months", "declared_duration_months", "duration_missing"),
        ("objet_clean", "objet_clean", "text_missing"),
    ]
    for real_col, syn_col, prop in missing_fields:
        if real_col not in real.columns or syn_col not in syn.columns:
            continue
        real_rate = float(real[real_col].isna().mean())
        syn_rate = float(syn[syn_col].isna().mean())
        diff_pp = (syn_rate - real_rate) * 100
        metrics.append(_metric(data, "missingness_text_identifier", "overall", prop, "rate_abs_diff_pp", real_rate, syn_rate, diff_pp, abs(diff_pp), TOLERANCES["missingness_rate_pp"], classify_abs(diff_pp, TOLERANCES["missingness_rate_pp"])))

    if "text_length" in real.columns:
        r = _numeric(real["text_length"])
        s = _numeric(syn["text_length"])
        for q in [0.50, 0.90, 0.95]:
            rq = float(r.quantile(q))
            sq = float(s.quantile(q))
            rel = abs(sq - rq) / (abs(rq) if abs(rq) > 1e-9 else 1.0)
            metrics.append(_metric(data, "missingness_text_identifier", "overall", "text_length", f"q{int(q * 100)}_relative_error", rq, sq, sq - rq, rel, TOLERANCES["text_length_quantile_rel"], classify_upper(rel, TOLERANCES["text_length_quantile_rel"])))

    for syn_col, prop in [("buyer_siret_raw", "siret_present"), ("buyer_siren_raw", "siren_present")]:
        real_col = syn_col.replace("_raw", "_clean")
        if real_col in real.columns:
            real_rate = float(real[real_col].notna().mean())
            syn_rate = float(syn[syn_col].notna().mean())
            diff_pp = (syn_rate - real_rate) * 100
            metrics.append(_metric(data, "missingness_text_identifier", "overall", prop, "presence_rate_abs_diff_pp", real_rate, syn_rate, diff_pp, abs(diff_pp), TOLERANCES["identifier_rate_pp"], classify_abs(diff_pp, TOLERANCES["identifier_rate_pp"])))
    return metrics


def run_fidelity_validation(data: BenchmarkData, strict_60m: bool = False) -> list[MetricResult]:
    metrics: list[MetricResult] = []
    metrics.extend(run_marginal_metrics(data))
    metrics.extend(run_conditional_metrics(data))
    metrics.extend(run_temporal_metrics(data, strict_60m=strict_60m))
    metrics.extend(run_candidate_metrics(data))
    metrics.extend(run_missingness_text_identifier_metrics(data))
    return metrics
