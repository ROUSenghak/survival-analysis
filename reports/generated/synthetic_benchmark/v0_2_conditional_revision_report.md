# Synthetic benchmark v0.2 conditional revision report

Overall conditional-fidelity freeze gate: **PASS**.

## What changed

- SIRET observation now uses smoothed observable rates by schema, year, and notice type.
- Duration observation now uses smoothed observable rates by schema, year, and notice type; latent contract duration is unchanged.
- Text reuse now separates exact cross-buyer templates, near boilerplate with row-specific tokens, generic weak wording, and same-family near duplicates.
- CPV missingness, latent truth, and linkage algorithms were not tuned.

## Conditional summary

| target | version | eligible_cells | total_cells | eligible_real_population_share | weighted_mean_abs_error_pp | unweighted_mean_abs_error_pp | median_abs_error_pp | p90_abs_error_pp | max_abs_error_pp | weighted_signed_bias_pp | max_error_real_population_share | assessment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cpv_missing | v0_1_provisional | 4.00 | 6.00 | 0.96 | 2.36 | 1.65 | 1.36 | 2.57 | 3.04 | -2.08 | 0.61 | PASS |
| cpv_missing | v0_2_conditional_revision | 4.00 | 6.00 | 0.96 | 2.57 | 1.93 | 1.61 | 2.70 | 3.13 | -2.20 | 0.61 | PASS |
| duration_present | v0_1_provisional | 29.00 | 45.00 | 0.93 | 11.70 | 14.97 | 6.02 | 51.59 | 68.00 | 2.85 | 0.02 | NEEDS_REVISION |
| duration_present | v0_2_conditional_revision | 29.00 | 45.00 | 0.93 | 0.51 | 0.96 | 0.45 | 2.58 | 5.57 | 0.13 | 0.02 | PASS |
| generic_repeated_text | v0_1_provisional | 8.00 | 12.00 | 0.96 | 59.14 | 46.28 | 42.79 | 63.71 | 67.11 | 59.14 | 0.23 | NEEDS_REVISION |
| generic_repeated_text | v0_2_conditional_revision | 8.00 | 12.00 | 0.96 | 1.40 | 4.27 | 0.90 | 10.67 | 25.53 | 1.00 | 0.00 | PASS |
| siret_present | v0_1_provisional | 29.00 | 45.00 | 0.93 | 12.43 | 19.89 | 11.17 | 44.79 | 58.44 | -1.92 | 0.00 | NEEDS_REVISION |
| siret_present | v0_2_conditional_revision | 29.00 | 45.00 | 0.93 | 1.88 | 2.16 | 2.15 | 3.78 | 9.72 | -0.48 | 0.01 | PASS |

## Before/after WMAE

| target | v0_1_provisional | v0_2_conditional_revision | wmae_improvement_pp |
| --- | --- | --- | --- |
| cpv_missing | 2.36 | 2.57 | -0.21 |
| duration_present | 11.70 | 0.51 | 11.19 |
| generic_repeated_text | 59.14 | 1.40 | 57.74 |
| siret_present | 12.43 | 1.88 | 10.55 |

## Text metrics

| dataset | n_nonmissing_text | exact_duplicate_row_rate | exact_cross_buyer_duplicate_row_rate | within_buyer_duplicate_row_rate | near_duplicate_nn_rate_threshold_0_92_sample_cap_8000 | nearest_neighbor_median_similarity | median_text_length | p90_text_length | n_unique_templates | top_template_share | top10_template_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| real | 84622 | 0.54 | 0.08 | 0.51 | 0.10 | 0.55 | 98.00 | 169.00 | 58918 | 0.00 | 0.01 |
| v0_1_provisional | 9537 | 0.60 | 0.54 | 0.50 | 0.65 | 1.00 | 94.00 | 111.00 | 4615 | 0.15 | 0.44 |
| v0_2_conditional_revision | 9607 | 0.09 | 0.08 | 0.08 | 0.37 | 0.76 | 118.00 | 144.00 | 8840 | 0.01 | 0.06 |

## Remaining caveats

- The text metric now passes on weighted conditional fidelity, but the maximum text cell remains higher than the median because rare activity/type strata are sensitive to exact-template allocation.
- Median synthetic text length increased after adding contract-specific reference tokens; this is a trade-off against unrealistic exact reuse and should be monitored in later text-quality work.
- CPV missingness remains close and was intentionally not retuned.

## Next readiness decision

The revised benchmark is ready to proceed to temporal and candidate-environment validation, but not to linkage-score calibration or threshold optimization.
