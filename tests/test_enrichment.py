import pandas as pd
import pytest

from boamp.data.identity_enriched import (
    build_alias_bridge,
    clean_siren,
    clean_siret,
    dept_key,
    enrich_clean_notices,
    is_generic_alias,
)


def test_clean_siren_from_various_inputs():
    assert clean_siren("552100554") == "552100554"
    assert clean_siren("552 100 554") == "552100554"
    assert clean_siren("55210055400013") == "552100554"  # SIRET -> SIREN prefix
    assert clean_siren("12345") is None
    assert clean_siren(None) is None


def test_clean_siret():
    assert clean_siret("55210055400013") == "55210055400013"
    assert clean_siret("552100554") is None


def test_dept_key():
    assert dept_key("44;49") == "44;49"
    assert dept_key("Loire-Atlantique (44)") == "44"
    assert dept_key(None) is None


def test_generic_alias_stoplist(cfg):
    assert is_generic_alias("mairie", cfg) is True
    assert is_generic_alias("abc", cfg) is True            # below min length
    assert is_generic_alias("nantes metropole", cfg) is False
    assert is_generic_alias(None, cfg) is True


def test_enrich_refuses_duplicate_join_keys():
    clean = pd.DataFrame({"notice_id": ["n1"], "buyer_key": ["K"], "buyer_siret_raw": [None],
                          "buyer_siret_clean": [None], "buyer_siren_clean": [None],
                          "buyer_name_normalized": ["x"]})
    enrichment = pd.DataFrame({"notice_id": ["n1", "n1"], "buyer_siren_enriched_raw": ["a", "b"]})
    with pytest.raises(ValueError, match="many-to-many"):
        enrich_clean_notices(clean, enrichment)


def _enriched_clean_fixture():
    """Rows carrying validated enriched SIRENs for the alias bridge."""
    def row(nid, name, dept, siren, date):
        return {
            "notice_id": nid,
            "buyer_name_raw": name.upper(),
            "buyer_name_normalized": name,
            "buyer_name_enrichment_normalized": name,
            "code_departement": dept,
            "enrichment_department_key": dept,
            "buyer_siren_enriched": siren,
            "buyer_siren_enriched_valid": True,
            "buyer_identity_conflict": False,
            "buyer_legal_name_enriched_display": name,
            "publication_date": pd.Timestamp(date),
        }
    rows = [
        # unambiguous, support 2, non-generic -> AUTO_PROPAGATE_ELIGIBLE
        row("n1", "nantes metropole", "44", "111111111", "2024-01-01"),
        row("n2", "nantes metropole", "44", "111111111", "2024-02-01"),
        # two SIRENs for one (name, dept) -> AMBIGUOUS_MULTIPLE_SIREN
        row("n3", "syndicat des eaux", "49", "222222222", "2024-01-01"),
        row("n4", "syndicat des eaux", "49", "333333333", "2024-02-01"),
        # generic name -> GENERIC_ALIAS_REVIEW_ONLY even with support 2
        row("n5", "mairie", "53", "444444444", "2024-01-01"),
        row("n6", "mairie", "53", "444444444", "2024-02-01"),
        # support 1 -> LOW_SUPPORT_REVIEW_ONLY
        row("n7", "angers loire habitat", "49", "555555555", "2024-03-01"),
    ]
    return pd.DataFrame(rows)


def test_alias_bridge_statuses(cfg):
    bridge, ambiguous = build_alias_bridge(_enriched_clean_fixture(), cfg)
    status = bridge.set_index("alias_name_normalized")["confidence_status"]
    assert status["nantes metropole"] == "AUTO_PROPAGATE_ELIGIBLE"
    assert status["syndicat des eaux"] == "AMBIGUOUS_MULTIPLE_SIREN"
    assert status["mairie"] == "GENERIC_ALIAS_REVIEW_ONLY"
    assert status["angers loire habitat"] == "LOW_SUPPORT_REVIEW_ONLY"
    # ambiguous frame excludes only the auto-propagate group
    assert "nantes metropole" not in set(ambiguous["alias_name_normalized"])
    # ambiguous multi-SIREN group must not carry a single siren value
    assert bridge.set_index("alias_name_normalized").loc["syndicat des eaux", "siren"] is None
