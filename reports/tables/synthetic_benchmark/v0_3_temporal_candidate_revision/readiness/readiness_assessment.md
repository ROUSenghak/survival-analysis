# Synthetic Benchmark Readiness Assessment

This is a validated synthetic benchmark only to the readiness level supported above. It cannot prove real BOAMP precision, recall, renewal prevalence, survival estimates, or algorithm ranking.

Benchmark version: `v0_3_temporal_candidate_revision`
Scenario: `central_provisional`
Validation status read from manifest: `PASS_WITH_WARNINGS`
Generated data commit: `436c9bdec8446043cab317531ad6f9bd34901cef`
Current HEAD: `436c9bdec8446043cab317531ad6f9bd34901cef`

## Decisions

### PIPELINE_TECHNICALLY_VALID: PASS

Supporting evidence:
- internal gate: PASS
- specification_recovery gate: PASS
- privacy gate: PASS
- canonical replay checked: True
- all generated artifacts replay: PASS
- replayed artifacts: 51
- source state manifest hashed paths: 629
- worktree dirty: True
- verified dirty-state release package: True
- release package verification status: PASS

Failed hard gates:
- none

Permitted uses:
- local reproducibility checks
- debugging generator and validation mechanisms

Prohibited claims:
- Synthetic precision, recall, recurrence prevalence, or survival estimates equal their unknown real BOAMP values.
- The benchmark proves real-world algorithm ranking or real renewal prevalence.
- Previously accepted BOAMP links, linkage scores, thresholds, or the six-month window are real ground truth.
- A validated synthetic benchmark replaces missing manual/legal BOAMP recurrence labels.

### READY_FOR_PRELIMINARY_MODELING: PASS_WITH_LIMITATIONS

Supporting evidence:
- validation framework overall_status: PASS_WITH_WARNINGS
- probe linker best pair-F1: 0.3164959378311551

Failed hard gates:
- none

Permitted uses:
- exploratory linker debugging
- pipeline integration tests
- method development dry runs

Prohibited claims:
- Synthetic precision, recall, recurrence prevalence, or survival estimates equal their unknown real BOAMP values.
- The benchmark proves real-world algorithm ranking or real renewal prevalence.
- Previously accepted BOAMP links, linkage scores, thresholds, or the six-month window are real ground truth.
- A validated synthetic benchmark replaces missing manual/legal BOAMP recurrence labels.

### READY_FOR_CONTROLLED_ALGORITHM_COMPARISON: FAIL

Supporting evidence:
- scenarios present: ['central_provisional', 'clean_sanity', 'difficult', 'easier', 'moderate', 'stress']
- replicates by scenario: {'difficult': 10, 'clean_sanity': 1, 'moderate': 10, 'stress': 10, 'central_provisional': 10, 'easier': 10}
- metric failures: 5
- three evaluation settings reported: True
- required executable scenario configs present: True
- main pairwise comparison support: {'ready': True, 'n_pairs': 3, 'supported_fraction': 1.0, 'ambiguous_fraction': 0.0, 'warning_fraction': 0.0}
- overall pairwise comparison support: {'ready': True, 'n_pairs': 3, 'supported_fraction': 1.0, 'ambiguous_fraction': 0.0, 'warning_fraction': 0.3333333333333333}

Failed hard gates:
- observable hard-fidelity failures remain in non-critical current gates

Permitted uses:
- controlled synthetic algorithm comparisons within documented scenarios
- seed-aggregated moderate/central scenario comparisons when all results are labelled synthetic-only

Prohibited claims:
- Synthetic precision, recall, recurrence prevalence, or survival estimates equal their unknown real BOAMP values.
- The benchmark proves real-world algorithm ranking or real renewal prevalence.
- Previously accepted BOAMP links, linkage scores, thresholds, or the six-month window are real ground truth.
- A validated synthetic benchmark replaces missing manual/legal BOAMP recurrence labels.

### READY_FOR_FINAL_ALGORITHM_RANKING: FAIL

Supporting evidence:
- multi-seed ready: True
- required scenario artifacts ready: True
- observable hard failures: True
- probe ranking summary rows: 21
- probe pairwise comparison rows: 21
- main-scenario top-probe rank-1 frequency: 1.0
- all-benchmark top-probe rank-1 frequency: 1.0
- cross-scenario-mean top-probe rank-1 frequency: 1.0
- main pairwise comparison support: {'ready': True, 'n_pairs': 3, 'supported_fraction': 1.0, 'ambiguous_fraction': 0.0, 'warning_fraction': 0.0}
- overall pairwise comparison support: {'ready': True, 'n_pairs': 3, 'supported_fraction': 1.0, 'ambiguous_fraction': 0.0, 'warning_fraction': 0.3333333333333333}
- cross-scenario pairwise comparison support: {'ready': True, 'n_pairs': 3, 'supported_fraction': 1.0, 'ambiguous_fraction': 0.0, 'warning_fraction': 0.3333333333333333}

Failed hard gates:
- observable hard-fidelity failures remain in non-critical current gates
- headline difficulty varies materially across scenarios and must be scenario-labelled
- cross-scenario probe-linker ranking stability is warning or inconclusive

Permitted uses:
- none beyond preliminary labelled diagnostics

Prohibited claims:
- Synthetic precision, recall, recurrence prevalence, or survival estimates equal their unknown real BOAMP values.
- The benchmark proves real-world algorithm ranking or real renewal prevalence.
- Previously accepted BOAMP links, linkage scores, thresholds, or the six-month window are real ground truth.
- A validated synthetic benchmark replaces missing manual/legal BOAMP recurrence labels.

### READY_FOR_VALIDATED_SYNTHETIC_BENCHMARK_RELEASE: FAIL

Supporting evidence:
- validation status: PASS_WITH_WARNINGS
- calendar-month metric present in saved outputs: True
- generated_from_current_head: True
- source state manifest hashed paths: 629
- worktree dirty: True
- verified dirty-state release package: True
- release package archive sha256: a61c2f8c742d8464efc5012d15fb1c726997bac4f72ddb898e281f6e200ac967

Failed hard gates:
- observable hard-fidelity failures remain in non-critical current gates
- headline difficulty varies materially across scenarios and must be scenario-labelled
- cross-scenario probe-linker ranking stability is warning or inconclusive

Permitted uses:
- not release-ready

Prohibited claims:
- Synthetic precision, recall, recurrence prevalence, or survival estimates equal their unknown real BOAMP values.
- The benchmark proves real-world algorithm ranking or real renewal prevalence.
- Previously accepted BOAMP links, linkage scores, thresholds, or the six-month window are real ground truth.
- A validated synthetic benchmark replaces missing manual/legal BOAMP recurrence labels.

## Current Problem Inventory

- `marginals` / `text_length` / `W1_scaled`: WARNING (real=nan, synthetic=nan, effect=0.1623472823472831, tolerance=0.1)
- `marginals` / `text_length` / `q75_relative_error`: WARNING (real=133.0, synthetic=118.0, effect=0.112781954887218, tolerance=0.1)
- `temporal` / `followup_runway` / `abs_diff_pp`: WARNING (real=0.5501577585290052, synthetic=0.4399267399267399, effect=11.023101860226523, tolerance=5.0)
- `missingness_text_identifier` / `siret_missing` / `rate_abs_diff_pp`: FAIL (real=0.7277572291221063, synthetic=0.6866529304029304, effect=4.110429871917587, tolerance=2.0)
- `missingness_text_identifier` / `siren_missing` / `rate_abs_diff_pp`: WARNING (real=0.7277572291221063, synthetic=0.6937385531135531, effect=3.401867600855313, tolerance=2.0)
- `missingness_text_identifier` / `cpv_missing` / `rate_abs_diff_pp`: WARNING (real=0.1706155536910769, synthetic=0.1504922161172161, effect=2.0123337573860782, tolerance=2.0)
- `missingness_text_identifier` / `siret_present` / `presence_rate_abs_diff_pp`: FAIL (real=0.2722427708778937, synthetic=0.3133470695970696, effect=4.110429871917587, tolerance=2.0)
- `missingness_text_identifier` / `siren_present` / `presence_rate_abs_diff_pp`: WARNING (real=0.2722427708778937, synthetic=0.3062614468864469, effect=3.4018676008553186, tolerance=2.0)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.3827800952459733, synthetic=0.33076923076923076, effect=5.201086447674258, tolerance=10.0)
- `buyer_activity` / `relative_notices_per_buyer` / `q99_abs_diff`: FAIL (real=16.20559138768418, synthetic=13.864239926739927, effect=2.341351460944253, tolerance=1.0)
- `text` / `unigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.4409631507433597, tolerance=0.3)
- `text` / `bigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.7825531557249248, tolerance=0.4)
- `robustness` / `blocking_pairs_completeness` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.3012798913836802, effect=0.3012798913836802, tolerance=0.25)
- `robustness` / `probe_headroom` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.5703378913378353, effect=0.5703378913378353, tolerance=0.25)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
