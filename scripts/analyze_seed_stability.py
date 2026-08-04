"""Paired world-level algorithm comparison and ranking stability.

Seed stability is a *separate* question from observable fidelity and is treated
that way here: this script reads only linkage results that already exist and
never feeds anything back into the generator. Fixing the observable mechanisms
does not automatically make algorithm rankings stable, and this script exists to
say so with numbers instead of assuming either way.

For every pair of algorithms it reports the paired per-world difference
`delta_world = metric_a - metric_b`, computed on the *same* generated worlds so
world-to-world difficulty cancels:

    mean and median paired difference, standard deviation, a bootstrap
    confidence interval, the Monte Carlo standard error of the mean, the share
    of worlds each algorithm wins, and the ranking-reversal rate.

Claims are graded, not forced. A comparison whose interval straddles zero, or
whose winner changes across scenarios, is reported as practically tied,
metric-dependent or scenario-dependent rather than resolved.

Note on scenario counting: `moderate` is a documented alias of
`central_provisional` with the same seeds, so the two produce identical worlds.
Cross-scenario spread therefore rests on four distinct scenarios, not five, and
this script reports both counts.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

VERSION = "v0_4_population_alias_revision"
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 20260803
# Below this, a mean paired F1 difference is called practically tied regardless
# of significance: it is smaller than the seed-to-seed spread the benchmark
# itself carries, so it cannot support a ranking claim.
PRACTICAL_EQUIVALENCE_F1 = 0.02
DUPLICATE_SCENARIOS = {"moderate": "central_provisional"}


def _paired_bootstrap(deltas: np.ndarray, reps: int, seed: int) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    n = len(deltas)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    draws = rng.choice(deltas, size=(reps, n), replace=True).mean(axis=1)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)), float(draws.std(ddof=1))


def _classify(mean_delta: float, ci_low: float, ci_high: float, win_rate_a: float) -> tuple[str, str]:
    if not np.isfinite(ci_low) or not np.isfinite(ci_high):
        return "INCONCLUSIVE", "too few paired worlds to compare"
    crosses_zero = ci_low <= 0.0 <= ci_high
    if abs(mean_delta) < PRACTICAL_EQUIVALENCE_F1:
        return "PRACTICALLY_TIED", (
            f"mean paired difference {mean_delta:+.4f} is below the {PRACTICAL_EQUIVALENCE_F1} "
            "practical-equivalence margin"
        )
    if crosses_zero:
        return "UNCERTAIN", "95% paired bootstrap interval includes zero"
    if 0.2 <= win_rate_a <= 0.8:
        return "UNCERTAIN", (
            f"interval excludes zero but the winner changes in {100 * min(win_rate_a, 1 - win_rate_a):.0f}% "
            "of worlds"
        )
    return "SUPPORTED", "interval excludes zero and the winner is consistent across worlds"


def pairwise_table(frame: pd.DataFrame, metric: str, scope: str, scenario: str | None) -> list[dict]:
    rows = []
    algorithms = sorted(frame["algorithm"].unique())
    for a, b in combinations(algorithms, 2):
        left = frame.loc[frame["algorithm"].eq(a)].set_index(["scenario", "world"])[metric]
        right = frame.loc[frame["algorithm"].eq(b)].set_index(["scenario", "world"])[metric]
        common = left.index.intersection(right.index)
        if len(common) < 2:
            continue
        deltas = (left.loc[common] - right.loc[common]).to_numpy(dtype=float)
        deltas = deltas[np.isfinite(deltas)]
        mean_delta = float(np.mean(deltas))
        ci_low, ci_high, mcse = _paired_bootstrap(deltas, BOOTSTRAP_REPS, BOOTSTRAP_SEED)
        win_rate_a = float((deltas > 0).mean())
        status, claim = _classify(mean_delta, ci_low, ci_high, win_rate_a)
        rows.append(
            {
                "scope": scope,
                "scenario": scenario or "ALL",
                "metric": metric,
                "algorithm_a": a,
                "algorithm_b": b,
                "n_paired_worlds": int(len(deltas)),
                "mean_a": float(left.loc[common].mean()),
                "mean_b": float(right.loc[common].mean()),
                "mean_paired_difference": mean_delta,
                "median_paired_difference": float(np.median(deltas)),
                "sd_paired_difference": float(np.std(deltas, ddof=1)) if len(deltas) > 1 else float("nan"),
                "ci_low": ci_low,
                "ci_high": ci_high,
                "monte_carlo_se_of_mean": mcse,
                "win_rate_a": win_rate_a,
                "win_rate_b": float((deltas < 0).mean()),
                "tie_rate": float((deltas == 0).mean()),
                "support_status": status,
                "winner": a if mean_delta > 0 else b,
                "claim": claim,
            }
        )
    return rows


def ranking_reversal_table(frame: pd.DataFrame, metric: str) -> pd.DataFrame:
    """How often the per-world ranking differs from the pooled ranking."""
    pooled = (
        frame.groupby("algorithm")[metric].mean().sort_values(ascending=False).index.tolist()
    )
    rows = []
    for (scenario, world), group in frame.groupby(["scenario", "world"]):
        order = group.sort_values(metric, ascending=False)["algorithm"].tolist()
        rows.append(
            {
                "scenario": scenario,
                "world": world,
                "metric": metric,
                "world_ranking": ">".join(order),
                "matches_pooled_ranking": order == pooled,
                "top1_matches_pooled": bool(order and order[0] == pooled[0]),
            }
        )
    out = pd.DataFrame(rows)
    out["pooled_ranking"] = ">".join(pooled)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=VERSION)
    parser.add_argument(
        "--metrics",
        default="pair_f1_end_to_end,pair_f1_fixed_candidate,pair_precision,pair_recall_end_to_end",
    )
    args = parser.parse_args()

    base = ROOT / "reports" / "tables" / "synthetic_benchmark" / args.version
    source = base / "linkage_algorithm_benchmark" / "per_world_metrics.csv"
    fallback = base / "validation_framework" / "probe_replicate_results.csv"
    if source.exists():
        frame = pd.read_csv(source)
        population = "linkage_algorithm_benchmark/per_world_metrics.csv"
    elif fallback.exists():
        # The frozen probe linkers the validation framework already evaluates on
        # every generated replicate. They are weaker than the trained models in
        # the linkage benchmark, but they are the same three methods on the same
        # worlds, so the *stability* question -- does the ranking survive a seed
        # change -- is answerable from them. The report must say which source it
        # used, because a claim about gradient boosting cannot rest on this one.
        frame = pd.read_csv(fallback).rename(columns={"probe": "algorithm"})
        population = "validation_framework/probe_replicate_results.csv (frozen probe linkers)"
        print(f"note: {source.relative_to(ROOT)} absent; using the frozen probe results instead")
    else:
        raise SystemExit(
            f"neither {source} nor {fallback} exists; generate benchmark results first"
        )
    out_dir = base / "seed_stability"
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = [m.strip() for m in args.metrics.split(",") if m.strip() in frame.columns]
    if not metrics:
        metrics = [c for c in ("pair_f1", "pair_precision", "pair_recall", "bcubed_f1")
                   if c in frame.columns]

    # `moderate` is a documented byte-identical alias of `central_provisional`:
    # same seeds, same worlds, identical results to machine precision. Pooling
    # both doubles central's weight in every overall statistic and narrows
    # confidence intervals that should be wider, because the duplicated worlds
    # carry no independent information. Both views are computed: the pooled one
    # for like-for-like comparison against v0.3, which included the duplicate,
    # and the deduplicated one as the statistic to actually quote.
    deduplicated = frame.loc[~frame["scenario"].isin(DUPLICATE_SCENARIOS)]

    rows = []
    reversal_frames = []
    for metric in metrics:
        rows.extend(pairwise_table(frame, metric, "overall_pooled", None))
        rows.extend(pairwise_table(deduplicated, metric, "overall_deduplicated", None))
        for scenario, group in frame.groupby("scenario"):
            rows.extend(pairwise_table(group, metric, "within_scenario", scenario))
        reversal_frames.append(ranking_reversal_table(deduplicated, metric))

    pairwise = pd.DataFrame(rows)
    pairwise.to_csv(out_dir / "paired_algorithm_differences.csv", index=False)
    reversals = pd.concat(reversal_frames, ignore_index=True)
    reversals.to_csv(out_dir / "ranking_reversals_by_world.csv", index=False)

    # Per-scenario spread of each algorithm, with the Monte Carlo standard error
    # of the reported mean so the reader can see how much of the spread is
    # sampling noise rather than scenario difficulty.
    spread = (
        frame.groupby(["scenario", "algorithm"])[metrics]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    spread.columns = [
        "_".join(part for part in col if part).strip("_") for col in spread.columns.to_flat_index()
    ]
    for metric in metrics:
        std_col, count_col = f"{metric}_std", f"{metric}_count"
        if std_col in spread.columns:
            spread[f"{metric}_mcse"] = spread[std_col] / np.sqrt(spread[count_col].clip(lower=1))
    spread.to_csv(out_dir / "scenario_by_seed_spread.csv", index=False)

    distinct_scenarios = sorted(set(frame["scenario"]) - set(DUPLICATE_SCENARIOS))
    headline_metric = metrics[0] if metrics else None
    # The deduplicated view is the one quoted; the pooled view exists only for
    # comparability with v0.3, which included the duplicate scenario.
    headline = pairwise.loc[
        pairwise["scope"].eq("overall_deduplicated") & pairwise["metric"].eq(headline_metric)
    ]
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": args.version,
        "source": population,
        "metrics": metrics,
        "n_algorithms": int(frame["algorithm"].nunique()),
        "n_worlds_pooled": int(frame.groupby(["scenario", "world"]).ngroups),
        "n_worlds_deduplicated": int(deduplicated.groupby(["scenario", "world"]).ngroups),
        "authoritative_scope": "overall_deduplicated",
        "scenarios_present": sorted(frame["scenario"].unique()),
        "distinct_scenarios": distinct_scenarios,
        "duplicate_scenarios": DUPLICATE_SCENARIOS,
        "bootstrap_reps": BOOTSTRAP_REPS,
        "practical_equivalence_margin_f1": PRACTICAL_EQUIVALENCE_F1,
        "headline_metric": headline_metric,
        "headline_support_counts": headline["support_status"].value_counts().to_dict()
        if len(headline)
        else {},
        "pooled_ranking_reproduced_in_worlds": (
            float(reversals.loc[reversals["metric"].eq(headline_metric), "matches_pooled_ranking"].mean())
            if headline_metric
            else None
        ),
        "top1_reproduced_in_worlds": (
            float(reversals.loc[reversals["metric"].eq(headline_metric), "top1_matches_pooled"].mean())
            if headline_metric
            else None
        ),
        "duplicate_scenario_handling": (
            "`moderate` duplicates `central_provisional` exactly. Statistics are reported both "
            "pooled (comparable to v0.3, which included it) and deduplicated. The deduplicated "
            "scope is authoritative; the pooled scope over-weights central and understates "
            "interval width."
        ),
        "interpretation_rule": (
            "A comparison is only reported as a supported winner when the paired bootstrap "
            "interval excludes zero, the mean difference exceeds the practical-equivalence "
            "margin, and the winner is consistent across worlds. Otherwise it is reported as "
            "practically tied, uncertain, or scenario-dependent. No generator parameter was "
            "tuned using any quantity in this file."
        ),
    }
    (out_dir / "seed_stability_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    print(f"algorithms={summary['n_algorithms']} "
          f"worlds={summary['n_worlds_deduplicated']} distinct "
          f"({summary['n_worlds_pooled']} pooled incl. the duplicate scenario); "
          f"distinct scenarios={len(distinct_scenarios)} of {len(summary['scenarios_present'])} named")
    if len(headline):
        pd.set_option("display.width", 200)
        print(headline[[
            "algorithm_a", "algorithm_b", "n_paired_worlds", "mean_paired_difference",
            "ci_low", "ci_high", "monte_carlo_se_of_mean", "win_rate_a", "support_status",
        ]].to_string(index=False))
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
