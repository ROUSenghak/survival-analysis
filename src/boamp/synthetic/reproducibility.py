"""Canonical content hashing and replay helpers for synthetic benchmarks.

Parquet files can differ byte-for-byte across writer versions while carrying
the same table. Reproducibility checks here therefore compare canonical table
content: stable column order, stable row order, normalized scalar values, and a
SHA-256 digest over that representation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from boamp.synthetic.pipeline import generate_clean_world, generate_observed_world


TABLE_ATTRS: dict[str, str] = {
    "latent_buyers": "buyers",
    "latent_establishments": "establishments",
    "latent_needs": "needs",
    "latent_cycles": "cycles",
    "true_relations": "true_relations",
    "notice_family_membership": "notice_family_membership",
    "clean_notices": "clean_notices",
    "observed_notices": "observed_notices",
    "corruption_log": "corruption_log",
}

TABLE_SORT_KEYS: dict[str, list[str]] = {
    "latent_buyers": ["buyer_id_true"],
    "latent_establishments": ["establishment_id_true"],
    "latent_needs": ["need_id_true"],
    "latent_cycles": ["cycle_id_true"],
    "true_relations": ["source_cycle_id"],
    "notice_family_membership": ["notice_id_synthetic"],
    "clean_notices": ["notice_id_synthetic"],
    "observed_notices": ["notice_id_synthetic"],
    "corruption_log": ["notice_id_synthetic", "field", "corruption_type", "clean_value", "observed_value"],
}


@dataclass(frozen=True)
class ReplayComparison:
    """Table-level replay comparison result."""

    table: str
    expected_hash: str
    actual_hash: str
    expected_rows: int
    actual_rows: int
    expected_columns: tuple[str, ...]
    actual_columns: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return (
            self.expected_hash == self.actual_hash
            and self.expected_rows == self.actual_rows
            and self.expected_columns == self.actual_columns
        )


def _normalize_value(value) -> str:
    if value is None:
        return "<NA>"
    try:
        if bool(pd.isna(value)):
            return "<NA>"
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.datetime64):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, (float, np.floating)):
        return format(float(value), ".17g")
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, np.ndarray):
        return json.dumps(value.tolist(), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return str(value)


def canonicalize_frame(table: str, frame: pd.DataFrame) -> pd.DataFrame:
    """Return a string-valued frame with deterministic column and row order."""
    out = frame.copy()
    columns = list(out.columns)
    out = out[columns]
    for col in columns:
        out[col] = out[col].map(_normalize_value)
    sort_keys = [c for c in TABLE_SORT_KEYS.get(table, []) if c in out.columns]
    if sort_keys:
        out = out.sort_values(sort_keys, kind="mergesort")
    else:
        out = out.sort_values(columns, kind="mergesort")
    return out.reset_index(drop=True)


def canonical_frame_hash(table: str, frame: pd.DataFrame) -> str:
    canonical = canonicalize_frame(table, frame)
    payload = canonical.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def table_hashes(tables: Mapping[str, pd.DataFrame]) -> dict[str, str]:
    return {table: canonical_frame_hash(table, frame) for table, frame in sorted(tables.items())}


def benchmark_tables_from_world(
    world: dict[str, pd.DataFrame],
    observed: pd.DataFrame,
    corruption_log: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    return {
        "latent_buyers": world["buyers"],
        "latent_establishments": world["establishments"],
        "latent_needs": world["needs"],
        "latent_cycles": world["cycles"],
        "true_relations": world["true_relations"],
        "notice_family_membership": world["notice_family_membership"],
        "clean_notices": world["clean_notices"],
        "observed_notices": observed,
        "corruption_log": corruption_log,
    }


def environment_drift(metadata: Mapping) -> dict[str, dict[str, str]]:
    """Compare the recorded generation environment with the current one.

    Returned keys are libraries whose version differs. A replay mismatch
    confined to floating-point columns is expected under such a difference:
    NumPy's generator and reduction kernels are bit-stable per build, not
    across builds. An empty dict means the environment cannot explain a
    mismatch, so the generator or its configuration really did change.
    """
    from boamp.synthetic.pipeline import _runtime_environment

    recorded = dict(metadata.get("runtime_environment") or {})
    if not recorded:
        return {}
    current = _runtime_environment()
    return {
        key: {"recorded": str(recorded[key]), "current": str(current.get(key, "MISSING"))}
        for key in sorted(recorded)
        if str(recorded[key]) != str(current.get(key, "MISSING"))
    }


def regenerate_tables_from_metadata(project_root: Path, metadata: dict, scenario_id: str) -> dict[str, pd.DataFrame]:
    """Regenerate benchmark tables using recorded seeds and row-count scale."""
    n_buyers = int((metadata.get("row_counts") or {}).get("buyers") or metadata.get("n_buyers") or 0)
    if n_buyers <= 0:
        raise ValueError("metadata does not record a positive buyer count")
    world_seed = int(metadata["world_seed"])
    corruption_seed = int(metadata["corruption_seed"])
    world = generate_clean_world(scenario_id, project_root, n_buyers=n_buyers, world_seed=world_seed)
    observed, corruption_log = generate_observed_world(world, scenario_id, project_root, corruption_seed=corruption_seed)
    return benchmark_tables_from_world(world, observed, corruption_log)


def compare_table_sets(
    expected: Mapping[str, pd.DataFrame],
    actual: Mapping[str, pd.DataFrame],
) -> list[ReplayComparison]:
    comparisons: list[ReplayComparison] = []
    for table in sorted(expected):
        if table not in actual:
            comparisons.append(
                ReplayComparison(
                    table=table,
                    expected_hash=canonical_frame_hash(table, expected[table]),
                    actual_hash="MISSING",
                    expected_rows=len(expected[table]),
                    actual_rows=-1,
                    expected_columns=tuple(expected[table].columns),
                    actual_columns=(),
                )
            )
            continue
        comparisons.append(
            ReplayComparison(
                table=table,
                expected_hash=canonical_frame_hash(table, expected[table]),
                actual_hash=canonical_frame_hash(table, actual[table]),
                expected_rows=len(expected[table]),
                actual_rows=len(actual[table]),
                expected_columns=tuple(expected[table].columns),
                actual_columns=tuple(actual[table].columns),
            )
        )
    return comparisons
