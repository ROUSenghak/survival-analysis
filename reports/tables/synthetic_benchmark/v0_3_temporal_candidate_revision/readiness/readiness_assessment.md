# Synthetic Benchmark Readiness Assessment

This is a validated synthetic benchmark only to the readiness level supported above. It cannot prove real BOAMP precision, recall, renewal prevalence, survival estimates, or algorithm ranking.

Benchmark version: `v0_3_temporal_candidate_revision`
Scenario: `central_provisional`
Validation status read from manifest: `PASS_WITH_WARNINGS`
Generated data commit: `40dfad87881560ebd8b6dae91fa6397d545bc9cd`
Current HEAD: `40dfad87881560ebd8b6dae91fa6397d545bc9cd`

## Decisions

### PIPELINE_TECHNICALLY_VALID: PASS_WITH_LIMITATIONS

Supporting evidence:
- internal gate: PASS
- specification_recovery gate: PASS
- privacy gate: PASS
- canonical replay checked: True
- all generated artifacts replay: PASS
- replayed artifacts: 51
- source state manifest hashed paths: 619
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
- probe linker best pair-F1: 0.35220125786163525

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
- replicates by scenario: {'difficult': 10, 'clean_sanity': 1, 'moderate': 10, 'central_provisional': 10, 'easier': 10, 'stress': 10}
- metric failures: 2
- three evaluation settings reported: True
- required executable scenario configs present: True

Failed hard gates:
- observable hard-fidelity failures remain in non-critical current gates
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
- observable hard failures: True
- probe ranking summary rows: 21
- main-scenario top-probe rank-1 frequency: 0.5
- all-benchmark top-probe rank-1 frequency: 0.58
- cross-scenario-mean top-probe rank-1 frequency: 1.0

Failed hard gates:
- observable hard-fidelity failures remain in non-critical current gates
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
- source state manifest hashed paths: 619
- worktree dirty: True

Failed hard gates:
- observable hard-fidelity failures remain in non-critical current gates
- main-scenario seed robustness is warning or inconclusive
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

- `marginals` / `text_length` / `W1_scaled`: WARNING (real=nan, synthetic=nan, effect=0.16073112073112, tolerance=0.1)
- `temporal` / `followup_runway` / `abs_diff_pp`: WARNING (real=0.5501577585290052, synthetic=0.4307709724895279, effect=11.938678603947729, tolerance=5.0)
- `missingness_text_identifier` / `siret_missing` / `rate_abs_diff_pp`: FAIL (real=0.7277572291221063, synthetic=0.6840258122948035, effect=4.3731416827302745, tolerance=2.0)
- `missingness_text_identifier` / `siren_missing` / `rate_abs_diff_pp`: WARNING (real=0.7277572291221063, synthetic=0.69398845239443, effect=3.376877672767631, tolerance=2.0)
- `missingness_text_identifier` / `siret_present` / `presence_rate_abs_diff_pp`: FAIL (real=0.2722427708778937, synthetic=0.3159741877051964, effect=4.373141682730269, tolerance=2.0)
- `missingness_text_identifier` / `siren_present` / `presence_rate_abs_diff_pp`: WARNING (real=0.2722427708778937, synthetic=0.30601154760557003, effect=3.376877672767631, tolerance=2.0)
- `buyer_activity` / `activity_gini` / `abs_diff`: WARNING (real=0.8316141557268819, synthetic=0.7138582998635006, effect=0.1177558558633813, tolerance=0.1)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.3827800952459733, synthetic=0.3064643948828258, effect=7.631570036314756, tolerance=10.0)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.6612859388109615, synthetic=0.5419449790558134, effect=11.934095975514811, tolerance=10.0)
- `buyer_activity` / `activity_share` / `abs_diff_pp`: WARNING (real=0.7798234522529336, synthetic=0.6559492811049473, effect=12.387417114798629, tolerance=10.0)
- `buyer_activity` / `relative_notices_per_buyer` / `q99_abs_diff`: WARNING (real=16.20559138768418, synthetic=14.365859843767739, effect=1.8397315439164412, tolerance=1.0)
- `text` / `unigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.4255640695754855, tolerance=0.3)
- `text` / `bigram_distribution` / `JS`: WARNING (real=nan, synthetic=nan, effect=0.776259241085664, tolerance=0.4)
- `hidden_truth_difficulty` / `pairs_quality` / `PQ`: WARNING (real=nan, synthetic=0.038435140700068635, effect=0.0384351407000686, tolerance=0.05)
- `hidden_truth_difficulty` / `pairs_quality` / `PQ`: WARNING (real=nan, synthetic=0.030213903743315507, effect=0.0302139037433155, tolerance=0.05)
- `robustness` / `blocking_pairs_completeness` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.32152326847656354, effect=0.3215232684765635, tolerance=0.25)
- `robustness` / `blocking_pairs_completeness` / `nonpass_frequency`: WARNING (real=nan, synthetic=0.1, effect=0.1, tolerance=0)
- `robustness` / `match_vs_hard_negative_score` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.3232700104040579, effect=0.3232700104040579, tolerance=0.25)
- `robustness` / `probe_headroom` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.3904025982709695, effect=0.3904025982709695, tolerance=0.25)
- `robustness` / `probe_headroom` / `nonpass_frequency`: WARNING (real=nan, synthetic=0.1, effect=0.1, tolerance=0)
- `robustness` / `blocking_pairs_completeness` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.36674663847145395, effect=0.3667466384714539, tolerance=0.25)
- `robustness` / `match_vs_hard_negative_score` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.28378895702782286, effect=0.2837889570278228, tolerance=0.25)
- `robustness` / `probe_headroom` / `coefficient_of_variation`: WARNING (real=nan, synthetic=0.5871439400907855, effect=0.5871439400907855, tolerance=0.25)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=-1.0, effect=-1.0, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=-1.0, effect=-1.0, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=0.3333333333333333, effect=0.3333333333333333, tolerance=0.8)
- `robustness` / `probe_ranking` / `min_kendall_tau`: WARNING (real=nan, synthetic=-1.0, effect=-1.0, tolerance=0.8)
