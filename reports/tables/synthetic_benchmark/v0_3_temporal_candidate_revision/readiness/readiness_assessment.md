# Synthetic Benchmark Readiness Assessment

This is a validated synthetic benchmark only to the readiness level supported above. It cannot prove real BOAMP precision, recall, renewal prevalence, survival estimates, or algorithm ranking.

Benchmark version: `v0_3_temporal_candidate_revision`
Scenario: `central_provisional`
Validation status read from manifest: `PASS_WITH_WARNINGS`
Generated data commit: `9ca1edb91f09f4b39f5e7aa59620145197c9f443`
Current HEAD: `9ca1edb91f09f4b39f5e7aa59620145197c9f443`

## Decisions

### PIPELINE_TECHNICALLY_VALID: PASS_WITH_LIMITATIONS

Supporting evidence:
- internal gate: PASS
- specification_recovery gate: PASS
- privacy gate: PASS
- canonical replay checked: True
- all generated artifacts replay: PASS
- replayed artifacts: 51
- source state manifest hashed paths: 591
- worktree dirty: True

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
- probe linker best pair-F1: 0.37962962962962965

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
- main-scenario top-probe rank-1 frequency: 0.8
- all-benchmark top-probe rank-1 frequency: 0.76
- cross-scenario-mean top-probe rank-1 frequency: 1.0

Failed hard gates:
- headline difficulty varies materially across scenarios and must be scenario-labelled
- main-scenario probe-linker ranking stability is warning or inconclusive
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
- source state manifest hashed paths: 591
- worktree dirty: True

Failed hard gates:
- headline difficulty varies materially across scenarios and must be scenario-labelled
- main-scenario probe-linker ranking stability is warning or inconclusive
- cross-scenario probe-linker ranking stability is warning or inconclusive
- worktree has uncommitted or untracked changes; source_state_manifest.json records the dirty state, but final release still requires a clean commit or standalone release package

Permitted uses:
- not release-ready

Prohibited claims:
- Synthetic precision, recall, recurrence prevalence, or survival estimates equal their unknown real BOAMP values.
- The benchmark proves real-world algorithm ranking or real renewal prevalence.
- Previously accepted BOAMP links, linkage scores, thresholds, or the six-month window are real ground truth.
- A validated synthetic benchmark replaces missing manual/legal BOAMP recurrence labels.

## Current Problem Inventory

- `marginals` / `text_length` / `W1_scaled`: WARNING (real=nan, synthetic=nan, effect=0.1642360109026767, tolerance=0.1)
- `temporal` / `followup_runway` / `abs_diff_pp`: WARNING (real=0.5501577585290052, synthetic=0.4479144611475757, effect=10.224329738142943, tolerance=5.0)
- `missingness_text_identifier` / `siret_missing` / `rate_abs_diff_pp`: WARNING (real=0.7277572291221063, synthetic=0.6921448232055897, effect=3.56124059165166, tolerance=2.0)
- `missingness_text_identifier` / `siren_missing` / `rate_abs_diff_pp`: WARNING (real=0.7277572291221063, synthetic=0.6980732585221258, effect=2.968397059998052, tolerance=2.0)
- `missingness_text_identifier` / `siret_present` / `presence_rate_abs_diff_pp`: WARNING (real=0.2722427708778937, synthetic=0.3078551767944103, effect=3.56124059165166, tolerance=2.0)
- `missingness_text_identifier` / `siren_present` / `presence_rate_abs_diff_pp`: WARNING (real=0.2722427708778937, synthetic=0.30192674147787424, effect=2.968397059998052, tolerance=2.0)
- `buyer_activity` / `activity_gini` / `abs_diff`: WARNING (real=0.8316141557268819, synthetic=0.7274026236809981, effect=0.1042115320458838, tolerance=0.1)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.3827800952459733, synthetic=0.32373491424941775, effect=5.904518099655559, tolerance=10.0)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.6612859388109615, synthetic=0.559284353165361, effect=10.200158564560056, tolerance=10.0)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.7798234522529336, synthetic=0.665890323946644, effect=11.393312830628954, tolerance=10.0)
- `text` / `unigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.4253820065080732, tolerance=0.3)
- `text` / `bigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.7762602091290521, tolerance=0.4)
- `robustness` / `blocking_pairs_completeness` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.2594557828845025, effect=0.2594557828845025, tolerance=0.25)
- `robustness` / `probe_headroom` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.5448003032017842, effect=0.5448003032017842, tolerance=0.25)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=-1.0, effect=-1.0, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=-1.0, effect=-1.0, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=-0.3333333333333333, effect=-0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=-1.0, effect=-1.0, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=-1.0, effect=-1.0, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=-1.0, effect=-1.0, tolerance=0.8)
