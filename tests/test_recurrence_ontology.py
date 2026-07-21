import yaml

REPO = __import__("pathlib").Path(__file__).resolve().parents[1]
ONTOLOGY_PATH = REPO / "config" / "synthetic" / "recurrence_ontology.yaml"

REQUIRED_FIELDS = [
    "description", "applies_to", "same_buyer_requirement", "siret_or_siren_level",
    "cpv_change_allowance", "scope_change_allowance", "cardinality",
    "temporal_ordering", "strict_label", "broad_label", "survival_event_treatment",
]


def _load():
    with open(ONTOLOGY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_ontology_loads():
    ontology = _load()
    assert "relations" in ontology
    assert "enums" in ontology


def test_minimum_relation_types_present():
    relations = _load()["relations"]
    required = {
        "NEXT_CYCLE", "PARTIAL_RECURRENCE", "SPLIT", "MERGE",
        "SAME_THEME_DIFFERENT_NEED", "UNRELATED", "NO_SUCCESSOR", "UNCERTAIN",
    }
    assert required <= set(relations)


def test_every_relation_defines_all_required_fields():
    relations = _load()["relations"]
    for name, rel in relations.items():
        missing = [f for f in REQUIRED_FIELDS if f not in rel]
        assert not missing, f"{name} is missing fields: {missing}"


def test_enum_valued_fields_use_declared_vocabulary():
    ontology = _load()
    enums = ontology["enums"]
    for name, rel in ontology["relations"].items():
        assert rel["same_buyer_requirement"] in enums["same_buyer_requirement"], name
        assert rel["siret_or_siren_level"] in enums["siret_or_siren_level"], name
        assert rel["cpv_change_allowance"] in enums["cpv_change_allowance"], name
        assert rel["scope_change_allowance"] in enums["scope_change_allowance"], name
        assert rel["cardinality"] in enums["cardinality"], name
        assert rel["temporal_ordering"]["requirement"] in enums["temporal_ordering_requirement"], name
        assert rel["survival_event_treatment"]["value"] in enums["survival_event_treatment"], name
        for tag in rel["applies_to"]:
            assert tag in enums["applies_to"], name


def test_uncertain_is_real_data_review_only():
    relations = _load()["relations"]
    uncertain = relations["UNCERTAIN"]
    assert uncertain["applies_to"] == ["real_data_review"]
    assert uncertain["strict_label"] is None
    assert uncertain["broad_label"] is None


def test_exit_criterion_synthetic_relations_have_unambiguous_labels():
    """WP10 exit criterion: every relation the synthetic generator can emit
    must have a non-null boolean interpretation under both strict and broad
    recurrence. UNCERTAIN is the sole, deliberate exception (real-data-review
    only) and is checked separately above.
    """
    relations = _load()["relations"]
    for name, rel in relations.items():
        if "synthetic" not in rel["applies_to"]:
            continue
        assert isinstance(rel["strict_label"], bool), f"{name}.strict_label must be a non-null boolean"
        assert isinstance(rel["broad_label"], bool), f"{name}.broad_label must be a non-null boolean"


def test_no_successor_matches_followup_censoring_convention():
    """NO_SUCCESSOR's survival treatment must match Work Package 9's own
    administrative-censoring definition (delta=0, T=F_i), not a second,
    inconsistent convention.
    """
    rel = _load()["relations"]["NO_SUCCESSOR"]
    assert rel["survival_event_treatment"]["value"] == "censored_administrative"
    assert rel["strict_label"] is False
    assert rel["broad_label"] is False
