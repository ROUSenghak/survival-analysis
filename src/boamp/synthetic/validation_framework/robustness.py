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
}

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

    headline, probes = collect_replicates(data.project_root, data.benchmark_version)
    if headline.empty:
        metrics.append(
            _metric(
                data, "all_replicates", "headline_stability", "availability", 0, None, ">=2",
                Status.INCONCLUSIVE, notes="no replicate could be evaluated",
            )
        )
        return metrics, empty

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
        metrics.append(
            _metric(
                data, "cross_scenario", prop, "coefficient_of_variation", cv, cv,
                TOLERANCES["headline_cv_max"],
                Status.PASS if np.isfinite(cv) and cv <= TOLERANCES["headline_cv_max"] else Status.WARNING,
                notes=(
                    f"n_replicates={len(values)}; values="
                    + ", ".join(
                        f"{r.scenario}/{r.world}-{r.corruption}={r.value:.3f}"
                        for r in group.itertuples()
                        if np.isfinite(r.value)
                    )
                    + ". A high value means this headline property is scenario-dependent and must be "
                    "quoted with its scenario, not as a single benchmark number"
                ),
            )
        )

    # Probe-linker ranking stability. This is the conclusion a benchmark user
    # actually draws, so it matters more than any single metric value.
    if not probes.empty:
        pivot = probes.pivot_table(
            index="probe", columns=["scenario", "world", "corruption"], values="pair_f1"
        )
        columns = list(pivot.columns)
        if len(columns) < 2:
            metrics.append(
                _metric(
                    data, "ranking_stability", "probe_ranking", "kendall_tau", None, None,
                    TOLERANCES["ranking_kendall_tau_min"], Status.INCONCLUSIVE,
                    notes=(
                        f"probe rankings available for only {len(columns)} replicate; ranking stability "
                        "needs at least two"
                    ),
                )
            )
        else:
            taus, pairs_compared = [], []
            for i in range(len(columns)):
                for j in range(i + 1, len(columns)):
                    a = pivot[columns[i]].astype(float)
                    b = pivot[columns[j]].astype(float)
                    joint = pd.concat([a, b], axis=1).dropna()
                    if len(joint) < 2:
                        continue
                    tau = _kendall_tau(joint.iloc[:, 0].tolist(), joint.iloc[:, 1].tolist())
                    taus.append(tau)
                    pairs_compared.append(f"{columns[i][0]} vs {columns[j][0]}: tau={tau:.2f}")
            finite_taus = [t for t in taus if np.isfinite(t)]
            worst = float(min(finite_taus)) if finite_taus else float("nan")
            metrics.append(
                _metric(
                    data, "ranking_stability", "probe_ranking", "min_kendall_tau", worst, worst,
                    TOLERANCES["ranking_kendall_tau_min"],
                    Status.PASS
                    if np.isfinite(worst) and worst >= TOLERANCES["ranking_kendall_tau_min"]
                    else Status.WARNING
                    if np.isfinite(worst)
                    else Status.INCONCLUSIVE,
                    notes=(
                        "; ".join(pairs_compared)
                        + ". Rank agreement across replicates that differ only by scenario; a low value "
                        "means algorithm conclusions from this benchmark are scenario-specific"
                    ),
                )
            )
    return metrics, probes
