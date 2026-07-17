from utils.identifiers import normalize_buyer_name, siren_from_siret, validate_siren, validate_siret


def test_valid_siren_luhn():
    # 552100554 is the well-known valid SIREN (Saint-Gobain)
    ok_format, ok_checksum = validate_siren("552100554")
    assert ok_format and ok_checksum


def test_invalid_siren_checksum():
    ok_format, ok_checksum = validate_siren("552100555")
    assert ok_format and not ok_checksum


def test_siren_wrong_length():
    assert validate_siren("12345")[0] is False


def test_siret_format():
    assert validate_siret("55210055400013")[0] is True
    assert validate_siret("5521005540001")[0] is False


def test_siren_from_siret():
    assert siren_from_siret("55210055400013") == "552100554"


def test_normalize_buyer_name_accents_and_case():
    assert normalize_buyer_name("Ville de Saint-Étienne") == normalize_buyer_name("VILLE DE SAINT-ETIENNE")
