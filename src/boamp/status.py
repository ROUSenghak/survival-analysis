"""Canonical project status constants and scientific gate checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


UNKNOWN_REAL_PRECISION_RECALL = "UNKNOWN_REAL_PRECISION_RECALL"
INITIAL_MANUAL_AUDIT_DIAGNOSTIC_AVAILABLE = "INITIAL_MANUAL_AUDIT_DIAGNOSTIC_AVAILABLE"
NOT_SUPPORTED_BY_STRATIFIED_AUDIT_DESIGN = "NOT_SUPPORTED_BY_STRATIFIED_AUDIT_DESIGN"
BLOCKED_BY_MANUAL_AUDIT = "BLOCKED_BY_MANUAL_AUDIT"
BLOCKED_BY_EXTERNAL_CLASSIFICATION = "BLOCKED_BY_EXTERNAL_CLASSIFICATION"
PROVISIONAL_LINKAGE_OUTPUT = "PROVISIONAL_LINKAGE_OUTPUT"
UNCLASSIFIED = "UNCLASSIFIED"

MANUAL_AUDIT_LABELS = {
    "CORRECT_LINK",
    "WRONG_LINK",
    "MISSED_LINK",
    "CORRECT_REJECTION",
    "INSUFFICIENT_INFORMATION",
}


class ScientificGateError(RuntimeError):
    """Raised when a requested downstream analysis crosses a project gate."""


@dataclass(frozen=True)
class GateStatus:
    status: str
    reason: str
    path: str | None = None


def _read_if_present(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path)


def manual_audit_status(path: Path) -> GateStatus:
    """Return whether real manual audit labels exist and are usable."""
    df = _read_if_present(path)
    if df is None:
        return GateStatus(
            BLOCKED_BY_MANUAL_AUDIT,
            "manual audit label file is absent",
            str(path),
        )
    if "reviewer_label" not in df.columns:
        return GateStatus(
            BLOCKED_BY_MANUAL_AUDIT,
            "manual audit file has no reviewer_label column",
            str(path),
        )
    labels = df["reviewer_label"].dropna().astype(str).str.strip()
    labels = labels[labels.ne("")]
    if labels.empty:
        return GateStatus(
            BLOCKED_BY_MANUAL_AUDIT,
            "manual audit labels are blank",
            str(path),
        )
    unknown = sorted(set(labels) - MANUAL_AUDIT_LABELS)
    if unknown:
        return GateStatus(
            BLOCKED_BY_MANUAL_AUDIT,
            f"manual audit contains unknown labels: {unknown}",
            str(path),
        )
    return GateStatus("PASS", f"{len(labels)} manual labels present", str(path))


def require_manual_audit_labels(path: Path) -> None:
    status = manual_audit_status(path)
    if status.status != "PASS":
        raise ScientificGateError(status.reason)


def classification_export_status(path: Path) -> GateStatus:
    """Return whether the teammate classification export is available."""
    if not path.exists():
        return GateStatus(
            BLOCKED_BY_EXTERNAL_CLASSIFICATION,
            "external technological classification export is absent",
            str(path),
        )
    return GateStatus("PASS", "external technological classification export is present", str(path))


def require_classification_export(path: Path) -> None:
    status = classification_export_status(path)
    if status.status != "PASS":
        raise ScientificGateError(status.reason)


def require_final_event_dataset_gate(manual_audit_path: Path) -> None:
    """Final event/censoring datasets require completed real audit labels."""
    require_manual_audit_labels(manual_audit_path)


def require_technology_specific_gate(classification_export_path: Path) -> None:
    """Technology-specific survival/trend analyses require the external export."""
    require_classification_export(classification_export_path)
