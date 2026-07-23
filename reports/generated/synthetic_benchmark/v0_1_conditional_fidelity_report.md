# Synthetic benchmark v0.1 - conditional fidelity validation

Generated from `notebooks/07_synthetic_conditional_fidelity_validation.ipynb`.

## Overall assessment

**Needs revision.** CPV missingness by schema and notice type is close, but the current synthetic pilot does not reproduce the requested SIRET, duration, or generic-text conditional structures.

## Headline metrics

| comparison | cells_total | cells_with_n_ge_30_both | mean_abs_diff_pp | median_abs_diff_pp | p90_abs_diff_pp | max_abs_diff_pp | share_ci_overlap | assessment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P(SIRET present | schema, year, notice type) | 45 | 29 | 19.89 | 11.17 | 44.79 | 58.44 | 0.31 | NEEDS_REVISION |
| P(CPV missing | schema, notice type) | 6 | 4 | 1.65 | 1.36 | 2.57 | 3.04 | 0.25 | PASS |
| P(duration present | schema, notice type, year) | 45 | 29 | 14.97 | 6.02 | 51.59 | 68.00 | 0.10 | NEEDS_REVISION |
| P(generic repeated text | notice type, buyer activity) | 12 | 8 | 46.28 | 42.79 | 63.71 | 67.11 | 0.00 | NEEDS_REVISION |

## Output tables

- `reports/tables/synthetic_benchmark/v0_1/conditional_fidelity_siret_by_schema_year_notice_type.csv`
- `reports/tables/synthetic_benchmark/v0_1/conditional_fidelity_cpv_missing_by_schema_notice_type.csv`
- `reports/tables/synthetic_benchmark/v0_1/conditional_fidelity_cpv_division_identifiability.csv`
- `reports/tables/synthetic_benchmark/v0_1/conditional_fidelity_duration_by_schema_year_notice_type.csv`
- `reports/tables/synthetic_benchmark/v0_1/conditional_fidelity_generic_text_by_notice_type_buyer_activity.csv`
- `reports/tables/synthetic_benchmark/v0_1/conditional_fidelity_summary.csv`

## Caveat

`P(CPV missing | CPV division)` is not identifiable from the prepared real corpus because `cpv_division` is derived from `cpv_clean`; if CPV is missing, the division is also missing. The notebook saves an identifiability diagnostic rather than a circular division-conditioned missingness rate.
