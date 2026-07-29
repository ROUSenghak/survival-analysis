# Synthetic Benchmark Readiness Assessment

This is a validated synthetic benchmark only to the readiness level supported above. It cannot prove real BOAMP precision, recall, renewal prevalence, survival estimates, or algorithm ranking.

Benchmark version: `v0_3_temporal_candidate_revision`
Scenario: `central_provisional`
Validation status read from manifest: `PASS_WITH_WARNINGS`
Generated data commit: `e3aeb6353740f1c09674302847ee80faa2dc54ef`
Current HEAD: `e3aeb6353740f1c09674302847ee80faa2dc54ef`

## Decisions

### PIPELINE_TECHNICALLY_VALID: PASS

Supporting evidence:
- internal gate: PASS
- specification_recovery gate: PASS
- privacy gate: PASS
- canonical replay checked: True
- all generated artifacts replay: PASS
- replayed artifacts: 51
- source state manifest hashed paths: 697
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
- probe linker best pair-F1: 0.22950819672131148

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
- metric failures: 0
- three evaluation settings reported: True
- required executable scenario configs present: True

Failed hard gates:
- main-scenario seed robustness is warning or inconclusive

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
- all-benchmark top-probe rank-1 frequency: 0.9
- cross-scenario-mean top-probe rank-1 frequency: 1.0

Failed hard gates:
- main-scenario seed robustness is warning or inconclusive
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
- source state manifest hashed paths: 697
- worktree dirty: True
- verified dirty-state release package: True
- release package archive sha256: cd41659736a76fe68d2100289b53de1277c7dbfe5eef3a2bb81f98b7983d3e76

Failed hard gates:
- main-scenario seed robustness is warning or inconclusive
- headline difficulty varies materially across scenarios and must be scenario-labelled
- main-scenario probe-linker ranking stability is warning or inconclusive
- cross-scenario probe-linker ranking stability is warning or inconclusive

Permitted uses:
- not release-ready

Prohibited claims:
- Synthetic precision, recall, recurrence prevalence, or survival estimates equal their unknown real BOAMP values.
- The benchmark proves real-world algorithm ranking or real renewal prevalence.
- Previously accepted BOAMP links, linkage scores, thresholds, or the six-month window are real ground truth.
- A validated synthetic benchmark replaces missing manual/legal BOAMP recurrence labels.

## Current Problem Inventory

- `marginals` / `text_length` / `W1_scaled`: WARNING (real=nan, synthetic=nan, effect=0.173961840628508, tolerance=0.1)
- `marginals` / `text_length` / `q75_relative_error`: WARNING (real=133.0, synthetic=117.0, effect=0.1203007518796992, tolerance=0.1)
- `temporal` / `followup_runway` / `abs_diff_pp`: WARNING (real=0.5501577585290052, synthetic=0.4310053029448268, effect=11.915245558417835, tolerance=5.0)
- `missingness_text_identifier` / `siret_missing` / `rate_abs_diff_pp`: WARNING (real=0.7277572291221063, synthetic=0.7069840911655195, effect=2.077313795658675, tolerance=2.0)
- `missingness_text_identifier` / `siret_present` / `presence_rate_abs_diff_pp`: WARNING (real=0.2722427708778937, synthetic=0.2930159088344804, effect=2.07731379565867, tolerance=2.0)
- `buyer_activity` / `activity_gini` / `abs_diff`: WARNING (real=0.8316141557268819, synthetic=0.7316588899848229, effect=0.099955265742059, tolerance=0.1)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.3827800952459733, synthetic=0.31400203091504003, effect=6.877806433093331, tolerance=10.0)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.6612859388109615, synthetic=0.5599684079882659, effect=10.131753082269569, tolerance=10.0)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.7798234522529336, synthetic=0.673473993004626, effect=10.634945924830763, tolerance=10.0)
- `text` / `token_count` / `q50_relative_error`: WARNING (real=17.0, synthetic=13.0, effect=0.2352941176470588, tolerance=0.2)
- `text` / `unigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.4421110581068999, tolerance=0.3)
- `text` / `bigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.7835691386850636, tolerance=0.4)
- `hidden_truth_difficulty` / `pairs_quality` / `PQ`: WARNING (real=nan, synthetic=0.03518518518518519, effect=0.0351851851851851, tolerance=0.05)
- `hidden_truth_difficulty` / `pairs_quality` / `PQ`: WARNING (real=nan, synthetic=0.03188028627195836, effect=0.0318802862719583, tolerance=0.05)
- `robustness` / `blocking_pairs_completeness` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.26105641030101995, effect=0.2610564103010199, tolerance=0.25)
- `robustness` / `blocking_pairs_completeness` / `nonpass_frequency`: WARNING (real=nan, synthetic=0.1, effect=0.1, tolerance=0)
- `robustness` / `match_vs_hard_negative_score` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.2524004615376075, effect=0.2524004615376075, tolerance=0.25)
- `robustness` / `probe_headroom` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.4984839783230138, effect=0.4984839783230138, tolerance=0.25)
- `robustness` / `probe_headroom` / `nonpass_frequency`: WARNING (real=nan, synthetic=0.1, effect=0.1, tolerance=0)
- `robustness` / `blocking_pairs_completeness` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.31108823999025986, effect=0.3110882399902598, tolerance=0.25)
- `robustness` / `probe_headroom` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.6611260254405965, effect=0.6611260254405965, tolerance=0.25)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=-0.3333333333333333, effect=-0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=-1.0, effect=-1.0, tolerance=0.8)
