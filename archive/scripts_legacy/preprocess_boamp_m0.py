"""
Step 5 & 6 - Clean BOAMP data for M0 and build the M0 source population.

Inputs:  data/interim/boamp_raw_flattened.csv
Outputs: data/processed/boamp_clean_m0_no_enrichment.csv  (all notice types/sectors, cleaned)
         data/processed/boamp_m0_sources.csv               (APPEL_OFFRE, digital scope only)

No external SIREN/SIRET enrichment is performed anywhere in this script.
Only BOAMP-provided identifiers are cleaned/validated (src/utils/identifiers.py).

Scope: the raw data retrieved by download_boamp.py is already restricted to
Pays de la Loire buyers (server-side `code_departement` filter). This
script additionally applies a digital/ICT CPV-or-keyword hard filter when
constructing boamp_m0_sources.csv, per the internship guide's recommended
scope (CPV divisions 48/72/32/35). See DIGITAL_CPV_DIVISIONS below.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.identifiers import (  # noqa: E402
    normalize_buyer_name,
    siren_from_siret,
    validate_siren,
    validate_siret,
)
from utils.text_clean import clean_objet, normalize_objet  # noqa: E402

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
TABLES_DIR.mkdir(parents=True, exist_ok=True)

MAX_PLAUSIBLE_DURATION_MONTHS = 120  # 10 years; longer values are treated as OUT_OF_RANGE
MIN_PLAUSIBLE_DURATION_MONTHS = 1

# Digital/ICT scope: HARD FILTER on the M0 source population (Step 5-I),
# matching the internship guide's recommended scope exactly - CPV divisions
# 48 (software), 72 (IT services), 32 (telecommunications equipment),
# 35 (security). A notice qualifies if its CPV division is in this set OR
# its cleaned object text hits one of DIGITAL_KEYWORDS: CPV coverage among
# APPEL_OFFRE sources was only ~39% nationally, so requiring an exact CPV
# match alone would silently drop many genuine digital notices that simply
# lack a recoverable CPV code. The CPV-only count is reported separately as
# a sensitivity check (see reports/boamp_m0_preprocessing_report.md).
# This filter applies ONLY to boamp_m0_sources.csv, not to the full cleaned
# dataset (boamp_clean_m0_no_enrichment.csv keeps all notice types/sectors,
# since the ATTRIBUTION reverse-lookup for start_date needs the full
# ATTRIBUTION population regardless of theme).
DIGITAL_CPV_DIVISIONS = {"32", "35", "48", "72"}  # telecom equipment, security, software, IT services
DIGITAL_KEYWORDS = [
    "informatique", "logiciel", "numerique", "numérique", "cloud", "cybersecurite",
    "cybersécurité", "reseau informatique", "réseau informatique", "application web",
    "systeme d'information", "système d'information", "site internet", "infogerance",
    "infogérance", "erp", "progiciel", "developpement logiciel", "développement logiciel",
]

# Pays de la Loire departments - matches the server-side filter already
# applied in download_boamp.py. Used here only as a defense-in-depth
# diagnostic (not a second filter): logs how many cleaned notices fall
# outside this set, which should be ~0 given the download-time filter. A
# nonzero count would flag either a stale (pre-rescope) raw file or a
# genuinely multi-department notice (kept, not dropped - see report).
PDL_DEPARTMENTS = {"44", "49", "53", "72", "85"}


def normalize_notice_type(nature_raw: str) -> str:
    if not isinstance(nature_raw, str) or not nature_raw.strip():
        return "OTHER"
    v = nature_raw.strip().upper()
    if v == "APPEL_OFFRE":
        return "APPEL_OFFRE"
    if v == "ATTRIBUTION":
        return "ATTRIBUTION"
    return "OTHER"


def first_token(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value)
    if not s or s.lower() == "nan":
        return None
    return s.split(";")[0].strip() or None


def cpv_is_generic(cpv_main: str) -> bool:
    """A CPV code is treated as 'generic' if only its 2-digit division is
    meaningful, i.e. the trailing 6 digits are all zero (pattern XX000000).
    This means the notice classified itself at the broadest possible level
    instead of a specific category/class. Documented rule, not a
    third-party list."""
    if not cpv_main or len(cpv_main) != 8:
        return False
    return cpv_main[2:] == "000000"


def tag_digital_scope(cpv_division, objet_normalized) -> bool:
    if cpv_division in DIGITAL_CPV_DIVISIONS:
        return True
    if isinstance(objet_normalized, str):
        for kw in DIGITAL_KEYWORDS:
            if kw in objet_normalized:
                return True
    return False


def main():
    print("Loading flattened interim data...")
    # dtype=str for everything on read: several columns (CPV/SIRET/SIREN
    # candidate strings) are numeric-looking with NaNs, which pandas would
    # otherwise silently coerce to float64 and break later `.str[...]`
    # slicing. duration_months_raw is cast to numeric explicitly below.
    df = pd.read_csv(INTERIM_DIR / "boamp_raw_flattened.csv", low_memory=False, dtype=str)
    df["duration_months_raw"] = pd.to_numeric(df["duration_months_raw"], errors="coerce")
    print(f"Loaded {len(df)} rows")

    # ---- A. Notice ID -------------------------------------------------
    df["notice_id"] = df["notice_id_raw"]
    dupe_ids = df["notice_id"].duplicated().sum()
    if dupe_ids:
        print(f"WARNING: {dupe_ids} duplicate notice_id values found; keeping first occurrence")
        df = df.drop_duplicates(subset="notice_id", keep="first")

    # ---- B. Notice type -------------------------------------------------
    df["notice_type_raw"] = df["nature"]
    df["notice_type_normalized"] = df["nature"].map(normalize_notice_type)

    # ---- C. Dates --------------------------------------------------------
    df["publication_date"] = pd.to_datetime(df["dateparution"], errors="coerce", utc=True).dt.tz_localize(None)
    df["publication_year"] = df["publication_date"].dt.year
    df["publication_month"] = df["publication_date"].dt.month
    df["publication_quarter"] = df["publication_date"].dt.quarter
    # datefindiffusion / datelimitereponse kept as auxiliary, separate columns
    df["end_diffusion_date"] = pd.to_datetime(df["datefindiffusion"], errors="coerce", utc=True).dt.tz_localize(None)
    df["response_deadline"] = pd.to_datetime(df["datelimitereponse"], errors="coerce", utc=True).dt.tz_localize(None)

    # ---- D. Buyer identity (no external enrichment) -----------------------
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

    def buyer_key_and_type(row):
        if pd.notna(row["buyer_siret_clean"]):
            return f"SIRET:{row['buyer_siret_clean']}", "RAW_SIRET"
        if pd.notna(row["buyer_siren_clean"]):
            return f"SIREN:{row['buyer_siren_clean']}", "RAW_SIREN"
        if pd.notna(row["buyer_name_normalized"]):
            return f"NAME:{row['buyer_name_normalized']}", "NAME_FALLBACK"
        return None, "MISSING"

    keys_types = df.apply(buyer_key_and_type, axis=1)
    df["buyer_key"] = keys_types.map(lambda t: t[0])
    df["buyer_key_type"] = keys_types.map(lambda t: t[1])

    # ---- E. Text fields -----------------------------------------------
    df["objet_raw"] = df["objet"]
    df["objet_clean"] = df["objet_raw"].map(clean_objet)
    df["objet_normalized"] = df["objet_clean"].map(normalize_objet)
    df["text_length"] = df["objet_clean"].fillna("").map(len)
    df["token_count"] = df["objet_clean"].fillna("").map(lambda s: len(s.split()))
    df["object_missing_flag"] = df["objet_clean"].isna()

    # ---- F. CPV fields -----------------------------------------------
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

    # ---- Scope tagging (moved ahead of duration so imputation can be
    # computed on the in-scope population only - see below) ----------------
    df["is_digital_scope"] = df.apply(lambda r: tag_digital_scope(r["cpv_division"], r["objet_normalized"]), axis=1)
    df["category_label"] = np.where(df["is_digital_scope"], "DIGITAL_ICT", "OTHER")
    df["is_digital_scope_cpv_only"] = df["cpv_division"].isin(DIGITAL_CPV_DIVISIONS)

    df["_dept_tokens"] = df["code_departement"].fillna("").astype(str).str.split(";")
    df["is_in_pdl"] = df["_dept_tokens"].map(lambda toks: any(t.strip() in PDL_DEPARTMENTS for t in toks))
    n_outside_pdl = int((~df["is_in_pdl"]).sum())
    if n_outside_pdl:
        print(f"WARNING: {n_outside_pdl} cleaned notices have no department in the "
              f"Pays de la Loire set {sorted(PDL_DEPARTMENTS)} - expected ~0 given the "
              f"download-time filter; check for a stale pre-rescope raw file or a "
              f"genuinely multi-department notice (kept, not dropped).")
    df = df.drop(columns=["_dept_tokens"])

    # ---- G. Duration fields --------------------------------------------
    df["duration_raw"] = df["duration_months_raw"]
    in_range = df["duration_raw"].between(MIN_PLAUSIBLE_DURATION_MONTHS, MAX_PLAUSIBLE_DURATION_MONTHS)
    df["declared_duration_months"] = np.where(df["duration_raw"].notna() & in_range, df["duration_raw"], np.nan)
    df["duration_unit"] = np.where(df["declared_duration_months"].notna(), "months", None)
    df["duration_valid"] = df["declared_duration_months"].notna()
    df["duration_quality_flag"] = np.select(
        [
            df["declared_duration_months"].notna(),
            df["duration_raw"].notna() & ~in_range,
        ],
        ["OBSERVED", "OUT_OF_RANGE"],
        default="MISSING",
    )
    df["dur_was_imputed"] = False

    # Documented default imputation: median observed duration within the
    # same CPV division; falls back to the global median observed duration
    # if the division has no observed durations. Computed on the digital
    # + Pays-de-la-Loire APPEL_OFFRE population only (the M0 source scope),
    # not the whole cleaned dataset, so imputed durations reflect the
    # actual in-scope contracts rather than importing out-of-scope behavior.
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

    print(f"Global median observed APPEL_OFFRE duration (months): {global_median}")

    # ---- H. Start date (APPEL_OFFRE only) -------------------------------
    # Reverse-lookup: for each idweb, find ATTRIBUTION notices whose
    # annonce_lie references it (annonce_lie is stored as a ';'-joined list
    # by parse_boamp.py). This uses only BOAMP-native linkage, no enrichment.
    attribution_links = {}
    attr_rows = df.loc[df["notice_type_normalized"] == "ATTRIBUTION", ["notice_id", "annonce_lie", "publication_date"]]
    for _, r in attr_rows.iterrows():
        if pd.isna(r["annonce_lie"]):
            continue
        for ref in str(r["annonce_lie"]).split(";"):
            ref = ref.strip()
            if ref:
                # keep the earliest linked attribution date if multiple exist
                if ref not in attribution_links or r["publication_date"] < attribution_links[ref][1]:
                    attribution_links[ref] = (r["notice_id"], r["publication_date"])

    df["linked_attribution_notice_id"] = df["notice_id"].map(lambda i: attribution_links.get(i, (None, None))[0])
    df["linked_attribution_date"] = df["notice_id"].map(lambda i: attribution_links.get(i, (None, None))[1])

    start_date = df["linked_attribution_date"].where(df["linked_attribution_date"].notna(), df["publication_date"])
    start_source = np.where(df["linked_attribution_date"].notna(), "LINKED_ATTRIBUTION_DATE", "PUBLICATION_DATE_FALLBACK")
    df["start_date"] = start_date
    df["start_date_source"] = start_source

    # ---- Write full cleaned dataset (all notice types) --------------------
    clean_path = PROCESSED_DIR / "boamp_clean_m0_no_enrichment.csv"
    df.to_csv(clean_path, index=False)
    print(f"Wrote cleaned dataset -> {clean_path} ({len(df)} rows)")

    # ---- Step 6: M0 source population (APPEL_OFFRE, digital scope only) ---
    # Digital/ICT is now a HARD FILTER (previously informational-only), per
    # the internship guide's recommended scope. The full cleaned dataset
    # above still keeps all sectors/notice types.
    study_end_date = df["publication_date"].max()
    appel_offre_all = df.loc[df["notice_type_normalized"] == "APPEL_OFFRE"]
    n_appel_offre_all = len(appel_offre_all)
    n_digital_cpv_only = int((appel_offre_all["is_digital_scope_cpv_only"]).sum())
    sources = appel_offre_all.loc[appel_offre_all["is_digital_scope"]].copy()
    print(f"APPEL_OFFRE total (all sectors): {n_appel_offre_all}")
    print(f"APPEL_OFFRE digital scope (CPV-or-keyword, used as M0 sources): {len(sources)}")
    print(f"APPEL_OFFRE digital scope (CPV-division-only, sensitivity check): {n_digital_cpv_only}")
    sources["estimated_end_date"] = sources.apply(
        lambda r: (r["start_date"] + relativedelta(months=int(round(r["declared_duration_months"]))))
        if pd.notna(r["start_date"]) and pd.notna(r["declared_duration_months"]) else pd.NaT,
        axis=1,
    )
    sources["study_end_date"] = study_end_date

    m0_cols = [
        "notice_id", "publication_date", "start_date", "start_date_source",
        "buyer_key", "buyer_key_type", "buyer_name_normalized",
        "buyer_siret_clean", "buyer_siren_clean",
        "objet_clean", "cpv_clean", "cpv_division", "cpv_group", "cpv_class", "cpv_category", "cpv_generic_flag",
        "declared_duration_months", "dur_was_imputed", "estimated_end_date",
        "is_digital_scope", "category_label", "study_end_date",
    ]
    sources_out = sources[m0_cols].rename(columns={"cpv_clean": "cpv_clean"})
    sources_path = PROCESSED_DIR / "boamp_m0_sources.csv"
    sources_out.to_csv(sources_path, index=False)
    print(f"Wrote M0 source population -> {sources_path} ({len(sources_out)} rows)")

    print("\n=== Preprocess summary ===")
    print(f"Total cleaned notices: {len(df)}")
    print(df["notice_type_normalized"].value_counts())
    print(f"APPEL_OFFRE source population: {len(sources_out)}")
    print(f"Study end date (max publication_date observed): {study_end_date}")
    print(f"buyer_key_type distribution:\n{df['buyer_key_type'].value_counts()}")


if __name__ == "__main__":
    main()
