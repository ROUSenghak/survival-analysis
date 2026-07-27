"""Column schemas for every synthetic-benchmark v0.1 table.

Single source of truth for expected column names, used by both the
generator (every writer conforms to these) and by tests/validation.py (so a
silently renamed or dropped column fails loudly instead of passing by
accident). Deliberately does not enforce exact pandas dtypes beyond a light
sanity check — Parquet round-trips can shift nullable-int/float
representations across pandas/pyarrow versions, and pinning dtypes exactly
would make the schema brittle for no real benefit here.
"""
from __future__ import annotations

import re

import pandas as pd

LATENT_BUYERS: tuple[str, ...] = (
    "buyer_id_true", "siren_true", "department_true", "buyer_type_true",
    "activity_rate", "activity_tier", "active_start", "active_end",
    "alias_propensity", "identifier_quality_propensity",
)

LATENT_ESTABLISHMENTS: tuple[str, ...] = (
    "establishment_id_true", "buyer_id_true", "siren_true", "siret_true",
    "department_true", "active_start", "active_end",
)

LATENT_NEEDS: tuple[str, ...] = (
    "need_id_true", "buyer_id_true", "establishment_id_true", "segment_true",
    "cpv_true", "base_concepts", "base_vocabulary", "duration_profile_months",
    "recurrence_propensity",
)

LATENT_CYCLES: tuple[str, ...] = (
    "cycle_id_true", "need_id_true", "buyer_id_true", "cycle_number",
    "start_date_true", "duration_true_months", "expected_end_true", "scenario",
)

TRUE_RELATIONS: tuple[str, ...] = (
    "source_cycle_id", "target_cycle_id", "relation_type", "strict_label",
    "broad_label", "true_gap_months", "source_expected_end", "target_start",
    "scenario",
)

NOTICE_FAMILY_MEMBERSHIP: tuple[str, ...] = (
    "notice_id_synthetic", "cycle_id_true", "role",
)

CLEAN_NOTICES: tuple[str, ...] = (
    "notice_id_synthetic", "cycle_id_true", "need_id_true", "buyer_id_true",
    "establishment_id_true", "role", "publication_date_true",
    "notice_type_true", "schema_family_true", "siret_true", "siren_true",
    "buyer_name_true", "department_true", "cpv_true", "duration_true_months",
    "objet_true", "linked_call_notice_id_true",
)

# Truth columns that must NEVER appear in observed_notices.parquet (spec
# Phase 7: "Truth columns must not appear in observed_notices.parquet").
CLEAN_NOTICES_TRUTH_ONLY: tuple[str, ...] = (
    "cycle_id_true", "need_id_true", "buyer_id_true", "establishment_id_true",
    "siret_true", "siren_true", "buyer_name_true", "cpv_true",
    "duration_true_months", "objet_true", "linked_call_notice_id_true",
)

OBSERVED_NOTICES: tuple[str, ...] = (
    "notice_id_synthetic", "publication_date", "notice_type_normalized",
    "schema_family", "buyer_siret_raw", "buyer_siren_raw", "buyer_name_raw",
    "code_departement", "cpv_clean", "declared_duration_months", "objet_clean",
    "linked_call_notice_id",
)

CORRUPTION_LOG: tuple[str, ...] = (
    "notice_id_synthetic", "field", "clean_value", "observed_value",
    "corruption_type", "scenario", "severity", "seed",
)

OBSERVED_FORBIDDEN_TRUTH_ALIASES: tuple[str, ...] = (
    "cycle_id",
    "need_id",
    "buyer_id",
    "establishment_id",
    "contract_family_id",
    "family_id",
    "source_cycle_id",
    "target_cycle_id",
    "successor_cycle_id",
    "predecessor_cycle_id",
    "relation_type",
    "strict_label",
    "broad_label",
    "true_gap_months",
    "source_expected_end",
    "target_start",
    "corruption_type",
    "corruption_history",
    "quality_class",
    "scenario_label",
)


def _column_signature(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def validate_columns(df: pd.DataFrame, schema: tuple[str, ...], table_name: str) -> None:
    """Raise ValueError if df is missing any column required by schema."""
    missing = [c for c in schema if c not in df.columns]
    if missing:
        raise ValueError(f"{table_name}: missing required columns {missing}")


def assert_no_truth_leakage(observed: pd.DataFrame) -> None:
    """observed_notices must not carry truth columns or hidden-label aliases."""
    forbidden_aliases = {_column_signature(c) for c in OBSERVED_FORBIDDEN_TRUTH_ALIASES}
    leaked = [
        c
        for c in observed.columns
        if c.endswith("_true") or _column_signature(c) in forbidden_aliases
    ]
    if leaked:
        raise ValueError(f"observed_notices leaks truth columns: {leaked}")
