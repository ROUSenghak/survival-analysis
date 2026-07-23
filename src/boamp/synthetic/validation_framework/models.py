"""Shared result records and status helpers for validation tables."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from math import isfinite

import numpy as np
import pandas as pd


LONG_METRIC_COLUMNS = [
    "benchmark_version",
    "scenario",
    "seed",
    "scope",
    "subgroup",
    "property",
    "metric",
    "real_estimate",
    "synthetic_estimate",
    "difference",
    "effect_size",
    "ci_low",
    "ci_high",
    "tolerance",
    "status",
    "provenance",
    "notes",
]

GATE_COLUMNS = [
    "gate",
    "status",
    "critical",
    "n_pass",
    "n_warning",
    "n_fail",
    "n_inconclusive",
    "headline",
    "blocking_reason",
]


class Status(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class MetricResult:
    benchmark_version: str
    scenario: str
    seed: str
    scope: str
    subgroup: str
    property: str
    metric: str
    real_estimate: float | str | None
    synthetic_estimate: float | str | None
    difference: float | None
    effect_size: float | None
    ci_low: float | None
    ci_high: float | None
    tolerance: float | str | None
    status: Status | str
    provenance: str
    notes: str = ""

    def to_dict(self) -> dict:
        out = asdict(self)
        out["status"] = str(self.status)
        return out


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: Status | str
    critical: bool
    n_pass: int
    n_warning: int
    n_fail: int
    n_inconclusive: int
    headline: str
    blocking_reason: str = ""

    def to_dict(self) -> dict:
        out = asdict(self)
        out["status"] = str(self.status)
        return out


def _finite_number(value) -> bool:
    if value is None:
        return False
    try:
        return bool(isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def classify_abs(value: float | None, pass_max: float, warning_max: float | None = None) -> Status:
    """Classify an absolute discrepancy against pass and warning bounds."""
    if not _finite_number(value):
        return Status.INCONCLUSIVE
    value = abs(float(value))
    if value <= pass_max:
        return Status.PASS
    if warning_max is None:
        warning_max = pass_max * 2
    if value <= warning_max:
        return Status.WARNING
    return Status.FAIL


def classify_upper(value: float | None, pass_max: float, warning_max: float | None = None) -> Status:
    if not _finite_number(value):
        return Status.INCONCLUSIVE
    if float(value) <= pass_max:
        return Status.PASS
    if warning_max is None:
        warning_max = pass_max * 2
    return Status.WARNING if float(value) <= warning_max else Status.FAIL


def classify_range(value: float | None, pass_min: float, pass_max: float) -> Status:
    if not _finite_number(value):
        return Status.INCONCLUSIVE
    value = float(value)
    return Status.PASS if pass_min <= value <= pass_max else Status.FAIL


def classify_invariant(ok: bool | np.bool_) -> Status:
    return Status.PASS if bool(ok) else Status.FAIL


def metric_frame(metrics: list[MetricResult]) -> pd.DataFrame:
    if not metrics:
        return pd.DataFrame(columns=LONG_METRIC_COLUMNS)
    return pd.DataFrame([m.to_dict() for m in metrics])[LONG_METRIC_COLUMNS]


def gate_frame(gates: list[GateResult]) -> pd.DataFrame:
    if not gates:
        return pd.DataFrame(columns=GATE_COLUMNS)
    return pd.DataFrame([g.to_dict() for g in gates])[GATE_COLUMNS]
