from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from boamp.synthetic.corruption import corrupt_notices
from boamp.synthetic.pipeline import generate_clean_world, generate_observed_world
from boamp.synthetic.reproducibility import (
    benchmark_tables_from_world,
    compare_table_sets,
    environment_drift,
    regenerate_tables_from_metadata,
    table_hashes,
)
from boamp.synthetic.validation_framework.loaders import load_benchmark_data

REPO = Path(__file__).resolve().parents[1]


def test_fixed_seed_gives_identical_row_counts():
    w1 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=555)
    w2 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=555)
    for key in ["buyers", "establishments", "needs", "cycles", "true_relations",
                "notice_family_membership", "clean_notices"]:
        assert len(w1[key]) == len(w2[key]), key


def test_fixed_seed_gives_byte_identical_key_columns():
    w1 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=555)
    w2 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=555)
    assert w1["buyers"]["siren_true"].tolist() == w2["buyers"]["siren_true"].tolist()
    assert w1["establishments"]["siret_true"].tolist() == w2["establishments"]["siret_true"].tolist()
    assert w1["clean_notices"]["objet_true"].tolist() == w2["clean_notices"]["objet_true"].tolist()
    assert w1["true_relations"]["relation_type"].tolist() == w2["true_relations"]["relation_type"].tolist()


def test_fixed_seed_corruption_is_also_reproducible():
    w = generate_clean_world("central_provisional", REPO, n_buyers=40, world_seed=777)
    obs1, log1 = generate_observed_world(w, "central_provisional", REPO, corruption_seed=888)
    obs2, log2 = generate_observed_world(w, "central_provisional", REPO, corruption_seed=888)
    assert obs1.equals(obs2)
    assert len(log1) == len(log2)


def test_observed_buyer_identity_is_stable_within_notice_family():
    w = generate_clean_world("central_provisional", REPO, n_buyers=80, world_seed=20260721)
    observed, _ = generate_observed_world(w, "central_provisional", REPO, corruption_seed=20260722)
    cycle_lookup = w["clean_notices"][["notice_id_synthetic", "cycle_id_true"]]
    with_cycle = observed.merge(cycle_lookup, on="notice_id_synthetic", how="left")
    sibling_cycles = with_cycle.groupby("cycle_id_true").filter(lambda g: len(g) > 1)

    assert not sibling_cycles.empty
    max_distinct = sibling_cycles.groupby("cycle_id_true")["buyer_name_raw"].nunique(dropna=False).max()
    assert max_distinct == 1


def test_conditional_identifier_visibility_is_notice_level_with_stable_family_name():
    from boamp.synthetic.scenarios import load_scenario

    scenario = load_scenario(REPO, "central_provisional")
    scenario.identifiers.conditional_siret_presence.enabled = True
    scenario.identifiers.conditional_siret_presence.siren_only_among_absent_rate = 0.0
    scenario.identifiers.conditional_siret_presence.invalid_among_absent_rate = 0.0
    scenario.identifiers.wrong_establishment_siret_rate = 0.0
    scenario.buyer_names.generic_collision_rate = 0.0
    scenario.buyer_names.false_split_rate = 0.0

    buyers = pd.DataFrame(
        [{
            "buyer_id_true": "B1",
            "identifier_quality_propensity": 0.5,
            "alias_propensity": 0.0,
            "buyer_type_true": "COMMUNE",
        }]
    )
    establishments = pd.DataFrame([{"siren_true": "356000000", "siret_true": "35600000000048"}])
    clean = pd.DataFrame(
        [
            {
                "notice_id_synthetic": "N_CALL",
                "buyer_id_true": "B1",
                "need_id_true": "NEED1",
                "cycle_id_true": "CYCLE1",
                "cpv_true": "32000000",
                "siret_true": "35600000000048",
                "siren_true": "356000000",
                "buyer_name_true": "Commune de Test",
                "department_true": "75",
                "publication_date_true": pd.Timestamp("2026-01-01"),
                "notice_type_true": "APPEL_OFFRE",
                "schema_family_true": "EFORMS",
                "duration_true_months": 12.0,
                "objet_true": "Maintenance informatique",
                "role": "CALL",
                "linked_call_notice_id_true": None,
            },
            {
                "notice_id_synthetic": "N_AWARD",
                "buyer_id_true": "B1",
                "need_id_true": "NEED1",
                "cycle_id_true": "CYCLE1",
                "cpv_true": "32000000",
                "siret_true": "35600000000048",
                "siren_true": "356000000",
                "buyer_name_true": "Commune de Test",
                "department_true": "75",
                "publication_date_true": pd.Timestamp("2026-01-15"),
                "notice_type_true": "ATTRIBUTION",
                "schema_family_true": "EFORMS",
                "duration_true_months": 12.0,
                "objet_true": "Maintenance informatique",
                "role": "AWARD",
                "linked_call_notice_id_true": "N_CALL",
            },
        ]
    )

    class ObservationModel:
        def siret_present_rate(self, row):
            return 0.0 if row["notice_type_true"] == "APPEL_OFFRE" else 1.0

        def duration_present_rate(self, row):
            return 1.0

        def declared_duration_value(self, notice_id):
            return 12.0

        def generic_text_rate(self, notice_type, buyer_activity_tier):
            return 0.0

    logger = SimpleNamespace(log=lambda *args, **kwargs: None)
    observed = corrupt_notices(
        clean, buyers, establishments, scenario, np.random.default_rng(1), logger,
        observation_model=ObservationModel(),
    )

    by_id = observed.set_index("notice_id_synthetic")
    assert by_id.loc["N_CALL", "buyer_siret_raw"] is None
    assert by_id.loc["N_AWARD", "buyer_siret_raw"] == "35600000000048"
    assert observed["buyer_name_raw"].nunique() == 1
    assert by_id.loc["N_CALL", "objet_clean"] == "Maintenance informatique"
    assert by_id.loc["N_AWARD", "objet_clean"] == "Maintenance informatique - attribution du marché."


def test_different_world_seed_changes_the_generated_population():
    w1 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=1)
    w2 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=2)
    assert w1["buyers"]["siren_true"].tolist() != w2["buyers"]["siren_true"].tolist()
    assert w1["clean_notices"]["objet_true"].tolist() != w2["clean_notices"]["objet_true"].tolist()


def test_different_corruption_seed_changes_observed_notices():
    w = generate_clean_world("central_provisional", REPO, n_buyers=40, world_seed=333)
    obs1, _ = generate_observed_world(w, "central_provisional", REPO, corruption_seed=1)
    obs2, _ = generate_observed_world(w, "central_provisional", REPO, corruption_seed=2)
    assert not obs1["buyer_name_raw"].equals(obs2["buyer_name_raw"])


def test_world_seed_independent_of_corruption_seed():
    """Holding the world fixed while varying only the corruption seed must
    not change the clean world itself (spec: two independent seeds)."""
    w = generate_clean_world("central_provisional", REPO, n_buyers=30, world_seed=42)
    before = w["clean_notices"]["objet_true"].tolist()
    generate_observed_world(w, "central_provisional", REPO, corruption_seed=1)
    generate_observed_world(w, "central_provisional", REPO, corruption_seed=2)
    after = w["clean_notices"]["objet_true"].tolist()
    assert before == after


def test_canonical_table_hashes_replay_generated_content():
    w1 = generate_clean_world("central_provisional", REPO, n_buyers=45, world_seed=909)
    obs1, log1 = generate_observed_world(w1, "central_provisional", REPO, corruption_seed=1010)
    w2 = generate_clean_world("central_provisional", REPO, n_buyers=45, world_seed=909)
    obs2, log2 = generate_observed_world(w2, "central_provisional", REPO, corruption_seed=1010)

    expected = benchmark_tables_from_world(w1, obs1, log1)
    actual = benchmark_tables_from_world(w2, obs2, log2)
    assert table_hashes(expected) == table_hashes(actual)
    assert all(item.passed for item in compare_table_sets(expected, actual))


@pytest.mark.slow
def test_released_benchmark_replays_from_recorded_configuration():
    """The published tables must still follow from the published config.

    Generating twice in one process only proves the generator is deterministic.
    This is the check that the released artifacts and the released scenario
    file have not drifted apart.
    """
    version, scenario = "v0_3_temporal_candidate_revision", "central_provisional"
    data = load_benchmark_data(REPO, version, scenario)
    released = {
        "latent_buyers": data.latent_buyers,
        "latent_establishments": data.latent_establishments,
        "latent_needs": data.latent_needs,
        "latent_cycles": data.latent_cycles,
        "true_relations": data.true_relations,
        "notice_family_membership": data.notice_family_membership,
        "clean_notices": data.clean,
        "observed_notices": data.observed,
        "corruption_log": data.corruption_log,
    }
    regenerated = regenerate_tables_from_metadata(REPO, data.metadata, scenario)
    failed = [item.table for item in compare_table_sets(released, regenerated) if not item.passed]
    drift = environment_drift(data.metadata)
    assert not failed, (
        f"released tables no longer replay: {failed}; "
        f"numeric-environment drift since generation: {drift or 'none recorded'}"
    )
