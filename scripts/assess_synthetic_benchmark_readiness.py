"""Assess synthetic benchmark readiness at explicit use levels.

This script intentionally does not replace the validation framework's
metric-level outputs. It reads those outputs and translates them into the five
readiness decisions needed by the benchmark methodology, so a lower-level
``PASS_WITH_WARNINGS`` cannot be misread as final algorithm-ranking readiness.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.scenarios import VALID_SCENARIOS  # noqa: E402

DEFAULT_VERSION = "v0_3_temporal_candidate_revision"
DEFAULT_SCENARIO = "central_provisional"

PROHIBITED_CLAIMS = [
    "Synthetic precision, recall, recurrence prevalence, or survival estimates equal their unknown real BOAMP values.",
    "The benchmark proves real-world algorithm ranking or real renewal prevalence.",
    "Previously accepted BOAMP links, linkage scores, thresholds, or the six-month window are real ground truth.",
    "A validated synthetic benchmark replaces missing manual/legal BOAMP recurrence labels.",
]


def _git_head(project_root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return out.stdout.strip()
    except Exception:
        return None


def _git_dirty(project_root: Path) -> bool:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return bool(out.stdout.strip())
    except Exception:
        return True


def _load_metadata(project_root: Path, version: str, scenario: str, world: str, corruption: str) -> dict:
    path = (
        project_root
        / "data"
        / "processed"
        / "synthetic_benchmark"
        / version
        / scenario
        / f"world_{world}"
        / f"corruption_{corruption}"
        / "generation_metadata.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(metrics: pd.DataFrame, scope: str, prop: str, metric: str) -> pd.DataFrame:
    return metrics.loc[
        metrics["scope"].eq(scope)
        & metrics["property"].eq(prop)
        & metrics["metric"].eq(metric)
    ]


def _has_status(metrics: pd.DataFrame, scope: str, statuses: set[str]) -> bool:
    return metrics.loc[metrics["scope"].eq(scope), "status"].astype(str).isin(statuses).any()


def _replicate_counts(project_root: Path, version: str) -> dict[str, int]:
    root = project_root / "data" / "processed" / "synthetic_benchmark" / version
    counts: dict[str, int] = {}
    for metadata in root.glob("*/world_*/corruption_*/generation_metadata.json"):
        scenario = metadata.parent.parent.parent.name
        counts[scenario] = counts.get(scenario, 0) + 1
    return counts


def _problem_table(metrics: pd.DataFrame) -> list[dict]:
    hard_scopes = {
        "buyer_activity",
        "text",
        "marginals",
        "candidate_environment",
        "hidden_truth_difficulty",
        "robustness",
        "temporal",
        "missingness_text_identifier",
    }
    rows = metrics.loc[
        metrics["scope"].isin(hard_scopes)
        & metrics["status"].astype(str).isin({"FAIL", "WARNING", "INCONCLUSIVE"})
    ].copy()
    keep = [
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
        "notes",
    ]
    return rows[keep].to_dict("records")


def assess(project_root: Path, version: str, scenario: str, world: str, corruption: str) -> dict:
    validation_dir = project_root / "reports" / "tables" / "synthetic_benchmark" / version / "validation_framework"
    metrics = pd.read_csv(validation_dir / "validation_metrics_long.csv")
    gates = pd.read_csv(validation_dir / "validation_gate_summary.csv")
    manifest = json.loads((validation_dir / "validation_manifest.json").read_text(encoding="utf-8"))
    replay_replicates_path = validation_dir / "replay_replicates.json"
    replay_replicates = (
        json.loads(replay_replicates_path.read_text(encoding="utf-8"))
        if replay_replicates_path.exists()
        else {}
    )
    source_state_path = (
        project_root
        / "reports"
        / "tables"
        / "synthetic_benchmark"
        / version
        / "source_state_manifest.json"
    )
    source_state = (
        json.loads(source_state_path.read_text(encoding="utf-8"))
        if source_state_path.exists()
        else {}
    )
    ranking_summary_path = validation_dir / "probe_ranking_stability.csv"
    ranking_summary = (
        pd.read_csv(ranking_summary_path)
        if ranking_summary_path.exists()
        else pd.DataFrame()
    )
    metadata = _load_metadata(project_root, version, scenario, world, corruption)
    head = _git_head(project_root)
    worktree_dirty = _git_dirty(project_root)
    replicate_counts = _replicate_counts(project_root, version)
    scenarios_present = sorted(replicate_counts)
    required_scenarios = {"easier", "moderate", "difficult", "stress"}
    executable_required_scenarios = required_scenarios.issubset(set(VALID_SCENARIOS))

    internal_ok = not _has_status(metrics, "internal", {"FAIL"})
    specification_ok = not _has_status(metrics, "specification_recovery", {"FAIL"})
    privacy_ok = not _has_status(metrics, "privacy", {"FAIL"})
    replay_ok = bool(manifest.get("canonical_replay_checked")) and manifest.get("overall_status") != "FAIL"
    all_replicate_replay_ok = replay_replicates.get("overall_status") == "PASS"
    generated_from_head = bool(head and metadata.get("git_commit") == head)

    multi_seed_ready = replicate_counts.get(scenario, 0) >= 10
    required_scenario_artifacts_ready = required_scenarios.issubset(set(scenarios_present))
    observable_hard_failures = any(
        _has_status(metrics, scope, {"FAIL"})
        for scope in ["buyer_activity", "text", "marginals", "missingness_text_identifier"]
    )
    main_robustness = metrics.loc[
        metrics["scope"].eq("robustness")
        & metrics["subgroup"].astype(str).eq(f"seed_replicates:{scenario}")
    ]
    main_seed_robustness_blocked = main_robustness["status"].astype(str).isin(
        {"FAIL", "WARNING", "INCONCLUSIVE"}
    ).any()
    cross_scenario_robustness_warning = metrics.loc[
        metrics["scope"].eq("robustness")
        & metrics["subgroup"].astype(str).eq("cross_scenario"),
        "status",
    ].astype(str).isin({"FAIL", "WARNING", "INCONCLUSIVE"}).any()
    main_probe_ranking_warning = metrics.loc[
        metrics["scope"].eq("robustness")
        & metrics["subgroup"].astype(str).eq(f"ranking_stability:{scenario}"),
        "status",
    ].astype(str).isin({"FAIL", "WARNING", "INCONCLUSIVE"}).any()
    cross_probe_ranking_warning = metrics.loc[
        metrics["scope"].eq("robustness")
        & metrics["subgroup"].astype(str).eq("ranking_stability:cross_scenario"),
        "status",
    ].astype(str).isin({"FAIL", "WARNING", "INCONCLUSIVE"}).any()
    overall_probe_ranking_warning = metrics.loc[
        metrics["scope"].eq("robustness")
        & metrics["subgroup"].astype(str).eq("ranking_stability"),
        "status",
    ].astype(str).isin({"FAIL", "WARNING", "INCONCLUSIVE"}).any()
    widened_pc = _metric(metrics, "hidden_truth_difficulty", "blocking_pairs_completeness", "PC")
    widened_warning = bool(
        len(widened_pc.loc[widened_pc["subgroup"].astype(str).str.contains("36m")])
        and widened_pc.loc[widened_pc["subgroup"].astype(str).str.contains("36m"), "status"].astype(str).ne("PASS").any()
    )
    calendar_month_metric_present = not _metric(metrics, "temporal", "publication_calendar_month", "TVD").empty
    subgroups = metrics["subgroup"].astype(str)
    production_blocking_reported = bool((subgroups == "PRODUCTION_BLOCKING").any())
    oracle_scoring_reported = bool(subgroups.str.startswith("ORACLE_CANDIDATE_SCORING:").any())
    end_to_end_reported = bool(subgroups.str.startswith("END_TO_END:").any())
    three_settings_reported = production_blocking_reported and oracle_scoring_reported and end_to_end_reported
    comparison_warnings = []
    if not three_settings_reported:
        comparison_warnings.append(
            "production blocking completeness and scoring are not yet reported as three separate settings"
        )
    if cross_scenario_robustness_warning:
        comparison_warnings.append(
            "headline difficulty varies materially across scenarios; comparisons must be scenario-labelled"
        )
    if main_probe_ranking_warning:
        comparison_warnings.append(
            "main-scenario probe-linker ranking stability remains a warning; do not claim final ranking"
        )
    if cross_probe_ranking_warning or overall_probe_ranking_warning:
        comparison_warnings.append(
            "probe-linker ranking stability is scenario-dependent; do not claim one global ranking"
        )
    main_top_rank1_frequency = None
    overall_top_rank1_frequency = None
    cross_top_rank1_frequency = None
    if not ranking_summary.empty:
        main_rows = ranking_summary.loc[
            ranking_summary["scope"].astype(str).eq("within_scenario")
            & ranking_summary["scenario"].astype(str).eq(scenario)
        ].copy()
        if len(main_rows):
            main_top_rank1_frequency = float(main_rows["prob_rank1"].astype(float).max())
        overall_rows = ranking_summary.loc[
            ranking_summary["scope"].astype(str).eq("all_benchmark_replicates")
        ].copy()
        if len(overall_rows):
            overall_top_rank1_frequency = float(overall_rows["prob_rank1"].astype(float).max())
        cross_rows = ranking_summary.loc[
            ranking_summary["scope"].astype(str).eq("cross_scenario_means")
        ].copy()
        if len(cross_rows):
            cross_top_rank1_frequency = float(cross_rows["prob_rank1"].astype(float).max())

    decisions = []
    technical_limitations = []
    if not generated_from_head:
        technical_limitations.append(
            f"generated data metadata commit {metadata.get('git_commit')} differs from current HEAD {head}"
        )
    if worktree_dirty:
        if source_state:
            technical_limitations.append(
                "worktree has uncommitted or untracked changes; source_state_manifest.json records the dirty state, but final release still requires a clean commit or standalone release package"
            )
        else:
            technical_limitations.append(
                "worktree has uncommitted or untracked changes, so current HEAD does not fully identify the source/artifact state"
            )
    if not calendar_month_metric_present:
        technical_limitations.append("saved validation outputs do not yet include the calendar-month seasonality metric")
    if not all_replicate_replay_ok:
        technical_limitations.append("all-generated-artifact replay evidence is missing or failing")
    if internal_ok and specification_ok and privacy_ok and replay_ok:
        technical_status = "PASS_WITH_LIMITATIONS" if technical_limitations else "PASS"
    else:
        technical_status = "FAIL"
    decisions.append(
        {
            "level": "PIPELINE_TECHNICALLY_VALID",
            "status": technical_status,
            "supporting_evidence": [
                f"internal gate: {gates.loc[gates.gate.eq('internal'), 'status'].iloc[0]}",
                f"specification_recovery gate: {gates.loc[gates.gate.eq('specification_recovery'), 'status'].iloc[0]}",
                f"privacy gate: {gates.loc[gates.gate.eq('privacy'), 'status'].iloc[0]}",
                f"canonical replay checked: {manifest.get('canonical_replay_checked')}",
                f"all generated artifacts replay: {replay_replicates.get('overall_status', 'MISSING')}",
                f"replayed artifacts: {replay_replicates.get('n_replicates', 0)}",
                f"source state manifest hashed paths: {source_state.get('n_hashed_paths', 0)}",
                f"worktree dirty: {worktree_dirty}",
            ],
            "failed_hard_gates": [] if technical_status != "FAIL" else ["internal/specification/privacy/replay"],
            "remaining_warnings": technical_limitations,
            "permitted_uses": ["local reproducibility checks", "debugging generator and validation mechanisms"],
            "prohibited_claims": PROHIBITED_CLAIMS,
        }
    )

    decisions.append(
        {
            "level": "READY_FOR_PRELIMINARY_MODELING",
            "status": "PASS_WITH_LIMITATIONS" if technical_status != "FAIL" else "FAIL",
            "supporting_evidence": [
                f"validation framework overall_status: {manifest.get('overall_status')}",
                f"probe linker best pair-F1: {metrics.loc[(metrics.property.eq('probe_headroom')) & (metrics.metric.eq('best_pair_f1')), 'synthetic_estimate'].max()}",
            ],
            "failed_hard_gates": [],
            "remaining_warnings": [
                "preliminary modeling must be labelled synthetic-only",
                "observable fidelity warnings remain in buyer-activity concentration, text lexical distribution, and identifier completeness",
            ],
            "permitted_uses": ["exploratory linker debugging", "pipeline integration tests", "method development dry runs"],
            "prohibited_claims": PROHIBITED_CLAIMS,
        }
    )

    comparison_blockers = []
    if observable_hard_failures:
        comparison_blockers.append("observable hard-fidelity failures remain in non-critical current gates")
    if main_seed_robustness_blocked:
        comparison_blockers.append("main-scenario seed robustness is warning or inconclusive")
    if not executable_required_scenarios:
        comparison_blockers.append("required easier/moderate/difficult/stress scenarios are not executable configs")
    if not required_scenario_artifacts_ready:
        comparison_blockers.append("required easier/moderate/difficult/stress scenarios have not been generated as benchmark artifacts")
    decisions.append(
        {
            "level": "READY_FOR_CONTROLLED_ALGORITHM_COMPARISON",
            "status": "FAIL" if comparison_blockers else "PASS_WITH_LIMITATIONS",
            "supporting_evidence": [
                f"scenarios present: {scenarios_present}",
                f"replicates by scenario: {replicate_counts}",
                f"metric failures: {manifest.get('n_metric_failures')}",
                f"three evaluation settings reported: {three_settings_reported}",
                f"required executable scenario configs present: {executable_required_scenarios}",
            ],
            "failed_hard_gates": comparison_blockers,
            "remaining_warnings": comparison_warnings,
            "permitted_uses": [
                "controlled synthetic algorithm comparisons within documented scenarios",
                "seed-aggregated moderate/central scenario comparisons when all results are labelled synthetic-only",
            ],
            "prohibited_claims": PROHIBITED_CLAIMS,
        }
    )

    final_blockers = list(comparison_blockers)
    if not multi_seed_ready:
        final_blockers.append("fewer than 10 independent worlds for the main scenario")
    if widened_warning:
        final_blockers.append("36-month widened blocking completeness does not pass its floor")
    if cross_scenario_robustness_warning:
        final_blockers.append("headline difficulty varies materially across scenarios and must be scenario-labelled")
    if main_probe_ranking_warning:
        final_blockers.append("main-scenario probe-linker ranking stability is warning or inconclusive")
    if cross_probe_ranking_warning or overall_probe_ranking_warning:
        final_blockers.append("cross-scenario probe-linker ranking stability is warning or inconclusive")
    decisions.append(
        {
            "level": "READY_FOR_FINAL_ALGORITHM_RANKING",
            "status": "FAIL" if final_blockers else "PASS_WITH_LIMITATIONS",
            "supporting_evidence": [
                f"multi-seed ready: {multi_seed_ready}",
                f"required scenario artifacts ready: {required_scenario_artifacts_ready}",
                f"observable hard failures: {observable_hard_failures}",
                f"probe ranking summary rows: {len(ranking_summary)}",
                f"main-scenario top-probe rank-1 frequency: {main_top_rank1_frequency}",
                f"all-benchmark top-probe rank-1 frequency: {overall_top_rank1_frequency}",
                f"cross-scenario-mean top-probe rank-1 frequency: {cross_top_rank1_frequency}",
            ],
            "failed_hard_gates": final_blockers,
            "remaining_warnings": ["algorithm rankings have not been shown stable across seeds and scenarios"],
            "permitted_uses": ["none beyond preliminary labelled diagnostics"],
            "prohibited_claims": PROHIBITED_CLAIMS,
        }
    )

    release_blockers = list(final_blockers)
    if technical_limitations:
        release_blockers.extend(technical_limitations)
    decisions.append(
        {
            "level": "READY_FOR_VALIDATED_SYNTHETIC_BENCHMARK_RELEASE",
            "status": "FAIL" if release_blockers else "PASS_WITH_LIMITATIONS",
            "supporting_evidence": [
                f"validation status: {manifest.get('overall_status')}",
                f"calendar-month metric present in saved outputs: {calendar_month_metric_present}",
                f"generated_from_current_head: {generated_from_head}",
                f"source state manifest hashed paths: {source_state.get('n_hashed_paths', 0)}",
                f"worktree dirty: {worktree_dirty}",
            ],
            "failed_hard_gates": release_blockers,
            "remaining_warnings": ["release docs must use validated synthetic benchmark language only"],
            "permitted_uses": ["not release-ready"],
            "prohibited_claims": PROHIBITED_CLAIMS,
        }
    )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": version,
        "scenario": scenario,
        "world": world,
        "corruption": corruption,
        "validation_manifest_status": manifest.get("overall_status"),
        "current_git_head": head,
        "worktree_dirty": worktree_dirty,
        "generated_data_git_commit": metadata.get("git_commit"),
        "replicate_counts": replicate_counts,
        "current_problem_inventory": _problem_table(metrics),
        "decisions": decisions,
        "global_limit": (
            "This is a validated synthetic benchmark only to the readiness level supported above. "
            "It cannot prove real BOAMP precision, recall, renewal prevalence, survival estimates, or algorithm ranking."
        ),
    }


def _write_markdown(result: dict, path: Path) -> None:
    lines = [
        "# Synthetic Benchmark Readiness Assessment",
        "",
        result["global_limit"],
        "",
        f"Benchmark version: `{result['benchmark_version']}`",
        f"Scenario: `{result['scenario']}`",
        f"Validation status read from manifest: `{result['validation_manifest_status']}`",
        f"Generated data commit: `{result['generated_data_git_commit']}`",
        f"Current HEAD: `{result['current_git_head']}`",
        "",
        "## Decisions",
    ]
    for decision in result["decisions"]:
        lines.extend(
            [
                "",
                f"### {decision['level']}: {decision['status']}",
                "",
                "Supporting evidence:",
                *[f"- {item}" for item in decision["supporting_evidence"]],
                "",
                "Failed hard gates:",
                *[f"- {item}" for item in (decision["failed_hard_gates"] or ["none"])],
                "",
                "Permitted uses:",
                *[f"- {item}" for item in decision["permitted_uses"]],
                "",
                "Prohibited claims:",
                *[f"- {item}" for item in decision["prohibited_claims"]],
            ]
        )
    lines.extend(["", "## Current Problem Inventory", ""])
    for row in result["current_problem_inventory"]:
        lines.append(
            f"- `{row['scope']}` / `{row['property']}` / `{row['metric']}`: "
            f"{row['status']} (real={row['real_estimate']}, synthetic={row['synthetic_estimate']}, "
            f"effect={row['effect_size']}, tolerance={row['tolerance']})"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO)
    parser.add_argument("--world", default="001")
    parser.add_argument("--corruption", default="001")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    out_dir = args.output_dir or (
        ROOT / "reports" / "tables" / "synthetic_benchmark" / args.version / "readiness"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    result = assess(ROOT, args.version, args.scenario, args.world, args.corruption)
    (out_dir / "readiness_decisions.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    _write_markdown(result, out_dir / "readiness_assessment.md")
    print(json.dumps({"output_dir": str(out_dir), "decisions": result["decisions"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
