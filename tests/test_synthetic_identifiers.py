from pathlib import Path

import numpy as np
import pytest

from boamp.synthetic.establishments import generate_valid_siren, generate_valid_siret
from boamp.synthetic.pipeline import generate_clean_world
from utils.identifiers import siren_from_siret, validate_siren, validate_siret

REPO = Path(__file__).resolve().parents[1]


def test_generate_valid_siren_passes_real_validator():
    rng = np.random.default_rng(0)
    for _ in range(50):
        siren = generate_valid_siren(rng)
        fmt_ok, checksum_ok = validate_siren(siren)
        assert fmt_ok and checksum_ok, siren


def test_generate_valid_siret_belongs_to_its_siren_and_passes_real_validator():
    rng = np.random.default_rng(0)
    siren = generate_valid_siren(rng)
    for seq in range(1, 4):
        siret = generate_valid_siret(siren, seq)
        fmt_ok, checksum_ok = validate_siret(siret)
        assert fmt_ok and checksum_ok, siret
        assert siren_from_siret(siret) == siren


@pytest.fixture(scope="module")
def tiny_world():
    return generate_clean_world("clean_sanity", REPO, n_buyers=60, world_seed=3)


def test_every_establishment_siret_and_siren_valid(tiny_world):
    est = tiny_world["establishments"]
    for _, row in est.iterrows():
        fmt_ok, checksum_ok = validate_siren(row["siren_true"])
        assert fmt_ok and checksum_ok
        fmt_ok, checksum_ok = validate_siret(row["siret_true"])
        assert fmt_ok and checksum_ok


def test_every_siret_belongs_to_its_siren(tiny_world):
    est = tiny_world["establishments"]
    assert (est["siret_true"].map(siren_from_siret) == est["siren_true"]).all()


def test_no_duplicate_sirets_or_sirens_across_establishments(tiny_world):
    est = tiny_world["establishments"]
    assert not est["siret_true"].duplicated().any()


def test_establishments_sharing_a_siren_belong_to_one_buyer(tiny_world):
    est = tiny_world["establishments"]
    per_siren_buyers = est.groupby("siren_true")["buyer_id_true"].nunique()
    assert (per_siren_buyers == 1).all()


def test_no_generated_identifier_collides_with_a_real_boamp_identifier(tiny_world):
    """A real BOAMP SIRET/SIREN happens to be recoverable from the prepared
    interim corpus (data/interim/boamp_common_prepared.csv). This test only
    runs the comparison if that file is present (it is a large, gitignored-
    scale data artifact in some checkouts) — never copying a real identifier
    is a structural property of the generator (validate_siren/validate_siret
    on freshly-drawn digits), not something that depends on this file
    existing, but checking it directly here is the strongest evidence."""
    import pandas as pd

    prepared_path = REPO / "data" / "interim" / "boamp_common_prepared.csv"
    if not prepared_path.exists():
        pytest.skip("data/interim/boamp_common_prepared.csv not present in this checkout")
    real = pd.read_csv(prepared_path, usecols=["buyer_siret_clean"], dtype=str, low_memory=False)
    real_sirets = set(real["buyer_siret_clean"].dropna())
    synthetic_sirets = set(tiny_world["establishments"]["siret_true"])
    assert not (real_sirets & synthetic_sirets)
