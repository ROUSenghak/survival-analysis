# Synthetic benchmark v0.2 temporal and candidate validation

## Result

**Legacy freeze-gate status: SUPERSEDED_BY_V0_3_READINESS_ASSESSMENT.**

This v0.2 notebook is retained as historical diagnostic evidence. It does not
define current benchmark readiness; use the v0.3 five-level readiness
assessment for permitted uses and prohibited claims.

Temporal validation status: **PASS**.
Candidate-environment validation status: **NEEDS_REVISION**.

This means the v0.2 benchmark should **not yet be used as the main benchmark
for linkage-algorithm evaluation**. The candidate code runs, but the
algorithm-scope candidate environment does not yet resemble the real Layer 1
source universe closely enough.

## Temporal findings

- Publication-year TVD: 0.149
  against threshold 0.20.
- Schema-by-year WMAE: 0.24pp.
- Notice-type-by-year WMAE: 3.98pp.
- Follow-up runway 12m/24m differences:
  -1.2pp /
  -1.9pp.
- Longer 60m follow-up is underrepresented by
  -10.6pp;
  treat long-horizon survival checks cautiously until the date distribution is
  revised.

## Candidate-environment findings

- Real Layer 1 source count: 3,380.
- Synthetic Layer 1 source-scope count: 354
  versus 383.7 expected after scaling real source
  count to synthetic total volume; ratio = 0.92.
- Zero-candidate rate: real 40.7%,
  synthetic 90.4%.
- P90 candidates per source: real 9,
  synthetic 0.
- Cap-reached rate: real 0.1%,
  synthetic 0.0%.
- Broad all-observed compatibility check: production candidate generation ran
  and produced 33,327 pairs, but that broad universe is
  diagnostic only and is not the algorithm-readiness criterion.

## Interpretation

The conditional generator revision solved the earlier field-fidelity gate, but
the benchmark still needs a temporal/candidate revision before linkage
algorithm evaluation. The main issue is not a linkage-score problem; it is the
observable source universe and candidate environment entering the existing
candidate generator.

Recommended next work:

1. Preserve the now-acceptable `APPEL_OFFRE` + `DIGITAL_ICT` source count, but
   revise within-scope recurrence so enough sources have same-buyer future
   candidates near their expected end dates.
2. Calibrate buyer-key reuse, digital CPV/text assignment, and duration/end-date
   co-occurrence inside the algorithm source scope without using linkage scores
   or thresholds as tuning targets.
3. Rerun this notebook and require the candidate-environment gate to pass
   before running linkage-score comparisons.

## Saved artifacts

- `notebooks/09_synthetic_temporal_candidate_validation.ipynb`
- `reports/tables/synthetic_benchmark/v0_2_conditional_revision/temporal_candidate_freeze_gate.csv`
- `reports/tables/synthetic_benchmark/v0_2_conditional_revision/candidate_environment_validation_gate.csv`
- `reports/generated/synthetic_benchmark/v0_2_temporal_candidate_validation_report.md`
