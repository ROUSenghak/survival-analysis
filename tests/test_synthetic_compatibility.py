import pandas as pd

from boamp.synthetic.compatibility import adapt_observed_notices_to_sources


def test_adapter_imputes_out_of_range_observed_durations_before_end_date():
    observed = pd.DataFrame(
        [
            {
                "notice_id_synthetic": "NOTICE-1",
                "publication_date": pd.Timestamp("2024-01-01"),
                "notice_type_normalized": "APPEL_OFFRE",
                "schema_family": "EFORMS",
                "buyer_siret_raw": None,
                "buyer_siren_raw": None,
                "buyer_name_raw": "Commune Test",
                "code_departement": "44",
                "cpv_clean": "48000000",
                "declared_duration_months": 12,
                "objet_clean": "Maintenance informatique",
                "linked_call_notice_id": None,
            },
            {
                "notice_id_synthetic": "NOTICE-2",
                "publication_date": pd.Timestamp("2024-02-01"),
                "notice_type_normalized": "APPEL_OFFRE",
                "schema_family": "EFORMS",
                "buyer_siret_raw": None,
                "buyer_siren_raw": None,
                "buyer_name_raw": "Commune Test",
                "code_departement": "44",
                "cpv_clean": "48000001",
                "declared_duration_months": 50000,
                "objet_clean": "Maintenance informatique reseau",
                "linked_call_notice_id": None,
            },
        ]
    )

    adapted = adapt_observed_notices_to_sources(observed)
    invalid_row = adapted.loc[adapted["notice_id"].eq("NOTICE-2")].iloc[0]

    assert invalid_row["dur_was_imputed"]
    assert invalid_row["declared_duration_months"] == 12
    assert invalid_row["estimated_end_date"] < pd.Timestamp("2026-01-01")
