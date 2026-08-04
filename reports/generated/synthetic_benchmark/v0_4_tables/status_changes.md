| metric | v0.3 | v0.4 | |dev| v0.3 | |dev| v0.4 | tolerance |
|---|---|---|---|---|---|
| buyer_activity / overall / observed_keys_per_notice / relative_error |  | WARNING | n/a | 0.2739 |  |
| buyer_activity / overall / relative_notices_per_buyer / q99_abs_diff | FAIL | PASS | 2.3414 | 0.6069 | 1.0 |
| buyer_activity / top5pct / activity_share / abs_diff_pp | PASS | WARNING | 4.5192 | 5.2119 | 10.0 |
| missingness_structure / pattern=110100 / missingness_pattern / max_single_pattern_abs_diff |  | PASS | n/a | 0.0462 |  |
| missingness_structure / pattern=111100 / missingness_pattern / max_single_pattern_abs_diff | PASS |  | 0.0481 | n/a | 0.15 |
| missingness_text_identifier / overall / cpv_missing / rate_abs_diff_pp | WARNING | PASS | 2.0123 | 1.8655 | 2.0 |
| missingness_text_identifier / overall / siren_missing / rate_abs_diff_pp | WARNING | PASS | 3.4019 | 1.6753 | 2.0 |
| missingness_text_identifier / overall / siren_present / presence_rate_abs_diff_pp | WARNING | PASS | 3.4019 | 1.6753 | 2.0 |
| missingness_text_identifier / overall / siret_missing / rate_abs_diff_pp | FAIL | WARNING | 4.1104 | 2.3790 | 2.0 |
| missingness_text_identifier / overall / siret_present / presence_rate_abs_diff_pp | FAIL | WARNING | 4.1104 | 2.3790 | 2.0 |
| names_identifiers / silver_siren_groups / name_jaro_winkler / q25_abs_diff |  | PASS | n/a | 0.0082 |  |
| names_identifiers / silver_siren_groups / name_jaro_winkler / q50_abs_diff | WARNING | PASS | 0.1899 | 0.0002 | 0.15 |
| names_identifiers / silver_siren_groups / name_jaro_winkler / q75_abs_diff |  | PASS | n/a | 0.0103 |  |
| names_identifiers / silver_siren_groups / name_jaro_winkler / q90_abs_diff |  | PASS | n/a | 0.0319 |  |
| names_identifiers / silver_siren_groups / name_token_count_difference / mean_abs_diff |  | PASS | n/a | 1.2960 |  |
| names_identifiers / silver_siren_groups / name_token_jaccard / full_token_overlap_share |  | PASS | n/a | 0.0004 |  |
| names_identifiers / silver_siren_groups / name_token_jaccard / q10_abs_diff | FAIL | PASS | 0.3333 | 0.0000 | 0.15 |
| names_identifiers / silver_siren_groups / name_token_jaccard / q25_abs_diff |  | PASS | n/a | 0.1111 |  |
| names_identifiers / silver_siren_groups / name_token_jaccard / q50_abs_diff | FAIL | PASS | 0.4167 | 0.0833 | 0.15 |
| names_identifiers / silver_siren_groups / name_token_jaccard / q75_abs_diff |  | PASS | n/a | 0.0000 |  |
| names_identifiers / silver_siren_groups / name_token_jaccard / q90_abs_diff |  | PASS | n/a | 0.0476 |  |
| names_identifiers / silver_siren_groups / name_token_jaccard / zero_token_overlap_share |  | PASS | n/a | 0.0218 |  |
| names_identifiers / silver_siren_groups / name_variants_per_buyer / distribution_TV |  | WARNING | n/a | 0.1532 |  |
| robustness / pairwise_comparison:stress / ranking_pairwise_support / ambiguous_pair_fraction | PASS | WARNING | 0.0000 | 0.3333 | 0.25 |
| robustness / pairwise_comparison:stress / ranking_pairwise_support / supported_pair_fraction | PASS | WARNING | 1.0000 | 0.6667 | 0.8 |
| robustness / ranking_stability:difficult / probe_ranking / min_kendall_tau | WARNING | PASS | 0.3333 | 1.0000 | 0.8 |
| temporal / 12m / followup_runway / abs_diff_pp | PASS | WARNING | 0.4639 | 3.4847 | 3.0 |
| temporal / 60m / followup_runway / abs_diff_pp | WARNING | PASS | 11.0231 | 3.2644 | 5.0 |
| temporal / overall / publication_year / WMAE_pp |  | PASS | n/a | 0.7235 |  |
