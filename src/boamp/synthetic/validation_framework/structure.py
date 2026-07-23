"""Buyer-activity, missingness-pattern and identifier/name fidelity gates.

These are the Section 5.4-5.5 modules of the validation specification. Three
properties matter for record linkage and none of them is captured by the
fieldwise marginal rates already checked in ``fidelity.py``:

* how *concentrated* buyer activity is -- a corpus where a few buyers publish
  most notices produces dense candidate neighbourhoods that a corpus with the
  same mean activity but a flat distribution never produces;
* which fields go missing *together* -- a notice missing both SIRET and CPV is
  much harder to link than two notices each missing one of them, so joint
  patterns, not marginal rates, set the difficulty;
* how buyer identifiers and names *vary within one real-world buyer* -- this is
  the mechanism the linker actually has to defeat.

Real-side entity grouping is unavailable, so within-buyer statistics use a
silver-standard group (checksum-valid SIREN) on both sides and are labelled as
such. The synthetic side additionally exposes a hidden-truth version of the
same statistic; the gap between the two is itself reported, because it
quantifies the bias that the silver standard imposes on the real estimate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from boamp.synthetic.compatibility import adapt_observed_notices_to_sources
from boamp.synthetic.validation_framework.bootstrap import (
    cluster_bootstrap_difference,
    equivalence_status,
    gini,
    top_share,
)
from boamp.synthetic.validation_framework.loaders import BenchmarkData
from boamp.synthetic.validation_framework.models import (
    MetricResult,
    Status,
    classify_abs,
    classify_upper,
)


TOLERANCES = {
    "activity_gini_abs": 0.10,
    "activity_top_share_pp": 10.0,
    "activity_relative_quantile_abs": 1.0,
    "activity_w1_log": 0.30,
    "missing_pattern_tv": 0.15,
    "missing_pattern_entropy_bits": 0.30,
    "missing_lift_log_gap": 1.00,
    "identifier_invalid_pp": 2.0,
    "identifier_source_tv": 0.10,
    "name_variants_per_buyer_abs": 0.50,
    "name_similarity_quantile_abs": 0.15,
}

MISSINGNESS_FIELDS = [
    ("siret", "buyer_siret_clean", "buyer_siret_clean"),
    ("siren", "buyer_siren_clean", "buyer_siren_clean"),
    ("cpv", "cpv_clean", "cpv_clean"),
    ("duration", "declared_duration_months", "declared_duration_months"),
    ("text", "objet_clean", "objet_clean"),
    ("department", "code_departement", "code_departement"),
]

MIN_GROUP_SIZE = 30
MAX_PAIRS_PER_GROUP = 20


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
    ci_low=None,
    ci_high=None,
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
        ci_low=ci_low,
        ci_high=ci_high,
        tolerance=tolerance,
        status=status,
        provenance=provenance,
        notes=notes,
    )


def _synthetic_sources(data: BenchmarkData) -> pd.DataFrame:
    """Observed synthetic notices in the same column shape as the real corpus."""
    syn = adapt_observed_notices_to_sources(data.observed)
    syn["declared_duration_months"] = pd.to_numeric(
        data.observed["declared_duration_months"], errors="coerce"
    ).to_numpy()
    return syn


# --------------------------------------------------------------------------
# Buyer activity and concentration
# --------------------------------------------------------------------------


def _activity(frame: pd.DataFrame) -> pd.Series:
    eligible = frame.loc[frame["buyer_key_type"].astype(str).ne("MISSING")]
    return eligible.groupby("buyer_key", dropna=False).size()


def run_buyer_activity_metrics(
    data: BenchmarkData, syn_sources: pd.DataFrame, bootstrap_reps: int = 0
) -> list[MetricResult]:
    real = data.real.loc[:, ["buyer_key", "buyer_key_type"]].copy()
    syn = syn_sources.loc[:, ["buyer_key", "buyer_key_type"]].copy()
    real_activity = _activity(real)
    syn_activity = _activity(syn)
    metrics: list[MetricResult] = []

    if real_activity.empty or syn_activity.empty:
        return [
            _metric(
                data, "buyer_activity", "overall", "activity_distribution", "availability",
                len(real_activity), len(syn_activity), None, None, "n>0", Status.INCONCLUSIVE,
                notes="no eligible buyer keys on one side",
            )
        ]

    # Concentration. Gini and top-shares are bootstrapped over buyers, which is
    # the natural resampling unit for a per-buyer statistic.
    real_frame = pd.DataFrame({"buyer_key": real_activity.index, "activity": real_activity.to_numpy()})
    syn_frame = pd.DataFrame({"buyer_key": syn_activity.index, "activity": syn_activity.to_numpy()})

    boot = cluster_bootstrap_difference(
        real_frame, syn_frame, lambda f: gini(f["activity"]), "buyer_key", "buyer_key", reps=bootstrap_reps
    )
    metrics.append(
        _metric(
            data, "buyer_activity", "overall", "activity_gini", "abs_diff",
            boot["real"], boot["synthetic"], boot["difference"], abs(boot["difference"]),
            TOLERANCES["activity_gini_abs"],
            equivalence_status(boot["difference"], boot["ci_low"], boot["ci_high"], TOLERANCES["activity_gini_abs"]),
            boot["ci_low"], boot["ci_high"],
            notes=f"bootstrap_reps={boot['reps']}; n_real_buyers={len(real_frame)}; n_syn_buyers={len(syn_frame)}",
        )
    )

    for fraction, label in [(0.01, "top1pct"), (0.05, "top5pct"), (0.10, "top10pct")]:
        boot = cluster_bootstrap_difference(
            real_frame, syn_frame, lambda f, fr=fraction: top_share(f["activity"], fr),
            "buyer_key", "buyer_key", reps=bootstrap_reps, scale=100.0,
        )
        metrics.append(
            _metric(
                data, "buyer_activity", label, "activity_share", "abs_diff_pp",
                boot["real"], boot["synthetic"], boot["difference"], abs(boot["difference"]),
                TOLERANCES["activity_top_share_pp"],
                equivalence_status(
                    boot["difference"], boot["ci_low"], boot["ci_high"], TOLERANCES["activity_top_share_pp"]
                ),
                boot["ci_low"], boot["ci_high"],
                notes=f"share of all notices held by the {label} most active buyers",
            )
        )

    # The benchmark is deliberately smaller than the real corpus, so each
    # synthetic buyer has less exposure than a real one. Raw notices-per-buyer
    # quantiles are therefore not comparable: they are recorded as context, and
    # the gated comparison uses activity relative to each corpus's own mean,
    # which is invariant to that scale difference.
    real_mean = float(real_activity.mean())
    syn_mean = float(syn_activity.mean())
    exposure_ratio = syn_mean / real_mean if real_mean else float("nan")
    metrics.append(
        _metric(
            data, "buyer_activity", "overall", "mean_notices_per_buyer", "exposure_ratio",
            real_mean, syn_mean, syn_mean - real_mean, exposure_ratio, "context_only", Status.PASS,
            notes=(
                f"n_real_buyers={len(real_activity)}, n_syn_buyers={len(syn_activity)}; "
                "recorded so relative-activity comparisons below can be read correctly; "
                "not a fidelity gate because benchmark size is a design choice"
            ),
        )
    )

    real_relative = real_activity / real_mean if real_mean else real_activity
    syn_relative = syn_activity / syn_mean if syn_mean else syn_activity
    for q in [0.50, 0.90, 0.99]:
        rq = float(real_relative.quantile(q))
        sq = float(syn_relative.quantile(q))
        diff = sq - rq
        metrics.append(
            _metric(
                data, "buyer_activity", "overall", "relative_notices_per_buyer",
                f"q{int(q * 100)}_abs_diff", rq, sq, diff, abs(diff),
                TOLERANCES["activity_relative_quantile_abs"],
                classify_abs(diff, TOLERANCES["activity_relative_quantile_abs"]),
                notes="activity divided by that corpus's own mean activity (scale-free)",
            )
        )
        metrics.append(
            _metric(
                data, "buyer_activity", "overall", "notices_per_buyer", f"q{int(q * 100)}_raw_counts",
                float(real_activity.quantile(q)), float(syn_activity.quantile(q)),
                float(syn_activity.quantile(q) - real_activity.quantile(q)), None,
                "context_only", Status.PASS,
                notes="raw counts, not gated: confounded by the corpus-size difference above",
            )
        )

    # Heavy-tailed activity is compared on the log scale so the tail does not
    # dominate the whole statistic.
    grid = np.linspace(0.01, 0.99, 99)
    rq = np.log1p(real_relative).quantile(grid).to_numpy()
    sq = np.log1p(syn_relative).quantile(grid).to_numpy()
    w1 = float(np.mean(np.abs(rq - sq)))
    metrics.append(
        _metric(
            data, "buyer_activity", "overall", "log_relative_activity", "W1_log1p",
            None, None, w1, w1, TOLERANCES["activity_w1_log"], classify_upper(w1, TOLERANCES["activity_w1_log"]),
        )
    )
    return metrics


# --------------------------------------------------------------------------
# Joint missingness patterns and error co-occurrence
# --------------------------------------------------------------------------


def _missingness_matrix(frame: pd.DataFrame, columns: list[tuple[str, str]]) -> pd.DataFrame:
    out = pd.DataFrame(index=frame.index)
    for label, col in columns:
        out[label] = frame[col].isna() if col in frame.columns else True
    return out


def _pattern_shares(matrix: pd.DataFrame) -> pd.Series:
    if matrix.empty:
        return pd.Series(dtype=float)
    keys = matrix.astype(int).astype(str).agg("".join, axis=1)
    counts = keys.value_counts()
    return counts / counts.sum()


def _entropy_bits(shares: pd.Series) -> float:
    p = shares[shares > 0].to_numpy(dtype=float)
    return float(-(p * np.log2(p)).sum()) if p.size else float("nan")


def run_missingness_pattern_metrics(
    data: BenchmarkData, syn_sources: pd.DataFrame, bootstrap_reps: int = 0
) -> list[MetricResult]:
    fields = [
        (label, real_col)
        for label, real_col, syn_col in MISSINGNESS_FIELDS
        if real_col in data.real.columns and syn_col in syn_sources.columns
    ]
    syn_fields = [
        (label, syn_col)
        for label, real_col, syn_col in MISSINGNESS_FIELDS
        if real_col in data.real.columns and syn_col in syn_sources.columns
    ]
    if not fields:
        return []

    real_matrix = _missingness_matrix(data.real, fields)
    syn_matrix = _missingness_matrix(syn_sources, syn_fields)
    real_shares = _pattern_shares(real_matrix)
    syn_shares = _pattern_shares(syn_matrix)
    idx = real_shares.index.union(syn_shares.index)
    tv = float(
        0.5 * (real_shares.reindex(idx, fill_value=0) - syn_shares.reindex(idx, fill_value=0)).abs().sum()
    )
    entropy_gap = _entropy_bits(syn_shares) - _entropy_bits(real_shares)

    metrics = [
        _metric(
            data, "missingness_structure", "joint_pattern", "missingness_pattern", "TV",
            None, None, tv, tv, TOLERANCES["missing_pattern_tv"],
            classify_upper(tv, TOLERANCES["missing_pattern_tv"]),
            notes=f"fields={[f[0] for f in fields]}; n_real_patterns={len(real_shares)}; n_syn_patterns={len(syn_shares)}",
        ),
        _metric(
            data, "missingness_structure", "joint_pattern", "missingness_entropy", "abs_diff_bits",
            _entropy_bits(real_shares), _entropy_bits(syn_shares), entropy_gap, abs(entropy_gap),
            TOLERANCES["missing_pattern_entropy_bits"],
            classify_abs(entropy_gap, TOLERANCES["missing_pattern_entropy_bits"]),
        ),
    ]

    # Largest single-pattern discrepancy: a matching TV can still hide one
    # dominant pattern being badly wrong.
    gaps = (syn_shares.reindex(idx, fill_value=0) - real_shares.reindex(idx, fill_value=0)).abs()
    worst_pattern = str(gaps.idxmax()) if len(gaps) else ""
    worst = float(gaps.max()) if len(gaps) else float("nan")
    metrics.append(
        _metric(
            data, "missingness_structure", f"pattern={worst_pattern}", "missingness_pattern",
            "max_single_pattern_abs_diff",
            float(real_shares.get(worst_pattern, 0.0)), float(syn_shares.get(worst_pattern, 0.0)),
            worst, worst, TOLERANCES["missing_pattern_tv"],
            classify_upper(worst, TOLERANCES["missing_pattern_tv"]),
            notes="pattern bit order: " + ",".join(f[0] for f in fields),
        )
    )

    # Pairwise co-occurrence lift: do the same fields fail together?
    labels = [f[0] for f in fields]
    worst_gap, worst_pair = 0.0, ""
    for i, a in enumerate(labels):
        for b in labels[i + 1 :]:
            def log_lift(matrix: pd.DataFrame, x=a, y=b) -> float:
                pa = float(matrix[x].mean())
                pb = float(matrix[y].mean())
                pab = float((matrix[x] & matrix[y]).mean())
                if pa <= 0 or pb <= 0 or pab <= 0:
                    return float("nan")
                return float(np.log(pab / (pa * pb)))

            gap = log_lift(syn_matrix) - log_lift(real_matrix)
            if np.isfinite(gap) and abs(gap) > abs(worst_gap):
                worst_gap, worst_pair = gap, f"{a}+{b}"
    metrics.append(
        _metric(
            data, "missingness_structure", worst_pair or "none", "co_occurrence_lift",
            "max_abs_log_lift_gap",
            None, None, worst_gap, abs(worst_gap), TOLERANCES["missing_lift_log_gap"],
            classify_abs(worst_gap, TOLERANCES["missing_lift_log_gap"]) if worst_pair else Status.INCONCLUSIVE,
            notes="worst-case field pair over all missingness-indicator pairs",
        )
    )
    return metrics


# --------------------------------------------------------------------------
# Identifier validity and buyer-name variation
# --------------------------------------------------------------------------


def _invalid_identifier_rate(frame: pd.DataFrame, raw_col: str, clean_col: str) -> float:
    """Share of notices carrying a *present but unusable* identifier."""
    if raw_col not in frame.columns or clean_col not in frame.columns:
        return float("nan")
    present = frame[raw_col].notna()
    if not present.any():
        return float("nan")
    return float((present & frame[clean_col].isna()).mean())


def _name_variants_per_group(frame: pd.DataFrame, group_col: str, name_col: str) -> pd.Series:
    sub = frame.loc[frame[group_col].notna() & frame[name_col].notna(), [group_col, name_col]]
    if sub.empty:
        return pd.Series(dtype=float)
    return sub.groupby(group_col)[name_col].nunique()


def _within_group_similarities(
    frame: pd.DataFrame, group_col: str, name_col: str, seed: int = 20260723
) -> pd.DataFrame:
    """Jaro-Winkler and token-Jaccard similarity for name pairs inside a group.

    Groups are capped at ``MAX_PAIRS_PER_GROUP`` sampled pairs so a handful of
    very large buyers cannot dominate the similarity distribution.
    """
    from rapidfuzz.distance import JaroWinkler

    sub = frame.loc[frame[group_col].notna() & frame[name_col].notna(), [group_col, name_col]]
    if sub.empty:
        return pd.DataFrame(columns=["group", "jaro_winkler", "token_jaccard"])
    rng = np.random.default_rng(seed)
    rows = []
    for group, names in sub.groupby(group_col)[name_col]:
        distinct = sorted(set(names.astype(str)))
        if len(distinct) < 2:
            continue
        pairs = [(i, j) for i in range(len(distinct)) for j in range(i + 1, len(distinct))]
        if len(pairs) > MAX_PAIRS_PER_GROUP:
            picks = rng.choice(len(pairs), size=MAX_PAIRS_PER_GROUP, replace=False)
            pairs = [pairs[p] for p in picks]
        for i, j in pairs:
            a, b = distinct[i], distinct[j]
            ta, tb = set(a.split()), set(b.split())
            union = ta | tb
            rows.append(
                {
                    "group": str(group),
                    "jaro_winkler": float(JaroWinkler.similarity(a, b)),
                    "token_jaccard": float(len(ta & tb) / len(union)) if union else float("nan"),
                }
            )
    return pd.DataFrame(rows, columns=["group", "jaro_winkler", "token_jaccard"])


def run_identifier_name_metrics(
    data: BenchmarkData, syn_sources: pd.DataFrame, bootstrap_reps: int = 0
) -> list[MetricResult]:
    real = data.real
    metrics: list[MetricResult] = []

    for label, raw_col, clean_col in [
        ("siret", "buyer_siret_raw", "buyer_siret_clean"),
        ("siren", "buyer_siren_raw", "buyer_siren_clean"),
    ]:
        real_rate = _invalid_identifier_rate(real, raw_col, clean_col)
        syn_rate = _invalid_identifier_rate(syn_sources, raw_col, clean_col)
        diff_pp = (syn_rate - real_rate) * 100 if np.isfinite(real_rate) and np.isfinite(syn_rate) else float("nan")
        metrics.append(
            _metric(
                data, "names_identifiers", "overall", f"{label}_invalid_among_present", "abs_diff_pp",
                real_rate, syn_rate, diff_pp, abs(diff_pp) if np.isfinite(diff_pp) else None,
                TOLERANCES["identifier_invalid_pp"],
                classify_abs(diff_pp, TOLERANCES["identifier_invalid_pp"]),
                notes="present raw identifier that fails format/checksum validation",
            )
        )

    # Which identifier the production buyer key ends up resting on is the
    # single strongest driver of candidate-set size, so its mix is gated.
    if "buyer_key_type" in real.columns and "buyer_key_type" in syn_sources.columns:
        real_shares = real["buyer_key_type"].fillna("__MISSING__").astype(str).value_counts(normalize=True)
        syn_shares = syn_sources["buyer_key_type"].fillna("__MISSING__").astype(str).value_counts(normalize=True)
        idx = real_shares.index.union(syn_shares.index)
        tv = float(0.5 * (real_shares.reindex(idx, fill_value=0) - syn_shares.reindex(idx, fill_value=0)).abs().sum())
        metrics.append(
            _metric(
                data, "names_identifiers", "overall", "buyer_key_type_mix", "TV",
                None, None, tv, tv, TOLERANCES["identifier_source_tv"],
                classify_upper(tv, TOLERANCES["identifier_source_tv"]),
                notes="; ".join(f"{k}: real={real_shares.get(k, 0):.3f} syn={syn_shares.get(k, 0):.3f}" for k in idx),
            )
        )

    # Within-buyer name variation, on a checksum-valid-SIREN silver standard.
    real_variants = _name_variants_per_group(real, "buyer_siren_clean", "buyer_name_normalized")
    syn_variants = _name_variants_per_group(syn_sources, "buyer_siren_clean", "buyer_name_normalized")
    if len(real_variants) >= MIN_GROUP_SIZE and len(syn_variants) >= MIN_GROUP_SIZE:
        diff = float(syn_variants.mean() - real_variants.mean())
        metrics.append(
            _metric(
                data, "names_identifiers", "silver_siren_groups", "name_variants_per_buyer", "mean_abs_diff",
                float(real_variants.mean()), float(syn_variants.mean()), diff, abs(diff),
                TOLERANCES["name_variants_per_buyer_abs"],
                classify_abs(diff, TOLERANCES["name_variants_per_buyer_abs"]),
                provenance="silver_standard_real_vs_synthetic",
                notes=(
                    f"n_real_groups={len(real_variants)}; n_syn_groups={len(syn_variants)}; "
                    "SIREN-grouped silver standard over-represents cleanly identified buyers"
                ),
            )
        )
    else:
        metrics.append(
            _metric(
                data, "names_identifiers", "silver_siren_groups", "name_variants_per_buyer", "mean_abs_diff",
                None, None, None, None, TOLERANCES["name_variants_per_buyer_abs"], Status.INCONCLUSIVE,
                provenance="silver_standard_real_vs_synthetic",
                notes=f"insufficient silver groups: real={len(real_variants)}, synthetic={len(syn_variants)}",
            )
        )

    real_sim = _within_group_similarities(real, "buyer_siren_clean", "buyer_name_normalized")
    syn_sim = _within_group_similarities(syn_sources, "buyer_siren_clean", "buyer_name_normalized")
    for column in ["jaro_winkler", "token_jaccard"]:
        if len(real_sim) < MIN_GROUP_SIZE or len(syn_sim) < MIN_GROUP_SIZE:
            metrics.append(
                _metric(
                    data, "names_identifiers", "silver_siren_groups", f"name_{column}", "q50_abs_diff",
                    None, None, None, None, TOLERANCES["name_similarity_quantile_abs"], Status.INCONCLUSIVE,
                    provenance="silver_standard_real_vs_synthetic",
                    notes=f"insufficient within-group name pairs: real={len(real_sim)}, synthetic={len(syn_sim)}",
                )
            )
            continue
        for q in [0.10, 0.50]:
            rq = float(real_sim[column].quantile(q))
            sq = float(syn_sim[column].quantile(q))
            diff = sq - rq
            metrics.append(
                _metric(
                    data, "names_identifiers", "silver_siren_groups", f"name_{column}",
                    f"q{int(q * 100)}_abs_diff", rq, sq, diff, abs(diff),
                    TOLERANCES["name_similarity_quantile_abs"],
                    classify_abs(diff, TOLERANCES["name_similarity_quantile_abs"]),
                    provenance="silver_standard_real_vs_synthetic",
                    notes=f"n_real_pairs={len(real_sim)}; n_syn_pairs={len(syn_sim)}",
                )
            )

    # Silver-standard bias quantification: the same synthetic statistic under
    # hidden truth versus under the SIREN silver grouping. This is not a
    # real-vs-synthetic comparison; it measures how much the real-side estimate
    # above is expected to be biased by using SIREN groups at all.
    truth_names = data.observed[["notice_id_synthetic", "buyer_name_raw"]].merge(
        data.clean[["notice_id_synthetic", "buyer_id_true"]], on="notice_id_synthetic", how="left"
    )
    truth_names["buyer_name_normalized"] = syn_sources["buyer_name_normalized"].to_numpy()
    truth_variants = _name_variants_per_group(truth_names, "buyer_id_true", "buyer_name_normalized")
    if len(truth_variants) and len(syn_variants):
        bias = float(syn_variants.mean() - truth_variants.mean())
        metrics.append(
            _metric(
                data, "names_identifiers", "silver_vs_truth", "name_variants_per_buyer",
                "silver_minus_truth", float(truth_variants.mean()), float(syn_variants.mean()),
                bias, abs(bias), "documented_bias", Status.PASS,
                provenance="synthetic_truth_vs_silver",
                notes=(
                    "negative values mean the SIREN silver standard under-counts true within-buyer "
                    "name variation; reported as a caveat on the real-side estimate, never as a failure"
                ),
            )
        )
    return metrics


def run_structure_validation(data: BenchmarkData, bootstrap_reps: int = 0) -> list[MetricResult]:
    syn_sources = _synthetic_sources(data)
    metrics: list[MetricResult] = []
    metrics.extend(run_buyer_activity_metrics(data, syn_sources, bootstrap_reps=bootstrap_reps))
    metrics.extend(run_missingness_pattern_metrics(data, syn_sources, bootstrap_reps=bootstrap_reps))
    metrics.extend(run_identifier_name_metrics(data, syn_sources, bootstrap_reps=bootstrap_reps))
    return metrics
