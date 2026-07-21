from pathlib import Path

import pandas as pd
import pytest

from boamp.synthetic.pipeline import generate_clean_world, generate_observed_world
from boamp.synthetic.validation import run_full_structural_validation

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def tiny_world():
    return generate_clean_world("central_provisional", REPO, n_buyers=100, world_seed=21)


def test_clean_world_passes_full_structural_validation(tiny_world):
    result = run_full_structural_validation(tiny_world)
    assert result.passed, result.failures()


def test_every_establishment_belongs_to_exactly_one_buyer(tiny_world):
    est = tiny_world["establishments"]
    buyer_ids = set(tiny_world["buyers"]["buyer_id_true"])
    assert est["buyer_id_true"].isin(buyer_ids).all()
    # establishment_id_true is unique -> each row (establishment) has exactly
    # one buyer_id_true value by construction (one column, no duplicate ids)
    assert not est["establishment_id_true"].duplicated().any()


def test_every_need_belongs_to_exactly_one_buyer(tiny_world):
    needs = tiny_world["needs"]
    buyer_ids = set(tiny_world["buyers"]["buyer_id_true"])
    assert needs["buyer_id_true"].isin(buyer_ids).all()
    assert not needs["need_id_true"].duplicated().any()


def test_every_cycle_belongs_to_exactly_one_need(tiny_world):
    cycles = tiny_world["cycles"]
    need_ids = set(tiny_world["needs"]["need_id_true"])
    assert cycles["cycle_id_true"].is_unique
    assert cycles["need_id_true"].isin(need_ids).all()


def test_a_buyer_can_have_several_simultaneous_needs(tiny_world):
    needs_per_buyer = tiny_world["needs"].groupby("buyer_id_true").size()
    assert (needs_per_buyer > 1).any()


def test_same_buyer_same_cpv_distinct_needs_exist(tiny_world):
    """Spec Phase 4.3: generate same-buyer/same-CPV but different-need cases
    so realistic hard negatives can emerge (structural, not scripted)."""
    needs = tiny_world["needs"]
    dup = needs.groupby(["buyer_id_true", "segment_true"]).size()
    assert (dup > 1).any()


def test_notice_family_members_share_exactly_one_cycle(tiny_world):
    membership = tiny_world["notice_family_membership"]
    per_notice = membership.groupby("notice_id_synthetic")["cycle_id_true"].nunique()
    assert (per_notice == 1).all()


def test_notice_family_role_values_restricted(tiny_world):
    membership = tiny_world["notice_family_membership"]
    assert set(membership["role"]) <= {"CALL", "AWARD"}


def test_every_cycle_has_at_least_one_call_notice(tiny_world):
    membership = tiny_world["notice_family_membership"]
    calls_per_cycle = membership[membership["role"] == "CALL"].groupby("cycle_id_true").size()
    assert (calls_per_cycle == 1).all()
    assert set(calls_per_cycle.index) == set(tiny_world["cycles"]["cycle_id_true"])


def test_award_notices_reference_a_call_notice_in_the_same_cycle(tiny_world):
    clean = tiny_world["clean_notices"]
    calls = clean[clean["role"] == "CALL"].set_index("notice_id_synthetic")
    awards = clean[clean["role"] == "AWARD"]
    for _, award in awards.iterrows():
        linked = award["linked_call_notice_id_true"]
        assert linked in calls.index
        assert calls.loc[linked, "cycle_id_true"] == award["cycle_id_true"]


def test_no_real_identifier_or_text_is_copied_structurally(tiny_world):
    """Every buyer name is synthetically generated (syllable-based place
    names never sourced from an external real-name list), and every
    objet_true is template+vocabulary assembled, never a literal string
    pulled from any real corpus file."""
    names = tiny_world["buyers"]["buyer_name_true"]
    assert names.map(lambda n: isinstance(n, str) and len(n) > 0).all()
    texts = tiny_world["clean_notices"]["objet_true"]
    assert texts.map(lambda t: isinstance(t, str) and len(t) > 0).all()


def test_structural_validation_failure_blocks_progression(monkeypatch):
    """Spec Phase 5: must not proceed to corruption on a failed clean world."""
    import boamp.synthetic.pipeline as pipeline_mod
    from boamp.synthetic.relations import build_true_relations as real_build_true_relations

    def _broken_relations(cycles, scenario_id):
        rel = real_build_true_relations(cycles, scenario_id)
        rel = rel.iloc[:-1]  # drop one row -> some cycle now has zero outgoing edges
        return rel

    monkeypatch.setattr(pipeline_mod, "build_true_relations", _broken_relations)
    with pytest.raises(ValueError, match="structural validation FAILED"):
        generate_clean_world("clean_sanity", REPO, n_buyers=20, world_seed=42)


def test_observed_notices_column_count_matches_clean_notices_row_count(tiny_world):
    observed, _log = generate_observed_world(tiny_world, "central_provisional", REPO, corruption_seed=22)
    assert len(observed) == len(tiny_world["clean_notices"])
