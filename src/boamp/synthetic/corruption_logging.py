"""Corruption event logging (Phase 7's `corruption_log.parquet` requirement)."""
from __future__ import annotations

import math

import pandas as pd

from boamp.synthetic import schemas


def _is_missing(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return False


def _values_equal(a, b) -> bool:
    if _is_missing(a) and _is_missing(b):
        return True
    return a == b


class CorruptionLogger:
    """Accumulates one row per *actual* field change (clean_value !=
    observed_value); a field left untouched is not logged, so the log's row
    count is a direct measure of how much corruption a scenario injected."""

    def __init__(self, scenario_id: str, seed: int):
        self.scenario_id = scenario_id
        self.seed = seed
        self._rows: list[dict] = []

    def log(self, notice_id: str, field: str, clean_value, observed_value,
             corruption_type: str, severity: float | None = None) -> None:
        if _values_equal(clean_value, observed_value):
            return
        # Stored as strings: clean_value/observed_value mix str/float/None
        # across corruption types (identifier, CPV, duration, text), and a
        # single Parquet column needs one Arrow type. The log is a diagnostic
        # audit trail, not a typed analytic column, so this loses no
        # information that matters here.
        self._rows.append(dict(
            notice_id_synthetic=notice_id, field=field,
            clean_value=None if _is_missing(clean_value) else str(clean_value),
            observed_value=None if _is_missing(observed_value) else str(observed_value),
            corruption_type=corruption_type,
            scenario=self.scenario_id, severity=severity, seed=self.seed,
        ))

    def to_frame(self) -> pd.DataFrame:
        if not self._rows:
            return pd.DataFrame(columns=list(schemas.CORRUPTION_LOG))
        return pd.DataFrame(self._rows)[list(schemas.CORRUPTION_LOG)]
