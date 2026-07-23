from pathlib import Path
from types import SimpleNamespace

import pytest

from boamp.synthetic.pipeline import generate_clean_world
from boamp.synthetic.relations import build_true_relations
from boamp.synthetic.scenarios import load_scenario
from boamp.synthetic.validation import validate_relations
from boamp.synthetic.cycles import _draw_successor_gap_months

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def tiny_world():
    return generate_clean_world("central_provisional", REPO, n_buyers=80, world_seed=11)


def test_relation_types_restricted_to_v0_1_ontology(tiny_world):
    rel = tiny_world["true_relations"]
    assert set(rel["relation_type"]) <= {"NEXT_CYCLE", "NO_SUCCESSOR"}


def test_every_cycle_has_exactly_one_outgoing_relation(tiny_world):
    result = validate_relations(tiny_world["cycles"], tiny_world["true_relations"])
    assert result.checks["exactly_one_outgoing_edge_per_cycle"], result.failures()


def test_no_successor_has_null_target_and_false_labels(tiny_world):
    rel = tiny_world["true_relations"]
    no_succ = rel[rel["relation_type"] == "NO_SUCCESSOR"]
    assert len(no_succ) > 0
    assert no_succ["target_cycle_id"].isna().all()
    assert (no_succ["strict_label"] == False).all()  # noqa: E712
    assert (no_succ["broad_label"] == False).all()  # noqa: E712


def test_next_cycle_is_one_to_one_and_true_labels(tiny_world):
    rel = tiny_world["true_relations"]
    next_cyc = rel[rel["relation_type"] == "NEXT_CYCLE"]
    assert len(next_cyc) > 0
    assert not next_cyc["target_cycle_id"].duplicated().any()
    assert not next_cyc["source_cycle_id"].duplicated().any()
    assert (next_cyc["strict_label"] == True).all()  # noqa: E712
    assert (next_cyc["broad_label"] == True).all()  # noqa: E712


def test_successor_dates_strictly_after_source(tiny_world):
    cycles = tiny_world["cycles"].set_index("cycle_id_true")
    rel = tiny_world["true_relations"]
    next_cyc = rel[rel["relation_type"] == "NEXT_CYCLE"]
    for _, r in next_cyc.iterrows():
        source_start = cycles.loc[r["source_cycle_id"], "start_date_true"]
        target_start = cycles.loc[r["target_cycle_id"], "start_date_true"]
        assert target_start > source_start


def test_true_gap_months_not_all_within_pipeline_six_month_window(tiny_world):
    """Spec Phase 4.4: 'Some true successors must fall outside the current
    temporal blocking rule' (the real pipeline's 6-month window)."""
    rel = tiny_world["true_relations"]
    gaps = rel.loc[rel["relation_type"] == "NEXT_CYCLE", "true_gap_months"]
    assert (gaps > 6).any(), "central_provisional's gap distribution should place some true gaps beyond the pipeline's 6-month window"


def test_build_true_relations_is_pure_function_of_cycles(tiny_world):
    rel_a = build_true_relations(tiny_world["cycles"], "central_provisional")
    rel_b = build_true_relations(tiny_world["cycles"], "central_provisional")
    assert rel_a.equals(rel_b)


def test_scoped_candidate_gap_mixture_draws_near_window_when_enabled():
    scenario = SimpleNamespace(
        recurrence=SimpleNamespace(
            cycle_gap_distribution=SimpleNamespace(type="normal", mean_months=18.0, sd_months=9.0, min_months=1.0),
            scoped_candidate_environment=SimpleNamespace(
                enabled=True,
                cpv_divisions=["32"],
                near_window_share=1.0,
                near_window_distribution=SimpleNamespace(
                    type="normal", mean_months=2.0, sd_months=0.01, min_months=0.1, max_months=6.0
                ),
            ),
        )
    )
    need = {"cpv_true": "32123456", "recurrence_propensity": 0.4}
    gap = _draw_successor_gap_months(need, scenario, __import__("numpy").random.default_rng(123))
    assert 0.1 <= gap <= 6.0
    assert gap == pytest.approx(2.0, abs=0.1)


def test_v0_3_scoped_candidate_revision_preserves_relation_integrity():
    scenario = load_scenario(REPO, "central_provisional")
    scenario.recurrence.scoped_candidate_environment.enabled = True
    scenario.recurrence.scoped_candidate_environment.recurrence_propensity_multiplier = 2.0
    scenario.recurrence.scoped_candidate_environment.near_window_share = 0.75
    scenario.recurrence.scoped_candidate_environment.hard_negative_alignment_rate = 0.10
    world = generate_clean_world(
        "central_provisional", REPO, n_buyers=120, world_seed=202, scenario_override=scenario
    )
    result = validate_relations(world["cycles"], world["true_relations"])
    assert result.passed, result.failures()
    gaps = world["true_relations"].loc[
        world["true_relations"]["relation_type"] == "NEXT_CYCLE", "true_gap_months"
    ]
    assert (gaps > 6).mean() >= 0.45
