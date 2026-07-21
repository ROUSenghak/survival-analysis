from pathlib import Path

import pandas as pd
import pytest

from boamp.synthetic import schemas
from boamp.synthetic.pipeline import generate_clean_world, generate_observed_world

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def tiny_world():
    return generate_clean_world("clean_sanity", REPO, n_buyers=40, world_seed=7)


@pytest.fixture(scope="module")
def tiny_observed(tiny_world):
    return generate_observed_world(tiny_world, "clean_sanity", REPO, corruption_seed=8)


@pytest.mark.parametrize("table_name,schema", [
    ("buyers", schemas.LATENT_BUYERS),
    ("establishments", schemas.LATENT_ESTABLISHMENTS),
    ("needs", schemas.LATENT_NEEDS),
    ("cycles", schemas.LATENT_CYCLES),
    ("true_relations", schemas.TRUE_RELATIONS),
    ("notice_family_membership", schemas.NOTICE_FAMILY_MEMBERSHIP),
    ("clean_notices", schemas.CLEAN_NOTICES),
])
def test_clean_world_table_has_required_columns(tiny_world, table_name, schema):
    schemas.validate_columns(tiny_world[table_name], schema, table_name)


def test_observed_notices_has_required_columns(tiny_observed):
    observed, _log = tiny_observed
    schemas.validate_columns(observed, schemas.OBSERVED_NOTICES, "observed_notices")


def test_observed_notices_never_leaks_truth_columns(tiny_observed):
    observed, _log = tiny_observed
    schemas.assert_no_truth_leakage(observed)
    for col in schemas.CLEAN_NOTICES_TRUTH_ONLY:
        assert col not in observed.columns


def test_corruption_log_has_required_columns(tiny_observed):
    _observed, log = tiny_observed
    schemas.validate_columns(log, schemas.CORRUPTION_LOG, "corruption_log")


def test_schema_repeated_generation_is_column_stable():
    """Two independent generations at different scale/seed must produce the
    exact same column set (stable schema requirement, Phase 5)."""
    w1 = generate_clean_world("clean_sanity", REPO, n_buyers=20, world_seed=1)
    w2 = generate_clean_world("central_provisional", REPO, n_buyers=25, world_seed=2)
    for key in ["buyers", "establishments", "needs", "cycles", "true_relations",
                "notice_family_membership", "clean_notices"]:
        assert list(w1[key].columns) == list(w2[key].columns), key
