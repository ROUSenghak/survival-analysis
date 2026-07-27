from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import hashlib

import pandas as pd

from boamp.synthetic.validation_framework.bootstrap import equivalence_status
from boamp.synthetic.validation_framework.difficulty import run_difficulty_metrics
from boamp.synthetic.validation_framework.fidelity import run_candidate_metrics
from boamp.synthetic.validation_framework.internal import (
    run_negative_controls,
    validate_corruption_replay,
    validate_leakage,
    validate_parameter_recovery,
    validate_truth_graph,
)
from boamp.synthetic.validation_framework.loaders import load_benchmark_data
from boamp.synthetic.validation_framework.models import Status, classify_abs, classify_range, classify_upper
from boamp.synthetic.validation_framework.robustness import run_robustness_validation
from boamp.synthetic.validation_framework.runner import run_validation, write_validation_outputs
from boamp.synthetic.validation_framework.text import run_text_memorisation_audit

REPO = Path(__file__).resolve().parents[1]
VERSION = "v0_3_temporal_candidate_revision"
SCENARIO = "central_provisional"


def _status_for(metrics, prop: str, metric: str) -> str:
    for item in metrics:
        if item.property == prop and item.metric == metric:
            return str(item.status)
    raise AssertionError(f"metric not found: {prop}/{metric}")


def test_status_helpers_classify_boundaries():
    assert classify_abs(3.0, 3.0) == Status.PASS
    assert classify_abs(3.1, 3.0, 5.0) == Status.WARNING
    assert classify_abs(5.1, 3.0, 5.0) == Status.FAIL
    assert classify_abs(float("nan"), 3.0) == Status.INCONCLUSIVE

    assert classify_upper(0.01, 0.01) == Status.PASS
    assert classify_upper(0.02, 0.01, 0.03) == Status.WARNING
    assert classify_range(1.0, 0.8, 1.2) == Status.PASS
    assert classify_range(1.3, 0.8, 1.2) == Status.FAIL


def test_v0_3_fixture_has_no_internal_invariant_failures():
    """Invariants, leakage, replay and negative controls must all hold.

    The gate itself only reaches WARNING because byte-identical regeneration is
    reported INCONCLUSIVE by design (it needs a generator re-run, which this
    suite does not do), so the assertion is on the absence of failures rather
    than on the aggregate status.
    """
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    _metrics, gates, _discrepancies, _manifest = run_validation(data, robustness=False)
    internal = gates.loc[gates["gate"].eq("internal")].iloc[0]
    assert internal["n_fail"] == 0
    assert internal["status"] in {"PASS", "WARNING"}


def test_negative_controls_all_detect_their_injected_defect():
    """The suite must fail when the data is deliberately broken (Section 6.9)."""
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    controls = run_negative_controls(data)
    assert len(controls) == 6
    assert {str(m.status) for m in controls} == {"PASS"}


def test_v0_3_specification_recovery_accepts_versioned_scenario_parameters():
    """v0.3 selected candidate-revision parameters must live in scenario YAML."""
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    metrics = validate_parameter_recovery(data)
    assert _status_for(metrics, "parameter_recovery", "scenario_file_describes_generated_data") == "PASS"
    assert _status_for(metrics, "parameter_recovery", "max_cycles_per_need_respected") == "PASS"


def test_gap_recovery_passes_on_correctly_generated_data():
    """The declared gap mechanism must recover without any status softening.

    This metric was once downgraded to a warning whenever hard-negative chain
    alignment was enabled. The real defect was that the Monte Carlo null
    measured the censoring window from the source cycle's start instead of its
    expected end, which overstated the headroom by a full cycle duration and
    biased the interval upward.
    """
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    metrics = validate_parameter_recovery(data)
    assert _status_for(metrics, "parameter_recovery", "mean_true_gap_months_in_monte_carlo_interval") == "PASS"


def test_gap_recovery_still_fails_when_the_gap_mechanism_is_wrong():
    """Chain alignment must not make this metric unfalsifiable.

    central_provisional runs with hard_negative_alignment_rate > 0, so this is
    exactly the configuration in which the metric was previously incapable of
    reporting a failure.
    """
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    relations = data.true_relations.copy()
    is_next = relations["relation_type"].eq("NEXT_CYCLE")
    relations.loc[is_next, "true_gap_months"] = (
        pd.to_numeric(relations.loc[is_next, "true_gap_months"], errors="coerce") + 6.0
    )
    metrics = validate_parameter_recovery(replace(data, true_relations=relations))
    assert _status_for(metrics, "parameter_recovery", "mean_true_gap_months_in_monte_carlo_interval") == "FAIL"


def test_scenario_snapshot_mismatch_is_reported():
    """Editing the scenario file behind a released benchmark must be detected."""
    from boamp.synthetic.validation_framework.internal import validate_reproducibility_manifest

    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    assert (
        _status_for(validate_reproducibility_manifest(data), "reproducibility",
                    "scenario_snapshot_matches_scenario_file") == "PASS"
    )

    metadata = dict(data.metadata)
    snapshot = dict(metadata["resolved_scenario"])
    snapshot["recurrence"] = dict(snapshot["recurrence"], max_cycles_per_need=99)
    metadata["resolved_scenario"] = snapshot
    drifted = validate_reproducibility_manifest(replace(data, metadata=metadata))
    assert _status_for(drifted, "reproducibility", "scenario_snapshot_matches_scenario_file") == "FAIL"


def test_difficulty_gate_is_neither_trivial_nor_impossible():
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    metrics, probes = run_difficulty_metrics(data)
    assert len(probes) == 3
    assert probes["pair_f1"].max() < 0.99, "a probe solving the benchmark means a shortcut exists"
    assert probes["pair_f1"].max() > 0.05, "no probe learning anything means the task is unusable"
    assert _status_for(metrics, "probe_headroom", "best_pair_f1") == "PASS"
    assert _status_for(metrics, "match_vs_hard_negative_score", "overlap") == "PASS"


def test_difficulty_reports_blocking_scoring_and_end_to_end_settings():
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    metrics, _probes = run_difficulty_metrics(data)
    rows = pd.DataFrame([m.to_dict() for m in metrics])
    subgroups = set(rows["subgroup"])
    assert "PRODUCTION_BLOCKING" in subgroups
    assert any(s.startswith("ORACLE_CANDIDATE_SCORING:") for s in subgroups)
    assert any(s.startswith("END_TO_END:") for s in subgroups)

    product_checks = rows.loc[
        rows["property"].eq("recall_decomposition")
        & rows["metric"].eq("R_blocking_times_scoring")
    ]
    assert not product_checks.empty
    assert set(product_checks["status"]) == {"PASS"}
    assert product_checks["effect_size"].max() < 1e-12


def test_robustness_reports_central_multi_seed_summary_when_available():
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    metrics, _probes = run_robustness_validation(data)
    rows = pd.DataFrame([m.to_dict() for m in metrics])
    central = rows.loc[rows["subgroup"].eq(f"seed_replicates:{SCENARIO}")]
    if len(central):
        assert {
            "seed_count",
            "mean",
            "std",
            "central_95pct_interval",
            "worst_case",
            "coefficient_of_variation",
            "nonpass_frequency",
        }.issubset(set(central["metric"]))
        counts = central.loc[central["metric"].eq("seed_count"), "synthetic_estimate"].astype(float)
        assert counts.max() >= 10
    ranking_subgroups = set(rows.loc[rows["property"].eq("probe_ranking"), "subgroup"])
    assert f"ranking_stability:{SCENARIO}" in ranking_subgroups
    assert "ranking_stability:cross_scenario" in ranking_subgroups
    assert "ranking_stability" in ranking_subgroups


def test_probe_ranking_stability_artifact_is_written(tmp_path):
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    result = write_validation_outputs(
        REPO,
        VERSION,
        SCENARIO,
        output_dir=tmp_path,
        bootstrap_reps=0,
        replay=False,
    )
    replicate_path = tmp_path / "probe_replicate_results.csv"
    ranking_path = tmp_path / "probe_ranking_stability.csv"
    assert replicate_path.exists()
    assert ranking_path.exists()
    ranking = pd.read_csv(ranking_path)
    assert {
        "scope",
        "scenario",
        "probe",
        "n_units",
        "mean_pair_f1",
        "mean_rank",
        "prob_rank1",
    }.issubset(ranking.columns)
    assert result["manifest"]["probe_replicate_result_count"] >= 3
    assert result["manifest"]["probe_ranking_summary_count"] == len(ranking)


def test_no_record_specific_text_copied_from_real_corpus():
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    metrics = run_text_memorisation_audit(data)
    assert _status_for(metrics, "record_specific_exact_copy", "count") == "PASS"


def test_equivalence_needs_an_interval_not_just_a_point_estimate():
    # Interval inside the tolerance: equivalence supported.
    assert equivalence_status(0.5, -1.0, 1.5, 2.0) == Status.PASS
    # Same point estimate, interval too wide to conclude anything: not a pass.
    assert equivalence_status(0.5, -5.0, 6.0, 2.0) == Status.WARNING
    # Interval wholly beyond the warning band: an established difference.
    assert equivalence_status(9.0, 8.0, 10.0, 2.0) == Status.FAIL
    assert equivalence_status(float("nan"), None, None, 2.0) == Status.INCONCLUSIVE


def test_leaked_truth_columns_fail_leakage_check():
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    observed = data.observed.copy()
    observed["cycle_id_true"] = data.clean["cycle_id_true"].to_numpy()
    broken = replace(data, observed=observed)
    metrics = validate_leakage(broken)
    assert _status_for(metrics, "leakage", "no_truth_columns_in_observed") == "FAIL"


def test_unsuffixed_hidden_truth_alias_columns_fail_leakage_check():
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    observed = data.observed.copy()
    observed["buyer_id"] = data.clean["buyer_id_true"].to_numpy()
    broken = replace(data, observed=observed)
    metrics = validate_leakage(broken)
    assert _status_for(metrics, "leakage", "no_hidden_truth_alias_columns_in_observed") == "FAIL"


def test_transformed_truth_id_values_fail_leakage_check():
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    observed = data.observed.copy()
    raw_cycle_ids = data.clean["cycle_id_true"].astype(str)
    observed["opaque_cycle_key"] = raw_cycle_ids.map(
        lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
    ).to_numpy()
    broken = replace(data, observed=observed)
    metrics = validate_leakage(broken)
    assert _status_for(metrics, "leakage", "no_internal_truth_id_values_in_observed") == "FAIL"


def test_broken_truth_graph_target_dates_fail():
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    rel = data.true_relations.copy()
    idx = rel.index[rel["relation_type"].eq("NEXT_CYCLE")][0]
    rel.loc[idx, "target_cycle_id"] = rel.loc[idx, "source_cycle_id"]
    broken = replace(data, true_relations=rel)
    metrics = validate_truth_graph(broken)
    assert _status_for(metrics, "truth_graph", "successor_after_source") == "FAIL"
    assert _status_for(metrics, "truth_graph", "acyclic_next_cycle_graph") == "FAIL"


def test_corrupted_observed_value_fails_corruption_replay():
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    first = data.corruption_log.iloc[0]
    observed = data.observed.copy()
    observed.loc[
        observed["notice_id_synthetic"].eq(first["notice_id_synthetic"]),
        first["field"],
    ] = "__BROKEN_REPLAY_VALUE__"
    broken = replace(data, observed=observed)
    metrics = validate_corruption_replay(broken)
    assert _status_for(metrics, "corruption_replay", "logged_changes_match_tables") == "FAIL"


def test_candidate_gate_reproduces_existing_v0_3_pass_statuses():
    data = load_benchmark_data(REPO, VERSION, SCENARIO)
    metrics = run_candidate_metrics(data)
    assert {str(m.status) for m in metrics} == {"PASS"}

    existing = pd.read_csv(
        REPO
        / "reports"
        / "tables"
        / "synthetic_benchmark"
        / "v0_3_real_synthetic_comparison"
        / "candidate_environment_validation_gate_by_version.csv"
    )
    existing_v3 = existing.loc[existing["version"].eq(VERSION)]
    assert set(existing_v3["status"]) == {"PASS"}
