# Synthetic Benchmark Readiness Assessment

This is a validated synthetic benchmark only to the readiness level supported above. It cannot prove real BOAMP precision, recall, renewal prevalence, survival estimates, or algorithm ranking.

Benchmark version: `v0_4_population_alias_revision`
Scenario: `central_provisional`
Validation status read from manifest: `PASS_WITH_WARNINGS`
Generated data commit: `2640115395f69c7f88f2199feda34432935f8eab`
Current HEAD: `2640115395f69c7f88f2199feda34432935f8eab`

## Decisions

### PIPELINE_TECHNICALLY_VALID: PASS

Supporting evidence:
- internal gate: PASS
- specification_recovery gate: PASS
- privacy gate: PASS
- canonical replay checked: True
- all generated artifacts replay: PASS
- replayed artifacts: 51
- source state manifest hashed paths: 274
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
- probe linker best pair-F1: 0.2702169625246548

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

### READY_FOR_CONTROLLED_ALGORITHM_COMPARISON: PASS_WITH_LIMITATIONS

Supporting evidence:
- scenarios present: ['central_provisional', 'clean_sanity', 'difficult', 'easier', 'moderate', 'stress']
- replicates by scenario: {'difficult': 10, 'clean_sanity': 1, 'moderate': 10, 'stress': 10, 'central_provisional': 10, 'easier': 10}
- metric failures: 0
- three evaluation settings reported: True
- required executable scenario configs present: True
- main pairwise comparison support: {'ready': True, 'n_pairs': 3, 'supported_fraction': 1.0, 'ambiguous_fraction': 0.0, 'warning_fraction': 0.0}
- overall pairwise comparison support: {'ready': True, 'n_pairs': 3, 'supported_fraction': 1.0, 'ambiguous_fraction': 0.0, 'warning_fraction': 0.3333333333333333}

Failed hard gates:
- none

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
- observable hard failures: False
- probe ranking summary rows: 21
- probe pairwise comparison rows: 21
- main-scenario top-probe rank-1 frequency: 1.0
- all-benchmark top-probe rank-1 frequency: 1.0
- cross-scenario-mean top-probe rank-1 frequency: 1.0
- main pairwise comparison support: {'ready': True, 'n_pairs': 3, 'supported_fraction': 1.0, 'ambiguous_fraction': 0.0, 'warning_fraction': 0.0}
- overall pairwise comparison support: {'ready': True, 'n_pairs': 3, 'supported_fraction': 1.0, 'ambiguous_fraction': 0.0, 'warning_fraction': 0.3333333333333333}
- cross-scenario pairwise comparison support: {'ready': True, 'n_pairs': 3, 'supported_fraction': 1.0, 'ambiguous_fraction': 0.0, 'warning_fraction': 0.3333333333333333}

Failed hard gates:
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
- source state manifest hashed paths: 274
- worktree dirty: True
- verified dirty-state release package: True
- release package archive sha256: 7449f9f165881cbd654f29c6c8c339919cb107daeba0a7c8810cb429559a9f6a

Failed hard gates:
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

- `marginals` / `text_length` / `W1_scaled`: WARNING (real=nan, synthetic=nan, effect=0.174532627865962, tolerance=0.1)
- `marginals` / `text_length` / `q75_relative_error`: WARNING (real=133.0, synthetic=116.0, effect=0.1278195488721804, tolerance=0.1)
- `temporal` / `followup_runway` / `abs_diff_pp`: WARNING (real=0.9167838530895857, synthetic=0.8819368482461898, effect=3.484700484339576, tolerance=3.0)
- `missingness_text_identifier` / `siret_missing` / `rate_abs_diff_pp`: WARNING (real=0.7277572291221063, synthetic=0.7039670385765332, effect=2.379019054557308, tolerance=2.0)
- `missingness_text_identifier` / `siret_present` / `presence_rate_abs_diff_pp`: WARNING (real=0.2722427708778937, synthetic=0.2960329614234668, effect=2.379019054557308, tolerance=2.0)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.3827800952459733, synthetic=0.3193563285446899, effect=6.342376670128341, tolerance=10.0)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.6612859388109615, synthetic=0.6091664843579085, effect=5.211945445305299, tolerance=10.0)
- `buyer_activity` / `observed_keys_per_notice` / `relative_error`: WARNING (real=0.062252579086064, synthetic=0.04520041809475194, effect=0.2739189482854606, tolerance=0.2)
- `text` / `unigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.4435413764280175, tolerance=0.3)
- `text` / `bigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.7834833391526554, tolerance=0.4)
- `robustness` / `blocking_pairs_completeness` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.28988829846181163, effect=0.2898882984618116, tolerance=0.25)
- `robustness` / `probe_headroom` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.6210798769150476, effect=0.6210798769150476, tolerance=0.25)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `ranking_pairwise_support` / `supported_pair_fraction`: WARNING (real=nan, synthetic=0.6666666666666666, effect=0.6666666666666666, tolerance=0.8)
- `robustness` / `ranking_pairwise_support` / `ambiguous_pair_fraction`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.25)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
