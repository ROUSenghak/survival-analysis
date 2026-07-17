"""Layer 2 (enriched) buyer identity - external SIREN enrichment + alias bridge.

Extracted from scripts/build_m1_buyer_siren_experiment.py (lines ~89-557),
logic unchanged except:
  - all constants come from cfg.pipeline.enrichment;
  - the dead `if False` scaffolding in the original build_diagnostics is not
    carried over;
  - clean_siren / clean_siret moved here (candidates for utils.identifiers).

Enrichment source: offline exact join (validate=one_to_one on notice_id/idweb)
against the pinned Hugging Face Parquet files - NOT fuzzy matching. The
internal alias bridge then propagates a SIREN to historical notices only when
an exact (normalized name, department) group maps to exactly one SIREN, is
not a generic name, and has support >= min_support. All provenance and
conflict columns are preserved; BOAMP-native identifiers are never
overwritten.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from utils.identifiers import normalize_buyer_name, siren_from_siret, validate_siren, validate_siret

ENRICHMENT_COLUMNS = [
    "B_04_codeDepartement",
    "B_09_dateParution",
    "B_17_idweb",
    "B_20_nature",
    "B_24_nomAcheteur",
    "B_38_urlAvis",
    "B_46_NUM_SIRET_ACHETEURS_RECUP",
    "B_47_NOM_SIRET_ACHETEURS_RECUP",
    "B_48_NOM_CAT_JUR_ACHETEUR",
    "SN_06_categorieJuridiqueUniteLegale",
    "SN_10_denominationUniteLegale",
    "SN_15_etatAdministratifUniteLegale",
    "SN_18_nomUniteLegale",
    "SN_29_sigleUniteLegale",
    "SN_30_siren",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_clean_token(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    for part in str(value).split(";"):
        digits = re.sub(r"\D", "", part)
        if digits:
            return digits
    return None


def clean_siren(value) -> str | None:
    digits = first_clean_token(value)
    if digits and len(digits) == 9:
        return digits
    if digits and len(digits) == 14:
        return digits[:9]
    return None


def clean_siret(value) -> str | None:
    digits = first_clean_token(value)
    if digits and len(digits) == 14:
        return digits
    return None


def first_nonempty(*values) -> str | None:
    for value in values:
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def dept_key(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    tokens = sorted(set(re.findall(r"\b\d{2}\b", str(value))))
    return ";".join(tokens) if tokens else None


def parse_date_series(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce")
    missing = parsed.isna()
    if missing.any():
        numeric = pd.to_numeric(values[missing], errors="coerce")
        numeric_mask = numeric.notna()
        if numeric_mask.any():
            parsed.loc[numeric[numeric_mask].index] = pd.to_datetime(
                numeric[numeric_mask], errors="coerce", unit="ns"
            )
    return parsed


def is_generic_alias(name: str | None, cfg) -> bool:
    if not name:
        return True
    compact = name.strip()
    if len(compact) < cfg.pipeline.enrichment.alias_bridge.min_name_length:
        return True
    return compact in set(cfg.pipeline.enrichment.alias_bridge.generic_names)


# ---------------------------------------------------------------------------
# Part E: load + audit the external enrichment files
# ---------------------------------------------------------------------------

def load_enrichment(cfg) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read the pinned enrichment Parquets. Returns (enrichment, audit, fields)."""
    raw_dir = cfg.paths.raw_enrichment_dir
    project_root = cfg.project_root
    files = sorted(raw_dir.glob(cfg.pipeline.enrichment.file_glob))
    if not files:
        raise FileNotFoundError(
            f"No enrichment Parquet files matching {cfg.pipeline.enrichment.file_glob} in {raw_dir}. "
            "Run boamp.data.download_enrichment.download_enrichment(cfg) first."
        )

    audit_rows, schema_rows, frames = [], [], []
    for path in files:
        year_match = re.search(r"(20\d{2})", path.name)
        year = year_match.group(1) if year_match else None
        pf = pq.ParquetFile(path)
        frame = pd.read_parquet(path, columns=ENRICHMENT_COLUMNS)
        frame["enrichment_file"] = str(path.relative_to(project_root))
        frame["enrichment_year_file"] = year
        frames.append(frame)

        ids = frame["B_17_idweb"].astype("string")
        siren = frame["SN_30_siren"].astype("string")
        siret = frame["B_46_NUM_SIRET_ACHETEURS_RECUP"].astype("string")
        dates = pd.to_datetime(frame["B_09_dateParution"], errors="coerce")
        id_counts = ids.dropna().value_counts()
        audit_rows.append({
            "file": str(path.relative_to(project_root)),
            "year_in_filename": year,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "parquet_rows": pf.metadata.num_rows,
            "read_rows": len(frame),
            "columns": len(pf.schema_arrow.names),
            "date_min": str(dates.min().date()) if dates.notna().any() else None,
            "date_max": str(dates.max().date()) if dates.notna().any() else None,
            "missing_notice_id_count": int(ids.isna().sum()),
            "missing_notice_id_rate": float(ids.isna().mean()),
            "distinct_notice_ids": int(ids.dropna().nunique()),
            "duplicate_notice_id_rows": int(ids.dropna().duplicated().sum()),
            "notice_ids_with_multiple_rows": int((id_counts > 1).sum()),
            "missing_siren_count": int((siren.isna() | (siren.str.strip() == "")).sum()),
            "missing_siren_rate": float((siren.isna() | (siren.str.strip() == "")).mean()),
            "missing_recovered_siret_count": int((siret.isna() | (siret.str.strip() == "")).sum()),
            "missing_recovered_siret_rate": float((siret.isna() | (siret.str.strip() == "")).mean()),
            "join_key_recommendation": "B_17_idweb -> notice_id",
            "many_to_many_risk": "LOW" if ids.dropna().duplicated().sum() == 0 else "REQUIRES_DEDUPLICATION_BEFORE_MERGE",
        })
        for col in ENRICHMENT_COLUMNS:
            ser = frame[col].astype("string")
            non_null = ~ser.isna() & (ser.str.strip() != "")
            schema_rows.append({
                "file": str(path.relative_to(project_root)),
                "year_in_filename": year,
                "field": col,
                "non_null_count": int(non_null.sum()),
                "non_null_rate": float(non_null.mean()),
                "sample_values": " | ".join(ser[non_null].drop_duplicates().astype(str).str.slice(0, 80).head(3)),
            })

    enrichment = pd.concat(frames, ignore_index=True)
    enrichment = enrichment.rename(columns={
        "B_17_idweb": "notice_id",
        "B_09_dateParution": "enrichment_publication_date",
        "B_20_nature": "enrichment_notice_type",
        "B_24_nomAcheteur": "buyer_name_enrichment_raw",
        "B_04_codeDepartement": "enrichment_department_raw",
        "B_38_urlAvis": "enrichment_boamp_url",
        "B_46_NUM_SIRET_ACHETEURS_RECUP": "buyer_siret_enriched_raw",
        "B_47_NOM_SIRET_ACHETEURS_RECUP": "buyer_siret_name_enriched_raw",
        "B_48_NOM_CAT_JUR_ACHETEUR": "buyer_legal_category_enriched",
        "SN_06_categorieJuridiqueUniteLegale": "buyer_legal_category_sirene",
        "SN_10_denominationUniteLegale": "buyer_legal_name_enriched",
        "SN_15_etatAdministratifUniteLegale": "buyer_legal_status_enriched",
        "SN_18_nomUniteLegale": "buyer_legal_person_name_enriched",
        "SN_29_sigleUniteLegale": "buyer_sigle_enriched",
        "SN_30_siren": "buyer_siren_enriched_raw",
    })
    enrichment["buyer_siren_enriched"] = enrichment["buyer_siren_enriched_raw"].map(clean_siren)
    enrichment["buyer_siret_enriched_clean"] = enrichment["buyer_siret_enriched_raw"].map(clean_siret)
    siren_checks = enrichment["buyer_siren_enriched"].map(validate_siren)
    enrichment["buyer_siren_enriched_format_valid"] = siren_checks.map(lambda x: x[0])
    enrichment["buyer_siren_enriched_checksum_valid"] = siren_checks.map(lambda x: x[1])
    enrichment["buyer_siren_enriched_valid"] = (
        enrichment["buyer_siren_enriched_format_valid"] & enrichment["buyer_siren_enriched_checksum_valid"]
    )
    enrichment["buyer_legal_name_enriched_display"] = enrichment.apply(
        lambda r: first_nonempty(
            r["buyer_legal_name_enriched"],
            r["buyer_legal_person_name_enriched"],
            r["buyer_sigle_enriched"],
            r["buyer_siret_name_enriched_raw"],
        ),
        axis=1,
    )
    enrichment["buyer_name_enrichment_normalized"] = enrichment["buyer_name_enrichment_raw"].map(normalize_buyer_name)
    enrichment["enrichment_department_key"] = enrichment["enrichment_department_raw"].map(dept_key)

    return enrichment, pd.DataFrame(audit_rows), pd.DataFrame(schema_rows)


def enrich_clean_notices(clean: pd.DataFrame, enrichment: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Exact one-to-one join of the cleaned corpus to the enrichment table.

    Returns (enriched_clean, conflicts). BOAMP-native identifiers are kept in
    their own columns; conflicts (BOAMP-SIRET-derived SIREN != enriched SIREN)
    are flagged, never silently resolved.
    """
    if enrichment["notice_id"].duplicated().any():
        raise ValueError("Refusing many-to-many enrichment merge: duplicate B_17_idweb values exist.")

    enriched = clean.merge(
        enrichment, on="notice_id", how="left", validate="one_to_one", suffixes=("", "_enrichment"),
    )
    enriched["enrichment_join_status"] = np.where(
        enriched["buyer_siren_enriched_raw"].notna(), "JOINED", "NOT_IN_ENRICHMENT"
    )
    enriched["buyer_key_m0"] = enriched["buyer_key"]
    enriched["buyer_siret_boamp_raw"] = enriched["buyer_siret_raw"]
    enriched["buyer_siren_from_boamp_siret"] = enriched["buyer_siret_clean"].map(
        lambda v: siren_from_siret(v) if pd.notna(v) and validate_siret(v)[0] else None
    )
    enriched["buyer_siren_boamp_effective"] = enriched["buyer_siren_clean"].where(
        enriched["buyer_siren_clean"].notna(), enriched["buyer_siren_from_boamp_siret"],
    )
    enriched["buyer_identity_conflict"] = (
        enriched["buyer_siren_from_boamp_siret"].notna()
        & enriched["buyer_siren_enriched_valid"].fillna(False)
        & (enriched["buyer_siren_from_boamp_siret"] != enriched["buyer_siren_enriched"])
    )
    enriched["buyer_siren_agrees_with_boamp_siret"] = (
        enriched["buyer_siren_from_boamp_siret"].notna()
        & enriched["buyer_siren_enriched_valid"].fillna(False)
        & (enriched["buyer_siren_from_boamp_siret"] == enriched["buyer_siren_enriched"])
    )

    def direct_identity_source(row):
        if pd.notna(row["buyer_siret_clean"]):
            if row["buyer_siren_agrees_with_boamp_siret"]:
                return "BOAMP_SIRET_CORROBORATED_BY_ENRICHED_SIREN"
            if row["buyer_identity_conflict"]:
                return "BOAMP_SIRET_WITH_ENRICHED_SIREN_CONFLICT"
            return "DIRECT_BOAMP_SIRET"
        if row["buyer_siren_enriched_valid"] and pd.notna(row["buyer_siren_enriched"]):
            return "DIRECT_ENRICHMENT_NOTICE_JOIN"
        if pd.notna(row["buyer_siren_clean"]):
            return "DIRECT_BOAMP_SIREN"
        if pd.notna(row["buyer_name_normalized"]):
            return "NAME_FALLBACK"
        return "MISSING"

    enriched["buyer_identity_source_direct"] = enriched.apply(direct_identity_source, axis=1)
    enriched["buyer_identity_confidence_direct"] = np.select(
        [
            enriched["buyer_identity_source_direct"].isin([
                "BOAMP_SIRET_CORROBORATED_BY_ENRICHED_SIREN", "DIRECT_BOAMP_SIRET",
            ]),
            enriched["buyer_identity_source_direct"].eq("DIRECT_ENRICHMENT_NOTICE_JOIN"),
            enriched["buyer_identity_source_direct"].eq("DIRECT_BOAMP_SIREN"),
            enriched["buyer_identity_source_direct"].eq("BOAMP_SIRET_WITH_ENRICHED_SIREN_CONFLICT"),
            enriched["buyer_identity_source_direct"].eq("NAME_FALLBACK"),
        ],
        ["HIGH", "MEDIUM_HIGH", "MEDIUM", "CONFLICT", "LOW"],
        default="MISSING",
    )

    conflicts = enriched.loc[enriched["buyer_identity_conflict"].fillna(False), [
        "notice_id", "publication_date", "notice_type_normalized",
        "buyer_name_raw", "buyer_name_normalized", "buyer_legal_name_enriched_display",
        "buyer_siret_raw", "buyer_siret_clean", "buyer_siren_from_boamp_siret",
        "buyer_siren_enriched", "buyer_siren_enriched_raw",
        "code_departement", "enrichment_department_raw",
        "url_avis", "enrichment_boamp_url",
        "buyer_legal_category_enriched", "buyer_legal_category_sirene", "buyer_legal_status_enriched",
    ]].copy()
    return enriched, conflicts


def build_alias_bridge(enriched_clean: pd.DataFrame, cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Exact (normalized name, department) alias bridge from direct-enriched rows.

    A SIREN is auto-propagatable only when the group is unambiguous (exactly
    one SIREN), conflict-free, non-generic, and has support >= min_support.
    Everything else is exported as review-only.
    """
    min_support = cfg.pipeline.enrichment.alias_bridge.min_support
    direct = enriched_clean[
        enriched_clean["buyer_siren_enriched_valid"].fillna(False)
        & enriched_clean["buyer_siren_enriched"].notna()
        & ~enriched_clean["buyer_identity_conflict"].fillna(False)
    ].copy()
    direct["alias_name_normalized"] = direct["buyer_name_normalized"].where(
        direct["buyer_name_normalized"].notna(), direct["buyer_name_enrichment_normalized"],
    )
    direct["alias_department_key"] = direct["code_departement"].map(dept_key).where(
        direct["code_departement"].notna(), direct["enrichment_department_key"],
    )
    direct = direct[direct["alias_name_normalized"].notna()].copy()

    rows = []
    for (name, dept), grp in direct.groupby(["alias_name_normalized", "alias_department_key"], dropna=False):
        sirens = sorted(grp["buyer_siren_enriched"].dropna().unique())
        raw_names = sorted(set(grp["buyer_name_raw"].dropna().astype(str).head(20)))
        legal_names = sorted(set(grp["buyer_legal_name_enriched_display"].dropna().astype(str).head(20)))
        support = len(grp)
        boamp_siret_conflicts = int(grp["buyer_identity_conflict"].fillna(False).sum())
        generic = is_generic_alias(name, cfg)
        if len(sirens) != 1:
            status = "AMBIGUOUS_MULTIPLE_SIREN"
        elif boamp_siret_conflicts:
            status = "CONFLICT_WITH_BOAMP_SIRET"
        elif generic:
            status = "GENERIC_ALIAS_REVIEW_ONLY"
        elif support < min_support:
            status = "LOW_SUPPORT_REVIEW_ONLY"
        else:
            status = "AUTO_PROPAGATE_ELIGIBLE"
        rows.append({
            "alias_name_normalized": name,
            "department_key": dept,
            "raw_buyer_name_variants": " || ".join(raw_names),
            "legal_name_variants": " || ".join(legal_names),
            "siren": sirens[0] if len(sirens) == 1 else None,
            "distinct_siren_count": len(sirens),
            "all_sirens": ";".join(sirens),
            "support_notice_count": support,
            "first_observation_date": grp["publication_date"].min(),
            "last_observation_date": grp["publication_date"].max(),
            "confidence_status": status,
            "ambiguity_reason": "" if status == "AUTO_PROPAGATE_ELIGIBLE" else status,
            "generic_alias_flag": generic,
        })

    bridge = pd.DataFrame(rows).sort_values(
        ["confidence_status", "support_notice_count", "alias_name_normalized"],
        ascending=[True, False, True],
    )
    ambiguous = bridge[bridge["confidence_status"] != "AUTO_PROPAGATE_ELIGIBLE"].copy()
    return bridge, ambiguous


def apply_enriched_identity(sources: pd.DataFrame, enriched_clean: pd.DataFrame,
                            bridge: pd.DataFrame, cfg) -> pd.DataFrame:
    """Attach the Layer 2 identity columns to the SAME source population.

    Renamed from the legacy apply_m1_identity. Output keeps every Layer 1
    column plus: buyer_siren_l2 (final Layer 2 SIREN), buyer_key_l2 (final
    Layer 2 blocking key), buyer_identity_source, buyer_identity_confidence,
    conflict/agreement flags, and enrichment join status.
    """
    hist_max_year = cfg.pipeline.enrichment.alias_bridge.historical_max_year

    m1 = sources.copy()
    for date_col in ["publication_date", "start_date", "estimated_end_date", "study_end_date"]:
        m1[date_col] = parse_date_series(m1[date_col])

    extras = enriched_clean[[
        "notice_id",
        "buyer_key_m0",
        "buyer_siret_boamp_raw",
        "buyer_siren_from_boamp_siret",
        "buyer_siren_boamp_effective",
        "buyer_siren_enriched",
        "buyer_siren_enriched_valid",
        "buyer_legal_name_enriched_display",
        "buyer_identity_source_direct",
        "buyer_identity_confidence_direct",
        "buyer_identity_conflict",
        "buyer_siren_agrees_with_boamp_siret",
        "enrichment_join_status",
    ]]
    m1 = m1.merge(extras, on="notice_id", how="left", validate="one_to_one")

    eligible_bridge = bridge[bridge["confidence_status"] == "AUTO_PROPAGATE_ELIGIBLE"][
        ["alias_name_normalized", "department_key", "siren", "support_notice_count"]
    ].rename(columns={"siren": "buyer_siren_alias", "support_notice_count": "buyer_alias_support_notice_count"})
    m1["department_key"] = m1["code_departement"].map(dept_key)
    m1 = m1.merge(
        eligible_bridge,
        left_on=["buyer_name_normalized", "department_key"],
        right_on=["alias_name_normalized", "department_key"],
        how="left",
        validate="many_to_one",
    )
    historical_mask = (
        m1["publication_date"].dt.year.le(hist_max_year)
        & m1["buyer_siren_alias"].notna()
        & m1["buyer_siret_clean"].isna()
        & m1["buyer_siren_clean"].isna()
    )

    m1["buyer_siren_l2"] = m1["buyer_siren_boamp_effective"]
    direct_enriched_mask = (
        m1["buyer_siren_l2"].isna()
        & m1["buyer_siren_enriched_valid"].fillna(False)
        & ~m1["buyer_identity_conflict"].fillna(False)
    )
    m1.loc[direct_enriched_mask, "buyer_siren_l2"] = m1.loc[direct_enriched_mask, "buyer_siren_enriched"]
    m1.loc[historical_mask & m1["buyer_siren_l2"].isna(), "buyer_siren_l2"] = m1.loc[
        historical_mask & m1["buyer_siren_l2"].isna(), "buyer_siren_alias"
    ]

    def final_source(row):
        if pd.notna(row["buyer_siret_clean"]):
            if bool(row.get("buyer_identity_conflict", False)):
                return "DIRECT_BOAMP_SIRET_CONFLICT_FLAGGED"
            return "DIRECT_BOAMP_SIRET"
        if pd.notna(row["buyer_siren_clean"]):
            return "DIRECT_BOAMP_SIREN"
        if bool(row.get("buyer_siren_enriched_valid", False)) and pd.notna(row["buyer_siren_enriched"]) and not bool(row.get("buyer_identity_conflict", False)):
            return "DIRECT_ENRICHMENT_NOTICE_JOIN"
        if pd.notna(row["buyer_siren_alias"]) and row["publication_date"].year <= hist_max_year:
            return "UNIQUE_NAME_DEPARTMENT_ALIAS"
        if bool(row.get("buyer_identity_conflict", False)):
            return "CONFLICT_UNRESOLVED"
        if pd.notna(row["buyer_name_normalized"]):
            return "NAME_FALLBACK"
        return "MISSING"

    m1["buyer_identity_source"] = m1.apply(final_source, axis=1)
    m1["buyer_identity_confidence"] = np.select(
        [
            m1["buyer_identity_source"].isin(["DIRECT_BOAMP_SIRET", "DIRECT_BOAMP_SIRET_CONFLICT_FLAGGED"]),
            m1["buyer_identity_source"].eq("DIRECT_ENRICHMENT_NOTICE_JOIN"),
            m1["buyer_identity_source"].eq("DIRECT_BOAMP_SIREN"),
            m1["buyer_identity_source"].eq("UNIQUE_NAME_DEPARTMENT_ALIAS"),
            m1["buyer_identity_source"].eq("CONFLICT_UNRESOLVED"),
            m1["buyer_identity_source"].eq("NAME_FALLBACK"),
        ],
        ["HIGH", "MEDIUM_HIGH", "MEDIUM", "MEDIUM_LOW", "CONFLICT", "LOW"],
        default="MISSING",
    )
    m1["buyer_key_l2"] = np.select(
        [
            m1["buyer_siret_clean"].notna(),
            m1["buyer_siren_l2"].notna(),
            m1["buyer_name_normalized"].notna(),
        ],
        [
            "SIRET:" + m1["buyer_siret_clean"].fillna(""),
            "SIREN:" + m1["buyer_siren_l2"].fillna(""),
            "NAME:" + m1["buyer_name_normalized"].fillna(""),
        ],
        default=None,
    )
    return m1


def merge_split_summary(l2_sources: pd.DataFrame) -> pd.DataFrame:
    """Buyer merges/splits introduced by enrichment (Layer 1 key vs Layer 2 key)."""
    g = l2_sources.groupby("buyer_key_l2")["buyer_key"].nunique()
    merges = g[g > 1]
    g2 = l2_sources.groupby("buyer_key")["buyer_key_l2"].nunique()
    splits = g2[g2 > 1]
    return pd.DataFrame([{
        "n_l2_keys": int(l2_sources["buyer_key_l2"].nunique()),
        "n_l1_keys": int(l2_sources["buyer_key"].nunique()),
        "n_l2_keys_merging_multiple_l1_keys": int(len(merges)),
        "max_l1_keys_merged_into_one_l2_key": int(g.max()) if len(g) else 0,
        "n_l1_keys_split_across_l2_keys": int(len(splits)),
    }])
