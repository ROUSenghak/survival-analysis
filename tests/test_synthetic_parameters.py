from pathlib import Path

import pandas as pd

from boamp.synthetic.parameters import load_calibration_parameters
from boamp.synthetic.scenarios import VALID_SCENARIOS, load_benchmark_defaults, load_scenario

REPO = Path(__file__).resolve().parents[1]


def test_calibration_parameters_load():
    calib = load_calibration_parameters(REPO)
    assert calib.value("population", "full_corpus_size") == 84623
    assert calib.value("cpv", "missing_rate") == 0.1706


def test_calibration_parameter_source_tables_resolve():
    calib = load_calibration_parameters(REPO)
    df = calib.table("cpv", "division_distribution_table")
    assert isinstance(df, pd.DataFrame)
    assert "cpv_division" in df.columns


def test_benchmark_defaults_load():
    defaults = load_benchmark_defaults(REPO)
    assert defaults.target_n_buyers == 2000
    assert defaults.seed.latent_world_seed != defaults.seed.corruption_seed


def test_all_three_scenarios_load():
    for scenario_id in VALID_SCENARIOS:
        scenario = load_scenario(REPO, scenario_id)
        assert scenario.scenario_id == scenario_id
        assert hasattr(scenario, "recurrence")
        assert hasattr(scenario, "identifiers")
        assert hasattr(scenario, "cpv")
        assert hasattr(scenario, "duration")
        assert hasattr(scenario, "text")
        assert hasattr(scenario, "quality_class_mix")


def test_scenario_id_validation_rejects_unknown():
    import pytest
    with pytest.raises(ValueError):
        load_scenario(REPO, "not_a_real_scenario")


def test_clean_sanity_is_lower_corruption_than_adverse_identity():
    clean = load_scenario(REPO, "clean_sanity")
    adverse = load_scenario(REPO, "adverse_identity")
    assert clean.identifiers.siret_missing_rate < adverse.identifiers.siret_missing_rate
    assert clean.buyer_names.false_split_rate < adverse.buyer_names.false_split_rate
    assert clean.cpv.missing_rate < adverse.cpv.missing_rate


def test_generator_parameter_actions_table_has_valid_actions():
    df = pd.read_csv(REPO / "reports" / "tables" / "synthetic_calibration" / "generator_parameter_actions.csv")
    valid = {"USE_DIRECTLY", "USE_AS_FIDELITY_TARGET", "SCENARIO_PARAMETER", "DO_NOT_USE"}
    assert set(df["action"]) <= valid
    assert df["parameter_name"].is_unique


def test_precision_recall_never_use_directly_or_scenario_world_truth():
    """Phase 2 instruction #1: precision/recall must never be a generator
    input for synthetic-world truth."""
    df = pd.read_csv(REPO / "reports" / "tables" / "synthetic_calibration" / "generator_parameter_actions.csv")
    row = df[df["parameter_name"] == "true_linkage_precision_recall"].iloc[0]
    assert row["action"] == "SCENARIO_PARAMETER"
    assert "NEVER a generator parameter for synthetic-world truth" in row["notes"]


def test_frozen_thresholds_and_weights_are_do_not_use():
    """These are algorithm-conditioned pipeline internals, not properties of
    the synthetic world (spec: 'must not define synthetic truth')."""
    df = pd.read_csv(REPO / "reports" / "tables" / "synthetic_calibration" / "generator_parameter_actions.csv")
    for name in ["frozen_link_thresholds", "composite_score_weights",
                 "temporal_window_months", "max_candidates_per_source_cap"]:
        row = df[df["parameter_name"] == name].iloc[0]
        assert row["action"] == "DO_NOT_USE", f"{name} should be DO_NOT_USE, got {row['action']}"


def test_candidate_counts_are_fidelity_targets_not_do_not_use():
    """Spec Phase 2 instruction #3: production candidate counts must be
    fidelity targets, not simply excluded."""
    df = pd.read_csv(REPO / "reports" / "tables" / "synthetic_calibration" / "generator_parameter_actions.csv")
    row = df[df["parameter_name"] == "candidates_per_source_distribution"].iloc[0]
    assert row["action"] == "USE_AS_FIDELITY_TARGET"
