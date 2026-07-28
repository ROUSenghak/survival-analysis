# Synthetic benchmark v0.3 temporal/candidate revision report

> **Authoritative document:** `reports/synthetic_benchmark_technical_report.tex`
> and its compiled PDF. Every statistic there is generated from the artifacts by
> `scripts/build_report_values.py` and gated by
> `scripts/check_report_consistency.py`. This markdown note is a hand-maintained
> summary of the v0.3 revision decisions; where the two differ, the generated
> report is current.

## Result

**Validation-framework status: PASS_WITH_WARNINGS across 210 metrics.**

This is not a final readiness label. The current five-level readiness
assessment is:

- `PIPELINE_TECHNICALLY_VALID`: **PASS_WITH_LIMITATIONS**
- `READY_FOR_PRELIMINARY_MODELING`: **PASS_WITH_LIMITATIONS**
- `READY_FOR_CONTROLLED_ALGORITHM_COMPARISON`: **FAIL**
- `READY_FOR_FINAL_ALGORITHM_RANKING`: **FAIL**
- `READY_FOR_VALIDATED_SYNTHETIC_BENCHMARK_RELEASE`: **FAIL**

The benchmark may be used for preliminary synthetic-only linker debugging and
pipeline integration. It is not ready for controlled algorithm comparison,
final algorithm ranking, or release as a validated synthetic benchmark.

Critical gates:

- algorithm_utility: **PASS**
- candidate_environment: **PASS**
- conditionals: **WARNING**
- internal: **PASS**
- privacy: **PASS**
- specification_recovery: **PASS**
- hidden_truth_difficulty: **WARNING**
- temporal: **WARNING**

Canonical replay from the recorded seeds and the live scenario file was evaluated inside the validation run (internal gate: **PASS**). The all-artifact replay audit also passes for 51 generated artifacts. `source_state_manifest.json` hashes the current dirty source/artifact state for auditability.

Leakage prevention is a hard internal invariant. The observed layer passes
checks for explicit truth columns, unsuffixed hidden-truth alias columns, exact
or normalised truth-ID values, and direct MD5/SHA1/SHA256 hashes of hidden
truth IDs.

Temporal validation now separates chronological `YYYY-MM` publication-period
fit from calendar-month seasonality. Publication year, chronological period,
calendar-month seasonality, schema-by-year, and notice-type-by-year metrics now
pass; the overall temporal gate remains at **WARNING** because the 60-month
follow-up runway is still weak.

## Candidate improvement

- Zero-candidate rate: v0.2 90.4% -> v0.3 38.6%; real 40.7%.
- P75/P90/P95 candidates: v0.3 6/11/13; real 4/9.1/14.
- Source-count ratio vs scaled real target: 1.20.
- Cap-reached rate: 0.0%.
- Primary-department marginal fidelity now passes after removing the synthetic
  `OTHER` bucket and sampling the empirical primary-department tail explicitly
  (`TV=0.031`, `JS=0.005`).

## Blocking and scoring separation

- `PRODUCTION_BLOCKING`: `R_blocking = 0.467`.
- `36M_BLOCKING`: `R_blocking = 0.942`, above the 0.80 widened-window floor.
- `END_TO_END` recall decomposes exactly as
  `R_end_to_end = R_blocking * R_scoring_given_reachable`; for the frozen probes,
  end-to-end pair recall is reported in `probe_linker_results.csv`.
- `ORACLE_CANDIDATE_SCORING` inserts hidden true-successor pairs into the
  production-distractor environment. Oracle metrics are synthetic-only scoring
  diagnostics, not real BOAMP performance estimates.

## Multi-seed and scenario coverage

- Generated artifacts now cover 10 seeds each for `central_provisional`,
  `easier`, `moderate`, `difficult`, and `stress`; `clean_sanity` remains a
  single-seed smoke-test artifact.
- The four required benchmark scenarios (`easier`, `moderate`, `difficult`,
  `stress`) were regenerated for worlds 001-010 and are included in the
  scenario manifest. All generated artifacts replay with exact canonical table
  hashes (`51/51` PASS).
- Central seed summaries are reported in the robustness gate. Production
  blocking completeness has mean 0.399, standard deviation 0.128, empirical
  95% interval 0.182-0.596, worst case 0.145, and one non-pass central seed.
- Probe-headroom pair-F1 has mean 0.281, standard deviation 0.110, empirical
  95% interval 0.068-0.413, and one non-pass central seed.
- `probe_replicate_results.csv` records 150 benchmark-scenario probe results.
  `probe_ranking_stability.csv` shows the top probe is rank 1 in 50% of
  central/moderate seeds and 58% of all benchmark-scenario artifacts, while
  lower-rank orderings still flip; this is enough for diagnostic comparison,
  not final ranking.

## Remaining caveats

- The benchmark is credible for preliminary synthetic-only linkage debugging, but the resulting evaluation is still synthetic-benchmark evidence, not a replacement for inaccessible real BOAMP ground truth.
- Long 60m follow-up remains diagnostic, not a hard blocker for the next linkage stage.
- Linkage-score calibration and threshold optimization were not performed here.
- Two noncritical metrics currently fail: SIRET missing and SIRET present rates
  differ from the real corpus by 4.37 percentage points against a 2 percentage
  point tolerance. The run remains `PASS_WITH_WARNINGS` because the failures are
  noncritical, while buyer-activity concentration, text lexical JS, identifier
  completeness, 60-month follow-up runway, hidden-truth difficulty,
  cross-scenario spread, and probe-ranking diagnostics still carry warnings.
- A tested notice-type split of family-level identifier persistence reduced one
  attribution-specific identifier mismatch but introduced a critical
  conditional text failure and degraded widened blocking reachability. The
  current generator therefore retains family/need-level identifier persistence
  as an explicit reachability-vs-conditional-fidelity trade-off.
- Ten-seed summaries now exist for every required benchmark scenario. Main-scenario
  seed robustness passes for the headline difficulty metrics, but cross-scenario
  spread remains material and probe rankings are unstable even within scenarios;
  this blocks controlled synthetic comparison, final algorithm ranking, and
  release.
- Central metadata now records the current Git HEAD, and `source_state_manifest.json`
  hashes the current dirty source/artifact state. `dirty_state_overlay.tar.gz`
  packages that overlay against the recorded Git HEAD for auditability, and
  `dirty_state_overlay_verification.json` verifies replay onto a clean Git HEAD
  snapshot with no missing files or hash mismatches. A release still requires a
  clean commit or standalone release package.
- Superseded v0.1 artifacts and the notebooks that read them (05-08) were moved to `archive/` on 2026-07-28 and are recorded in `archive/ARCHIVE_MANIFEST.csv`; no active notebook or script reads them. The five-level readiness assessment remains authoritative for current permitted uses and prohibited claims.

## Artifacts

- `notebooks/10_synthetic_temporal_candidate_revision_validation.ipynb`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/temporal_candidate_freeze_gate.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/candidate_environment_validation_gate_by_version.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/validation_gate_summary.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/discrepancy_register.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/probe_replicate_results.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/probe_ranking_stability.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/replay_replicates.json`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/required_scenario_10_seed_generation_manifest.json`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/mechanism_tradeoff_log.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/mechanism_tradeoff_log.json`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/source_state_manifest.json`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/dirty_state_overlay.tar.gz`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/dirty_state_overlay_manifest.json`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/dirty_state_overlay_verification.json`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/registries/parameter_registry.csv`
- `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/readiness/readiness_assessment.md`
- `reports/generated/synthetic_benchmark/v0_3_temporal_candidate_revision_report.md`
