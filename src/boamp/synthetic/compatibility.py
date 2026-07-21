"""Phase 12 compatibility check: adapt `observed_notices.parquet` into the
column shape the existing Layer 1 candidate-generation code
(`boamp.linkage.candidates.generate_pairs_single_key`) expects, so its
emergent candidate-count statistics can be compared against the real
corpus's own candidate-environment tables (USE_AS_FIDELITY_TARGET,
`generator_parameter_actions.csv`).

This performs no linkage and makes no accuracy claim (spec Phase 12: "Do not
yet claim real-world linkage accuracy" — "You may prepare compatibility
checks showing that the existing Layer 1 and Layer 2 code can consume
observed_notices.parquet"). It reuses the real production buyer-key,
CPV-genericity and identifier-validation logic directly (`identity_boamp`,
`prepare.cpv_is_generic`, `utils.identifiers`) rather than re-deriving it, so
"compatible" means the same thing here as it does for real BOAMP data.
"""
from __future__ import annotations

import pandas as pd

from boamp.data.identity_boamp import build_boamp_buyer_key
from boamp.data.prepare import cpv_is_generic
from utils.identifiers import normalize_buyer_name, validate_siren, validate_siret


def adapt_observed_notices_to_sources(observed: pd.DataFrame) -> pd.DataFrame:
    """observed_notices.parquet -> the `sources`-shaped frame
    `generate_pairs_single_key` expects. Duration imputation here mirrors
    `boamp.data.prepare`'s median-by-CPV-division rule exactly (same rule,
    applied to the synthetic corpus), so the fidelity comparison isn't
    confounded by using a different imputation convention than the real
    pipeline uses on real data.
    """
    df = observed.copy()

    siret_valid = df["buyer_siret_raw"].map(lambda v: all(validate_siret(v)) if pd.notna(v) else False)
    df["buyer_siret_clean"] = df["buyer_siret_raw"].where(siret_valid)
    siren_valid = df["buyer_siren_raw"].map(lambda v: all(validate_siren(v)) if pd.notna(v) else False)
    df["buyer_siren_clean"] = df["buyer_siren_raw"].where(siren_valid)
    df["buyer_name_normalized"] = df["buyer_name_raw"].map(normalize_buyer_name)

    df = build_boamp_buyer_key(df)

    df["cpv_main"] = df["cpv_clean"]
    df["cpv_division"] = df["cpv_main"].str[0:2]
    df["cpv_group"] = df["cpv_main"].str[0:3]
    df["cpv_class"] = df["cpv_main"].str[0:4]
    df["cpv_category"] = df["cpv_main"].str[0:5]
    df["cpv_generic_flag"] = df["cpv_main"].map(lambda v: cpv_is_generic(v) if pd.notna(v) else False)

    df["notice_id"] = df["notice_id_synthetic"]

    div_medians = df.groupby("cpv_division")["declared_duration_months"].median()
    global_median = df["declared_duration_months"].median()
    needs_impute = df["declared_duration_months"].isna()
    df["dur_was_imputed"] = needs_impute
    imputed_vals = df.loc[needs_impute, "cpv_division"].map(div_medians).fillna(global_median)
    df.loc[needs_impute, "declared_duration_months"] = imputed_vals

    duration_for_end_date = df["declared_duration_months"].fillna(global_median)
    df["estimated_end_date"] = df["publication_date"] + pd.to_timedelta(
        (duration_for_end_date * 30.44).round(), unit="D"
    )
    return df
