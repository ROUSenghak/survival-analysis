# v0.4 calibration evidence

Everything in this directory is derived from the **calibration** side of
`config/synthetic/real_holdout_buyer_keys.csv` (70% of real buyer keys). The
held-out 30% is never read here; it is used once, by
`scripts/evaluate_v0_4_real_holdout.py`, after the parameters are frozen.

| file | what it records |
|---|---|
| `observable_targets.json` | every EMPIRICAL_OBSERVABLE parameter, with its fit |
| `mechanism_parameters.json` | every MECHANISM_PARAMETER, and how it was selected |
| `activity_tail_fit.csv` | the x_min search and the three heavy-tail families compared at the selected x_min |
| `activity_body_quantiles.csv` | the smoothed empirical body of the activity distribution |
| `span_by_activity_rank.csv` | observed active-window span against activity rank |
| `publication_year_share.csv` | the observable by-year notice shares the entry weights target |
| `siret_buyer_effect_fit.csv` | logit-normal-binomial profile likelihood for the between-buyer SIRET dispersion |
| `alias_set_size_weights.csv` | distinct normalised names per checksum-valid SIREN |
| `name_similarity_target.csv` | the real within-SIREN similarity quantiles the alias bands target |
| `entry_weight_deconvolution_trace.csv` | the fixed-point iterations that solved for the entry weights |
| `mechanism_parameter_sweep_*.csv` | every candidate parameter set tried, with its full acceptance vector |
| `sweep_population_partial.log` | the abandoned population sweep, kept as the rejection record |

None of these files reads accepted links, linkage scores, acceptance thresholds,
synthetic precision/recall/F1, algorithm rankings or survival results.
