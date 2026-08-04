# Synthetic Benchmark Readiness Assessment

This is a validated synthetic benchmark only to the readiness level supported above. It cannot prove real BOAMP precision, recall, renewal prevalence, survival estimates, or algorithm ranking.

Benchmark version: `v0_4_population_alias_revision`
Scenario: `central_provisional`
Validation status read from manifest: `PASS_WITH_WARNINGS`
Generated data commit: `3fa502b7bce38f110e0066afd4e9e1afcd11ad34`
Current HEAD: `3fa502b7bce38f110e0066afd4e9e1afcd11ad34`

## Decisions

### PIPELINE_TECHNICALLY_VALID: PASS_WITH_LIMITATIONS

Supporting evidence:
- internal gate: PASS
- specification_recovery gate: PASS
- privacy gate: PASS
- canonical replay checked: True
- all generated artifacts replay: PASS
- replayed artifacts: 51
- source state manifest hashed paths: 0
- worktree dirty: True
- verified dirty-state release package: False
- release package verification status: MISSING

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
- probe linker best pair-F1: 0.26491994177583694

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
- metric failures: 1
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
- source state manifest hashed paths: 0
- worktree dirty: True
- verified dirty-state release package: False
- release package archive sha256: MISSING

Failed hard gates:
- observable hard-fidelity failures remain in non-critical current gates
- headline difficulty varies materially across scenarios and must be scenario-labelled
- cross-scenario probe-linker ranking stability is warning or inconclusive
- worktree has uncommitted or untracked changes, so current HEAD does not fully identify the source/artifact state

Permitted uses:
- not release-ready

Prohibited claims:
- Synthetic precision, recall, recurrence prevalence, or survival estimates equal their unknown real BOAMP values.
- The benchmark proves real-world algorithm ranking or real renewal prevalence.
- Previously accepted BOAMP links, linkage scores, thresholds, or the six-month window are real ground truth.
- A validated synthetic benchmark replaces missing manual/legal BOAMP recurrence labels.

## Current Problem Inventory

- `marginals` / `text_length` / `W1_scaled`: FAIL (real=nan, synthetic=nan, effect=0.2227930094596769, tolerance=0.1)
- `marginals` / `text_length` / `q50_relative_error`: WARNING (real=98.0, synthetic=88.0, effect=0.1020408163265306, tolerance=0.1)
- `marginals` / `text_length` / `q75_relative_error`: WARNING (real=133.0, synthetic=114.0, effect=0.1428571428571428, tolerance=0.1)
- `temporal` / `followup_runway` / `abs_diff_pp`: WARNING (real=0.9167838530895857, synthetic=0.8819368482461898, effect=3.484700484339576, tolerance=3.0)
- `candidate_environment` / `zero_candidate_rate_by_key` / `abs_diff_pp`: WARNING (real=0.4462242562929062, synthetic=0.5475862068965517, effect=10.13619506036455, tolerance=10.0)
- `missingness_text_identifier` / `siret_missing` / `rate_abs_diff_pp`: WARNING (real=0.7277572291221063, synthetic=0.7039548846593257, effect=2.3802344462780622, tolerance=2.0)
- `missingness_text_identifier` / `text_length` / `q50_relative_error`: WARNING (real=98.0, synthetic=88.0, effect=0.1020408163265306, tolerance=0.1)
- `missingness_text_identifier` / `siret_present` / `presence_rate_abs_diff_pp`: WARNING (real=0.2722427708778937, synthetic=0.2960451153406743, effect=2.380234446278057, tolerance=2.0)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.3827800952459733, synthetic=0.31989110090182066, effect=6.288899434415268, tolerance=10.0)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.6612859388109615, synthetic=0.6096283332117942, effect=5.165760559916732, tolerance=10.0)
- `buyer_activity` / `observed_keys_per_notice` / `relative_error`: WARNING (real=0.062252579086064, synthetic=0.045212572011959454, effect=0.2737237127243651, tolerance=0.2)
- `text` / `token_count` / `q50_relative_error`: WARNING (real=17.0, synthetic=13.0, effect=0.2352941176470588, tolerance=0.2)
- `text` / `unigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.448651492885821, tolerance=0.3)
- `text` / `bigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.7846034266814697, tolerance=0.4)
- `robustness` / `blocking_pairs_completeness` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.2922677390775673, effect=0.2922677390775673, tolerance=0.25)
- `robustness` / `probe_headroom` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.637617831459108, effect=0.637617831459108, tolerance=0.25)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `ranking_pairwise_support` / `supported_pair_fraction`: WARNING (real=nan, synthetic=0.6666666666666666, effect=0.6666666666666666, tolerance=0.8)
- `robustness` / `ranking_pairwise_support` / `ambiguous_pair_fraction`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.25)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
