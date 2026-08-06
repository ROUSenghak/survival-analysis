"""Validation and merge helpers for the external technology classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd

from boamp.status import UNCLASSIFIED


REQUIRED_CLASSIFICATION_COLUMNS = [
    "notice_id",
    "technology_label",
    "prediction_confidence",
    "low_confidence_flag",
    "classification_source",
    "taxonomy_version",
    "model_version",
    "classification_date",
]

LEAKAGE_FIELD_PATTERNS = (
    "event",
    "renewal",
    "successor",
    "linked_candidate",
    "ground_truth",
    "true_relation",
    "manual_label",
    "reviewer_label",
)


@dataclass(frozen=True)
class ClassificationValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    n_rows: int
    n_unique_notice_ids: int


def load_classification_export(path: Path) -> pd.DataFrame:
    """Load a CSV or Parquet classification export."""
    if not path.exists():
        raise FileNotFoundError(f"classification export not found: {path}")
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    return pd.read_csv(path)


def validate_classification_export(
    df: pd.DataFrame,
    *,
    allowed_labels: set[str] | None = None,
) -> ClassificationValidationResult:
    """Validate the teammate-owned classification export.

    This function does not train, infer, or repair labels. It only checks that a
    provided export is safe to merge onto BOAMP notices.
    """
    errors: list[str] = []
    warnings: list[str] = []

    missing = [c for c in REQUIRED_CLASSIFICATION_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"missing required columns: {missing}")

    leakage_cols = [
        c for c in df.columns
        if any(pattern in c.lower() for pattern in LEAKAGE_FIELD_PATTERNS)
    ]
    if leakage_cols:
        errors.append(f"possible outcome-leakage columns present: {leakage_cols}")

    if "notice_id" in df.columns:
        ids = df["notice_id"].astype(str).str.strip()
        if ids.eq("").any() or df["notice_id"].isna().any():
            errors.append("notice_id contains missing or empty values")
        invalid_format = ids[~ids.map(_looks_like_notice_id)]
        if len(invalid_format):
            examples = invalid_format.head(5).tolist()
            warnings.append(f"notice_id has unusual format examples: {examples}")
        dupes = ids[ids.duplicated(keep=False)]
        if len(dupes):
            errors.append(f"duplicate notice_id values: {dupes.nunique()}")
        n_unique = int(ids.nunique())
    else:
        n_unique = 0

    if "technology_label" in df.columns:
        labels = df["technology_label"].astype(str).str.strip()
        if labels.eq("").any() or df["technology_label"].isna().any():
            errors.append("technology_label contains missing or empty values")
        if allowed_labels is not None:
            unknown = sorted(set(labels) - set(allowed_labels))
            if unknown:
                errors.append(f"unknown technology labels: {unknown[:20]}")

    if "prediction_confidence" in df.columns:
        conf = pd.to_numeric(df["prediction_confidence"], errors="coerce")
        if conf.isna().any():
            errors.append("prediction_confidence contains non-numeric values")
        elif (~conf.between(0, 1)).any():
            errors.append("prediction_confidence must be between 0 and 1")

    if "low_confidence_flag" in df.columns:
        vals = set(df["low_confidence_flag"].dropna().astype(str).str.lower())
        allowed_boolish = {"true", "false", "0", "1", "yes", "no"}
        unknown = vals - allowed_boolish
        if unknown:
            errors.append(f"low_confidence_flag contains non-boolean values: {sorted(unknown)}")

    for col in ["classification_source", "taxonomy_version", "model_version"]:
        if col in df.columns:
            values = df[col].astype(str).str.strip()
            if values.eq("").any() or df[col].isna().any():
                errors.append(f"{col} contains missing or empty values")

    if "classification_date" in df.columns:
        dates = pd.to_datetime(df["classification_date"], errors="coerce")
        if dates.isna().any():
            errors.append("classification_date contains unparsable values")

    return ClassificationValidationResult(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        n_rows=int(len(df)),
        n_unique_notice_ids=n_unique,
    )


def merge_classification(
    notices: pd.DataFrame,
    classification: pd.DataFrame,
    *,
    allowed_labels: set[str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Validate and left-merge classifications onto notice-level data."""
    result = validate_classification_export(classification, allowed_labels=allowed_labels)
    if not result.valid:
        raise ValueError("; ".join(result.errors))
    if "notice_id" not in notices.columns:
        raise KeyError("notices must contain notice_id")

    cls = classification[REQUIRED_CLASSIFICATION_COLUMNS].copy()
    cls["notice_id"] = cls["notice_id"].astype(str).str.strip()
    base = notices.copy()
    base["notice_id"] = base["notice_id"].astype(str).str.strip()
    before = len(base)
    merged = base.merge(cls, on="notice_id", how="left", validate="many_to_one")
    if len(merged) != before:
        raise RuntimeError("classification merge changed row count")

    unmatched = merged["technology_label"].isna()
    for col in REQUIRED_CLASSIFICATION_COLUMNS:
        if col == "notice_id":
            continue
        if col == "technology_label":
            merged.loc[unmatched, col] = UNCLASSIFIED
        elif col == "low_confidence_flag":
            merged.loc[unmatched, col] = True
        else:
            merged.loc[unmatched, col] = pd.NA

    report = {
        "n_notices": int(before),
        "n_classified_rows": int(len(classification)),
        "n_matched": int((~unmatched).sum()),
        "n_unmatched": int(unmatched.sum()),
        "merge_coverage": float((~unmatched).mean()) if before else 0.0,
        "validation_warnings": list(result.warnings),
    }
    return merged, report


def _looks_like_notice_id(value: str) -> bool:
    """Accept common BOAMP IDs while warning on obviously malformed values."""
    if not value or value.lower() == "nan":
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_.:/-]{3,80}", value))
