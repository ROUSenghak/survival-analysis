"""Replicate, scenario and seed stability (Section 5.8, Phase 5).

A benchmark conclusion drawn from one generated world is a statement about one
draw, not about the generator. This module recomputes a compact headline
vector on every replicate that actually exists for a benchmark version and
asks two questions:

* do the headline properties move when the world or corruption seed changes?
* does the *ranking* of the probe linkers survive a change of scenario?

Where the required replicates were never generated -- for example only one
world seed exists for a scenario -- the answer is ``INCONCLUSIVE``, never
``PASS``. Absence of a replicate is absence of evidence about stability, and
recording it as a pass is exactly the failure mode the specification warns
about in Section 4.1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from boamp.synthetic.validation_framework.difficulty import run_difficulty_metrics
from boamp.synthetic.validation_framework.loaders import (
    BenchmarkData,
    available_replicates,
    load_benchmark_data,
)
from boamp.synthetic.validation_framework.models import MetricResult, Status


TOLERANCES = {
    "headline_cv_max": 0.25,
    "ranking_kendall_tau_min": 0.80,
    "pairwise_supported_fraction_min": 0.80,
    "pairwise_ambiguous_fraction_max": 0.25,
    "pairwise_win_rate_strong_min": 0.95,
    "pairwise_win_rate_directional_min": 0.80,
}

SCENARIOS_EXCLUDED_FROM_STABILITY = ("clean_sanity",)

PROBE_REPLICATE_COLUMNS = [
    "scenario",
    "world",
    "corruption",
    "probe",
    "n_predicted_pairs",
    "pair_precision",
    "pair_recall",
    "pair_f1",
    "bcubed_precision",
    "bcubed_recall",
    "bcubed_f1",
]

PROBE_RANKING_SUMMARY_COLUMNS = [
    "scope",
    "scenario",
    "probe",
    "n_units",
    "mean_pair_f1",
    "sd_pair_f1",
    "min_pair_f1",
    "max_pair_f1",
    "mean_rank",
    "min_rank",
    "max_rank",
    "prob_rank1",
    "notes",
]

PROBE_PAIRWISE_COMPARISON_COLUMNS = [
    "scope",
    "scenario",
    "algorithm_a",
    "algorithm_b",
    "n_units",
    "mean_a",
    "mean_b",
    "mean_difference",
    "sd_difference",
    "ci_low",
    "ci_high",
    "win_rate_a",
    "win_rate_b",
    "tie_rate",
    "support_status",
    "winner",
    "claim",
    "notes",
]

HEADLINE_PROPERTIES = [
    ("hidden_truth_difficulty", "production_window", "blocking_pairs_completeness", "PC"),
    ("hidden_truth_difficulty", "production_window", "match_vs_hard_negative_score", "overlap"),
    ("algorithm_utility", "all_probes", "probe_headroom", "best_pair_f1"),
]


def _metric(
    data: BenchmarkData,
    subgroup: str,
    prop: str,
    metric: str,
    synthetic,
    effect,
    tolerance,
    status: Status | str,
    notes: str = "",
) -> MetricResult:
    return MetricResult(
        benchmark_version=data.benchmark_version,
        scenario=data.scenario,
        seed=data.seed_label,
        scope="robustness",
        subgroup=subgroup,
        property=prop,
        metric=metric,
        real_estimate=None,
        synthetic_estimate=synthetic,
        difference=None,
        effect_size=effect,
        ci_low=None,
        ci_high=None,
        tolerance=tolerance,
        status=status,
        provenance="synthetic_truth",
        notes=notes,
    )


def _kendall_tau(a: list[float], b: list[float]) -> float:
    """Kendall rank correlation without a SciPy dependency."""
    n = len(a)
    if n < 2:
        return float("nan")
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            sign = np.sign(a[i] - a[j]) * np.sign(b[i] - b[j])
            if sign > 0:
                concordant += 1
            elif sign < 0:
                discordant += 1
    total = concordant + discordant
    return float((concordant - discordant) / total) if total else float("nan")


def _probe_rank_tau_summary(pivot: pd.DataFrame, max_examples: int = 8) -> tuple[float, list[str], int, int]:
    """Return the worst pairwise Kendall tau and compact worst-pair examples."""
    columns = list(pivot.columns)
    pair_rows = []
    for i in range(len(columns)):
        for j in range(i + 1, len(columns)):
            a = pivot[columns[i]].astype(float)
            b = pivot[columns[j]].astype(float)
            joint = pd.concat([a, b], axis=1).dropna()
            if len(joint) < 2:
                continue
            tau = _kendall_tau(joint.iloc[:, 0].tolist(), joint.iloc[:, 1].tolist())
            if np.isfinite(tau):
                pair_rows.append((float(tau), f"{columns[i]} vs {columns[j]}"))
    if not pair_rows:
        return float("nan"), [], len(columns), 0
    pair_rows.sort(key=lambda row: row[0])
    worst = pair_rows[0][0]
    examples = [f"{label}: tau={tau:.2f}" for tau, label in pair_rows[:max_examples]]
    return worst, examples, len(columns), len(pair_rows)


def _probe_ranking_metric(
    data: BenchmarkData,
    subgroup: str,
    pivot: pd.DataFrame,
    comparison_unit: str,
    notes_prefix: str,
) -> MetricResult:
    worst, worst_examples, n_columns, n_pairs = _probe_rank_tau_summary(pivot)
    if n_columns < 2:
        return _metric(
            data, subgroup, "probe_ranking", "min_kendall_tau", None, None,
            TOLERANCES["ranking_kendall_tau_min"], Status.INCONCLUSIVE,
            notes=f"{notes_prefix}; only {n_columns} {comparison_unit}(s) available",
        )
    return _metric(
        data, subgroup, "probe_ranking", "min_kendall_tau", worst, worst,
        TOLERANCES["ranking_kendall_tau_min"],
        Status.PASS
        if np.isfinite(worst) and worst >= TOLERANCES["ranking_kendall_tau_min"]
        else Status.WARNING
        if np.isfinite(worst)
        else Status.INCONCLUSIVE,
        notes=(
            f"{notes_prefix}; {comparison_unit}s compared={n_columns}; "
            f"pairwise comparisons={n_pairs}; worst examples="
            + "; ".join(worst_examples)
        ),
    )


def _paired_difference_summary(
    values_a: pd.Series,
    values_b: pd.Series,
    algorithm_a: str,
    algorithm_b: str,
    scope: str,
    scenario: str,
    notes: str,
) -> dict | None:
    joint = pd.concat(
        [
            pd.to_numeric(values_a, errors="coerce").rename("a"),
            pd.to_numeric(values_b, errors="coerce").rename("b"),
        ],
        axis=1,
    ).dropna()
    if joint.empty:
        return None
    diff = joint["a"] - joint["b"]
    n = int(len(diff))
    mean_diff = float(diff.mean())
    sd_diff = float(diff.std(ddof=1)) if n > 1 else 0.0
    if n > 1:
        se = sd_diff / float(np.sqrt(n))
        ci_low = float(mean_diff - 1.96 * se)
        ci_high = float(mean_diff + 1.96 * se)
    else:
        ci_low = float("nan")
        ci_high = float("nan")

    win_rate_a = float(diff.gt(0).mean())
    win_rate_b = float(diff.lt(0).mean())
    tie_rate = float(diff.eq(0).mean())
    if n < 2 or not np.isfinite(ci_low) or not np.isfinite(ci_high):
        support_status = str(Status.INCONCLUSIVE)
        winner = "INCONCLUSIVE"
        claim = "too few paired units for uncertainty-supported comparison"
    elif ci_low > 0:
        winner = algorithm_a
        support_status = (
            str(Status.PASS)
            if win_rate_a >= TOLERANCES["pairwise_win_rate_strong_min"]
            else str(Status.WARNING)
            if win_rate_a >= TOLERANCES["pairwise_win_rate_directional_min"]
            else str(Status.WARNING)
        )
        claim = (
            "supported winner"
            if support_status == str(Status.PASS)
            else "directional winner; report with uncertainty"
        )
    elif ci_high < 0:
        winner = algorithm_b
        support_status = (
            str(Status.PASS)
            if win_rate_b >= TOLERANCES["pairwise_win_rate_strong_min"]
            else str(Status.WARNING)
            if win_rate_b >= TOLERANCES["pairwise_win_rate_directional_min"]
            else str(Status.WARNING)
        )
        claim = (
            "supported winner"
            if support_status == str(Status.PASS)
            else "directional winner; report with uncertainty"
        )
    else:
        support_status = str(Status.WARNING)
        winner = "TIE_OR_NO_CLAIM"
        claim = "confidence interval crosses zero; do not rank this pair"

    return {
        "scope": scope,
        "scenario": scenario,
        "algorithm_a": algorithm_a,
        "algorithm_b": algorithm_b,
        "n_units": n,
        "mean_a": float(joint["a"].mean()),
        "mean_b": float(joint["b"].mean()),
        "mean_difference": mean_diff,
        "sd_difference": sd_diff,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "win_rate_a": win_rate_a,
        "win_rate_b": win_rate_b,
        "tie_rate": tie_rate,
        "support_status": support_status,
        "winner": winner,
        "claim": claim,
        "notes": notes,
    }


def _summarize_pairwise_units(frame: pd.DataFrame, scope: str, scenario: str, notes: str) -> list[dict]:
    if frame.empty:
        return []
    pivot = frame.pivot_table(index="unit", columns="probe", values="pair_f1")
    algorithms = sorted(pivot.columns.astype(str))
    rows: list[dict] = []
    for i, algorithm_a in enumerate(algorithms):
        for algorithm_b in algorithms[i + 1:]:
            row = _paired_difference_summary(
                pivot[algorithm_a],
                pivot[algorithm_b],
                algorithm_a,
                algorithm_b,
                scope,
                scenario,
                notes,
            )
            if row is not None:
                rows.append(row)
    return rows


def _summarize_rank_units(frame: pd.DataFrame, scope: str, scenario: str, notes: str) -> list[dict]:
    if frame.empty:
        return []
    ranked = frame.copy()
    ranked["rank"] = ranked.groupby("unit")["pair_f1"].rank(ascending=False, method="min")
    rows = []
    for probe, group in ranked.groupby("probe"):
        f1 = pd.to_numeric(group["pair_f1"], errors="coerce").dropna()
        ranks = pd.to_numeric(group["rank"], errors="coerce").dropna()
        if f1.empty or ranks.empty:
            continue
        rows.append(
            {
                "scope": scope,
                "scenario": scenario,
                "probe": probe,
                "n_units": int(len(f1)),
                "mean_pair_f1": float(f1.mean()),
                "sd_pair_f1": float(f1.std(ddof=1)) if len(f1) > 1 else 0.0,
                "min_pair_f1": float(f1.min()),
                "max_pair_f1": float(f1.max()),
                "mean_rank": float(ranks.mean()),
                "min_rank": int(ranks.min()),
                "max_rank": int(ranks.max()),
                "prob_rank1": float(ranks.eq(1).mean()),
                "notes": notes,
            }
        )
    return rows


def summarize_probe_ranking_stability(probes: pd.DataFrame) -> pd.DataFrame:
    """Probe rank intervals and rank-1 frequencies across generated artifacts."""
    if probes.empty:
        return pd.DataFrame(columns=PROBE_RANKING_SUMMARY_COLUMNS)
    usable = probes.loc[~probes["scenario"].isin(SCENARIOS_EXCLUDED_FROM_STABILITY)].copy()
    if usable.empty:
        return pd.DataFrame(columns=PROBE_RANKING_SUMMARY_COLUMNS)
    usable["unit"] = usable["scenario"].astype(str) + "/" + usable["world"].astype(str) + "-" + usable["corruption"].astype(str)
    rows: list[dict] = []
    for scenario, group in usable.groupby("scenario"):
        scenario_units = group.copy()
        scenario_units["unit"] = scenario_units["world"].astype(str) + "-" + scenario_units["corruption"].astype(str)
        rows.extend(
            _summarize_rank_units(
                scenario_units,
                "within_scenario",
                str(scenario),
                "rank distribution across generated seeds for one scenario",
            )
        )
    scenario_means = (
        usable.groupby(["scenario", "probe"], as_index=False)["pair_f1"]
        .mean()
        .rename(columns={"scenario": "unit"})
    )
    rows.extend(
        _summarize_rank_units(
            scenario_means,
            "cross_scenario_means",
            "BENCHMARK_SCENARIOS",
            "rank distribution across mean pair-F1 by benchmark scenario",
        )
    )
    rows.extend(
        _summarize_rank_units(
            usable,
            "all_benchmark_replicates",
            "ALL",
            "rank distribution across all benchmark scenario/seed artifacts",
        )
    )
    return pd.DataFrame(rows, columns=PROBE_RANKING_SUMMARY_COLUMNS)


def summarize_probe_pairwise_comparisons(probes: pd.DataFrame) -> pd.DataFrame:
    """Paired probe-linker comparisons with uncertainty and tie/no-claim labels."""
    if probes.empty:
        return pd.DataFrame(columns=PROBE_PAIRWISE_COMPARISON_COLUMNS)
    usable = probes.loc[~probes["scenario"].isin(SCENARIOS_EXCLUDED_FROM_STABILITY)].copy()
    if usable.empty:
        return pd.DataFrame(columns=PROBE_PAIRWISE_COMPARISON_COLUMNS)
    usable["unit"] = (
        usable["scenario"].astype(str)
        + "/"
        + usable["world"].astype(str)
        + "-"
        + usable["corruption"].astype(str)
    )
    rows: list[dict] = []
    for scenario, group in usable.groupby("scenario"):
        scenario_units = group.copy()
        scenario_units["unit"] = scenario_units["world"].astype(str) + "-" + scenario_units["corruption"].astype(str)
        rows.extend(
            _summarize_pairwise_units(
                scenario_units,
                "within_scenario",
                str(scenario),
                "paired pair-F1 differences across generated seeds for one scenario",
            )
        )
    scenario_means = (
        usable.groupby(["scenario", "probe"], as_index=False)["pair_f1"]
        .mean()
        .rename(columns={"scenario": "unit"})
    )
    rows.extend(
        _summarize_pairwise_units(
            scenario_means,
            "cross_scenario_means",
            "BENCHMARK_SCENARIOS",
            "paired differences across scenario mean pair-F1 values",
        )
    )
    rows.extend(
        _summarize_pairwise_units(
            usable,
            "all_benchmark_replicates",
            "ALL",
            "paired pair-F1 differences across all generated scenario/seed artifacts",
        )
    )
    return pd.DataFrame(rows, columns=PROBE_PAIRWISE_COMPARISON_COLUMNS)


def _pairwise_support_metric(
    data: BenchmarkData,
    subgroup: str,
    comparisons: pd.DataFrame,
    notes_prefix: str,
) -> list[MetricResult]:
    if comparisons.empty:
        return [
            _metric(
                data, subgroup, "ranking_pairwise_support", "comparison_count", 0, None,
                ">=1", Status.INCONCLUSIVE,
                notes=f"{notes_prefix}; no pairwise comparison rows available",
            )
        ]
    statuses = comparisons["support_status"].astype(str)
    supported = comparisons.loc[
        comparisons["winner"].astype(str).ne("TIE_OR_NO_CLAIM")
        & statuses.isin({str(Status.PASS), str(Status.WARNING)})
    ]
    ambiguous = comparisons.loc[comparisons["winner"].astype(str).eq("TIE_OR_NO_CLAIM")]
    inconclusive = statuses.eq(str(Status.INCONCLUSIVE))
    n = int(len(comparisons))
    supported_fraction = float(len(supported) / n) if n else float("nan")
    ambiguous_fraction = float(len(ambiguous) / n) if n else float("nan")
    rows = [
        _metric(
            data, subgroup, "ranking_pairwise_support", "comparison_count", n, None,
            ">=1", Status.PASS if n >= 1 else Status.INCONCLUSIVE,
            notes=f"{notes_prefix}; number of algorithm pairs with paired evidence",
        ),
        _metric(
            data, subgroup, "ranking_pairwise_support", "supported_pair_fraction",
            supported_fraction, supported_fraction, TOLERANCES["pairwise_supported_fraction_min"],
            Status.PASS
            if np.isfinite(supported_fraction)
            and supported_fraction >= TOLERANCES["pairwise_supported_fraction_min"]
            and not inconclusive.any()
            else Status.WARNING
            if np.isfinite(supported_fraction)
            else Status.INCONCLUSIVE,
            notes=(
                f"{notes_prefix}; fraction of pairs whose paired 95% CI excludes zero. "
                "Supported pairs can be compared; unsupported pairs must be reported as ties/no-claim"
            ),
        ),
        _metric(
            data, subgroup, "ranking_pairwise_support", "ambiguous_pair_fraction",
            ambiguous_fraction, ambiguous_fraction, TOLERANCES["pairwise_ambiguous_fraction_max"],
            Status.PASS
            if np.isfinite(ambiguous_fraction)
            and ambiguous_fraction <= TOLERANCES["pairwise_ambiguous_fraction_max"]
            and not inconclusive.any()
            else Status.WARNING
            if np.isfinite(ambiguous_fraction)
            else Status.INCONCLUSIVE,
            notes=(
                f"{notes_prefix}; fraction of pairs whose paired 95% CI crosses zero. "
                "Ambiguous pairs are allowed only as explicit tie/no-claim results"
            ),
        ),
    ]
    return rows


def collect_replicates(project_root, version: str, exclude_scenarios: tuple[str, ...] = ()) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Headline metrics and probe rankings for every generated replicate.

    Returns ``(headline_frame, probe_frame)``; both are empty if nothing could
    be evaluated.
    """
    headline_rows, probe_rows = [], []
    for scenario, world, corruption in available_replicates(project_root, version):
        if scenario in exclude_scenarios:
            continue
        try:
            data = load_benchmark_data(project_root, version, scenario, world, corruption)
            metrics, probes = run_difficulty_metrics(data)
        except (FileNotFoundError, KeyError, ValueError) as exc:  # pragma: no cover - defensive
            headline_rows.append(
                {
                    "scenario": scenario, "world": world, "corruption": corruption,
                    "property": "load", "metric": "error", "value": float("nan"), "error": str(exc),
                }
            )
            continue
        frame = pd.DataFrame([m.to_dict() for m in metrics])
        for scope, subgroup, prop, metric in HEADLINE_PROPERTIES:
            hit = frame.loc[
                frame["scope"].eq(scope)
                & frame["subgroup"].eq(subgroup)
                & frame["property"].eq(prop)
                & frame["metric"].eq(metric)
            ]
            headline_rows.append(
                {
                    "scenario": scenario,
                    "world": world,
                    "corruption": corruption,
                    "property": prop,
                    "metric": metric,
                    "value": float(hit["synthetic_estimate"].iloc[0]) if len(hit) else float("nan"),
                    "status": str(hit["status"].iloc[0]) if len(hit) else str(Status.INCONCLUSIVE),
                    "error": "",
                }
            )
        for row in probes.to_dict("records"):
            probe_rows.append({"scenario": scenario, "world": world, "corruption": corruption, **row})
    return pd.DataFrame(headline_rows), pd.DataFrame(probe_rows)


def run_robustness_validation(data: BenchmarkData, enabled: bool = True) -> tuple[list[MetricResult], pd.DataFrame]:
    """Scenario and seed stability for the benchmark version under validation."""
    empty = pd.DataFrame()
    if not enabled:
        return (
            [
                _metric(
                    data, "all_replicates", "replicate_stability", "availability", None, None,
                    "enabled", Status.INCONCLUSIVE,
                    notes="robustness sweep disabled for this run (--no-robustness)",
                )
            ],
            empty,
        )

    replicates = available_replicates(data.project_root, data.benchmark_version)
    scenarios = sorted({s for s, _w, _c in replicates})
    seeds_per_scenario = {
        s: len({(w, c) for sc, w, c in replicates if sc == s}) for s in scenarios
    }
    metrics: list[MetricResult] = [
        _metric(
            data, "all_replicates", "replicate_inventory", "count", len(replicates), None,
            "context_only", Status.PASS,
            notes=(
                f"scenarios={scenarios}; seed replicates per scenario={seeds_per_scenario}. "
                "Section 5.8 asks for several seeds per scenario; what exists is what is reported"
            ),
        )
    ]

    max_seeds = max(seeds_per_scenario.values(), default=0)
    if max_seeds < 2:
        metrics.append(
            _metric(
                data, "seed_replicates", "seed_stability", "availability", max_seeds, None, ">=2",
                Status.INCONCLUSIVE,
                notes=(
                    "no scenario has two independent world/corruption draws, so seed-to-seed "
                    "stability cannot be estimated. Generate a second world for at least the "
                    "central scenario before quoting any single-seed result as a benchmark property"
                ),
            )
        )
    elif seeds_per_scenario.get(data.scenario, 0) < 10:
        metrics.append(
            _metric(
                data, f"seed_replicates:{data.scenario}", "seed_stability", "availability",
                seeds_per_scenario.get(data.scenario, 0), None, ">=10", Status.WARNING,
                notes=(
                    f"{data.scenario} has {seeds_per_scenario.get(data.scenario, 0)} generated seed "
                    "replicates; final ranking readiness asks for at least 10"
                ),
            )
        )

    headline, probes = collect_replicates(
        data.project_root,
        data.benchmark_version,
        exclude_scenarios=SCENARIOS_EXCLUDED_FROM_STABILITY,
    )
    if headline.empty:
        metrics.append(
            _metric(
                data, "all_replicates", "headline_stability", "availability", 0, None, ">=2",
                Status.INCONCLUSIVE, notes="no replicate could be evaluated",
            )
        )
        return metrics, empty

    main = headline.loc[headline["scenario"].eq(data.scenario)].copy()
    if not main.empty:
        for prop, group in main.groupby("property"):
            values = pd.to_numeric(group["value"], errors="coerce").dropna()
            n = int(len(values))
            subgroup = f"seed_replicates:{data.scenario}"
            if n < 2:
                metrics.append(
                    _metric(
                        data, subgroup, prop, "seed_count", n, None, ">=10", Status.INCONCLUSIVE,
                        notes="fewer than two valid seeds, so within-scenario stability cannot be estimated",
                    )
                )
                continue
            mean = float(values.mean())
            sd = float(values.std(ddof=1))
            lo = float(values.quantile(0.025))
            hi = float(values.quantile(0.975))
            worst = float(values.min())
            cv = float(sd / mean) if mean else float("nan")
            nonpass = group.loc[
                group["status"].astype(str).isin({str(Status.WARNING), str(Status.FAIL), str(Status.INCONCLUSIVE)})
            ]
            nonpass_frequency = float(len(nonpass) / len(group))
            metrics.extend(
                [
                    _metric(
                        data, subgroup, prop, "seed_count", n, None, ">=10",
                        Status.PASS if n >= 10 else Status.WARNING,
                        notes="number of generated seed replicates included in the within-scenario summary",
                    ),
                    _metric(
                        data, subgroup, prop, "mean", mean, None, "context_only", Status.PASS,
                        notes=f"within-scenario mean over {n} generated seeds",
                    ),
                    _metric(
                        data, subgroup, prop, "std", sd, sd, "context_only", Status.PASS,
                        notes=f"within-scenario standard deviation over {n} generated seeds",
                    ),
                    _metric(
                        data, subgroup, prop, "central_95pct_interval", f"{lo:.6g}-{hi:.6g}",
                        None, "context_only", Status.PASS,
                        notes="empirical 2.5%-97.5% interval across generated seeds",
                    ),
                    _metric(
                        data, subgroup, prop, "worst_case", worst, None, "context_only", Status.PASS,
                        notes="minimum value observed across generated seeds",
                    ),
                    _metric(
                        data, subgroup, prop, "coefficient_of_variation", cv, cv,
                        TOLERANCES["headline_cv_max"],
                        Status.PASS if np.isfinite(cv) and cv <= TOLERANCES["headline_cv_max"] else Status.WARNING,
                        notes="within-scenario seed stability; high values mean one seed is not representative",
                    ),
                    _metric(
                        data, subgroup, prop, "nonpass_frequency", nonpass_frequency,
                        nonpass_frequency, "0",
                        Status.PASS if nonpass_frequency == 0 else Status.WARNING,
                        notes=(
                            "share of generated seeds whose underlying headline metric was not PASS "
                            f"(WARNING/FAIL/INCONCLUSIVE); affected seeds="
                            + ", ".join(f"{r.world}-{r.corruption}" for r in nonpass.itertuples())
                        ),
                    ),
                ]
            )

    # Cross-scenario spread of each headline property. Scenarios are meant to
    # differ, so a large spread here is informative rather than a failure: it
    # says which conclusions are scenario-dependent.
    for prop, group in headline.groupby("property"):
        values = pd.to_numeric(group["value"], errors="coerce").dropna()
        if len(values) < 2:
            metrics.append(
                _metric(
                    data, "cross_scenario", prop, "coefficient_of_variation", None, None,
                    TOLERANCES["headline_cv_max"], Status.INCONCLUSIVE,
                    notes=f"only {len(values)} evaluable replicate(s)",
                )
            )
            continue
        mean = float(values.mean())
        cv = float(values.std(ddof=1) / mean) if mean else float("nan")
        scenario_summaries = []
        for scenario_name, scenario_group in group.groupby("scenario"):
            scenario_values = pd.to_numeric(scenario_group["value"], errors="coerce").dropna()
            if scenario_values.empty:
                continue
            scenario_summaries.append(
                f"{scenario_name}:mean={scenario_values.mean():.3f},"
                f"range={scenario_values.min():.3f}-{scenario_values.max():.3f},n={len(scenario_values)}"
            )
        metrics.append(
            _metric(
                data, "cross_scenario", prop, "coefficient_of_variation", cv, cv,
                TOLERANCES["headline_cv_max"],
                Status.PASS if np.isfinite(cv) and cv <= TOLERANCES["headline_cv_max"] else Status.WARNING,
                notes=(
                    f"n_replicates={len(values)}; excluded={SCENARIOS_EXCLUDED_FROM_STABILITY}; "
                    "scenario summaries="
                    + "; ".join(scenario_summaries)
                    + ". A high value means this headline property is scenario-dependent and must be "
                    "quoted with its scenario, not as a single benchmark number"
                ),
            )
        )

    # Probe-linker ranking stability. This is the conclusion a benchmark user
    # actually draws, so it matters more than any single metric value. Report
    # within-scenario seed stability separately from cross-scenario stability:
    # scenarios are intentionally different and should not be silently averaged
    # into a single ranking claim.
    if not probes.empty:
        pairwise = summarize_probe_pairwise_comparisons(probes)
        for scenario, group in probes.groupby("scenario"):
            seed_pivot = group.pivot_table(
                index="probe", columns=["world", "corruption"], values="pair_f1"
            )
            metrics.append(
                _probe_ranking_metric(
                    data,
                    f"ranking_stability:{scenario}",
                    seed_pivot,
                    "seed replicate",
                    "within-scenario probe-ranking stability across generated seeds",
                )
            )
            pairwise_group = pairwise.loc[
                pairwise["scope"].eq("within_scenario")
                & pairwise["scenario"].astype(str).eq(str(scenario))
            ]
            metrics.extend(
                _pairwise_support_metric(
                    data,
                    f"pairwise_comparison:{scenario}",
                    pairwise_group,
                    "within-scenario paired probe-linker comparison support",
                )
            )

        scenario_pivot = probes.pivot_table(index="probe", columns="scenario", values="pair_f1", aggfunc="mean")
        metrics.append(
            _probe_ranking_metric(
                data,
                "ranking_stability:cross_scenario",
                scenario_pivot,
                "scenario mean",
                "cross-scenario probe-ranking stability using mean pair-F1 by scenario",
            )
        )
        metrics.extend(
            _pairwise_support_metric(
                data,
                "pairwise_comparison:cross_scenario",
                pairwise.loc[pairwise["scope"].eq("cross_scenario_means")],
                "cross-scenario paired probe-linker comparison support",
            )
        )

        overall_pivot = probes.pivot_table(
            index="probe", columns=["scenario", "world", "corruption"], values="pair_f1"
        )
        metrics.append(
            _probe_ranking_metric(
                data,
                "ranking_stability",
                overall_pivot,
                "scenario/seed replicate",
                (
                    "overall probe-ranking stability across all generated scenario/seed artifacts; "
                    "a low value means a single global algorithm ranking is not supported"
                ),
            )
        )
        metrics.extend(
            _pairwise_support_metric(
                data,
                "pairwise_comparison",
                pairwise.loc[pairwise["scope"].eq("all_benchmark_replicates")],
                "overall paired probe-linker comparison support",
            )
        )
    return metrics, probes
