"""Common BOAMP preparation shared by BOTH layers.

Extracted from scripts/preprocess_boamp_m0.py with the buyer-KEY construction
moved out (see identity_boamp.py / identity_enriched.py): everything here is
layer-neutral - dedup, notice types, dates, native identifier cleaning,
text cleaning, CPV levels, digital-scope tagging, duration cleaning +
imputation, ATTRIBUTION reverse-lookup start dates.

The fairness guarantee of the two-layer design rests on this module running
exactly once on the shared corpus.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from utils.identifiers import (
    normalize_buyer_name,
    siren_from_siret,
    validate_siren,
    validate_siret,
)
from utils.text_clean import clean_objet, normalize_objet


def first_token(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value)
    if not s or s.lower() == "nan":
        return None
    return s.split(";")[0].strip() or None


def cpv_is_generic(cpv_main: str) -> bool:
    """Generic = only the 2-digit division is meaningful (pattern XX000000)."""
    if not cpv_main or len(cpv_main) != 8:
        return False
    return cpv_main[2:] == "000000"


def normalize_notice_type(nature_raw: str) -> str:
    if not isinstance(nature_raw, str) or not nature_raw.strip():
        return "OTHER"
    v = nature_raw.strip().upper()
    if v in ("APPEL_OFFRE", "ATTRIBUTION"):
        return v
    return "OTHER"


def tag_digital_scope(cpv_division, objet_normalized, cfg) -> bool:
    if cpv_division in set(cfg.pipeline.scope.digital_cpv_divisions):
        return True
    if isinstance(objet_normalized, str):
        for kw in cfg.pipeline.scope.digital_keywords:
            if kw in objet_normalized:
                return True
    return False


def load_flattened(cfg) -> pd.DataFrame:
    # dtype=str everywhere: CPV/SIRET/SIREN candidate strings are
    # numeric-looking with NaNs and would otherwise be coerced to float64.
    df = pd.read_csv(cfg.paths.interim_flattened, low_memory=False, dtype=str)
    df["duration_months_raw"] = pd.to_numeric(df["duration_months_raw"], errors="coerce")
    return df


def prepare_common(df: pd.DataFrame, cfg, verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """Run the full layer-neutral preparation. Returns (clean_df, info)."""
    info: dict = {}
    p = cfg.pipeline

    # ---- A. Notice ID + dedup ----
    df = df.copy()
    df["notice_id"] = df["notice_id_raw"]
    dupe_ids = int(df["notice_id"].duplicated().sum())
    info["duplicate_notice_ids_dropped"] = dupe_ids
    if dupe_ids:
        df = df.drop_duplicates(subset="notice_id", keep="first")

    # ---- B. Notice type ----
    df["notice_type_raw"] = df["nature"]
    df["notice_type_normalized"] = df["nature"].map(normalize_notice_type)

    # ---- C. Dates ----
    df["publication_date"] = pd.to_datetime(df["dateparution"], errors="coerce", utc=True).dt.tz_localize(None)
    df["publication_year"] = df["publication_date"].dt.year
    df["publication_month"] = df["publication_date"].dt.month
    df["publication_quarter"] = df["publication_date"].dt.quarter
    df["end_diffusion_date"] = pd.to_datetime(df["datefindiffusion"], errors="coerce", utc=True).dt.tz_localize(None)
    df["response_deadline"] = pd.to_datetime(df["datelimitereponse"], errors="coerce", utc=True).dt.tz_localize(None)

    # ---- D. Native buyer identifiers (cleaning only - no key construction) ----
    df["buyer_name_raw"] = df["nomacheteur"]
    df["buyer_name_normalized"] = df["buyer_name_raw"].map(normalize_buyer_name)

    df["buyer_siret_raw"] = df["siret_candidates_raw"].map(first_token)
    siret_checks = df["buyer_siret_raw"].map(validate_siret)
    df["buyer_siret_format_valid"] = siret_checks.map(lambda t: t[0])
    df["buyer_siret_checksum_valid"] = siret_checks.map(lambda t: t[1])
    df["buyer_siret_clean"] = np.where(df["buyer_siret_format_valid"], df["buyer_siret_raw"], None)

    df["buyer_siren_raw"] = df["siren_candidates_raw"].map(first_token)
    siren_checks = df["buyer_siren_raw"].map(validate_siren)
    df["buyer_siren_format_valid"] = siren_checks.map(lambda t: t[0])
    df["buyer_siren_checksum_valid"] = siren_checks.map(lambda t: t[1])
    df["buyer_siren_clean"] = np.where(df["buyer_siren_format_valid"], df["buyer_siren_raw"], None)

    derived_mask = df["buyer_siren_clean"].isna() & df["buyer_siret_clean"].notna()
    df.loc[derived_mask, "buyer_siren_clean"] = df.loc[derived_mask, "buyer_siret_clean"].map(siren_from_siret)

    def identifier_source(row):
        if pd.notna(row["buyer_siret_clean"]):
            return "RAW_SIRET_FIELD"
        if pd.notna(row["buyer_siren_raw"]) and pd.notna(row["buyer_siren_clean"]) and not derived_mask.get(row.name, False):
            return "RAW_SIREN_FIELD"
        if pd.notna(row["buyer_siren_clean"]):
            return "DERIVED_FROM_SIRET"
        return "NONE"

    df["buyer_identifier_source"] = df.apply(identifier_source, axis=1)

    # ---- E. Text ----
    df["objet_raw"] = df["objet"]
    df["objet_clean"] = df["objet_raw"].map(clean_objet)
    df["objet_normalized"] = df["objet_clean"].map(normalize_objet)
    df["text_length"] = df["objet_clean"].fillna("").map(len)
    df["token_count"] = df["objet_clean"].fillna("").map(lambda s: len(s.split()))
    df["object_missing_flag"] = df["objet_clean"].isna()

    # ---- F. CPV ----
    df["cpv_raw"] = df["cpv_candidates_raw"]
    df["cpv_clean"] = df["cpv_candidates_raw"].map(first_token)
    df.loc[~df["cpv_clean"].fillna("").str.fullmatch(r"\d{8}"), "cpv_clean"] = None
    df["cpv_main"] = df["cpv_clean"]
    df["cpv_division"] = df["cpv_main"].str[0:2]
    df["cpv_group"] = df["cpv_main"].str[0:3]
    df["cpv_class"] = df["cpv_main"].str[0:4]
    df["cpv_category"] = df["cpv_main"].str[0:5]
    df["cpv_missing"] = df["cpv_main"].isna()
    df["cpv_generic_flag"] = df["cpv_main"].map(lambda v: cpv_is_generic(v) if pd.notna(v) else False)

    # ---- Scope tagging (before duration so imputation uses in-scope rows) ----
    df["is_digital_scope"] = df.apply(
        lambda r: tag_digital_scope(r["cpv_division"], r["objet_normalized"], cfg), axis=1
    )
    df["category_label"] = np.where(df["is_digital_scope"], "DIGITAL_ICT", "OTHER")
    df["is_digital_scope_cpv_only"] = df["cpv_division"].isin(set(p.scope.digital_cpv_divisions))

    pdl = set(p.scope.pdl_departments)
    df["_dept_tokens"] = df["code_departement"].fillna("").astype(str).str.split(";")
    df["is_in_pdl"] = df["_dept_tokens"].map(lambda toks: any(t.strip() in pdl for t in toks))
    info["n_outside_pdl"] = int((~df["is_in_pdl"]).sum())
    df = df.drop(columns=["_dept_tokens"])

    # ---- G. Duration ----
    lo, hi = p.duration.min_plausible_months, p.duration.max_plausible_months
    df["duration_raw"] = df["duration_months_raw"]
    in_range = df["duration_raw"].between(lo, hi)
    df["declared_duration_months"] = np.where(df["duration_raw"].notna() & in_range, df["duration_raw"], np.nan)
    df["duration_unit"] = np.where(df["declared_duration_months"].notna(), "months", None)
    df["duration_valid"] = df["declared_duration_months"].notna()
    df["duration_quality_flag"] = np.select(
        [df["declared_duration_months"].notna(), df["duration_raw"].notna() & ~in_range],
        ["OBSERVED", "OUT_OF_RANGE"],
        default="MISSING",
    )
    df["dur_was_imputed"] = False

    # Median-by-CPV-division imputation, computed on the in-scope
    # APPEL_OFFRE population only (the source scope), documented limitation:
    # 82.7% of current sources end up imputed.
    ao_mask = (df["notice_type_normalized"] == "APPEL_OFFRE") & df["is_digital_scope"]
    global_median = df.loc[ao_mask & df["duration_valid"], "declared_duration_months"].median()
    div_medians = (
        df.loc[ao_mask & df["duration_valid"]]
        .groupby("cpv_division")["declared_duration_months"]
        .median()
    )
    needs_impute = ao_mask & ~df["duration_valid"]
    imputed_vals = df.loc[needs_impute, "cpv_division"].map(div_medians).fillna(global_median)
    df.loc[needs_impute, "declared_duration_months"] = imputed_vals
    df.loc[needs_impute, "dur_was_imputed"] = True
    df.loc[needs_impute & df["declared_duration_months"].notna(), "duration_quality_flag"] = "IMPUTED_MEDIAN_BY_CPV_DIVISION"
    still_missing = needs_impute & df["declared_duration_months"].isna()
    if still_missing.any():
        df.loc[still_missing, "declared_duration_months"] = global_median
        df.loc[still_missing, "dur_was_imputed"] = True
        df.loc[still_missing, "duration_quality_flag"] = "IMPUTED_MEDIAN_GLOBAL"
    info["global_median_observed_duration_months"] = float(global_median)

    # ---- H. Start date via ATTRIBUTION reverse-lookup on annonce_lie ----
    attribution_links: dict = {}
    attr_rows = df.loc[df["notice_type_normalized"] == "ATTRIBUTION", ["notice_id", "annonce_lie", "publication_date"]]
    for _, r in attr_rows.iterrows():
        if pd.isna(r["annonce_lie"]):
            continue
        for ref in str(r["annonce_lie"]).split(";"):
            ref = ref.strip()
            if ref:
                if ref not in attribution_links or r["publication_date"] < attribution_links[ref][1]:
                    attribution_links[ref] = (r["notice_id"], r["publication_date"])

    df["linked_attribution_notice_id"] = df["notice_id"].map(lambda i: attribution_links.get(i, (None, None))[0])
    df["linked_attribution_date"] = df["notice_id"].map(lambda i: attribution_links.get(i, (None, None))[1])
    df["start_date"] = df["linked_attribution_date"].where(df["linked_attribution_date"].notna(), df["publication_date"])
    df["start_date_source"] = np.where(
        df["linked_attribution_date"].notna(), "LINKED_ATTRIBUTION_DATE", "PUBLICATION_DATE_FALLBACK"
    )

    info["n_cleaned"] = len(df)
    info["notice_type_counts"] = df["notice_type_normalized"].value_counts().to_dict()
    if verbose:
        print(f"Cleaned notices: {info['n_cleaned']} (dropped {dupe_ids} duplicate ids)")
        print(f"Notice types: {info['notice_type_counts']}")
        print(f"Global median observed in-scope duration: {global_median} months")
    return df, info


SOURCE_COLUMNS = [
    "notice_id", "publication_date", "start_date", "start_date_source",
    "buyer_key", "buyer_key_type", "buyer_name_raw", "buyer_name_normalized",
    "buyer_siret_clean", "buyer_siren_clean", "buyer_identifier_source",
    "code_departement",
    "objet_clean", "cpv_clean", "cpv_division", "cpv_group", "cpv_class",
    "cpv_category", "cpv_generic_flag",
    "declared_duration_months", "dur_was_imputed", "duration_quality_flag",
    "estimated_end_date", "is_digital_scope", "category_label", "study_end_date",
]


def build_source_population(clean: pd.DataFrame, cfg) -> tuple[pd.DataFrame, dict]:
    """The common eligible source population: in-scope APPEL_OFFRE notices.

    Requires buyer_key/buyer_key_type already attached (identity_boamp).
    Built ONCE and shared by both layers - Layer 2 only ADDS identity columns.
    """
    study_end_date = clean["publication_date"].max()
    appel_offre_all = clean.loc[clean["notice_type_normalized"] == "APPEL_OFFRE"]
    sources = appel_offre_all.loc[appel_offre_all["is_digital_scope"]].copy()

    sources["estimated_end_date"] = sources.apply(
        lambda r: (r["start_date"] + relativedelta(months=int(round(r["declared_duration_months"]))))
        if pd.notna(r["start_date"]) and pd.notna(r["declared_duration_months"]) else pd.NaT,
        axis=1,
    )
    sources["study_end_date"] = study_end_date

    info = {
        "study_end_date": study_end_date,
        "n_appel_offre_all_sectors": len(appel_offre_all),
        "n_sources_digital_scope": len(sources),
        "n_sources_cpv_only": int(appel_offre_all["is_digital_scope_cpv_only"].sum()),
    }
    return sources[SOURCE_COLUMNS], info
