from utils.boamp_schema import extract_cpv_codes, extract_siret_siren


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


def test_extract_siret_siren_uses_eforms_contracting_party_role():
    donnees = {
        "EFORMS": {
            "ContractNotice": {
                "ext:UBLExtensions": {
                    "ext:UBLExtension": {
                        "ext:ExtensionContent": {
                            "efext:EformsExtension": {
                                "efac:Organizations": {
                                    "efac:Organization": [
                                        {
                                            "efac:Company": {
                                                "cac:PartyIdentification": {"cbc:ID": {"#text": "ORG-0003"}},
                                                "cac:PartyLegalEntity": {"cbc:CompanyID": "17440005100010"},
                                            }
                                        },
                                        {
                                            "efac:Company": {
                                                "cac:PartyIdentification": {"cbc:ID": {"#text": "ORG-0001"}},
                                                "cac:PartyLegalEntity": {"cbc:CompanyID": "20006786600018"},
                                            }
                                        },
                                        {
                                            "efac:Company": {
                                                "cac:PartyIdentification": {"cbc:ID": {"#text": "ORG-0002"}},
                                                "cac:PartyLegalEntity": {"cbc:CompanyID": "80319892800027"},
                                            }
                                        },
                                    ]
                                }
                            }
                        }
                    }
                },
                "cac:ContractingParty": {
                    "cac:Party": {
                        "cac:PartyIdentification": {"cbc:ID": {"@schemeName": "organization", "#text": "ORG-0001"}},
                        "cac:ServiceProviderParty": {
                            "cac:Party": {
                                "cac:PartyIdentification": {"cbc:ID": {"#text": "ORG-0002"}}
                            }
                        },
                    }
                },
                "cac:ProcurementProjectLot": {
                    "cac:TenderingTerms": {
                        "cac:AppealTerms": {
                            "cac:AppealReceiverParty": {
                                "cac:PartyIdentification": {"cbc:ID": {"#text": "ORG-0003"}}
                            }
                        }
                    }
                },
            }
        }
    }

    sirets, sirens = extract_siret_siren(donnees)
    assert sirets == ["20006786600018"]
    assert sirens == []
