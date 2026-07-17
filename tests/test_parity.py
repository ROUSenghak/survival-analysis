"""Slow parity tests: the exported two-layer datasets must match the frozen
legacy fingerprints (counts + sorted source-ID hashes). Run with -m slow after
executing notebook 01."""

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "baseline_fingerprints.json"

pytestmark = pytest.mark.slow


def ids_sha(values):
    return hashlib.sha256("\n".join(sorted(str(v) for v in values)).encode()).hexdigest()


@pytest.fixture(scope="module")
def fp():
    return json.loads(FIXTURE.read_text())["files"]


def _need(path):
    if not path.exists():
        pytest.skip(f"{path} not built yet - run notebook 01 first")
    return path


def test_l1_sources_parity(cfg, fp):
    df = pd.read_csv(_need(cfg.paths.processed_boamp_only / "boamp_only_sources.csv"), dtype=str)
    assert len(df) == fp["m0_sources"]["rows"]
    assert ids_sha(df["notice_id"]) == fp["m0_sources"]["ids_sha256"]


def test_l1_pairs_parity(cfg, fp):
    df = pd.read_csv(_need(cfg.paths.processed_boamp_only / "boamp_only_candidate_pairs.csv"), dtype=str)
    assert len(df) == fp["m0_pairs"]["rows"]
    assert ids_sha(df["source_notice_id"]) == fp["m0_pairs"]["ids_sha256"]


@pytest.mark.parametrize("variant,key", [("broad", "m0_links_broad"),
                                         ("balanced", "m0_links_balanced"),
                                         ("strict", "m0_links_strict")])
def test_l1_links_parity(cfg, fp, variant, key):
    df = pd.read_csv(_need(cfg.paths.processed_boamp_only / f"boamp_only_links_{variant}.csv"), dtype=str)
    assert len(df) == fp[key]["rows"]
    assert ids_sha(df["source_notice_id"]) == fp[key]["ids_sha256"]


def test_l1_survival_parity(cfg, fp):
    df = pd.read_csv(_need(cfg.paths.processed_boamp_only / "boamp_only_survival.csv"))
    assert len(df) == fp["m0_survival_balanced"]["rows"]
    assert int(df["event"].sum()) == fp["m0_survival_balanced"]["events"]


def test_l2_pairs_parity(cfg, fp):
    df = pd.read_csv(_need(cfg.paths.processed_enriched / "enriched_candidate_pairs.csv"), dtype=str)
    assert len(df) == fp["m1_pairs"]["rows"]
    assert ids_sha(df["source_notice_id"]) == fp["m1_pairs"]["ids_sha256"]


def test_l2_links_parity(cfg, fp):
    df = pd.read_csv(_need(cfg.paths.processed_enriched / "enriched_links_balanced.csv"), dtype=str)
    assert len(df) == fp["m1_links_balanced"]["rows"]
    assert ids_sha(df["source_notice_id"]) == fp["m1_links_balanced"]["ids_sha256"]


def test_l2_survival_parity(cfg, fp):
    df = pd.read_csv(_need(cfg.paths.processed_enriched / "enriched_survival.csv"))
    assert len(df) == fp["m1_survival_balanced"]["rows"]
    assert int(df["event"].sum()) == fp["m1_survival_balanced"]["events"]
