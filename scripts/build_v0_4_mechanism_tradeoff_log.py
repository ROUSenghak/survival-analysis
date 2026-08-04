"""Auditable trail of v0.4 mechanism designs that were tested and rejected.

Three of the four mechanism designs below were measured on a real generated world
and discarded. Recording them is the point: each one looked reasonable a priori,
each fixed the metric it targeted, and each broke something else -- which is the
evidence that the accepted design was chosen against the joint acceptance vector
rather than against one failing number.

Schema matches `scripts/build_mechanism_tradeoff_log.py` so the v0.3 and v0.4
logs can be read together.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "v0_4_population_alias_revision"
BASE = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION

FIELDS = [
    "version", "mechanism_id", "component", "status", "provenance_category",
    "retained_mechanism", "tested_change", "intended_improvement", "evidence_level",
    "baseline_validation_status", "baseline_metric_failures", "baseline_blocking_gates",
    "baseline_replay_status", "observed_effect_summary", "quantitative_effect",
    "exact_trial_artifact_preserved", "decision_rationale", "readiness_consequence",
    "source_reference", "limitations",
]

ENTRIES = [
    {
        "mechanism_id": "v04_acceptance_vector_missing_text_metrics",
        "component": "boamp.synthetic.acceptance (development instrument)",
        "status": "CORRECTED",
        "provenance_category": "INSTRUMENT_GAP",
        "retained_mechanism": (
            "Acceptance vector extended with the marginals/text text-length and token-count "
            "metrics, the text gate's ngram, duplication and diversity statistics, and the "
            "hidden-truth difficulty floors, all computed by calling the release gate functions "
            "rather than reimplementing them."
        ),
        "tested_change": (
            "The v0.4 development sweep scored candidate parameter sets on composition, "
            "identifier, activity, name and candidate-environment metrics only. It carried no "
            "text metric and no linkage-difficulty metric."
        ),
        "intended_improvement": (
            "Reject any candidate parameter set that fixes one observable while breaking another."
        ),
        "evidence_level": "found by post-hoc diagnosis of the v0.4 release's only metric failure",
        "observed_effect_summary": (
            "The sweep could not see the failure it was causing. Correcting the buyer population "
            "moved notices into the activity tiers that trigger the same-buyer administrative "
            "template, whose rate was a scalar calibrated at v0.3's tier composition. The "
            "resulting shorter corpus turned text_length W1_scaled from a WARNING into the "
            "release's only FAIL, and nothing in the acceptance vector registered it."
        ),
        "quantitative_effect": (
            "Notices in the eligible 6-20/21+ tiers rose from 79.8% to 94.3%; template firing "
            "rose from 25.8% to 30.6% of notices; the template is 49 characters against a corpus "
            "median of 88-95. text_length W1_scaled 0.162 -> 0.223 against a 0.10 tolerance; "
            "median text length 95 -> 88 against a real 98."
        ),
        "decision_rationale": (
            "The instrument was extended rather than the result excused. A sweep can only reject "
            "a harmful trade-off it can measure, and this one was invisible. The same-buyer "
            "template rate remains uncorrected in v0.4 and is the declared residual; the extended "
            "vector is what a v0.5 attempt at it must be scored on."
        ),
    },
    {
        "mechanism_id": "v04_alias_size_quota_remainder",
        "component": "buyer_names.persistent_aliases",
        "status": "CORRECTED",
        "provenance_category": "IMPLEMENTATION_DEFECT",
        "retained_mechanism": (
            "Alias-set sizes assigned by quota against the calibrated size distribution, with the "
            "flooring remainder given to the most common size."
        ),
        "tested_change": (
            "First implementation gave the flooring remainder to the last size in the sorted list."
        ),
        "intended_improvement": (
            "Match the observable distinct-names-per-SIREN distribution exactly at any buyer count."
        ),
        "evidence_level": "code review, before the release generation",
        "observed_effect_summary": (
            "The calibrated size list runs up to 14 aliases, so the last entry is the largest set, "
            "not the most common one. Flooring loses at most one buyer per distinct size, so up to "
            "about fifteen buyers per world were being handed the largest alias set in the "
            "distribution."
        ),
        "quantitative_effect": (
            "At most 15 of 5,000 buyers (0.3%). The development sweep that ranked the candidate "
            "parameter sets ran under the pre-fix code; the selected parameters were re-verified "
            "on both development seeds under the corrected code before the release was generated."
        ),
        "decision_rationale": (
            "Corrected rather than accepted: the distortion is small but is entirely in the "
            "direction of over-fragmenting buyer names, which is the failure mode this revision "
            "exists to fix."
        ),
    },
    {
        "mechanism_id": "v04_entry_uniform_forward_span",
        "component": "buyers.activity_model / active window",
        "status": "REJECTED",
        "provenance_category": "MECHANISM_PARAMETER",
        "retained_mechanism": (
            "Reference-day window placement with left and right truncation: the buyer draws a "
            "span, then a reference day from the calibrated entry weights, and the window is "
            "placed uniformly around that day and clipped to the observation period."
        ),
        "tested_change": (
            "Drop v0.3's 'active_start uniform over the first 60% of the window' rule and draw "
            "entry uniformly over the whole window, with the span running forward from entry."
        ),
        "intended_improvement": (
            "Remove the mid-window pile-up that made the publication-year mix wrong and, through "
            "it, the aggregate SIRET-availability metric fail."
        ),
        "evidence_level": "measured on one generated world (world_seed 20260721)",
        "observed_effect_summary": (
            "Worse than v0.3. A high-activity buyer born late in the window had its window "
            "clipped at the corpus end and emitted its whole output into the final months."
        ),
        "quantitative_effect": (
            "2025 notice share 23.2% against a real 9.2%; 2026 18.3% against 4.4%; "
            "publication-year TVD 0.19 against v0.3's 0.151."
        ),
        "decision_rationale": (
            "Rejected: it replaced a mid-window bias with a much larger end-window bias."
        ),
    },
    {
        "mechanism_id": "v04_entry_truncated_to_fit",
        "component": "buyers.activity_model / active window",
        "status": "REJECTED",
        "provenance_category": "MECHANISM_PARAMETER",
        "retained_mechanism": "As above.",
        "tested_change": (
            "Draw the span first, then draw entry from the calibrated year weights truncated to "
            "[0, window_length - span] so every buyer's window fits inside the observation period."
        ),
        "intended_improvement": (
            "Stop long-lived buyers from being born late and dumping their output at the end."
        ),
        "evidence_level": "measured over six deconvolution iterations at 2,500 buyers",
        "observed_effect_summary": (
            "Fixed the end-window pile-up and created its mirror image. Forcing long spans to "
            "start early means no buyer window can cover the last years, so the entry-weight "
            "fixed point diverged trying to compensate."
        ),
        "quantitative_effect": (
            "Weight on 2015 ran away from 7.1% to 60.3% over six iterations while the "
            "publication-year WMAE got monotonically worse: 2.68 -> 2.07 -> 2.37 -> 2.84 -> "
            "3.00 -> 2.99 pp."
        ),
        "decision_rationale": (
            "Rejected: buyer windows must be allowed to extend past both ends of the observation "
            "period, because real buyers existed before 2015 and continue after 2026 and the "
            "corpus records only the intersection. With truncation allowed, the same "
            "deconvolution converged to 0.70 pp on its first iteration."
        ),
    },
    {
        "mechanism_id": "v04_untruncated_power_law_tail",
        "component": "buyers.activity_model / heavy tail",
        "status": "REJECTED",
        "provenance_category": "EMPIRICAL_OBSERVABLE (fit) + MECHANISM_PARAMETER (truncation)",
        "retained_mechanism": (
            "Power law truncated at the observable maximum relative activity "
            "(tail_xmax_relative = 190.37, i.e. the largest calibration buyer's 3,185 notices "
            "over the 16.73 mean)."
        ),
        "tested_change": (
            "Sample the tail from the untruncated discrete power law exactly as fitted by the "
            "Clauset-Shalizi-Newman MLE (alpha = 2.036 above x_min = 36)."
        ),
        "intended_improvement": (
            "Reproduce the real upper tail that the v0.3 single-Pareto mechanism was missing."
        ),
        "evidence_level": "measured on one generated world at 5,500 buyers",
        "observed_effect_summary": (
            "The fit is a good description of the real tail and a catastrophic sampler. With "
            "alpha ~= 2 the maximum grows almost linearly in the sample size, so the benchmark "
            "produced a single buyer that dwarfed the corpus."
        ),
        "quantitative_effect": (
            "Largest buyer key held 17,192 of 78,651 notices (21.9%) against a real maximum of "
            "3,185 of 84,623 (3.8%); top-1% share 65.7% against 39.4%; Gini 0.888 against 0.837; "
            "candidate cap-hit rate 44.3% against a 1% tolerance. After truncation on the same "
            "seed: largest key 2,313 notices, top-1% share 34.2%, Gini 0.805, cap-hit rate 0.0%."
        ),
        "decision_rationale": (
            "Rejected: a fitted tail index is not by itself a generative model of a bounded "
            "quantity. Truncation at the observable maximum is the standard treatment and is "
            "itself an observable, not a free parameter."
        ),
    },
    {
        "mechanism_id": "v04_carried_scoped_candidate_block",
        "component": "recurrence.scoped_candidate_environment",
        "status": "REJECTED",
        "provenance_category": "MECHANISM_PARAMETER",
        "retained_mechanism": (
            "The same block re-swept at the v0.4 buyer population against the "
            "candidate-environment gates."
        ),
        "tested_change": (
            "Carry v0.3's selected values unchanged (scoped_need_probability_high 0.54, "
            "scoped_buyer_affinity_share 0.102, recurrence_propensity_multiplier 1.60)."
        ),
        "intended_improvement": (
            "Preserve the v0.3 candidate environment, which passed all of its gates, while only "
            "the buyer population changed."
        ),
        "evidence_level": "measured over the first six candidates of the population sweep",
        "observed_effect_summary": (
            "The block concentrates digital-scope needs into a small share of buyers. That was "
            "calibrated against a corpus fragmented into 10,532 observed keys; at a correctly "
            "sized buyer population the same clustering piles the digital corpus onto a few "
            "large buyers and candidate sets hit the production cap."
        ),
        "quantitative_effect": (
            "Every candidate-environment gate failed on all six trials, including a cap-hit rate "
            "far above the 1% tolerance; tolerance-normalised total deviation 131-141."
        ),
        "decision_rationale": (
            "Rejected: a candidate-environment block is only meaningful relative to the buyer "
            "population it was tuned against, and must be re-swept whenever that population "
            "changes. Total digital-source volume is unaffected by the re-sweep because the "
            "division sampler renormalises the non-affinity probability."
        ),
    },
]

COMMON = {
    "version": VERSION,
    "exact_trial_artifact_preserved": "no (development trial; not written to the release tree)",
    "readiness_consequence": (
        "None: no rejected mechanism reached a released artifact. The accepted design is recorded "
        "in config/synthetic/scenarios/v0_4/central_provisional.yaml and its selection evidence in "
        "reports/tables/synthetic_benchmark/v0_4_population_alias_revision/calibration/."
    ),
    "source_reference": (
        "reports/tables/synthetic_benchmark/v0_4_population_alias_revision/calibration/"
        "{entry_weight_deconvolution_trace.csv,mechanism_parameter_sweep_*.csv,"
        "sweep_population_partial.log}"
    ),
    "limitations": (
        "Each trial was measured on one or two development seeds, so the quoted effects carry "
        "single-world sampling noise. They are recorded as the reason a design was abandoned, not "
        "as precise estimates of that design's behaviour."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    args = parser.parse_args()
    args.base.mkdir(parents=True, exist_ok=True)

    manifest_path = args.base / "validation_framework" / "validation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    replay_path = args.base / "validation_framework" / "replay_replicates.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8")) if replay_path.exists() else {}

    baseline = {
        "baseline_validation_status": str(manifest.get("overall_status", "NOT_YET_RUN")),
        "baseline_metric_failures": str(manifest.get("n_metric_failures", "NOT_YET_RUN")),
        "baseline_blocking_gates": json.dumps(manifest.get("blocking_gates", []), sort_keys=True),
        "baseline_replay_status": str(replay.get("overall_status", "NOT_YET_RUN")),
    }

    rows = [COMMON | baseline | entry for entry in ENTRIES]
    csv_path = args.base / "mechanism_tradeoff_log.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})
    (args.base / "mechanism_tradeoff_log.json").write_text(
        json.dumps(
            {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
             "benchmark_version": VERSION, "entries": rows},
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} rejected-mechanism entries to {csv_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
