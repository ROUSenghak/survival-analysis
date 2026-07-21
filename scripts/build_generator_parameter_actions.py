"""Build reports/tables/synthetic_calibration/generator_parameter_actions.csv.

Derives the synthetic-benchmark v0.1 generator-parameter decision inventory
from the two existing calibration inventories produced by
notebooks/04_synthetic_benchmark_calibration.ipynb:

- reports/tables/synthetic_calibration/parameter_inventory.csv
  (34 rows, generator-component-oriented, has `ready_to_freeze`)
- reports/tables/synthetic_calibration/calib_parameter_provenance_inventory.csv
  (47 rows, section-oriented OBSERVABLE/SILVER_STANDARD/UNIDENTIFIED tiering)
- reports/tables/synthetic_calibration/calib_unidentified_parameters_scenarios.csv
  (5 rows, explicit scenario-knob proposals)

This script does not re-derive any calibration numbers; it only classifies
existing rows into one of four generator actions
(USE_DIRECTLY / USE_AS_FIDELITY_TARGET / SCENARIO_PARAMETER / DO_NOT_USE) so
the v0.1 generator config can point at a single decision table instead of
three differently-shaped inventories. Deduplicates by parameter_name,
preferring parameter_inventory.csv's row (has generator_component and
ready_to_freeze) and falling back to calib_parameter_provenance_inventory.csv
otherwise.

Rerun with: python scripts/build_generator_parameter_actions.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CALIB_DIR = ROOT / "reports" / "tables" / "synthetic_calibration"

OUT_COLUMNS = [
    "parameter_name", "definition", "generator_component", "provenance",
    "ready_to_freeze", "action", "source_table", "conditioning_variables",
    "unit", "limitations", "notes",
]

# Parameters that describe the pipeline's *own* algorithmic choices or the
# output of its own threshold-based decisions. These must never define
# synthetic-world truth, even though several are LITERATURE_BASED/HIGH
# confidence and ready_to_freeze=True in parameter_inventory.csv — freezable
# does not mean "safe to use as generator truth" here.
FORCE_DO_NOT_USE = {
    "temporal_window_months": "The pipeline's current 6-month blocking window; the generator must not constrain true successor gaps to it (some true NEXT_CYCLE gaps must fall outside it, per spec).",
    "max_candidates_per_source_cap": "The pipeline's current 30-candidate cap; a computational-cost constant, not evidence about true candidate density.",
    "composite_score_weights": "The pipeline's current fixed a-priori score weights (unfitted); only useful for later replicating the linker's own scoring, never for generating synthetic truth.",
    "frozen_link_thresholds": "The pipeline's current frozen broad/balanced/strict thresholds; algorithm-conditioned acceptance cutoffs, not properties of the world.",
    "cpv_similarity_ladder": "Reused only to define the recurrence ontology's cpv_change_allowance *vocabulary* (config/synthetic/recurrence_ontology.yaml); must not be used to set the magnitude of injected CPV corruption, which is a scenario/corruption-mechanism decision instead.",
}

# Candidate-count / candidate-environment parameters are algorithm-conditioned
# (they depend on the pipeline's own blocking/window/cap) but are exactly the
# kind of emergent output the generator should be validated against, per
# Phase 9/13's "candidate counts are emergent validation targets. Do not
# assign candidate counts directly during generation."
FORCE_FIDELITY_TARGET = {
    "candidates_per_source_distribution": "Algorithm-conditioned (pipeline's own blocking/window/cap); use only as a post-hoc fidelity target for observed_notices candidate generation, never as a generation input.",
    "zero_candidate_source_rate": "SILVER_STANDARD / algorithm-conditioned; fidelity target only, per the same reasoning.",
    "text_similarity_plausible_recurrence_proxy": "Structural comparison group (same-SIRET/same-detailed-CPV pairs), not verified recurrence truth; use as a text-generation fidelity target only.",
    "text_similarity_same_buyer_distractor": "Distractor calibration target for hard-negative text generation, not a truth parameter.",
    "text_similarity_same_theme_distractor": "Distractor calibration target for SAME_THEME_DIFFERENT_NEED-style hard-negative text, not used in v0.1 (v0.1 ontology has no SAME_THEME_DIFFERENT_NEED relation) but retained as a text-realism fidelity target.",
    "text_similarity_unrelated_baseline": "True-negative background similarity target for background/hard-negative text generation.",
    "hard_negative_similarity_threshold": "Anchored to this notebook's own baseline distribution, not externally validated; fidelity target only.",
    "duration_imputation_rate": "Scoped to the pipeline's own eligible-source subset (APPEL_OFFRE & is_digital_scope); use as a secondary fidelity check on the *prepared* corpus's imputation behaviour, not as a v0.1 corruption-injection input (use duration_missing_rate, full-corpus, for that).",
    "key_technical_term_vocabulary_size": "A heuristic CountVectorizer vocabulary size (not a validated technical taxonomy); use only to loosely size the synthetic technical-term vocabulary, then check emergent text overlap against it.",
}

# Explicit correction for Phase 2 instruction #2: this parameter's name and
# generator_component are relabeled so nobody downstream mistakes a
# same-cycle (notice-family / lifecycle-episode) publication-similarity
# measurement for a true next-cycle recurrence text-drift measurement, which
# does not exist anywhere in this repo (see calib_unidentified_parameters_scenarios.csv,
# true_text_corruption_process).
RELABEL_GENERATOR_COMPONENT = {
    "text_similarity_next_cycle_proxy": "text_generation.same_cycle_publication_variation",
}
RELABEL_NOTES = {
    "text_similarity_next_cycle_proxy": (
        "CORRECTED LABEL: this measures same-provisional-notice-family "
        "(i.e. same procurement CYCLE, e.g. call+award of one episode) "
        "publication-level text similarity, NOT true next-cycle recurrence "
        "text drift. Use directly to calibrate clean_notices' same-cycle "
        "publication variation mechanism only. True next-cycle text drift "
        "has no empirical anchor in this repo and remains a scenario "
        "parameter (see true_text_corruption_process)."
    ),
}

# The 5 explicitly unidentified parameters from
# calib_unidentified_parameters_scenarios.csv: always SCENARIO_PARAMETER,
# and precision/recall must never be generator inputs (Phase 2 instruction #1)
# even as a scenario knob for the *world* (they remain valid only as knobs
# for an *injected/simulated* linker in later, separate evaluation work,
# never for defining synthetic recurrence truth itself).
UNIDENTIFIED_GENERATOR_COMPONENT = {
    "true_recurrence_prevalence": "cycles.successor_decision",
    "true_linkage_precision_recall": "NOT_A_GENERATOR_PARAMETER",
    "true_buyer_entity_resolution_rate": "corruption.buyer_name_corruption",
    "true_candidate_ambiguity_resolution": "needs.same_buyer_same_cpv_distinct_need",
    "true_text_corruption_process": "text_generation.next_cycle_drift",
}


def _action_for_row(name: str, provenance: str, ready_to_freeze) -> str:
    if name in FORCE_DO_NOT_USE:
        return "DO_NOT_USE"
    if name in FORCE_FIDELITY_TARGET:
        return "USE_AS_FIDELITY_TARGET"
    if provenance == "SCENARIO_ASSUMPTION":
        return "SCENARIO_PARAMETER"
    if provenance == "SILVER_STANDARD":
        return "DO_NOT_USE"
    if provenance in ("EMPIRICAL", "LITERATURE_BASED"):
        if ready_to_freeze is True or ready_to_freeze == "True":
            return "USE_DIRECTLY"
        return "USE_AS_FIDELITY_TARGET"
    return "USE_AS_FIDELITY_TARGET"


def main() -> None:
    pinv = pd.read_csv(CALIB_DIR / "parameter_inventory.csv")
    prov = pd.read_csv(CALIB_DIR / "calib_parameter_provenance_inventory.csv")
    unident = pd.read_csv(CALIB_DIR / "calib_unidentified_parameters_scenarios.csv")

    rows = []
    seen = set()

    for _, r in pinv.iterrows():
        name = r["parameter_name"]
        seen.add(name)
        action = _action_for_row(name, r["provenance"], r["ready_to_freeze"])
        notes = RELABEL_NOTES.get(name, "")
        if name in FORCE_DO_NOT_USE:
            notes = (notes + " " if notes else "") + FORCE_DO_NOT_USE[name]
        if name in FORCE_FIDELITY_TARGET:
            notes = (notes + " " if notes else "") + FORCE_FIDELITY_TARGET[name]
        rows.append(dict(
            parameter_name=name,
            definition=r["definition"],
            generator_component=RELABEL_GENERATOR_COMPONENT.get(name, r["generator_component"]),
            provenance=r["provenance"],
            ready_to_freeze=r["ready_to_freeze"],
            action=action,
            source_table="parameter_inventory.csv",
            conditioning_variables=r["conditioning_variables"],
            unit=r["unit"],
            limitations=r["limitations"],
            notes=notes,
        ))

    # Process the 5 explicit unidentified-parameter rows BEFORE the generic
    # section-oriented inventory below: several of them (e.g.
    # true_linkage_precision_recall) also appear as UNIDENTIFIED rows in
    # calib_parameter_provenance_inventory.csv, and the hand-written notes
    # here (esp. the precision/recall prohibition) must win over the generic
    # figure_or_table_ref note the section-oriented loop would otherwise
    # produce.
    for _, r in unident.iterrows():
        name = r["parameter_name"]
        if name in seen:
            continue
        seen.add(name)
        rows.append(dict(
            parameter_name=name,
            definition=r["why_unidentified"],
            generator_component=UNIDENTIFIED_GENERATOR_COMPONENT.get(name, "unassigned"),
            provenance="UNIDENTIFIED",
            ready_to_freeze=False,
            action="SCENARIO_PARAMETER",
            source_table="calib_unidentified_parameters_scenarios.csv",
            conditioning_variables="n/a",
            unit="n/a (scenario range)",
            limitations=r["justification_or_none"],
            notes=(
                f"proposed_scenario_range={r['proposed_scenario_range']}. "
                + ("NEVER a generator parameter for synthetic-world truth; only "
                   "valid as a knob for an injected/simulated linker in later, "
                   "separate evaluation work." if name == "true_linkage_precision_recall" else "")
            ),
        ))

    # SILVER_STANDARD-tier and any OBSERVABLE rows from the section-oriented
    # inventory not already covered above (e.g. candidate_environment,
    # notice_family, missingness §15c granular rows) — add as
    # USE_AS_FIDELITY_TARGET / DO_NOT_USE per the same rule, deduped by a
    # normalized parameter_id (prov's rows use parameter_id, not
    # parameter_name; keep both distinguishable via source_table).
    for _, r in prov.iterrows():
        pid = r["parameter_id"]
        if pid in seen:
            continue
        seen.add(pid)
        gen_use = r["generator_use_status"]  # CALIBRATE / DO_NOT_CALIBRATE / SCENARIO_KNOB
        if gen_use == "DO_NOT_CALIBRATE":
            action = "DO_NOT_USE"
        elif gen_use == "SCENARIO_KNOB":
            action = "SCENARIO_PARAMETER"
        else:  # CALIBRATE
            action = "USE_DIRECTLY" if r["tier"] == "OBSERVABLE" else "USE_AS_FIDELITY_TARGET"
        rows.append(dict(
            parameter_name=pid,
            definition=r["parameter_name"],
            generator_component=f"section_{r['notebook_section']}",
            provenance=r["tier"],
            ready_to_freeze=(action == "USE_DIRECTLY"),
            action=action,
            source_table=r["source_file"],
            conditioning_variables=r["stratification"],
            unit=r["unit"],
            limitations=r["caveat"],
            notes=f"figure_or_table_ref={r['figure_or_table_ref']}",
        ))

    out = pd.DataFrame(rows, columns=OUT_COLUMNS).sort_values(
        ["action", "parameter_name"]
    ).reset_index(drop=True)

    valid_actions = {"USE_DIRECTLY", "USE_AS_FIDELITY_TARGET", "SCENARIO_PARAMETER", "DO_NOT_USE"}
    assert set(out["action"]) <= valid_actions, set(out["action"]) - valid_actions
    assert out["parameter_name"].is_unique, out["parameter_name"][out["parameter_name"].duplicated()]

    out_path = CALIB_DIR / "generator_parameter_actions.csv"
    out.to_csv(out_path, index=False)
    print(f"wrote {len(out)} rows -> {out_path}")
    print(out["action"].value_counts())


if __name__ == "__main__":
    main()
