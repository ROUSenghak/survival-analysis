"""Integrity assertions - the pipeline fails loudly when a condition breaks.

New module (no legacy equivalent existed). Used by notebook 01 Part H and by
tests. Every check raises AssertionError with a specific message.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def assert_unique(df: pd.DataFrame, key: str, name: str) -> None:
    n = int(df[key].duplicated().sum())
    assert n == 0, f"{name}: {n} duplicated values in key column '{key}'"


def assert_no_null(df: pd.DataFrame, cols: list[str], name: str) -> None:
    for c in cols:
        n = int(df[c].isna().sum())
        assert n == 0, f"{name}: column '{c}' has {n} nulls (expected none)"


def assert_columns(df: pd.DataFrame, cols: list[str], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    assert not missing, f"{name}: missing required columns {missing}"


def assert_row_count(df: pd.DataFrame, expected: int, name: str, tolerance: int = 0) -> None:
    assert abs(len(df) - expected) <= tolerance, \
        f"{name}: {len(df)} rows, expected {expected} (+/-{tolerance})"


def assert_positive(df: pd.DataFrame, col: str, name: str) -> None:
    vals = pd.to_numeric(df[col], errors="coerce")
    n_bad = int((vals <= 0).sum())
    assert n_bad == 0, f"{name}: {n_bad} non-positive values in '{col}'"


def assert_layer_parity(l1_sources: pd.DataFrame, l2_sources: pd.DataFrame,
                        identity_columns: list[str]) -> None:
    """The fairness guarantee: the two layers' source tables are identical
    except for buyer-identity / enrichment-provenance columns.

    identity_columns = the ONLY columns allowed to differ or to exist in
    just one layer.
    """
    assert len(l1_sources) == len(l2_sources), \
        f"layer parity: row counts differ ({len(l1_sources)} vs {len(l2_sources)})"
    a = l1_sources.sort_values("notice_id").reset_index(drop=True)
    b = l2_sources.sort_values("notice_id").reset_index(drop=True)
    assert (a["notice_id"] == b["notice_id"]).all(), "layer parity: notice_id sets differ"

    shared = [c for c in a.columns if c in b.columns and c not in identity_columns]
    for c in shared:
        av, bv = a[c], b[c]
        if pd.api.types.is_float_dtype(av):
            equal = np.isclose(av.astype(float), bv.astype(float), equal_nan=True)
        else:
            equal = (av.fillna("__NA__").astype(str) == bv.fillna("__NA__").astype(str))
        n_diff = int((~equal).sum())
        assert n_diff == 0, \
            f"layer parity: non-identity column '{c}' differs on {n_diff} rows - " \
            f"the layers are no longer a controlled comparison"


def assert_links_consistent(links: pd.DataFrame, pairs: pd.DataFrame, name: str) -> None:
    """Every accepted link must exist in the candidate table, be rank 1,
    and have candidate_date strictly after source_date."""
    pair_keys = set(zip(pairs["source_notice_id"], pairs["candidate_notice_id"]))
    link_keys = set(zip(links["source_notice_id"], links["candidate_notice_id"]))
    orphans = link_keys - pair_keys
    assert not orphans, f"{name}: {len(orphans)} links missing from candidate table"
    assert (links["candidate_rank"] == 1).all(), f"{name}: non-rank-1 links present"
    bad_chrono = int((pd.to_datetime(links["candidate_date"])
                      <= pd.to_datetime(links["source_date"])).sum())
    assert bad_chrono == 0, f"{name}: {bad_chrono} links with candidate_date <= source_date"
    assert_unique(links, "source_notice_id", name)


def assert_survival_consistent(survival: pd.DataFrame, links: pd.DataFrame, name: str) -> None:
    """Events <-> links; censored rows carry no candidate; times positive."""
    events = survival[survival["event"] == 1]
    censored = survival[survival["event"] == 0]
    assert len(events) == len(links), \
        f"{name}: {len(events)} event rows vs {len(links)} links"
    assert events["linked_candidate_notice_id"].notna().all(), \
        f"{name}: event rows without a linked candidate"
    assert censored["linked_candidate_notice_id"].isna().all(), \
        f"{name}: censored rows carrying a linked candidate"
    assert_positive(survival, "time_to_event_or_censor_months", name)
    linked_ids = set(links["source_notice_id"])
    event_ids = set(events["notice_id"])
    assert linked_ids == event_ids, f"{name}: event notice_ids differ from link source ids"


def run_all(checks: list[tuple[str, callable]]) -> pd.DataFrame:
    """Run named check callables; return a pass/fail table; raise at the end
    if any failed (so a notebook cell shows the full table before failing)."""
    rows = []
    failures = []
    for label, fn in checks:
        try:
            fn()
            rows.append({"check": label, "passed": True, "error": ""})
        except AssertionError as e:
            rows.append({"check": label, "passed": False, "error": str(e)})
            failures.append(label)
    table = pd.DataFrame(rows)
    if failures:
        print(table.to_string(index=False))
        raise AssertionError(f"Integrity checks failed: {failures}")
    return table
