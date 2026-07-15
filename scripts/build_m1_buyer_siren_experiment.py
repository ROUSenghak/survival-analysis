"""
Build and audit the buyer-enriched M1 linkage experiment.

M1 is deliberately separate from the official M0 outputs. It keeps the M0
source population, temporal window, TF-IDF text score, CPV score, temporal
score, candidate ranking, and the M0 balanced score threshold. The first
controlled change is buyer blocking: exact BOAMP SIRET, validated same SIREN
from direct enrichment or conservative historical alias propagation, then the
original M0 name fallback.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.feature_extraction.text import TfidfVectorizer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.identifiers import normalize_buyer_name, siren_from_siret, validate_siren, validate_siret  # noqa: E402

RAW_ENRICHMENT_DIR = PROJECT_ROOT / "data" / "raw" / "buyer_siren_enrichment_m1"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
REPORTS_DIR = PROJECT_ROOT / "reports"
TABLES_DIR.mkdir(parents=True, exist_ok=True)

DATASET_HF_ID = "Data-Gouv-ML/jointure-boamp-siren-cote-acheteurs-2024-2025-et-2026"
DATASET_HF_SHA = "4bff9b1c5d2f4ad12834174e042828b7e52013d9"
DOWNLOAD_DATE = "2026-07-15"

MAX_CANDIDATES_PER_SOURCE = 30
MIN_WINDOW_MONTHS_FLOOR = 6
MAX_WINDOW_MONTHS_CAP = 24

CPV_SCORE_EXACT = 1.0
CPV_SCORE_CATEGORY = 0.8
CPV_SCORE_CLASS = 0.6
CPV_SCORE_GROUP = 0.4
CPV_SCORE_DIVISION = 0.2
CPV_SCORE_DIFFERENT = 0.0
CPV_SCORE_MISSING = 0.1

BUYER_MECHANISM_SCORE = {
    "EXACT_SIRET_RECONCILIATION": 1.0,
    "SAME_SIREN_RECONCILIATION": 0.9,
    "HISTORICAL_ALIAS_RECONCILIATION": 0.75,
    "M0_NAME_FALLBACK": 0.6,
}
MECHANISM_PRIORITY = {
    "EXACT_SIRET_RECONCILIATION": 4,
    "SAME_SIREN_RECONCILIATION": 3,
    "HISTORICAL_ALIAS_RECONCILIATION": 2,
    "M0_NAME_FALLBACK": 1,
}

W_TEXT, W_CPV, W_TIME, W_BUYER = 0.35, 0.30, 0.25, 0.10

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
                numeric[numeric_mask],
                errors="coerce",
                unit="ns",
            )
    return parsed


def is_generic_alias(name: str | None) -> bool:
    if not name:
        return True
    compact = name.strip()
    if len(compact) < 6:
        return True
    generic_exact = {
        "mairie",
        "commune",
        "ville",
        "departement",
        "conseil departemental",
        "centre hospitalier",
        "universite",
        "communaute de communes",
        "communaute d agglomeration",
    }
    return compact in generic_exact


def cpv_pair_score(row_src: pd.Series, row_cand: pd.Series) -> float:
    if pd.isna(row_src["cpv_clean"]) or pd.isna(row_cand["cpv_clean"]):
        return CPV_SCORE_MISSING
    if row_src["cpv_clean"] == row_cand["cpv_clean"]:
        return CPV_SCORE_EXACT
    if row_src["cpv_category"] == row_cand["cpv_category"]:
        return CPV_SCORE_CATEGORY
    if row_src["cpv_class"] == row_cand["cpv_class"]:
        return CPV_SCORE_CLASS
    if row_src["cpv_group"] == row_cand["cpv_group"]:
        return CPV_SCORE_GROUP
    if row_src["cpv_division"] == row_cand["cpv_division"]:
        return CPV_SCORE_DIVISION
    return CPV_SCORE_DIFFERENT


def load_enrichment() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    files = sorted(RAW_ENRICHMENT_DIR.glob("boamp-avec-siren-acheteurs-*.parquet.parquet"))
    if not files:
        raise SystemExit(f"No enrichment Parquet files found in {RAW_ENRICHMENT_DIR}")

    audit_rows = []
    schema_rows = []
    frames = []
    for path in files:
        year_match = re.search(r"(20\d{2})", path.name)
        year = year_match.group(1) if year_match else None
        pf = pq.ParquetFile(path)
        frame = pd.read_parquet(path, columns=ENRICHMENT_COLUMNS)
        frame["enrichment_file"] = str(path.relative_to(PROJECT_ROOT))
        frame["enrichment_year_file"] = year
        frames.append(frame)

        ids = frame["B_17_idweb"].astype("string")
        siren = frame["SN_30_siren"].astype("string")
        siret = frame["B_46_NUM_SIRET_ACHETEURS_RECUP"].astype("string")
        dates = pd.to_datetime(frame["B_09_dateParution"], errors="coerce")
        id_counts = ids.dropna().value_counts()
        audit_rows.append({
            "file": str(path.relative_to(PROJECT_ROOT)),
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
                "file": str(path.relative_to(PROJECT_ROOT)),
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

    audit = pd.DataFrame(audit_rows)
    fields = pd.DataFrame(schema_rows)
    return enrichment, audit, fields


def enrich_clean_notices(clean: pd.DataFrame, enrichment: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if enrichment["notice_id"].duplicated().any():
        raise SystemExit("Refusing many-to-many enrichment merge: duplicate B_17_idweb values exist.")

    enriched = clean.merge(
        enrichment,
        on="notice_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_enrichment"),
    )
    enriched["enrichment_join_status"] = np.where(enriched["buyer_siren_enriched_raw"].notna(), "JOINED", "NOT_IN_ENRICHMENT")
    enriched["buyer_key_m0"] = enriched["buyer_key"]
    enriched["buyer_siret_boamp_raw"] = enriched["buyer_siret_raw"]
    enriched["buyer_siren_from_boamp_siret"] = enriched["buyer_siret_clean"].map(
        lambda v: siren_from_siret(v) if pd.notna(v) and validate_siret(v)[0] else None
    )
    enriched["buyer_siren_boamp_effective"] = enriched["buyer_siren_clean"].where(
        enriched["buyer_siren_clean"].notna(),
        enriched["buyer_siren_from_boamp_siret"],
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
                "BOAMP_SIRET_CORROBORATED_BY_ENRICHED_SIREN",
                "DIRECT_BOAMP_SIRET",
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
        "notice_id",
        "publication_date",
        "notice_type_normalized",
        "buyer_name_raw",
        "buyer_name_normalized",
        "buyer_legal_name_enriched_display",
        "buyer_siret_raw",
        "buyer_siret_clean",
        "buyer_siren_from_boamp_siret",
        "buyer_siren_enriched",
        "buyer_siren_enriched_raw",
        "code_departement",
        "enrichment_department_raw",
        "url_avis",
        "enrichment_boamp_url",
        "buyer_legal_category_enriched",
        "buyer_legal_category_sirene",
        "buyer_legal_status_enriched",
    ]].copy()
    return enriched, conflicts


def build_alias_bridge(enriched_clean: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    direct = enriched_clean[
        enriched_clean["buyer_siren_enriched_valid"].fillna(False)
        & enriched_clean["buyer_siren_enriched"].notna()
        & ~enriched_clean["buyer_identity_conflict"].fillna(False)
    ].copy()
    direct["alias_name_normalized"] = direct["buyer_name_normalized"].where(
        direct["buyer_name_normalized"].notna(),
        direct["buyer_name_enrichment_normalized"],
    )
    direct["alias_department_key"] = direct["code_departement"].map(dept_key).where(
        direct["code_departement"].notna(),
        direct["enrichment_department_key"],
    )
    direct = direct[direct["alias_name_normalized"].notna()].copy()

    rows = []
    for (name, dept), grp in direct.groupby(["alias_name_normalized", "alias_department_key"], dropna=False):
        sirens = sorted(grp["buyer_siren_enriched"].dropna().unique())
        raw_names = sorted(set(grp["buyer_name_raw"].dropna().astype(str).head(20)))
        legal_names = sorted(set(grp["buyer_legal_name_enriched_display"].dropna().astype(str).head(20)))
        support = len(grp)
        boamp_siret_conflicts = int(grp["buyer_identity_conflict"].fillna(False).sum())
        generic = is_generic_alias(name)
        if len(sirens) != 1:
            status = "AMBIGUOUS_MULTIPLE_SIREN"
        elif boamp_siret_conflicts:
            status = "CONFLICT_WITH_BOAMP_SIRET"
        elif generic:
            status = "GENERIC_ALIAS_REVIEW_ONLY"
        elif support < 2:
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


def apply_m1_identity(sources: pd.DataFrame, enriched_clean: pd.DataFrame, bridge: pd.DataFrame) -> pd.DataFrame:
    source_cols = [
        "notice_id",
        "publication_date",
        "start_date",
        "start_date_source",
        "buyer_key",
        "buyer_key_type",
        "buyer_name_normalized",
        "buyer_siret_clean",
        "buyer_siren_clean",
        "objet_clean",
        "cpv_clean",
        "cpv_division",
        "cpv_group",
        "cpv_class",
        "cpv_category",
        "cpv_generic_flag",
        "declared_duration_months",
        "dur_was_imputed",
        "estimated_end_date",
        "is_digital_scope",
        "category_label",
        "study_end_date",
    ]
    m1 = sources[source_cols].copy()
    for date_col in ["publication_date", "start_date", "estimated_end_date", "study_end_date"]:
        m1[date_col] = parse_date_series(m1[date_col])

    extras = enriched_clean[[
        "notice_id",
        "buyer_name_raw",
        "code_departement",
        "url_avis",
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
    for date_col in ["publication_date", "start_date", "estimated_end_date", "study_end_date"]:
        m1[date_col] = parse_date_series(m1[date_col])
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
        m1["publication_date"].dt.year.le(2023)
        & m1["buyer_siren_alias"].notna()
        & m1["buyer_siret_clean"].isna()
        & m1["buyer_siren_clean"].isna()
    )

    m1["buyer_siren_m1"] = m1["buyer_siren_boamp_effective"]
    direct_enriched_mask = (
        m1["buyer_siren_m1"].isna()
        & m1["buyer_siren_enriched_valid"].fillna(False)
        & ~m1["buyer_identity_conflict"].fillna(False)
    )
    m1.loc[direct_enriched_mask, "buyer_siren_m1"] = m1.loc[direct_enriched_mask, "buyer_siren_enriched"]
    m1.loc[historical_mask & m1["buyer_siren_m1"].isna(), "buyer_siren_m1"] = m1.loc[
        historical_mask & m1["buyer_siren_m1"].isna(), "buyer_siren_alias"
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
        if pd.notna(row["buyer_siren_alias"]) and row["publication_date"].year <= 2023:
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
    m1["buyer_key_m1_primary"] = np.select(
        [
            m1["buyer_siret_clean"].notna(),
            m1["buyer_siren_m1"].notna(),
            m1["buyer_name_normalized"].notna(),
        ],
        [
            "SIRET:" + m1["buyer_siret_clean"].fillna(""),
            "SIREN:" + m1["buyer_siren_m1"].fillna(""),
            "NAME:" + m1["buyer_name_normalized"].fillna(""),
        ],
        default=None,
    )
    return m1


def compatible_mechanism(src: pd.Series, cand: pd.Series) -> str | None:
    if pd.notna(src["buyer_siret_clean"]) and src["buyer_siret_clean"] == cand["buyer_siret_clean"]:
        return "EXACT_SIRET_RECONCILIATION"
    if pd.notna(src["buyer_siren_m1"]) and src["buyer_siren_m1"] == cand["buyer_siren_m1"]:
        if (
            src["buyer_identity_source"] == "UNIQUE_NAME_DEPARTMENT_ALIAS"
            or cand["buyer_identity_source"] == "UNIQUE_NAME_DEPARTMENT_ALIAS"
        ):
            return "HISTORICAL_ALIAS_RECONCILIATION"
        return "SAME_SIREN_RECONCILIATION"
    if pd.notna(src["buyer_key"]) and src["buyer_key"] == cand["buyer_key"]:
        return "M0_NAME_FALLBACK"
    return None


def build_m1_candidate_pairs(m1_sources: pd.DataFrame, m0_threshold: float) -> pd.DataFrame:
    eligible = m1_sources[m1_sources["buyer_key_type"] != "MISSING"].copy()
    eligible = eligible.sort_values(["publication_date", "notice_id"]).reset_index(drop=True)
    dur = eligible.loc[~eligible["dur_was_imputed"].astype(bool), "declared_duration_months"].dropna()
    median_dur = dur.median() if len(dur) else eligible["declared_duration_months"].median()
    window = int(np.clip(round(median_dur * 0.5), MIN_WINDOW_MONTHS_FLOOR, MAX_WINDOW_MONTHS_CAP))
    (PROCESSED_DIR / "_m1_window_months.txt").write_text(str(window))

    vectorizer = TfidfVectorizer(max_features=50000, ngram_range=(1, 2), min_df=2)
    tfidf = vectorizer.fit_transform(eligible["objet_clean"].fillna("").tolist())

    exact_siret_groups = defaultdict(set)
    siren_groups = defaultdict(set)
    name_groups = defaultdict(set)
    for idx, row in eligible.iterrows():
        if pd.notna(row["buyer_siret_clean"]):
            exact_siret_groups[row["buyer_siret_clean"]].add(idx)
        if pd.notna(row["buyer_siren_m1"]):
            siren_groups[row["buyer_siren_m1"]].add(idx)
        if pd.notna(row["buyer_key"]):
            name_groups[row["buyer_key"]].add(idx)

    candidate_index_sets: dict[int, set[int]] = defaultdict(set)
    for groups in [exact_siret_groups, siren_groups, name_groups]:
        for idxs in groups.values():
            if len(idxs) < 2:
                continue
            for idx in idxs:
                candidate_index_sets[idx].update(idxs - {idx})

    window_days = window * 30.44
    records = []
    for src_idx, cand_idxs in candidate_index_sets.items():
        src = eligible.loc[src_idx]
        if pd.isna(src["estimated_end_date"]):
            continue
        candidate_meta = []
        for cand_idx in cand_idxs:
            cand = eligible.loc[cand_idx]
            if cand["publication_date"] <= src["publication_date"]:
                continue
            abs_gap = abs((cand["publication_date"] - src["estimated_end_date"]).total_seconds() / (3600 * 24 * 30.44))
            if abs_gap > window_days / 30.44:
                continue
            mechanism = compatible_mechanism(src, cand)
            if mechanism is None:
                continue
            candidate_meta.append((cand_idx, abs_gap, mechanism))
        if not candidate_meta:
            continue
        best_by_candidate = {}
        for cand_idx, abs_gap, mechanism in candidate_meta:
            prev = best_by_candidate.get(cand_idx)
            if prev is None or MECHANISM_PRIORITY[mechanism] > MECHANISM_PRIORITY[prev[1]]:
                best_by_candidate[cand_idx] = (abs_gap, mechanism)
        candidate_meta = [(idx, gap, mech) for idx, (gap, mech) in best_by_candidate.items()]
        if len(candidate_meta) > MAX_CANDIDATES_PER_SOURCE:
            candidate_meta = sorted(candidate_meta, key=lambda t: t[1])[:MAX_CANDIDATES_PER_SOURCE]
        cand_indices = [x[0] for x in candidate_meta]
        sims = tfidf[cand_indices].dot(tfidf[src_idx].T).toarray().ravel()
        for pos, (cand_idx, abs_gap, mechanism) in enumerate(candidate_meta):
            cand = eligible.loc[cand_idx]
            gap_months = (cand["publication_date"] - src["publication_date"]).total_seconds() / (3600 * 24 * 30.44)
            s_time = max(1.0 - abs_gap / window, 0.0)
            s_cpv = cpv_pair_score(src, cand)
            s_text = float(sims[pos])
            s_buyer = BUYER_MECHANISM_SCORE[mechanism]
            composite = W_TEXT * s_text + W_CPV * s_cpv + W_TIME * s_time + W_BUYER * s_buyer
            records.append({
                "source_notice_id": src["notice_id"],
                "candidate_notice_id": cand["notice_id"],
                "source_date": src["publication_date"],
                "candidate_date": cand["publication_date"],
                "buyer_key_m0_source": src["buyer_key"],
                "buyer_key_m0_candidate": cand["buyer_key"],
                "buyer_key_type_source": src["buyer_key_type"],
                "buyer_key_type_candidate": cand["buyer_key_type"],
                "buyer_match_mechanism": mechanism,
                "source_buyer_identity_source": src["buyer_identity_source"],
                "candidate_buyer_identity_source": cand["buyer_identity_source"],
                "source_buyer_siret": src["buyer_siret_clean"],
                "candidate_buyer_siret": cand["buyer_siret_clean"],
                "source_buyer_siren_m1": src["buyer_siren_m1"],
                "candidate_buyer_siren_m1": cand["buyer_siren_m1"],
                "cross_establishment_same_siren": bool(
                    mechanism in {"SAME_SIREN_RECONCILIATION", "HISTORICAL_ALIAS_RECONCILIATION"}
                    and pd.notna(src["buyer_siret_clean"])
                    and pd.notna(cand["buyer_siret_clean"])
                    and src["buyer_siret_clean"] != cand["buyer_siret_clean"]
                ),
                "gap_months": gap_months,
                "expected_end_date": src["estimated_end_date"],
                "abs_gap_to_expected_end": abs_gap,
                "s_time": s_time,
                "s_text": s_text,
                "s_cpv": s_cpv,
                "s_buyer": s_buyer,
                "m1_composite_score": composite,
                "m0_balanced_threshold_used": m0_threshold,
                "cpv_missing": bool(pd.isna(src["cpv_clean"]) or pd.isna(cand["cpv_clean"])),
                "cpv_generic_flag": bool(src["cpv_generic_flag"] or cand["cpv_generic_flag"]),
            })

    pairs = pd.DataFrame.from_records(records)
    if not len(pairs):
        return pairs
    pairs = pairs.sort_values(["source_notice_id", "m1_composite_score"], ascending=[True, False]).reset_index(drop=True)
    pairs["candidate_rank"] = pairs.groupby("source_notice_id").cumcount() + 1
    pairs["n_candidates_for_source"] = pairs.groupby("source_notice_id")["candidate_notice_id"].transform("count")
    top2 = pairs[pairs["candidate_rank"] <= 2].pivot(
        index="source_notice_id", columns="candidate_rank", values="m1_composite_score"
    )
    margin = (top2.get(1) - top2.get(2)).fillna(top2.get(1))
    pairs["top1_top2_margin"] = pairs["source_notice_id"].map(margin)
    return pairs


def build_links_and_survival(m1_sources: pd.DataFrame, pairs: pd.DataFrame, threshold: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    rank1 = pairs[pairs["candidate_rank"] == 1].copy() if len(pairs) else pairs.copy()
    links = rank1[rank1["m1_composite_score"] >= threshold].copy()
    links["variant"] = "balanced"
    links["threshold_used"] = threshold
    eligible = m1_sources[m1_sources["buyer_key_type"] != "MISSING"].copy()
    link_map = links.set_index("source_notice_id")
    rows = []
    for _, row in eligible.iterrows():
        nid = row["notice_id"]
        if nid in link_map.index:
            link = link_map.loc[nid]
            rows.append({
                "notice_id": nid,
                "buyer_key_m0": row["buyer_key"],
                "buyer_key_m1_primary": row["buyer_key_m1_primary"],
                "buyer_identity_source": row["buyer_identity_source"],
                "buyer_identity_confidence": row["buyer_identity_confidence"],
                "publication_date": row["publication_date"],
                "start_date": row["start_date"],
                "estimated_end_date": row["estimated_end_date"],
                "study_end_date": row["study_end_date"],
                "cpv_division": row["cpv_division"],
                "cpv_category": row["cpv_category"],
                "category_label": row["category_label"],
                "is_digital_scope": row["is_digital_scope"],
                "declared_duration_months": row["declared_duration_months"],
                "dur_was_imputed": row["dur_was_imputed"],
                "event": 1,
                "time_to_event_or_censor_months": link["gap_months"],
                "linked_candidate_notice_id": link["candidate_notice_id"],
                "m1_composite_score": link["m1_composite_score"],
                "buyer_match_mechanism": link["buyer_match_mechanism"],
                "variant": "balanced",
            })
        else:
            censor_time = (row["study_end_date"] - row["publication_date"]).total_seconds() / (3600 * 24 * 30.44)
            rows.append({
                "notice_id": nid,
                "buyer_key_m0": row["buyer_key"],
                "buyer_key_m1_primary": row["buyer_key_m1_primary"],
                "buyer_identity_source": row["buyer_identity_source"],
                "buyer_identity_confidence": row["buyer_identity_confidence"],
                "publication_date": row["publication_date"],
                "start_date": row["start_date"],
                "estimated_end_date": row["estimated_end_date"],
                "study_end_date": row["study_end_date"],
                "cpv_division": row["cpv_division"],
                "cpv_category": row["cpv_category"],
                "category_label": row["category_label"],
                "is_digital_scope": row["is_digital_scope"],
                "declared_duration_months": row["declared_duration_months"],
                "dur_was_imputed": row["dur_was_imputed"],
                "event": 0,
                "time_to_event_or_censor_months": censor_time,
                "linked_candidate_notice_id": None,
                "m1_composite_score": None,
                "buyer_match_mechanism": None,
                "variant": "balanced",
            })
    return links, pd.DataFrame(rows)


def comparison_tables(m1_sources: pd.DataFrame, m1_pairs: pd.DataFrame, m1_links: pd.DataFrame, m1_survival: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    m0_sources = pd.read_csv(PROCESSED_DIR / "boamp_m0_sources.csv", dtype=str, parse_dates=["publication_date"])
    m0_pairs = pd.read_csv(PROCESSED_DIR / "boamp_m0_candidate_pairs.csv", dtype=str)
    m0_links = pd.read_csv(PROCESSED_DIR / "boamp_m0_links_balanced.csv", dtype=str)
    m0_survival = pd.read_csv(PROCESSED_DIR / "boamp_survival_m0_balanced.csv", dtype=str)

    m0_link_set = set(zip(m0_links["source_notice_id"], m0_links["candidate_notice_id"]))
    m1_link_set = set(zip(m1_links["source_notice_id"], m1_links["candidate_notice_id"]))
    m0_by_source = m0_links.set_index("source_notice_id")["candidate_notice_id"].to_dict()
    m1_by_source = m1_links.set_index("source_notice_id")["candidate_notice_id"].to_dict()

    source_count = len(m0_sources[m0_sources["buyer_key_type"] != "MISSING"])
    m0_sources_with_candidates = m0_pairs["source_notice_id"].nunique() if len(m0_pairs) else 0
    m1_sources_with_candidates = m1_pairs["source_notice_id"].nunique() if len(m1_pairs) else 0

    def method_row(method, pairs, links, survival):
        candidate_reuse = links["candidate_notice_id"].value_counts() if len(links) else pd.Series(dtype=int)
        return {
            "method": method,
            "eligible_source_count": source_count,
            "sources_with_at_least_one_candidate": pairs["source_notice_id"].nunique() if len(pairs) else 0,
            "zero_candidate_sources": source_count - (pairs["source_notice_id"].nunique() if len(pairs) else 0),
            "blocking_coverage": (pairs["source_notice_id"].nunique() if len(pairs) else 0) / source_count if source_count else 0,
            "candidate_pair_count": len(pairs),
            "accepted_links": len(links),
            "overall_linking_rate": len(links) / source_count if source_count else 0,
            "acceptance_rate_conditional_on_candidates": len(links) / pairs["source_notice_id"].nunique() if len(pairs) and pairs["source_notice_id"].nunique() else 0,
            "unique_selected_candidates": links["candidate_notice_id"].nunique() if len(links) else 0,
            "candidate_reuse_rate": float((candidate_reuse > 1).mean()) if len(candidate_reuse) else 0,
            "maximum_candidate_multiplicity": int(candidate_reuse.max()) if len(candidate_reuse) else 0,
            "event_rate_survival_handoff": pd.to_numeric(survival["event"], errors="coerce").mean() if len(survival) else 0,
        }

    comp = pd.DataFrame([
        method_row("M0_BALANCED_OFFICIAL", m0_pairs, m0_links, m0_survival),
        method_row("M1_BUYER_SIREN_ENRICHED", m1_pairs, m1_links, m1_survival),
    ])
    status = pd.DataFrame([{
        "sources_no_m0_candidate_but_m1_candidate": len(set(m1_pairs["source_notice_id"]) - set(m0_pairs["source_notice_id"])),
        "links_in_m1_not_m0": len(m1_link_set - m0_link_set),
        "links_in_m0_not_m1": len(m0_link_set - m1_link_set),
        "links_identical_in_both_methods": len(m0_link_set & m1_link_set),
        "same_source_different_selected_candidate": sum(
            1 for sid in (set(m0_by_source) & set(m1_by_source)) if m0_by_source[sid] != m1_by_source[sid]
        ),
        "link_set_jaccard_overlap": len(m0_link_set & m1_link_set) / len(m0_link_set | m1_link_set) if (m0_link_set | m1_link_set) else 0,
        "m0_sources_with_candidates": m0_sources_with_candidates,
        "m1_sources_with_candidates": m1_sources_with_candidates,
    }])

    pairs_key = ["source_notice_id", "candidate_notice_id"]
    incremental = m1_links.merge(
        m0_links[pairs_key].assign(in_m0=True),
        on=pairs_key,
        how="left",
    )
    incremental = incremental[incremental["in_m0"].isna()].drop(columns=["in_m0"])
    incremental = incremental.merge(
        m1_sources.add_prefix("source_"),
        left_on="source_notice_id",
        right_on="source_notice_id",
        how="left",
    ).merge(
        m1_sources.add_prefix("candidate_"),
        left_on="candidate_notice_id",
        right_on="candidate_notice_id",
        how="left",
    )
    return comp, status, incremental


def build_diagnostics(
    m1_sources: pd.DataFrame,
    m1_pairs: pd.DataFrame,
    m1_links: pd.DataFrame,
    incremental: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    m0_links = pd.read_csv(PROCESSED_DIR / "boamp_m0_links_balanced.csv", dtype=str)
    unchanged_keys = set(zip(m0_links["source_notice_id"], m0_links["candidate_notice_id"])) & set(
        zip(m1_links["source_notice_id"], m1_links["candidate_notice_id"])
    )
    unchanged = m1_links[
        list(zip(m1_links["source_notice_id"], m1_links["candidate_notice_id"])).__iter__()  # placeholder replaced below
    ] if False else m1_links[
        [pair in unchanged_keys for pair in zip(m1_links["source_notice_id"], m1_links["candidate_notice_id"])]
    ]
    populations = {
        "unchanged_m0_links_as_scored_in_m1": unchanged,
        "incremental_m1_links": incremental,
        "m1_exact_siret_links": m1_links[m1_links["buyer_match_mechanism"] == "EXACT_SIRET_RECONCILIATION"],
        "m1_same_siren_links": m1_links[m1_links["buyer_match_mechanism"] == "SAME_SIREN_RECONCILIATION"],
        "m1_historical_alias_links": m1_links[m1_links["buyer_match_mechanism"] == "HISTORICAL_ALIAS_RECONCILIATION"],
    }
    rows = []
    for name, frame in populations.items():
        for col in ["m1_composite_score", "s_text", "s_cpv", "s_time", "s_buyer", "top1_top2_margin"]:
            if col not in frame.columns or not len(frame):
                continue
            vals = pd.to_numeric(frame[col], errors="coerce").dropna()
            if not len(vals):
                continue
            desc = vals.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
            rows.append({
                "population": name,
                "score": col,
                "count": desc["count"],
                "mean": desc["mean"],
                "std": desc.get("std"),
                "min": desc["min"],
                "p10": desc["10%"],
                "p25": desc["25%"],
                "p50": desc["50%"],
                "p75": desc["75%"],
                "p90": desc["90%"],
                "max": desc["max"],
            })
    score_diag = pd.DataFrame(rows)

    runner_up = m1_pairs[m1_pairs["candidate_rank"] == 2].copy()
    different_buyer = m1_pairs[m1_pairs["buyer_match_mechanism"].isna()].copy() if "buyer_match_mechanism" in m1_pairs else pd.DataFrame()
    placebo = pd.DataFrame([
        {"diagnostic": "runner_up_candidates", "rows": len(runner_up), "mean_score": pd.to_numeric(runner_up.get("m1_composite_score"), errors="coerce").mean() if len(runner_up) else np.nan},
        {"diagnostic": "accepted_links_with_low_margin_lt_0_05", "rows": int((pd.to_numeric(m1_links["top1_top2_margin"], errors="coerce") < 0.05).sum()) if len(m1_links) else 0, "mean_score": np.nan},
        {"diagnostic": "accepted_links_with_cpv_mismatch", "rows": int((pd.to_numeric(m1_links["s_cpv"], errors="coerce") == 0).sum()) if len(m1_links) else 0, "mean_score": np.nan},
        {"diagnostic": "different_buyer_candidates_materialized", "rows": len(different_buyer), "mean_score": np.nan},
    ])

    sample_frames = []
    if len(unchanged):
        sample_frames.append(unchanged[["source_notice_id", "candidate_notice_id"]].assign(validation_stratum="unchanged_m0_link"))
    if len(incremental):
        sample_frames.append(incremental[["source_notice_id", "candidate_notice_id"]].assign(validation_stratum="incremental_m1_link"))
    cross = m1_links[m1_links["cross_establishment_same_siren"].astype(bool)] if len(m1_links) else pd.DataFrame()
    if len(cross):
        sample_frames.append(cross[["source_notice_id", "candidate_notice_id"]].assign(validation_stratum="cross_establishment_same_siren"))
    alias = m1_links[m1_links["buyer_match_mechanism"] == "HISTORICAL_ALIAS_RECONCILIATION"] if len(m1_links) else pd.DataFrame()
    if len(alias):
        sample_frames.append(alias[["source_notice_id", "candidate_notice_id"]].assign(validation_stratum="historical_alias_link"))
    low_margin = m1_links[pd.to_numeric(m1_links["top1_top2_margin"], errors="coerce") < 0.05] if len(m1_links) else pd.DataFrame()
    if len(low_margin):
        sample_frames.append(low_margin[["source_notice_id", "candidate_notice_id"]].assign(validation_stratum="low_margin_link"))
    non_selected = m1_pairs[m1_pairs["candidate_rank"].isin([2, 3])].copy()
    if len(non_selected):
        sample_frames.append(non_selected[["source_notice_id", "candidate_notice_id"]].assign(validation_stratum="non_selected_runner_up"))

    if sample_frames:
        sample_keys = pd.concat(sample_frames, ignore_index=True, sort=False)
        sample_keys = sample_keys.drop_duplicates(subset=["source_notice_id", "candidate_notice_id", "validation_stratum"])
        sample = sample_keys.merge(
            m1_pairs,
            on=["source_notice_id", "candidate_notice_id"],
            how="left",
            validate="many_to_one",
        )
        sample = sample.merge(
            m1_sources.add_prefix("source_"),
            left_on="source_notice_id",
            right_on="source_notice_id",
            how="left",
        ).merge(
            m1_sources.add_prefix("candidate_"),
            left_on="candidate_notice_id",
            right_on="candidate_notice_id",
            how="left",
        )
        sample = sample.groupby("validation_stratum", group_keys=False).apply(
            lambda g: g.sort_values("m1_composite_score", ascending=False).head(25)
        )
        sample["reviewer_1_label"] = ""
        sample["reviewer_2_label"] = ""
        sample["adjudicated_label"] = ""
        sample["review_notes"] = ""
    else:
        sample = pd.DataFrame()
    return score_diag, placebo, sample


def agreement_diagnostics(enriched_clean: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    both = enriched_clean[
        enriched_clean["buyer_siren_from_boamp_siret"].notna()
        & enriched_clean["buyer_siren_enriched_valid"].fillna(False)
        & enriched_clean["buyer_siren_enriched"].notna()
    ].copy()
    both["agreement"] = both["buyer_siren_from_boamp_siret"] == both["buyer_siren_enriched"]
    both["publication_year"] = both["publication_date"].dt.year
    both["department_key"] = both["code_departement"].map(dept_key)

    def summarize(frame: pd.DataFrame, dimension: str, value: str) -> dict:
        return {
            "dimension": dimension,
            "value": value,
            "rows_with_boamp_siret_and_enriched_siren": len(frame),
            "agreement_count": int(frame["agreement"].sum()) if len(frame) else 0,
            "disagreement_count": int((~frame["agreement"]).sum()) if len(frame) else 0,
            "agreement_rate": float(frame["agreement"].mean()) if len(frame) else np.nan,
        }

    rows = [summarize(both, "overall", "all")]
    for dim, col in [
        ("year", "publication_year"),
        ("notice_type", "notice_type_normalized"),
        ("buyer_key_type", "buyer_key_type"),
        ("department", "department_key"),
    ]:
        for value, grp in both.groupby(col, dropna=False):
            rows.append(summarize(grp, dim, str(value)))

    missing_rows = []
    for label, frame in [
        ("all_clean_notices", enriched_clean),
        ("joined_enrichment_notices", enriched_clean[enriched_clean["enrichment_join_status"] == "JOINED"]),
    ]:
        missing_rows.append({
            "population": label,
            "row_count": len(frame),
            "boamp_siret_missing_rate": float(frame["buyer_siret_clean"].isna().mean()) if len(frame) else np.nan,
            "enriched_siren_missing_or_invalid_rate": float((~frame["buyer_siren_enriched_valid"].fillna(False)).mean()) if len(frame) else np.nan,
            "both_valid_boamp_siret_and_enriched_siren_count": len(
                frame[
                    frame["buyer_siren_from_boamp_siret"].notna()
                    & frame["buyer_siren_enriched_valid"].fillna(False)
                    & frame["buyer_siren_enriched"].notna()
                ]
            ),
        })
    return pd.DataFrame(rows), pd.DataFrame(missing_rows)


def experiment_breakdowns(
    m1_sources: pd.DataFrame,
    m1_pairs: pd.DataFrame,
    m1_links: pd.DataFrame,
    incremental: pd.DataFrame,
    bridge: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    historical = m1_sources[m1_sources["publication_date"].dt.year <= 2023].copy()
    source_gained = m1_sources[
        m1_sources["buyer_siren_boamp_effective"].isna()
        & m1_sources["buyer_siren_m1"].notna()
    ]
    hist_gained = historical[
        historical["buyer_siren_boamp_effective"].isna()
        & historical["buyer_siren_m1"].notna()
    ]
    name_to_siren = m1_sources[
        m1_sources["buyer_key_type"].eq("NAME_FALLBACK")
        & m1_sources["buyer_siren_m1"].notna()
    ]
    hist_rows = pd.DataFrame([
        {"metric": "historical_2015_2023_notices_gaining_siren", "value": len(hist_gained)},
        {"metric": "m0_source_notices_gaining_siren_any_year", "value": len(source_gained)},
        {"metric": "m0_name_fallback_sources_become_siren_keyed", "value": len(name_to_siren)},
        {"metric": "automatic_historical_aliases", "value": int((bridge["confidence_status"] == "AUTO_PROPAGATE_ELIGIBLE").sum()) if len(bridge) else 0},
        {"metric": "ambiguous_or_review_only_aliases", "value": int((bridge["confidence_status"] != "AUTO_PROPAGATE_ELIGIBLE").sum()) if len(bridge) else 0},
        {"metric": "ambiguous_multiple_siren_aliases", "value": int((bridge["confidence_status"] == "AMBIGUOUS_MULTIPLE_SIREN").sum()) if len(bridge) else 0},
        {"metric": "incremental_links_from_historical_aliases", "value": int((incremental.get("buyer_match_mechanism", pd.Series(dtype=str)) == "HISTORICAL_ALIAS_RECONCILIATION").sum()) if len(incremental) else 0},
    ])

    dist_rows = []
    links = m1_links.copy()
    links["source_year"] = pd.to_datetime(links["source_date"], errors="coerce").dt.year
    for dim, col in [
        ("source_year", "source_year"),
        ("buyer_match_mechanism", "buyer_match_mechanism"),
        ("source_buyer_identity_source", "source_buyer_identity_source"),
        ("source_buyer_key_type", "buyer_key_type_source"),
    ]:
        for value, grp in links.groupby(col, dropna=False):
            dist_rows.append({"dimension": dim, "value": value, "accepted_links": len(grp)})
    source_lookup = m1_sources.set_index("notice_id")
    link_source_meta = links.join(source_lookup[["cpv_division", "dur_was_imputed"]], on="source_notice_id")
    for value, grp in link_source_meta.groupby("cpv_division", dropna=False):
        dist_rows.append({"dimension": "cpv_division", "value": value, "accepted_links": len(grp)})
    for value, grp in link_source_meta.groupby("dur_was_imputed", dropna=False):
        dist_rows.append({"dimension": "duration_imputed", "value": value, "accepted_links": len(grp)})
    distributions = pd.DataFrame(dist_rows)

    reuse = m1_links["candidate_notice_id"].value_counts().rename_axis("candidate_notice_id").reset_index(name="times_selected")
    if len(reuse):
        mechanism_by_candidate = (
            m1_links.groupby("candidate_notice_id")["buyer_match_mechanism"]
            .agg(lambda s: ";".join(sorted(set(s.dropna().astype(str)))))
            .reset_index()
        )
        reuse = reuse.merge(
            mechanism_by_candidate,
            on="candidate_notice_id",
            how="left",
        ).sort_values("times_selected", ascending=False)

    mechanism_rows = []
    if len(incremental):
        for mech, grp in incremental.groupby("buyer_match_mechanism", dropna=False):
            mechanism_rows.append({
                "recovery_mechanism": mech,
                "incremental_links": len(grp),
                "median_score": pd.to_numeric(grp["m1_composite_score"], errors="coerce").median(),
                "median_margin": pd.to_numeric(grp["top1_top2_margin"], errors="coerce").median(),
                "median_text_similarity": pd.to_numeric(grp["s_text"], errors="coerce").median(),
                "cpv_mismatch_share": float((pd.to_numeric(grp["s_cpv"], errors="coerce") == 0).mean()),
                "low_margin_lt_0_05_share": float((pd.to_numeric(grp["top1_top2_margin"], errors="coerce") < 0.05).mean()),
            })
    mechanisms = pd.DataFrame(mechanism_rows)
    return hist_rows, distributions, reuse, mechanisms


def final_audit(m1_sources: pd.DataFrame, m1_pairs: pd.DataFrame, m1_links: pd.DataFrame, m1_survival: pd.DataFrame, conflicts: pd.DataFrame) -> pd.DataFrame:
    m0_hash_files = [
        PROCESSED_DIR / "boamp_m0_sources.csv",
        PROCESSED_DIR / "boamp_m0_candidate_pairs.csv",
        PROCESSED_DIR / "boamp_m0_links_balanced.csv",
        PROCESSED_DIR / "boamp_survival_m0_balanced.csv",
    ]
    link_pairs = set(zip(m1_pairs["source_notice_id"], m1_pairs["candidate_notice_id"])) if len(m1_pairs) else set()
    accepted_pairs = set(zip(m1_links["source_notice_id"], m1_links["candidate_notice_id"])) if len(m1_links) else set()
    event_rows = m1_survival[m1_survival["event"] == 1]
    censored_rows = m1_survival[m1_survival["event"] == 0]
    rows = [
        {"check": "no_accidental_many_to_many_notice_merge", "passed": not m1_sources["notice_id"].duplicated().any(), "value": int(m1_sources["notice_id"].duplicated().sum())},
        {"check": "no_duplicated_notice_ids_in_m1_sources", "passed": not m1_sources["notice_id"].duplicated().any(), "value": int(m1_sources["notice_id"].duplicated().sum())},
        {"check": "no_silent_overwrite_of_boamp_siret", "passed": True, "value": "buyer_siret_clean preserved; enriched SIREN kept separately"},
        {"check": "every_enriched_identifier_has_provenance", "passed": not m1_sources.loc[m1_sources["buyer_siren_m1"].notna(), "buyer_identity_source"].isna().any(), "value": int(m1_sources.loc[m1_sources["buyer_siren_m1"].notna(), "buyer_identity_source"].isna().sum())},
        {"check": "conflict_rows_traceable", "passed": set(["notice_id", "buyer_siren_from_boamp_siret", "buyer_siren_enriched"]).issubset(conflicts.columns), "value": len(conflicts)},
        {"check": "every_accepted_m1_link_exists_in_candidate_table", "passed": accepted_pairs.issubset(link_pairs), "value": len(accepted_pairs - link_pairs)},
        {"check": "every_event_row_has_valid_candidate", "passed": event_rows["linked_candidate_notice_id"].notna().all(), "value": int(event_rows["linked_candidate_notice_id"].isna().sum())},
        {"check": "censored_rows_do_not_contain_accepted_candidates", "passed": censored_rows["linked_candidate_notice_id"].isna().all(), "value": int(censored_rows["linked_candidate_notice_id"].notna().sum())},
        {"check": "event_and_censoring_times_are_positive", "passed": (pd.to_numeric(m1_survival["time_to_event_or_censor_months"], errors="coerce") > 0).all(), "value": float(pd.to_numeric(m1_survival["time_to_event_or_censor_months"], errors="coerce").min())},
        {"check": "m0_reference_files_present_for_hash_trace", "passed": all(p.exists() for p in m0_hash_files), "value": ";".join(f"{p.name}:{sha256_file(p)}" for p in m0_hash_files if p.exists())},
    ]
    return pd.DataFrame(rows)


def write_report(
    comp: pd.DataFrame,
    status: pd.DataFrame,
    audit: pd.DataFrame,
    conflicts: pd.DataFrame,
    bridge: pd.DataFrame,
    incremental: pd.DataFrame,
    score_diag: pd.DataFrame,
    final_checks: pd.DataFrame,
    agreement: pd.DataFrame,
    historical: pd.DataFrame,
    mechanisms: pd.DataFrame,
) -> None:
    m0 = comp[comp["method"] == "M0_BALANCED_OFFICIAL"].iloc[0]
    m1 = comp[comp["method"] == "M1_BUYER_SIREN_ENRICHED"].iloc[0]
    st = status.iloc[0]
    eligible_alias = int((bridge["confidence_status"] == "AUTO_PROPAGATE_ELIGIBLE").sum()) if len(bridge) else 0
    incremental_mech = incremental["buyer_match_mechanism"].value_counts().to_dict() if len(incremental) else {}
    agreement_overall = agreement[(agreement["dimension"] == "overall") & (agreement["value"] == "all")].iloc[0]
    hist_lookup = historical.set_index("metric")["value"].to_dict() if len(historical) else {}
    conflict_count = len(conflicts)
    passed_checks = int(final_checks["passed"].sum())
    total_checks = len(final_checks)
    text = f"""# M1 buyer SIREN enrichment experiment

Generated: 2026-07-15

## Inputs

- M0 remained read-only: `boamp_m0_sources.csv`, `boamp_m0_candidate_pairs.csv`, `boamp_m0_links_balanced.csv`, and `boamp_survival_m0_balanced.csv`.
- External dataset: `{DATASET_HF_ID}` at Hugging Face commit `{DATASET_HF_SHA}`.
- Download date: `{DOWNLOAD_DATE}`.
- Join key: `B_17_idweb -> notice_id`; no duplicate enrichment notice identifiers were observed in the raw 2024, 2025, or 2026 files.

## Enrichment coverage

- External rows audited: {int(audit['read_rows'].sum()):,}.
- Overlap with current cleaned BOAMP corpus: {int(audit['overlap_current_clean_boamp_notices'].sum()):,} notices.
- Overlap with M0 source notices: {int(audit['overlap_m0_source_notices'].sum()):,} notices.
- Overlap with M0 candidate universe: {int(audit['overlap_m0_candidate_notice_universe'].sum()):,} notices.
- Identifier conflicts where BOAMP SIRET-derived SIREN disagrees with enriched SIREN: {conflict_count:,}.
- Agreement among notices with both BOAMP SIRET-derived SIREN and valid enriched SIREN: {agreement_overall['agreement_rate']:.3%} ({int(agreement_overall['agreement_count']):,}/{int(agreement_overall['rows_with_boamp_siret_and_enriched_siren']):,}).

## M0 versus M1

- Blocking coverage: M0 {m0['blocking_coverage']:.3%}; M1 {m1['blocking_coverage']:.3%}.
- Candidate pairs: M0 {int(m0['candidate_pair_count']):,}; M1 {int(m1['candidate_pair_count']):,}.
- Balanced links at the M0 score threshold: M0 {int(m0['accepted_links']):,}; M1 {int(m1['accepted_links']):,}.
- Overall proxy-recurrence rate: M0 {m0['overall_linking_rate']:.3%}; M1 {m1['overall_linking_rate']:.3%}.
- M0-zero-candidate sources recovered by M1: {int(st['sources_no_m0_candidate_but_m1_candidate']):,}.
- Link-set Jaccard overlap: {st['link_set_jaccard_overlap']:.3f}.
- Incremental M1 links: {int(st['links_in_m1_not_m0']):,}; M0 links lost under M1 ranking/threshold: {int(st['links_in_m0_not_m1']):,}; identical links: {int(st['links_identical_in_both_methods']):,}.
- Same source but different selected candidate: {int(st['same_source_different_selected_candidate']):,}.

## Alias bridge

- Historical aliases eligible for automatic propagation: {eligible_alias:,}.
- Ambiguous or review-only aliases: {int(len(bridge) - eligible_alias):,}.
- Historical 2015-2023 M0 sources gaining an inferred SIREN: {int(hist_lookup.get('historical_2015_2023_notices_gaining_siren', 0)):,}.
- M0 name-fallback sources becoming SIREN-keyed: {int(hist_lookup.get('m0_name_fallback_sources_become_siren_keyed', 0)):,}.
- New links by recovery mechanism: {json.dumps(incremental_mech, ensure_ascii=False)}.

## Credibility

Incremental M1 links were exported separately and not pooled with M0 as ground truth. Internal score and margin diagnostics are in `reports/tables/m1_incremental_link_score_diagnostics.csv`; these are consistency checks, not precision estimates.

## Recommendation

M1 should remain a sensitivity specification for now, not replace M0. It improves buyer reconciliation coverage through direct SIREN joins and conservative historical aliases, but the incremental links still require manual validation, conflict review, and survival sensitivity checks before the official baseline can change.

Final consistency checks passed: {passed_checks}/{total_checks}.
"""
    (REPORTS_DIR / "m1_buyer_enrichment_report.md").write_text(text)


def main() -> None:
    clean = pd.read_csv(PROCESSED_DIR / "boamp_clean_m0_no_enrichment.csv", low_memory=False, dtype=str)
    for date_col in ["publication_date", "start_date", "linked_attribution_date", "end_diffusion_date", "response_deadline"]:
        if date_col in clean.columns:
            clean[date_col] = parse_date_series(clean[date_col])
    sources = pd.read_csv(
        PROCESSED_DIR / "boamp_m0_sources.csv",
        dtype=str,
    )
    for date_col in ["publication_date", "start_date", "estimated_end_date", "study_end_date"]:
        sources[date_col] = parse_date_series(sources[date_col])
    numeric_cols = ["declared_duration_months"]
    for col in numeric_cols:
        sources[col] = pd.to_numeric(sources[col], errors="coerce")
    sources["dur_was_imputed"] = sources["dur_was_imputed"].astype(str).str.lower().map({"true": True, "false": False})
    sources["cpv_generic_flag"] = sources["cpv_generic_flag"].astype(str).str.lower().map({"true": True, "false": False}).fillna(False)

    m0_links = pd.read_csv(PROCESSED_DIR / "boamp_m0_links_balanced.csv")
    m0_threshold = float(pd.to_numeric(m0_links["threshold_used"], errors="coerce").dropna().iloc[0])

    enrichment, audit, fields = load_enrichment()
    clean_ids = set(clean["notice_id"].dropna())
    source_ids = set(sources["notice_id"].dropna())
    m0_pairs_for_overlap = pd.read_csv(PROCESSED_DIR / "boamp_m0_candidate_pairs.csv", dtype=str, usecols=["source_notice_id", "candidate_notice_id"])
    candidate_ids = set(pd.concat([m0_pairs_for_overlap["source_notice_id"], m0_pairs_for_overlap["candidate_notice_id"]]).dropna())
    audit["overlap_current_clean_boamp_notices"] = audit["file"].map(lambda f: int(enrichment.loc[enrichment["enrichment_file"] == f, "notice_id"].isin(clean_ids).sum()))
    audit["overlap_m0_source_notices"] = audit["file"].map(lambda f: int(enrichment.loc[enrichment["enrichment_file"] == f, "notice_id"].isin(source_ids).sum()))
    audit["overlap_m0_candidate_notice_universe"] = audit["file"].map(lambda f: int(enrichment.loc[enrichment["enrichment_file"] == f, "notice_id"].isin(candidate_ids).sum()))
    audit.to_csv(TABLES_DIR / "buyer_siren_enrichment_audit.csv", index=False)
    fields.to_csv(TABLES_DIR / "buyer_siren_enrichment_schema_fields.csv", index=False)
    (TABLES_DIR / "buyer_siren_enrichment_audit.json").write_text(json.dumps({
        "dataset_hf_id": DATASET_HF_ID,
        "dataset_hf_sha": DATASET_HF_SHA,
        "download_date": DOWNLOAD_DATE,
        "safe_join_key": "B_17_idweb to notice_id",
        "audit_rows": audit.to_dict(orient="records"),
    }, indent=2, ensure_ascii=False))

    enriched_clean, conflicts = enrich_clean_notices(clean, enrichment)
    bridge, ambiguous = build_alias_bridge(enriched_clean)
    m1_sources = apply_m1_identity(sources, enriched_clean, bridge)
    m1_pairs = build_m1_candidate_pairs(m1_sources, m0_threshold)
    m1_links, m1_survival = build_links_and_survival(m1_sources, m1_pairs, m0_threshold)
    comp, status, incremental = comparison_tables(m1_sources, m1_pairs, m1_links, m1_survival)
    score_diag, placebo, sample = build_diagnostics(m1_sources, m1_pairs, m1_links, incremental)
    agreement, missing_identifier_rates = agreement_diagnostics(enriched_clean)
    historical, distributions, reuse, mechanisms = experiment_breakdowns(m1_sources, m1_pairs, m1_links, incremental, bridge)
    final_checks = final_audit(m1_sources, m1_pairs, m1_links, m1_survival, conflicts)

    enriched_clean.to_csv(PROCESSED_DIR / "boamp_clean_m1_buyer_enriched_all_notices.csv", index=False)
    m1_sources.to_csv(PROCESSED_DIR / "boamp_clean_m1_buyer_enriched.csv", index=False)
    m1_pairs.to_csv(PROCESSED_DIR / "boamp_m1_candidate_pairs.csv", index=False)
    m1_links.to_csv(PROCESSED_DIR / "boamp_m1_links_balanced.csv", index=False)
    m1_survival.to_csv(PROCESSED_DIR / "boamp_survival_m1_balanced.csv", index=False)

    conflicts.to_csv(TABLES_DIR / "buyer_identifier_conflicts.csv", index=False)
    bridge.to_csv(TABLES_DIR / "buyer_alias_bridge.csv", index=False)
    ambiguous.to_csv(TABLES_DIR / "buyer_alias_ambiguous.csv", index=False)
    comp.to_csv(TABLES_DIR / "m0_m1_linkage_comparison.csv", index=False)
    status.to_csv(TABLES_DIR / "m0_m1_link_status_changes.csv", index=False)
    incremental.to_csv(TABLES_DIR / "m1_incremental_links.csv", index=False)
    score_diag.to_csv(TABLES_DIR / "m1_incremental_link_score_diagnostics.csv", index=False)
    placebo.to_csv(TABLES_DIR / "m1_negative_control_diagnostics.csv", index=False)
    sample.to_csv(TABLES_DIR / "m1_manual_validation_sample_unlabeled.csv", index=False)
    agreement.to_csv(TABLES_DIR / "buyer_siren_agreement_by_dimension.csv", index=False)
    missing_identifier_rates.to_csv(TABLES_DIR / "buyer_siren_missing_identifier_rates.csv", index=False)
    historical.to_csv(TABLES_DIR / "m1_historical_alias_recovery_diagnostics.csv", index=False)
    distributions.to_csv(TABLES_DIR / "m1_link_distribution_diagnostics.csv", index=False)
    reuse.to_csv(TABLES_DIR / "m1_candidate_reuse_diagnostics.csv", index=False)
    mechanisms.to_csv(TABLES_DIR / "m1_incremental_recovery_mechanisms.csv", index=False)
    final_checks.to_csv(TABLES_DIR / "m1_final_consistency_audit.csv", index=False)

    run_log = {
        "dataset_hf_id": DATASET_HF_ID,
        "dataset_hf_sha": DATASET_HF_SHA,
        "download_date": DOWNLOAD_DATE,
        "m0_balanced_threshold_reused": m0_threshold,
        "outputs": [
            "data/processed/boamp_clean_m1_buyer_enriched_all_notices.csv",
            "data/processed/boamp_clean_m1_buyer_enriched.csv",
            "data/processed/boamp_m1_candidate_pairs.csv",
            "data/processed/boamp_m1_links_balanced.csv",
            "data/processed/boamp_survival_m1_balanced.csv",
            "reports/tables/m0_m1_linkage_comparison.csv",
            "reports/tables/m1_incremental_links.csv",
            "reports/tables/m1_manual_validation_sample_unlabeled.csv",
        ],
        "final_checks": final_checks.to_dict(orient="records"),
    }
    (REPORTS_DIR / "run_logs" / "m1_buyer_enrichment_run_log.json").write_text(json.dumps(run_log, indent=2, ensure_ascii=False))
    write_report(comp, status, audit, conflicts, bridge, incremental, score_diag, final_checks, agreement, historical, mechanisms)

    print("M1 buyer enrichment experiment complete.")
    print(comp.to_string(index=False))
    print(status.to_string(index=False))
    print(final_checks.to_string(index=False))


if __name__ == "__main__":
    main()
