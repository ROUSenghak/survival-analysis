# Frozen pre-change baseline (v0.3)

Copied verbatim from
`reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/` at the start of the
v0.4 `population_alias_revision` work, before any generator, configuration or validation code
was modified.

These files are the **comparison baseline** for every before/after table and figure in the v0.4
report. They are never regenerated. The live v0.3 artifacts they were copied from are also left
untouched; this directory exists so the v0.4 report can be rebuilt without depending on the v0.3
directory staying frozen.

Source commit at copy time: `3fa502b7bce38f110e0066afd4e9e1afcd11ad34` (branch
`restructure/two-layer`, clean worktree).

| file | source |
|---|---|
| `validation_metrics_long.csv` | `validation_framework/validation_metrics_long.csv` |
| `validation_gate_summary.csv` | `validation_framework/validation_gate_summary.csv` |
| `discrepancy_register.csv` | `validation_framework/discrepancy_register.csv` |
| `probe_linker_results.csv` | `validation_framework/probe_linker_results.csv` |
| `probe_ranking_stability.csv` | `validation_framework/probe_ranking_stability.csv` |
| `probe_pairwise_comparisons.csv` | `validation_framework/probe_pairwise_comparisons.csv` |
| `probe_replicate_results.csv` | `validation_framework/probe_replicate_results.csv` |
| `readiness_decisions.json` | `readiness/readiness_decisions.json` |
| `readiness_assessment.md` | `readiness/readiness_assessment.md` |
| `candidate_environment_summary_metrics.csv` | `candidate_environment_summary_metrics.csv` |
| `candidate_environment_validation_gate_by_version.csv` | `candidate_environment_validation_gate_by_version.csv` |

Baseline headline: `PASS_WITH_WARNINGS` over 231 metrics — 209 PASS, 16 WARNING, 5 FAIL,
1 INCONCLUSIVE. The five FAILs are the target of this revision.
