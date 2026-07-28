# Synthetic benchmark v0.3 temporal/candidate revision report

## Result

**Legacy freeze-gate status: SUPERSEDED_BY_READINESS_ASSESSMENT.**

This notebook-level gate is retained only as historical temporal/candidate
diagnostics. It does not define benchmark readiness. Use the five-level
readiness assessment in
`reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/readiness/`
for permitted uses and prohibited claims.

- Conditional fidelity: **NEEDS_REVISION**
- Temporal validation: **PASS**
- Candidate environment: **PASS**
- Structural truth: **PASS**

## Candidate improvement

- Zero-candidate rate: v0.2 90.4% -> v0.3 38.6%; real 40.7%.
- P75/P90/P95 candidates: v0.3 6/11/13; real 4/9/14.
- Source-count ratio vs scaled real target: 1.20.
- Cap-reached rate: 0.0%.

## Remaining caveats

- This legacy notebook supports preliminary synthetic-only linkage debugging,
  but it is not a controlled-comparison or release-readiness gate.
- The resulting evaluation is still synthetic-benchmark evidence, not a
  replacement for inaccessible real BOAMP recurrence ground truth.
- Long 60m follow-up remains diagnostic, not a hard blocker for the next linkage stage.
- Linkage-score calibration and threshold optimization were not performed here.
- Use the five-level readiness assessment for permitted uses and prohibited claims.

## Artifacts

- `notebooks/10_synthetic_temporal_candidate_revision_validation.ipynb`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/temporal_candidate_freeze_gate.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/candidate_environment_validation_gate_by_version.csv`
- `reports/generated/synthetic_benchmark/v0_3_temporal_candidate_revision_legacy_temporal_candidate_report.md`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/readiness/`
