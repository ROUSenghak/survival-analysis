from pathlib import Path

import pytest

from boamp.synthetic.pipeline import generate_clean_world
from boamp.synthetic.relations import build_true_relations
from boamp.synthetic.validation import validate_relations

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
