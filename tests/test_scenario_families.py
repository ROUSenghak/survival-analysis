import pytest
import yaml

REPO = __import__("pathlib").Path(__file__).resolve().parents[1]
SCENARIOS_DIR = REPO / "config" / "synthetic" / "scenarios"
PARAMETER_INVENTORY_PATH = REPO / "reports" / "tables" / "synthetic_calibration" / "parameter_inventory.csv"

EXPECTED_SCENARIO_FILES = [
    "01_clean_sanity.yaml",
    "02_central_boamp_like.yaml",
    "03_buyer_fragmentation.yaml",
    "04_duration_failure.yaml",
    "05_semantic_drift.yaml",
    "06_adverse_combined.yaml",
]

REQUIRED_FIELDS = [
    "scenario_id", "display_name", "purpose", "intended_stress_mechanism",
    "scientific_justification", "provenance", "baseline_reference", "changed_parameters",
]

VALID_PROVENANCE = {"EMPIRICAL", "SILVER_STANDARD", "LITERATURE_BASED", "SCENARIO_ASSUMPTION"}


def _load(filename):
    with open(SCENARIOS_DIR / filename, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_all_expected_scenario_files_exist():
    present = {p.name for p in SCENARIOS_DIR.glob("*.yaml")}
    assert set(EXPECTED_SCENARIO_FILES) <= present


@pytest.mark.parametrize("filename", EXPECTED_SCENARIO_FILES)
def test_every_scenario_defines_required_fields(filename):
    scenario = _load(filename)
    missing = [f for f in REQUIRED_FIELDS if f not in scenario]
    assert not missing, f"{filename} is missing fields: {missing}"


@pytest.mark.parametrize("filename", EXPECTED_SCENARIO_FILES)
def test_every_scenario_has_valid_provenance(filename):
    scenario = _load(filename)
    assert scenario["provenance"].strip() in VALID_PROVENANCE or set(
        p.strip() for p in scenario["provenance"].replace(",", " ").split()
    ) & VALID_PROVENANCE, f"{filename} provenance must name a Work Package 12 category"


@pytest.mark.parametrize("filename", [f for f in EXPECTED_SCENARIO_FILES if f != "02_central_boamp_like.yaml"])
def test_non_baseline_scenarios_change_at_least_one_parameter(filename):
    scenario = _load(filename)
    assert len(scenario["changed_parameters"]) > 0, f"{filename} must change something relative to the baseline"


def test_central_boamp_like_is_the_unperturbed_baseline():
    scenario = _load("02_central_boamp_like.yaml")
    assert scenario["changed_parameters"] == []


@pytest.mark.parametrize("filename", EXPECTED_SCENARIO_FILES)
def test_every_changed_parameter_entry_is_complete(filename):
    scenario = _load(filename)
    for entry in scenario["changed_parameters"]:
        for field in ["parameter_name", "baseline", "scenario_value", "rationale"]:
            assert field in entry, f"{filename}: changed_parameters entry {entry.get('parameter_name')} missing {field}"


@pytest.mark.slow
def test_changed_parameters_reference_the_frozen_inventory_or_are_flagged_new():
    """Every changed_parameters[].parameter_name must either exist in
    parameter_inventory.csv (Work Package 12) or be explicitly flagged
    is_new_scenario_knob: true - never silently reference a parameter that
    doesn't exist anywhere.
    """
    import pandas as pd
    inventory_names = set(pd.read_csv(PARAMETER_INVENTORY_PATH)["parameter_name"])
    for filename in EXPECTED_SCENARIO_FILES:
        scenario = _load(filename)
        for entry in scenario["changed_parameters"]:
            name = entry["parameter_name"]
            is_new = entry.get("is_new_scenario_knob", False)
            assert name in inventory_names or is_new, (
                f"{filename}: {name} is neither in parameter_inventory.csv nor flagged is_new_scenario_knob"
            )
