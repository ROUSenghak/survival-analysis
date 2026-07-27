from pathlib import Path

import pandas as pd
import yaml

from boamp.synthetic.parameters import load_calibration_parameters
from boamp.synthetic.conditional_observation import build_conditional_observation_model
from boamp.synthetic.compatibility import adapt_observed_notices_to_sources
from boamp.synthetic.pipeline import generate_clean_world, generate_observed_world
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


def test_required_benchmark_scenarios_are_executable_configs():
    required = {"easier", "moderate", "difficult", "stress"}
    assert required.issubset(set(VALID_SCENARIOS))
    for scenario_id in sorted(required):
        scenario = load_scenario(REPO, scenario_id)
        assert scenario.scenario_id == scenario_id
        assert hasattr(scenario, "scenario_design_note")
        assert "SCENARIO" in str(scenario.provenance)


def test_required_scenario_difficulty_order_is_declared():
    scenarios = {name: load_scenario(REPO, name) for name in ["easier", "moderate", "difficult", "stress"]}
    recurrence = [scenarios[name].recurrence.base_recurrence_propensity for name in scenarios]
    drift = [scenarios[name].text.next_cycle_drift_severity for name in scenarios]
    high_quality = [scenarios[name].quality_class_mix.HIGH for name in scenarios]
    assert recurrence == sorted(recurrence, reverse=True)
    assert drift == sorted(drift)
    assert high_quality == sorted(high_quality, reverse=True)


def test_moderate_is_required_name_for_central_scenario_assumption():
    central = load_scenario(REPO, "central_provisional")
    moderate = load_scenario(REPO, "moderate")
    assert moderate.recurrence.base_recurrence_propensity == central.recurrence.base_recurrence_propensity
    assert (
        moderate.recurrence.scoped_candidate_environment.near_window_share
        == central.recurrence.scoped_candidate_environment.near_window_share
    )
    assert moderate.conditional_observation.enabled == central.conditional_observation.enabled


def test_required_benchmark_scenarios_generate_tiny_observed_worlds():
    for idx, scenario_id in enumerate(["easier", "moderate", "difficult", "stress"], start=1):
        world = generate_clean_world(scenario_id, REPO, n_buyers=20, world_seed=9100 + idx)
        observed, corruption_log = generate_observed_world(
            world, scenario_id, REPO, corruption_seed=9200 + idx
        )
        assert len(observed) == len(world["clean_notices"])
        assert not corruption_log.empty


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


def test_scoped_candidate_environment_config_does_not_assign_candidate_counts():
    with open(REPO / "config/synthetic/scenarios/central_provisional.yaml", encoding="utf-8") as f:
        scenario = yaml.safe_load(f)
    cfg = scenario["recurrence"]["scoped_candidate_environment"]
    forbidden = {
        "candidate_count",
        "candidate_counts",
        "candidates_per_source",
        "zero_candidate_rate",
        "p75_candidate_count",
        "p90_candidate_count",
        "p95_candidate_count",
    }
    assert forbidden.isdisjoint(cfg)


def test_conditional_duration_value_sampler_uses_valid_raw_observed_values():
    model = build_conditional_observation_model(REPO)
    real = pd.read_csv(REPO / "data" / "interim" / "boamp_common_prepared.csv", usecols=["duration_raw"])
    valid_real_values = set(
        pd.to_numeric(real["duration_raw"], errors="coerce")
        .dropna()
        .loc[lambda s: s.between(1, 120)]
        .astype(float)
    )

    sampled = {model.declared_duration_value(f"SYN-NOTICE-{idx:05d}") for idx in range(250)}

    assert sampled
    assert sampled <= valid_real_values
    assert min(sampled) >= 1.0
    assert max(sampled) <= 120.0


def test_conditional_observed_duration_is_not_latent_truth_transform():
    world = generate_clean_world("central_provisional", REPO, n_buyers=100, world_seed=21)
    observed, corruption_log = generate_observed_world(
        world, "central_provisional", REPO, corruption_seed=22
    )
    merged = observed[["notice_id_synthetic", "declared_duration_months"]].merge(
        world["clean_notices"][["notice_id_synthetic", "duration_true_months"]],
        on="notice_id_synthetic",
    )
    present = merged.dropna(subset=["declared_duration_months"])

    assert not present.empty
    assert not present["declared_duration_months"].equals(present["duration_true_months"])
    assert (
        corruption_log["corruption_type"].eq("EMPIRICAL_RAW_DECLARED_DURATION").sum()
        == len(present)
    )


def test_scoped_recurrent_needs_keep_stable_observed_buyer_key():
    world = generate_clean_world("central_provisional", REPO, n_buyers=300, world_seed=20260721)
    observed, _corruption_log = generate_observed_world(
        world, "central_provisional", REPO, corruption_seed=20260722
    )
    sources = adapt_observed_notices_to_sources(observed)
    calls = world["clean_notices"].loc[
        world["clean_notices"]["role"].eq("CALL"),
        ["notice_id_synthetic", "need_id_true", "cpv_true"],
    ]
    scoped_calls = calls.loc[calls["cpv_true"].astype(str).str[:2].isin({"32", "35", "48", "72"})]
    recurrent_scoped_calls = scoped_calls.groupby("need_id_true").filter(lambda group: len(group) > 1)
    merged = recurrent_scoped_calls.merge(
        sources[["notice_id", "buyer_key", "buyer_key_type"]],
        left_on="notice_id_synthetic",
        right_on="notice_id",
    )

    assert not merged.empty
    assert (merged.groupby("need_id_true")["buyer_key"].nunique() == 1).all()
    assert (merged.groupby("need_id_true")["buyer_key_type"].nunique() == 1).all()


def test_parameter_registry_uses_required_provenance_inventory_schema():
    df = pd.read_csv(
        REPO
        / "reports"
        / "tables"
        / "synthetic_benchmark"
        / "v0_3_temporal_candidate_revision"
        / "registries"
        / "parameter_registry.csv"
    )
    required_columns = {
        "name",
        "definition",
        "value_or_distribution",
        "source_dataset_population",
        "estimation_code",
        "uncertainty",
        "version",
        "rationale",
        "may_be_used_for_calibration",
        "must_remain_held_out",
        "known_limitations",
        "provenance_category",
    }
    required_categories = {
        "EMPIRICAL_OBSERVABLE",
        "SILVER_STANDARD_APPROXIMATION",
        "SCENARIO_UNIDENTIFIED",
        "FIDELITY_TARGET",
        "ALGORITHM_PARAMETER",
        "IMPLEMENTATION_CONSTANT",
    }
    assert required_columns.issubset(df.columns)
    assert set(df["provenance_category"]).issubset(required_categories)
    assert {"EMPIRICAL_OBSERVABLE", "SCENARIO_UNIDENTIFIED"}.issubset(
        set(df["provenance_category"])
    )


def test_scenario_manifest_distinguishes_configured_from_generated_artifacts():
    manifest = pd.read_csv(
        REPO
        / "reports"
        / "tables"
        / "synthetic_benchmark"
        / "v0_3_temporal_candidate_revision"
        / "registries"
        / "scenario_manifest.csv"
    )
    required = {"easier", "moderate", "difficult", "stress"}
    assert required.issubset(set(manifest["scenario"]))
    required_rows = manifest.loc[manifest["scenario"].isin(required)]
    assert set(required_rows["config_status"]) == {"CONFIGURED"}
    assert set(required_rows["artifact_status"]) == {"GENERATED"}
    generated = manifest.loc[manifest["manifest_row_type"].eq("GENERATED_REPLICATE")]
    assert {"central_provisional", "clean_sanity"}.issubset(set(generated["scenario"]))
    assert len(generated.loc[generated["scenario"].eq("central_provisional")]) >= 10
    config_only = manifest.loc[manifest["manifest_row_type"].eq("CONFIG_ONLY")]
    assert "adverse_identity" in set(config_only["scenario"])
