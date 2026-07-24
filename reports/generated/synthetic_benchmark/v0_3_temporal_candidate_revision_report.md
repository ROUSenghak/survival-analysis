# Synthetic benchmark v0.3 temporal/candidate revision report

## Result

**Overall status: READY_FOR_LINKAGE.**

- Conditional fidelity: **PASS**
- Temporal validation: **PASS**
- Candidate environment: **PASS**
- Structural truth: **PASS**

Validation-framework status: **PASS_WITH_WARNINGS**, blocking gates: none.

Critical gates:

- algorithm_utility: **PASS**
- candidate_environment: **PASS**
- conditionals: **PASS**
- internal: **PASS**
- privacy: **PASS**
- specification_recovery: **PASS**
- hidden_truth_difficulty: **WARNING**
- temporal: **WARNING**

Canonical replay from the recorded seeds and the live scenario file was evaluated inside the validation run (internal gate: **PASS**).

## Candidate improvement

- Zero-candidate rate: v0.2 90.4% -> v0.3 63.0%; real 60.9%.
- P75/P90/P95 candidates: v0.3 1/2/3; real 2/6/10.
- Source-count ratio vs scaled real target: 1.12.
- Cap-reached rate: 0.0%.

## Remaining caveats

- The benchmark is credible for running linkage algorithms, but the resulting evaluation is still synthetic-benchmark evidence, not a replacement for inaccessible ground truth.
- Long 60m follow-up remains diagnostic, not a hard blocker for the next linkage stage.
- Linkage-score calibration and threshold optimization were not performed here.
- 18 metrics fail inside non-critical gates (marginals, missingness_text_identifier, buyer_activity, text). Under the documented gate policy these downgrade the run to PASS_WITH_WARNINGS rather than blocking it, and they remain visible in the discrepancy register rather than being tuned away.

## Artifacts

- `notebooks/10_synthetic_temporal_candidate_revision_validation.ipynb`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/temporal_candidate_freeze_gate.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/candidate_environment_validation_gate_by_version.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/validation_gate_summary.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/discrepancy_register.csv`
- `reports/generated/synthetic_benchmark/v0_3_temporal_candidate_revision_report.md`
