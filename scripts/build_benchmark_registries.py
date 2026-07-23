"""Emit the Phase 0 registries the validation specification requires.

Phase 0 asks for definitions to be frozen *before* any real-vs-synthetic
comparison is interpreted: what each table and column means, which parameter
came from where, which scenarios exist, and what tolerance each gate was
predeclared against. All four are generated from the code and config that
actually drive generation and validation rather than transcribed by hand, so a
renamed column or a retuned tolerance shows up in the registry on the next run
instead of silently diverging from it.

Outputs (under reports/tables/synthetic_benchmark/<version>/registries/):
    data_dictionary.csv     one row per table column, with its layer and whether
                            it is visible to a linkage method
    unit_of_analysis.csv    row counts and grain of every benchmark table
    parameter_registry.csv  scenario parameters with provenance class and the
                            in-memory overrides actually applied to the run
    tolerance_registry.csv  every predeclared tolerance, read from the gate code
    scenario_manifest.csv   scenarios and seed replicates generated so far
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic import schemas  # noqa: E402
from boamp.synthetic.validation_framework import loaders  # noqa: E402
from boamp.synthetic.validation_framework.difficulty import TOLERANCES as DIFFICULTY_TOL  # noqa: E402
from boamp.synthetic.validation_framework.fidelity import TOLERANCES as FIDELITY_TOL  # noqa: E402
from boamp.synthetic.validation_framework.robustness import TOLERANCES as ROBUSTNESS_TOL  # noqa: E402
from boamp.synthetic.validation_framework.runner import CRITICAL_GATES  # noqa: E402
from boamp.synthetic.validation_framework.structure import TOLERANCES as STRUCTURE_TOL  # noqa: E402
from boamp.synthetic.validation_framework.text import TOLERANCES as TEXT_TOL  # noqa: E402


# Which layer each table belongs to. "observed" is the only layer a linkage
# method may read; everything else is sealed evaluation truth.
TABLE_LAYERS = {
    "observed_notices": ("observed", "notice", "BOAMP-like notice table exposed to linkage methods"),
    "clean_notices": ("truth", "notice", "pre-corruption notice values, one row per observed notice"),
    "notice_family_membership": ("truth", "notice", "notice to latent cycle mapping with CALL/AWARD role"),
    "true_relations": ("truth", "cycle", "one row per cycle: its successor, or NO_SUCCESSOR"),
    "latent_cycles": ("truth", "cycle", "latent contract cycles with true start and duration"),
    "latent_needs": ("truth", "need", "recurring procurement needs that spawn cycle chains"),
    "latent_buyers": ("truth", "buyer", "latent buying entities with activity and quality propensities"),
    "latent_establishments": ("truth", "establishment", "establishments belonging to a latent buyer"),
    "corruption_log": ("truth", "notice-field-event", "every applied corruption, enabling exact replay"),
}

# Provenance classes carried by the scenario files. EMPIRICAL values are
# calibrated to observable real BOAMP; SCENARIO values encode assumptions about
# properties real BOAMP cannot identify; DERIVED values are re-swept to hit an
# empirical target through a known mechanism.
PARAMETER_PROVENANCE = {
    "recurrence.base_recurrence_propensity": "SCENARIO_UNIDENTIFIED",
    "recurrence.cycle_gap_distribution": "SCENARIO_UNIDENTIFIED",
    "recurrence.max_cycles_per_need": "SCENARIO_UNIDENTIFIED",
    "recurrence.scoped_candidate_environment": "SCENARIO_TUNED_TO_CANDIDATE_TARGETS",
    "identifiers.siret_missing_rate": "EMPIRICAL_OBSERVABLE",
    "identifiers.siren_only_rate": "DERIVED_RESWEPT",
    "identifiers.both_missing_rate": "DERIVED_RESWEPT",
    "identifiers.invalid_identifier_rate": "EMPIRICAL_OBSERVABLE",
    "identifiers.wrong_establishment_siret_rate": "SCENARIO_UNIDENTIFIED",
    "identifiers.year_regime_scale": "EMPIRICAL_OBSERVABLE",
    "identifiers.conditional_siret_presence": "EMPIRICAL_OBSERVABLE",
    "buyer_names.false_split_rate": "EMPIRICAL_OBSERVABLE",
    "buyer_names.false_merge_rate": "EMPIRICAL_OBSERVABLE",
    "buyer_names.generic_collision_rate": "EMPIRICAL_OBSERVABLE",
    "cpv.missing_rate": "EMPIRICAL_OBSERVABLE",
    "cpv.missing_rate_by_condition": "EMPIRICAL_OBSERVABLE",
    "cpv.generic_rate": "EMPIRICAL_OBSERVABLE",
    "cpv.parent_replace_rate": "SCENARIO_UNIDENTIFIED",
    "cpv.division_only_rate": "SCENARIO_UNIDENTIFIED",
    "cpv.wrong_related_rate": "SCENARIO_UNIDENTIFIED",
    "duration.missing_rate": "DERIVED_RESWEPT",
    "duration.missing_rate_by_schema": "DERIVED_RESWEPT",
    "duration.conditional_presence": "EMPIRICAL_OBSERVABLE",
    "duration.rounding_severity": "SCENARIO_UNIDENTIFIED",
    "duration.common_admin_value_rate": "SCENARIO_UNIDENTIFIED",
    "duration.unit_conversion_failure_rate": "SCENARIO_UNIDENTIFIED",
    "text.same_cycle_variation_severity": "DERIVED_RESWEPT",
    "text.next_cycle_drift_severity": "SCENARIO_UNIDENTIFIED",
    "text.hard_negative_overlap_rate": "SCENARIO_UNIDENTIFIED",
    "text.boilerplate_rate": "EMPIRICAL_OBSERVABLE",
    "text.conditional_reuse": "EMPIRICAL_OBSERVABLE",
    "linked_notice_visibility.missing_rate": "EMPIRICAL_OBSERVABLE",
    "conditional_observation": "EMPIRICAL_OBSERVABLE",
    "quality_class_mix": "SCENARIO_UNIDENTIFIED",
}

TOLERANCE_SOURCES = {
    "fidelity": FIDELITY_TOL,
    "structure": STRUCTURE_TOL,
    "text": TEXT_TOL,
    "difficulty": DIFFICULTY_TOL,
    "robustness": ROBUSTNESS_TOL,
}

# Which gate consumes which tolerance module, so the registry says what a
# breach actually costs.
MODULE_GATES = {
    "fidelity": ["marginals", "conditionals", "temporal", "candidate_environment", "missingness_text_identifier"],
    "structure": ["buyer_activity", "missingness_structure", "names_identifiers"],
    "text": ["text", "privacy"],
    "difficulty": ["hidden_truth_difficulty", "algorithm_utility"],
    "robustness": ["robustness"],
}


def _safe_nunique(series: pd.Series) -> object:
    try:
        return int(series.nunique(dropna=True))
    except TypeError:
        return "not countable (list-valued)"


def build_data_dictionary(data) -> pd.DataFrame:
    rows = []
    truth_only = set(schemas.CLEAN_NOTICES_TRUTH_ONLY)
    for table, columns in {
        "observed_notices": schemas.OBSERVED_NOTICES,
        "clean_notices": schemas.CLEAN_NOTICES,
        "notice_family_membership": schemas.NOTICE_FAMILY_MEMBERSHIP,
        "true_relations": schemas.TRUE_RELATIONS,
        "latent_cycles": schemas.LATENT_CYCLES,
        "latent_needs": schemas.LATENT_NEEDS,
        "latent_buyers": schemas.LATENT_BUYERS,
        "latent_establishments": schemas.LATENT_ESTABLISHMENTS,
        "corruption_log": schemas.CORRUPTION_LOG,
    }.items():
        layer, grain, description = TABLE_LAYERS[table]
        frame = getattr(data, {
            "observed_notices": "observed", "clean_notices": "clean",
            "notice_family_membership": "notice_family_membership",
            "true_relations": "true_relations", "latent_cycles": "latent_cycles",
            "latent_needs": "latent_needs", "latent_buyers": "latent_buyers",
            "latent_establishments": "latent_establishments", "corruption_log": "corruption_log",
        }[table])
        for column in columns:
            present = column in frame.columns
            rows.append(
                {
                    "table": table,
                    "layer": layer,
                    "grain": grain,
                    "table_description": description,
                    "column": column,
                    "present_in_output": present,
                    "dtype": str(frame[column].dtype) if present else "",
                    "null_share": round(float(frame[column].isna().mean()), 4) if present else "",
                    # Some latent columns hold list-valued vocabularies, which
                    # are unhashable and have no meaningful distinct count.
                    "n_distinct": _safe_nunique(frame[column]) if present else "",
                    "visible_to_linkage": layer == "observed",
                    "truth_only_field": column in truth_only or column.endswith("_true"),
                }
            )
    return pd.DataFrame(rows)


def build_unit_of_analysis(data) -> pd.DataFrame:
    rows = []
    for table, (layer, grain, description) in TABLE_LAYERS.items():
        frame = getattr(data, {
            "observed_notices": "observed", "clean_notices": "clean",
            "notice_family_membership": "notice_family_membership",
            "true_relations": "true_relations", "latent_cycles": "latent_cycles",
            "latent_needs": "latent_needs", "latent_buyers": "latent_buyers",
            "latent_establishments": "latent_establishments", "corruption_log": "corruption_log",
        }[table])
        rows.append(
            {
                "table": table,
                "layer": layer,
                "grain": grain,
                "n_rows": int(len(frame)),
                "n_columns": int(frame.shape[1]),
                "description": description,
            }
        )
    return pd.DataFrame(rows)


def _flatten(prefix: str, value) -> list[tuple[str, object]]:
    if isinstance(value, dict):
        out = []
        for key, item in value.items():
            out.extend(_flatten(f"{prefix}.{key}" if prefix else str(key), item))
        return out
    return [(prefix, value)]


def build_parameter_registry(project_root: Path, scenario: str, metadata: dict) -> pd.DataFrame:
    scenario_path = project_root / "config" / "synthetic" / "scenarios" / f"{scenario}.yaml"
    raw = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
    override = (metadata.get("candidate_revision") or {}).get("parameters") or {}

    rows = []
    for key, value in _flatten("", raw):
        if key in {"scenario_id", "display_name", "version", "purpose", "provenance", "references", "baseline_reference"}:
            continue
        if key.endswith(".note") or key.endswith("note"):
            continue
        provenance = "UNCLASSIFIED"
        for prefix, label in PARAMETER_PROVENANCE.items():
            if key == prefix or key.startswith(prefix + "."):
                provenance = label
                break
        override_key = key.split(".")[-1]
        overridden = override_key in override and key.startswith("recurrence.scoped_candidate_environment")
        rows.append(
            {
                "parameter": key,
                "scenario_file_value": value,
                "provenance_class": provenance,
                "overridden_at_runtime": overridden,
                "effective_value": override.get(override_key, value) if overridden else value,
                "scenario": scenario,
                "scenario_file": str(scenario_path.relative_to(project_root)),
                "generator_version": metadata.get("generator_version", ""),
            }
        )
    frame = pd.DataFrame(rows)
    unclassified = frame.loc[frame["provenance_class"].eq("UNCLASSIFIED"), "parameter"].tolist()
    if unclassified:
        print(f"  note: {len(unclassified)} parameter(s) have no provenance class yet: {unclassified[:8]}")
    return frame


def build_tolerance_registry() -> pd.DataFrame:
    rows = []
    for module, tolerances in TOLERANCE_SOURCES.items():
        for name, value in tolerances.items():
            for gate in MODULE_GATES[module]:
                rows.append(
                    {
                        "module": module,
                        "tolerance_key": name,
                        "value": value,
                        "gate": gate,
                        "gate_is_critical": CRITICAL_GATES.get(gate, False),
                        "breach_consequence": "blocks release" if CRITICAL_GATES.get(gate, False) else "documented in fidelity budget",
                    }
                )
    return pd.DataFrame(rows)


def build_scenario_manifest(project_root: Path, version: str) -> pd.DataFrame:
    rows = []
    for scenario, world, corruption in loaders.available_replicates(project_root, version):
        directory = loaders.benchmark_output_dir(project_root, version, scenario, world, corruption)
        metadata = pd.read_json(directory / "generation_metadata.json", typ="series")
        rows.append(
            {
                "benchmark_version": version,
                "scenario": scenario,
                "world": world,
                "corruption": corruption,
                "world_seed": metadata.get("world_seed"),
                "corruption_seed": metadata.get("corruption_seed"),
                "generator_version": metadata.get("generator_version"),
                "git_commit": metadata.get("git_commit"),
                "n_observed_notices": (metadata.get("row_counts") or {}).get("observed_notices"),
                "path": str(directory.relative_to(project_root)),
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        seeds = frame.groupby("scenario").size()
        thin = seeds[seeds < 2]
        if len(thin):
            print(
                f"  note: {list(thin.index)} have a single seed replicate; seed-stability claims are "
                "not supportable for them"
            )
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v0_3_temporal_candidate_revision")
    parser.add_argument("--scenario", default="central_provisional")
    parser.add_argument("--world", default="001")
    parser.add_argument("--corruption", default="001")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    data = loaders.load_benchmark_data(ROOT, args.version, args.scenario, args.world, args.corruption)
    out_dir = args.output_dir or (
        ROOT / "reports" / "tables" / "synthetic_benchmark" / args.version / "registries"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    artifacts = {
        "data_dictionary.csv": build_data_dictionary(data),
        "unit_of_analysis.csv": build_unit_of_analysis(data),
        "parameter_registry.csv": build_parameter_registry(ROOT, args.scenario, data.metadata),
        "tolerance_registry.csv": build_tolerance_registry(),
        "scenario_manifest.csv": build_scenario_manifest(ROOT, args.version),
    }
    for name, frame in artifacts.items():
        frame.to_csv(out_dir / name, index=False)
        print(f"wrote {out_dir.relative_to(ROOT) / name} ({len(frame)} rows)")


if __name__ == "__main__":
    main()
