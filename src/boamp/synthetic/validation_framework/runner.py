"""Orchestration and artifact writing for the validation framework."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from boamp.synthetic.validation_framework.difficulty import run_difficulty_metrics
from boamp.synthetic.validation_framework.fidelity import run_fidelity_validation
from boamp.synthetic.validation_framework.internal import checksum_file, run_internal_validation
from boamp.synthetic.validation_framework.loaders import BenchmarkData, load_benchmark_data
from boamp.synthetic.validation_framework.robustness import (
    PROBE_RANKING_SUMMARY_COLUMNS,
    PROBE_REPLICATE_COLUMNS,
    run_robustness_validation,
    summarize_probe_ranking_stability,
)
from boamp.synthetic.validation_framework.structure import run_structure_validation
from boamp.synthetic.validation_framework.text import run_text_validation
from boamp.synthetic.validation_framework.models import (
    GateResult,
    MetricResult,
    Status,
    gate_frame,
    metric_frame,
)


# Section 7 of the specification: a gate marked critical blocks release on its
# own; a non-critical gate can only downgrade the run to PASS_WITH_WARNINGS.
# Fidelity of observable marginals is deliberately non-critical -- the
# benchmark is allowed to simplify the real corpus as long as the simplification
# is documented in the fidelity budget -- while anything that would silently
# change a linkage conclusion, leak truth, or copy a real record is critical.
CRITICAL_GATES = {
    "internal": True,
    "specification_recovery": True,
    "marginals": False,
    "conditionals": True,
    "temporal": True,
    "candidate_environment": True,
    "missingness_text_identifier": False,
    "buyer_activity": False,
    "missingness_structure": False,
    "names_identifiers": False,
    "text": False,
    "privacy": True,
    "hidden_truth_difficulty": True,
    "algorithm_utility": True,
    "robustness": False,
}


def _gate_status(statuses: list[str], critical: bool) -> Status:
    if any(s == Status.FAIL for s in statuses):
        return Status.FAIL if critical else Status.WARNING
    if any(s == Status.WARNING for s in statuses):
        return Status.WARNING
    if statuses and all(s == Status.INCONCLUSIVE for s in statuses):
        return Status.INCONCLUSIVE
    if any(s == Status.INCONCLUSIVE for s in statuses):
        return Status.WARNING
    return Status.PASS


def summarize_gates(metrics: list[MetricResult]) -> list[GateResult]:
    frame = metric_frame(metrics)
    gates: list[GateResult] = []
    for gate, critical in CRITICAL_GATES.items():
        sub = frame.loc[frame["scope"].eq(gate)]
        statuses = sub["status"].astype(str).tolist()
        status = _gate_status(statuses, critical)
        failures = sub.loc[sub["status"].astype(str).eq(str(Status.FAIL))]
        warnings = sub.loc[sub["status"].astype(str).eq(str(Status.WARNING))]
        blocking = ""
        warning = ""
        if status == Status.FAIL and critical:
            blocking = "; ".join(f"{r.property}:{r.metric}" for r in failures.itertuples())
        elif status == Status.WARNING:
            warning = "; ".join(f"{r.property}:{r.metric}" for r in pd.concat([failures, warnings]).itertuples())
        gates.append(
            GateResult(
                gate=gate,
                status=status,
                critical=critical,
                n_pass=int((sub["status"].astype(str) == str(Status.PASS)).sum()),
                n_warning=int((sub["status"].astype(str) == str(Status.WARNING)).sum()),
                n_fail=int((sub["status"].astype(str) == str(Status.FAIL)).sum()),
                n_inconclusive=int((sub["status"].astype(str) == str(Status.INCONCLUSIVE)).sum()),
                headline=f"{gate} validation {status}",
                blocking_reason=blocking,
                warning_reason=warning,
            )
        )
    return gates


def discrepancy_register(metrics: list[MetricResult]) -> pd.DataFrame:
    frame = metric_frame(metrics)
    out = frame.loc[~frame["status"].astype(str).eq(str(Status.PASS))].copy()
    cols = [
        "scope",
        "subgroup",
        "property",
        "metric",
        "real_estimate",
        "synthetic_estimate",
        "difference",
        "effect_size",
        "tolerance",
        "status",
        "provenance",
        "notes",
    ]
    return out[cols]


def run_validation(
    data: BenchmarkData,
    strict_60m: bool = False,
    bootstrap_reps: int = 0,
    robustness: bool = True,
    replay: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    metrics: list[MetricResult] = []
    metrics.extend(run_internal_validation(data, replay=replay))
    metrics.extend(run_fidelity_validation(data, strict_60m=strict_60m))
    metrics.extend(run_structure_validation(data, bootstrap_reps=bootstrap_reps))
    metrics.extend(run_text_validation(data))
    difficulty_metrics, probe_frame = run_difficulty_metrics(data)
    metrics.extend(difficulty_metrics)
    robustness_metrics, replicate_probes = run_robustness_validation(data, enabled=robustness)
    metrics.extend(robustness_metrics)
    probe_ranking_summary = summarize_probe_ranking_stability(replicate_probes)
    metric_df = metric_frame(metrics)
    gate_df = gate_frame(summarize_gates(metrics))
    discrepancy_df = discrepancy_register(metrics)
    checksums = {
        p.name: checksum_file(p)
        for p in sorted(data.synthetic_dir.glob("*"))
        if p.is_file() and p.suffix in {".parquet", ".json", ".csv"}
    }
    manifest = {
        "benchmark_version": data.benchmark_version,
        "scenario": data.scenario,
        "world": data.world,
        "corruption": data.corruption,
        "synthetic_dir": str(data.synthetic_dir.relative_to(data.project_root)),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "strict_60m": strict_60m,
        "bootstrap_reps": bootstrap_reps,
        "robustness_sweep": robustness,
        "canonical_replay_checked": replay,
        "probe_linker_results": probe_frame.to_dict("records") if len(probe_frame) else [],
        "probe_replicate_results": replicate_probes.to_dict("records") if len(replicate_probes) else [],
        "probe_ranking_stability": (
            probe_ranking_summary.to_dict("records") if len(probe_ranking_summary) else []
        ),
        "probe_replicate_result_count": int(len(replicate_probes)),
        "probe_ranking_summary_count": int(len(probe_ranking_summary)),
        "metric_count": int(len(metric_df)),
        "gate_count": int(len(gate_df)),
        "overall_status": "FAIL"
        if ((gate_df["critical"]) & (gate_df["status"].astype(str) == str(Status.FAIL))).any()
        else "PASS_WITH_WARNINGS"
        if (gate_df["status"].astype(str) == str(Status.WARNING)).any()
        else "PASS",
        # A non-critical gate reports WARNING even when individual metrics
        # failed, so the headline status alone hides how many metric-level
        # failures the release is carrying. Report the count explicitly rather
        # than making a reader reconstruct it from the gate table.
        "n_metric_failures": int(gate_df["n_fail"].sum()),
        "n_metric_failures_in_noncritical_gates": int(gate_df.loc[~gate_df["critical"], "n_fail"].sum()),
        "noncritical_gates_with_metric_failures": gate_df.loc[
            (~gate_df["critical"]) & (gate_df["n_fail"] > 0), "gate"
        ].tolist(),
        "input_checksums": checksums,
        "notes": [
            "Covers the Section 7 minimum suite: internal integrity, marginals, conditionals, "
            "missingness, temporal, buyer activity, candidate environment, text, names/identifiers, "
            "hidden-truth difficulty, algorithm utility and robustness.",
            "Still out of scope and therefore never reported as passed: neural-embedding semantic "
            "distances and MAUVE, membership-inference attacks, Sobol sensitivity analysis, and "
            "held-out real-BOAMP partitions never used during generator design.",
            "Statistical non-rejection is not equivalence. Metrics carrying a bootstrap interval are "
            "decided by the TOST rule; metrics without one can only reach 'not obviously discrepant'.",
            "60-month runway is a warning unless --strict-60m is passed.",
        ],
    }
    return metric_df, gate_df, discrepancy_df, manifest


def write_validation_outputs(
    project_root: Path,
    version: str,
    scenario: str,
    world: str = "001",
    corruption: str = "001",
    output_dir: Path | None = None,
    strict_60m: bool = False,
    bootstrap_reps: int = 0,
    robustness: bool = True,
    replay: bool = True,
) -> dict:
    data = load_benchmark_data(project_root, version, scenario, world, corruption)
    metric_df, gate_df, discrepancy_df, manifest = run_validation(
        data, strict_60m=strict_60m, bootstrap_reps=bootstrap_reps, robustness=robustness, replay=replay
    )
    out_dir = output_dir or (
        Path(project_root)
        / "reports"
        / "tables"
        / "synthetic_benchmark"
        / version
        / "validation_framework"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    metric_df.to_csv(out_dir / "validation_metrics_long.csv", index=False)
    gate_df.to_csv(out_dir / "validation_gate_summary.csv", index=False)
    discrepancy_df.to_csv(out_dir / "discrepancy_register.csv", index=False)
    pd.DataFrame(manifest["probe_linker_results"]).to_csv(out_dir / "probe_linker_results.csv", index=False)
    replicate_probes = pd.DataFrame(manifest.get("probe_replicate_results", []))
    if replicate_probes.empty:
        replicate_probes = pd.DataFrame(columns=PROBE_REPLICATE_COLUMNS)
    replicate_probes.to_csv(out_dir / "probe_replicate_results.csv", index=False)
    ranking_summary = pd.DataFrame(manifest.get("probe_ranking_stability", []))
    if ranking_summary.empty:
        ranking_summary = pd.DataFrame(columns=PROBE_RANKING_SUMMARY_COLUMNS)
    ranking_summary.to_csv(out_dir / "probe_ranking_stability.csv", index=False)
    (out_dir / "validation_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return {
        "output_dir": out_dir,
        "metrics": metric_df,
        "gates": gate_df,
        "discrepancies": discrepancy_df,
        "manifest": manifest,
    }
