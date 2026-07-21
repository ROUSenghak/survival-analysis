from utils.boamp_schema import extract_cpv_codes


def test_extract_cpv_codes_from_eforms_item_classification_paths():
    donnees = {
        "EFORMS": {
            "ContractNotice": {
                "cac:ProcurementProject": {
                    "cac:MainCommodityClassification": {
                        "cbc:ItemClassificationCode": {"#text": "71400000"}
                    },
                    "cac:AdditionalCommodityClassification": [
                        {"cbc:ItemClassificationCode": {"#text": "71240000"}},
                        {"cbc:ItemClassificationCode": {"#text": "71313000"}},
                    ],
                    "cac:RequestedTenderTotal": {
                        "cbc:EstimatedOverallContractAmount": {"#text": "25500000"}
                    },
                }
            }
        }
    }

    assert extract_cpv_codes(donnees) == ["71400000", "71240000", "71313000"]


def test_extract_cpv_codes_preserves_legacy_cpv_paths():
    donnees = {
        "marche": {
            "CPV": {
                "objetPrincipal": {"classPrincipale": "48000000"},
                "objetSupplementaire": {"classSupplementaire": "72200000"},
            }
        }
    }

    assert extract_cpv_codes(donnees) == ["48000000", "72200000"]
