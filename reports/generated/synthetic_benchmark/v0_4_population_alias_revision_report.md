# Synthetic benchmark v0_4_population_alias_revision

Revision of `v0_3_temporal_candidate_revision`. The previous version's artifacts, configuration,
validation results and reports are unchanged; v0.4 is an additional version, not a
replacement.

**This document is generated** by `scripts/build_v0_4_revision_report.py` from the
artifacts on disk. Every number below comes from
`reports/generated/synthetic_benchmark/v0_4_report_values.json`.

## 1. What this revision changed and why

v0.3 validated `PASS_WITH_WARNINGS` over 231 metrics with five hard
failures, and `READY_FOR_CONTROLLED_ALGORITHM_COMPARISON` failed for exactly one
reason: those failures. The audit that opened this revision found that two of the
three underlying problems were not what the v0.3 report said they were.

**Aggregate SIRET availability was a composition artifact.** Standardised to the
real `schema_family x publication_year x notice_type` cell weights, v0.3's
checksum-valid SIRET rate is within tolerance; its raw marginal is not. The
difference is v0.3's publication-year mix, which under-produced 2015-2017 and
over-produced 2020-2024 by about 15 percentage points in total. SIRET presence
rises from roughly 7% in 2015 to 57% in 2022, so a year-composition error
presented itself as an identifier-mechanism error. The same skew also explains
v0.3's `siren_present`, `cpv_missing` and 60-month follow-up-runway warnings.

**The buyer-activity q99 failure was buyer-population scale, not tail shape.**
v0.3's extreme tail (q99.9, maximum) already matched real BOAMP. What it produced
was roughly twice as many observed buyer keys per notice as the real corpus, which
halves the mean and compresses every scale-free quantile. The excess sat entirely
on the SIRET-keyed side, because the v0.2 conditional revision made SIRET
visibility independent across a buyer's notices and left the buyer-level
`identifier_quality_propensity` unread on that path. Real BOAMP is strongly
buyer-persistent.

**Buyer-name variation was as reported**, with an additional finding: two of the
six v0.3 alias edit modes could not produce an observable variant at all, because
`normalize_buyer_name` erases them.

Three mechanisms were revised. `buyers.activity_model` replaces the single Pareto
draw with a smoothed empirical body plus a truncated power-law tail, and separates
buyer entry time and active-window length from publication intensity.
`identifiers.conditional_siret_presence` gains a buyer-level logit random effect
with a marginal-preserving intercept. `buyer_names.persistent_aliases` replaces
per-notice independent name edits with a persistent per-buyer alias set.

## 2. Calibration and provenance

Observable parameters follow a **per-parameter holdout policy**, because a
buyer-level split is not neutral for every quantity.

* *Distributional-shape parameters* -- the activity body and truncated tail, the
  span-versus-activity curve, the publication-entry weights, the alias-set sizes
  and token-overlap bands, and every swept mechanism parameter -- are estimated on
  the **calibration** side only and are evaluated out of sample on the held-out
  30%.
* *Conditional rate tables* (SIRET presence, duration presence, repeated text) are
  estimated on the **full** corpus. Checksum-valid SIRET presence is a buyer-level
  property, so splitting on buyer key splits it too: the real calibration and
  holdout sides differ by 10.2 pp, of which only
  0.76 pp is cell composition and 1.94 pp is buyer selection within the same
  cells. Estimating these tables on 70% of buyers would build a known ~2.7 pp bias
  into the released marginal -- against a gate whose reference is the whole corpus
  -- in exchange for an out-of-sample claim the split cannot support for this
  quantity.

The holdout split itself is stratified on activity decile, dominant schema and
year-span coverage (3713 of
5268
real buyer keys). Nothing reads accepted links, linkage scores, acceptance
thresholds, synthetic precision/recall/F1, algorithm rankings or survival results.

| parameter | value | provenance |
|---|---|---|
| activity tail family | discrete_power_law | EMPIRICAL_OBSERVABLE |
| tail alpha | 2.0364 | EMPIRICAL_OBSERVABLE (Clauset-Shalizi-Newman MLE) |
| tail x_min / x_max (relative) | 2.152 / 190.37 | EMPIRICAL_OBSERVABLE |
| observed keys per notice | 0.05977 | EMPIRICAL_OBSERVABLE |
| SIRET between-buyer logit SD | 2.10 | EMPIRICAL_OBSERVABLE (logit-normal-binomial marginal likelihood) |
| zero-token-overlap share of same-SIREN name pairs | 0.240 | EMPIRICAL_OBSERVABLE |
| mean names per SIREN | 1.727 | EMPIRICAL_OBSERVABLE |
| target buyer population | 5000 | MECHANISM_PARAMETER (swept) |
| needs per buyer | 8.382 | MECHANISM_PARAMETER (swept) |
| dominant alias share | 0.55 | MECHANISM_PARAMETER (swept) |

The v0.1-v0.3 `target_n_buyers` of 19,200 was documented as the real prepared
corpus's buyer count. That corpus contains 5,148 distinct raw buyer names, 4,492
normalised names, 1,506 checksum-valid SIRENs and 5,268 production buyer keys; the
figure is not traceable to any observable quantity in this repository. v0.4 sets
the buyer population by sweep against the observable keys-per-notice ratio instead.

The publication-year entry weights were solved by damped multiplicative fixed
point against the observable by-year notice shares, converging in
3 iterations to
0.495 pp weighted mean absolute error
(TVD 0.0307).

## 3. The five targeted failures, before and after

| metric | real | v0.3 | v0.3 deviation | tolerance | v0.3 status | v0.4 | v0.4 deviation | v0.4 status |
|---|---|---|---|---|---|---|---|---|
| overall / siret_missing / rate_abs_diff_pp | 0.728 | 0.687 | 4.110 | 2.000 | FAIL | 0.704 | 2.379 | WARNING |
| overall / siret_present / presence_rate_abs_diff_pp | 0.272 | 0.313 | 4.110 | 2.000 | FAIL | 0.296 | 2.379 | WARNING |
| overall / relative_notices_per_buyer / q99_abs_diff | 16.206 | 13.864 | 2.341 | 1.000 | FAIL | 15.599 | 0.607 | PASS |
| silver_siren_groups / name_token_jaccard / q10_abs_diff | 0.000 | 0.333 | 0.333 | 0.150 | FAIL | 0.000 | 0.000 | PASS |
| silver_siren_groups / name_token_jaccard / q50_abs_diff | 0.250 | 0.667 | 0.417 | 0.150 | FAIL | 0.333 | 0.083 | PASS |

## 4. Seed spread of the critical acceptance metrics at the frozen parameters

Development-time check on both development seeds, against the calibration side of
the real holdout. It is kept because it is what triggered the switch to multi-seed
selection: two critical metrics straddle their tolerance across seeds. It predates
the final regeneration under the per-parameter calibration policy, so the
fresh-seed table in the next section is the current evidence.

| critical metric | mean | min | max | tolerance | seeds passing | seeds |
|---|---|---|---|---|---|---|
| activity_relative_q99_abs_diff | -1.257 | -2.119 | -0.395 | 1.0 | 1 | 2 |
| candidate_cap_reached_rate | 0.000 | 0.000 | 0.001 | 0.01 | 2 | 2 |
| candidate_p75_abs_diff | -1.000 | -2.000 | 0.000 | 3.0 | 2 | 2 |
| candidate_p90_abs_diff | -1.000 | -3.000 | 1.000 | 5.0 | 2 | 2 |
| candidate_p95_abs_diff | -3.500 | -6.000 | -1.000 | 8.0 | 2 | 2 |
| candidate_source_count_ratio_deviation | -0.005 | -0.077 | 0.068 | 0.2 | 2 | 2 |
| candidate_zero_rate_abs_diff_pp | 0.273 | -2.901 | 3.447 | 5.0 | 2 | 2 |
| name_token_jaccard_q10_abs_diff | 0.000 | 0.000 | 0.000 | 0.15 | 2 | 2 |
| name_token_jaccard_q50_abs_diff | -0.008 | -0.008 | -0.008 | 0.15 | 2 | 2 |
| publication_year_wmae_pp | 0.657 | 0.651 | 0.662 | 1.0 | 2 | 2 |
| siret_present_abs_diff_pp | -0.851 | -3.323 | 1.620 | 2.0 | 1 | 2 |

## 5. Fresh-seed evaluation

Run **once**, on seeds used in neither the development sweep nor the release set,
against the **full** real corpus -- the same reference the release gates use. No
parameter was changed after these numbers existed.

| critical metric | mean | sd | MCSE | min | max | tolerance | pass rate |
|---|---|---|---|---|---|---|---|
| activity_relative_q99_abs_diff | -1.187 | 0.762 | 0.341 | -2.529 | -0.664 | 1.0 | 0.6 |
| candidate_cap_reached_rate | 0.002 | 0.006 | 0.002 | 0.000 | 0.012 | 0.01 | 0.8 |
| candidate_p75_abs_diff | 0.000 | 1.414 | 0.632 | -1.000 | 2.000 | 3.0 | 1.0 |
| candidate_p90_abs_diff | 0.300 | 3.912 | 1.749 | -3.100 | 6.900 | 5.0 | 0.8 |
| candidate_p95_abs_diff | -1.200 | 5.070 | 2.267 | -6.000 | 7.000 | 8.0 | 1.0 |
| candidate_source_count_ratio_deviation | -0.007 | 0.069 | 0.031 | -0.089 | 0.096 | 0.2 | 1.0 |
| candidate_zero_rate_abs_diff_pp | -0.810 | 2.651 | 1.185 | -4.550 | 1.172 | 5.0 | 1.0 |
| name_token_jaccard_q10_abs_diff | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.15 | 1.0 |
| name_token_jaccard_q50_abs_diff | 0.017 | 0.037 | 0.017 | 0.000 | 0.083 | 0.15 | 1.0 |
| publication_year_wmae_pp | 0.736 | 0.125 | 0.056 | 0.587 | 0.909 | 1.0 | 1.0 |
| siret_present_abs_diff_pp | 2.366 | 3.190 | 1.426 | -2.985 | 5.142 | 2.0 | 0.0 |
| text_length_w1_scaled | 0.163 | 0.008 | 0.003 | 0.151 | 0.170 | 0.1 | 0.0 |

Fresh world seeds: [20270101, 20270111, 20270121, 20270131, 20270210]; disjoint from the
development seeds: True; disjoint from
the release seeds: True.

## 6. Every metric whose status changed

9 metrics improved to PASS; 4 regressed from PASS;
13 metrics were added in v0.4 (metrics were only ever added,
never redefined, loosened or reclassified).

v0.3: PASS 209, WARNING 16, FAIL 5, INCONCLUSIVE 1.
v0.4: PASS 224, WARNING 18, INCONCLUSIVE 1.

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

## 7. Validation gates

| gate | critical | v0.3 | v0.4 |
|---|---|---|---|
| internal | True | PASS | PASS |
| specification_recovery | True | PASS | PASS |
| marginals | False | WARNING | WARNING |
| conditionals | True | PASS | PASS |
| temporal | True | WARNING | WARNING |
| candidate_environment | True | PASS | PASS |
| missingness_text_identifier | False | WARNING | WARNING |
| buyer_activity | False | WARNING | WARNING |
| missingness_structure | False | PASS | PASS |
| names_identifiers | False | WARNING | WARNING |
| text | False | WARNING | WARNING |
| privacy | True | PASS | PASS |
| hidden_truth_difficulty | True | PASS | PASS |
| algorithm_utility | True | PASS | PASS |
| robustness | False | WARNING | WARNING |

Failing critical gates in v0.4: none.

## 8. Between-world variance of the revised mechanisms

Two of the revised mechanisms deliberately introduce buyer-level dependence, and
that has a measurable cost in between-world variance of corpus-level rates. The
buyer random effect on SIRET visibility means a handful of large buyers can move
the marginal identifier rate by percentage points depending on their draw, and the
truncated activity tail means the identity of the largest buyers varies by world.

This was found the hard way. A parameter set selected on one development world
scored zero failing critical metrics on that world and two on the next
(`siret_present` and `activity_relative_q99`), with a 4.7 pp swing in the marginal
SIRET rate between the two. The sweep was therefore changed to score every
candidate on all development seeds and to require acceptance on *every* seed, not
on the mean; single-world selection was fitting single-world noise.

The consequence for reading this benchmark is that a headline gate evaluated on
world_001 alone carries Monte Carlo error comparable to some tolerances. Seed-level
spreads for every observable metric are reported in
`holdout/holdout_fidelity_summary.csv` (`sd_value`, `min_value`, `max_value` over
worlds) and should be quoted alongside any single-world figure. This is a property
of the revised generator, not a defect introduced by measurement: real BOAMP is
itself one draw from a process with the same buyer-level dependence.

## 9. Mechanisms considered and rejected

Four mechanism designs were measured on generated worlds and discarded; each is
recorded with its numbers in `mechanism_tradeoff_log.csv`. The most instructive is
the untruncated power-law tail: the Clauset-Shalizi-Newman fit describes the real
tail well and, sampled at benchmark scale, put 21.9% of the corpus under a single
buyer key against a real maximum of 3.8%. A fitted tail index is not by itself a
generative model of a bounded quantity.

## 10. Selection evidence

| candidate | target_n_buyers | dominant_alias_share | recurrence_propensity_multiplier | scoped_need_probability_high | scoped_buyer_affinity_share | n_notices | score | accepted | critical_failures |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 5500 | 0.55 | 1.15 | 0.22 | 0.08 | 82912 | 22.76423072462618 | False | activity_relative_q99_abs_diff;candidate_zero_rate_abs_diff_pp |
| 1 | 5500 | 0.55 | 1.45 | 0.22 | 0.08 | 83320 | 23.2481335380025 | False | activity_relative_q99_abs_diff |
| 3 | 5500 | 0.55 | 1.45 | 0.22 | 0.12 | 82571 | 25.625157566070936 | False | activity_relative_q99_abs_diff;candidate_zero_rate_abs_diff_pp;candidate_p95_abs_diff |
| 5 | 5500 | 0.55 | 1.45 | 0.3 | 0.08 | 84138 | 27.59538890353339 | False | activity_relative_q99_abs_diff;candidate_zero_rate_abs_diff_pp;candidate_p90_abs_diff;candidate_p95_abs_diff |
| 2 | 5500 | 0.55 | 1.15 | 0.22 | 0.12 | 81954 | 28.537832129069105 | False | activity_relative_q99_abs_diff;candidate_source_count_ratio_deviation;candidate_zero_rate_abs_diff_pp;candidate_p90_abs_diff;candidate_p95_abs_diff |
| 4 | 5500 | 0.55 | 1.15 | 0.3 | 0.08 | 83223 | 31.32153997065856 | False | activity_relative_q99_abs_diff;candidate_source_count_ratio_deviation;candidate_zero_rate_abs_diff_pp;candidate_p90_abs_diff;candidate_p95_abs_diff |
| 6 | 5500 | 0.55 | 1.15 | 0.3 | 0.12 | 83099 | 41.00953178720778 | False | activity_relative_q99_abs_diff;candidate_source_count_ratio_deviation;candidate_p90_abs_diff;candidate_p95_abs_diff;candidate_cap_reached_rate |
| 7 | 5500 | 0.55 | 1.45 | 0.3 | 0.12 | 83768 | 43.53692051366458 | False | activity_relative_q99_abs_diff;candidate_p90_abs_diff;candidate_p95_abs_diff;candidate_cap_reached_rate |

## 11. Out-of-sample evidence: the real-data holdout

| metric | mean_calibration | mean_holdout | calibration_minus_holdout | tolerance | in_sample_gap_flag |
|---|---|---|---|---|---|
| activity_gini_abs_diff | -0.0197 | -0.0000 | -0.0197 | 0.1 | False |
| activity_relative_q50_abs_diff | 0.0346 | 0.0159 | 0.0187 | 1.0 | False |
| activity_relative_q90_abs_diff | 0.2217 | 0.1078 | 0.1139 | 1.0 | False |
| activity_relative_q99_abs_diff | -1.0794 | -0.7189 | -0.3605 | 1.0 | False |
| activity_top1pct_share_abs_diff_pp | -5.7841 | -1.3556 | -4.4285 | 10.0 | False |
| bigram_js | 0.7811 | 0.7811 | 0.0000 | 0.4 | False |
| buyer_key_type_mix_tv | 0.0357 | 0.0663 | -0.0306 | 0.1 | False |
| candidate_cap_reached_rate | 0.0341 | 0.0341 | 0.0000 | 0.01 | False |
| candidate_p75_abs_diff | -0.5000 | 0.5000 | -1.0000 | 3.0 | False |
| candidate_p90_abs_diff | 4.0000 | 6.0000 | -2.0000 | 5.0 | False |
| candidate_p95_abs_diff | 1.9000 | 8.9000 | -7.0000 | 8.0 | True |
| candidate_source_count_ratio_deviation | 0.0431 | 0.1193 | -0.0762 | 0.2 | False |
| candidate_zero_rate_abs_diff_pp | -1.0465 | -4.3387 | 3.2922 | 5.0 | True |
| candidate_zero_rate_name_fallback_abs_diff_pp | -5.1613 | -3.0314 | -2.1299 | 10.0 | False |
| candidate_zero_rate_raw_siret_abs_diff_pp | 15.0671 | -15.4458 | 30.5129 | 10.0 | True |
| cpv_division_tv | 0.0435 | 0.0734 | -0.0299 | 0.05 | True |
| cpv_missing_abs_diff_pp | -1.2847 | -2.4045 | 1.1199 | 2.0 | True |
| duration_present_abs_diff_pp | -0.3542 | -0.5279 | 0.1737 | 5.0 | False |
| internal_duplicate_share_abs_diff_pp | 3.7558 | 3.7558 | 0.0000 | 10.0 | False |
| keys_per_notice_relative_error | -0.2661 | -0.3652 | 0.0992 | 0.2 | False |
| name_jaro_winkler_q50_abs_diff | 0.0108 | 0.0184 | -0.0075 | 0.15 | False |
| name_token_jaccard_q10_abs_diff | 0.0000 | 0.0000 | 0.0000 | 0.15 | False |
| name_token_jaccard_q50_abs_diff | 0.0321 | 0.0762 | -0.0440 | 0.15 | False |
| name_variants_per_buyer_abs_diff | -0.5242 | -0.3217 | -0.2025 | 0.5 | False |
| notice_type_tv | 0.0450 | 0.0436 | 0.0013 | 0.05 | False |
| publication_year_tvd | 0.0355 | 0.0542 | -0.0186 | 0.2 | False |
| publication_year_wmae_pp | 0.5884 | 0.8902 | -0.3019 | 1.0 | False |
| runway_60m_abs_diff_pp | 0.7255 | -0.0790 | 0.8046 | 5.0 | False |
| schema_family_tv | 0.0126 | 0.0117 | 0.0010 | 0.05 | False |
| siren_present_abs_diff_pp | -3.5348 | 6.6282 | -10.1630 | 2.0 | True |
| siret_present_abs_diff_pp | -2.7787 | 7.3843 | -10.1630 | 2.0 | True |
| text_length_q50_relative_error | 0.0296 | 0.0296 | 0.0000 | 0.1 | False |
| text_length_q75_relative_error | 0.1218 | 0.1218 | 0.0000 | 0.1 | False |
| text_length_w1_scaled | 0.1638 | 0.1638 | 0.0000 | 0.1 | False |
| token_count_q50_relative_error | 0.1765 | 0.1765 | 0.0000 | 0.2 | False |
| type_token_ratio_abs_diff | 0.0883 | 0.0883 | 0.0000 | 0.15 | False |
| unigram_js | 0.4411 | 0.4411 | 0.0000 | 0.3 | False |

Metrics with a material calibration-versus-holdout gap:
['candidate_p95_abs_diff', 'candidate_zero_rate_abs_diff_pp', 'candidate_zero_rate_raw_siret_abs_diff_pp', 'cpv_division_tv', 'cpv_missing_abs_diff_pp', 'siren_present_abs_diff_pp', 'siret_present_abs_diff_pp'].

**Not every flagged metric is a transfer failure, and one group of them cannot be.**
Checksum-valid SIRET availability is a buyer-level property -- 27% of real buyers
never publish one and 5% always do -- so splitting on buyer key splits that
property with it. The two real sides genuinely differ: 0.2993
on calibration buyers against 0.1976
on holdout buyers, a gap of 10.2 pp. A generator
calibrated to one side must differ from the other by about that amount, and it does.

The holdout therefore supplies genuine out-of-sample evidence for
*distributional-shape* metrics -- within-SIREN name similarity, publication-year
composition, candidate-count shape, activity quantiles -- and does **not** supply
an out-of-sample test of buyer-level marginal rates, which are confounded with the
split by construction. Those are reported as in-sample only. A notice-level split
would remove the confound and simultaneously destroy the out-of-sample property
for every within-buyer statistic, including the buyer-name variation this revision
exists to fix; the buyer-level split was kept and its limitation stated. Full
detail: `holdout/holdout_marginal_rate_limitation.json`.

The name metrics transfer cleanly: `name_token_jaccard` q10 and q50 pass on
**every** world against **both** real sides.

* The holdout carries roughly a quarter of real notices, so its quantile estimates are noisier; only scale-free metrics are compared.
* The real candidate baseline is filtered to holdout buyers, reducing its source count; candidate metrics are compared as rates and quantiles, never as counts.
* Synthetic buyers are not split: the same synthetic corpus is scored against both real sides, so this tests parameter transfer, not synthetic-side generalisation.

## 12. Seed stability and algorithm ranking

Seed stability is reported separately from observable fidelity, and **no generator
parameter was tuned using any of it**. Linkage results are a downstream diagnostic.

Source: `linkage_algorithm_benchmark/per_world_metrics.csv`, over
16 distinct worlds
(20 pooled including the duplicate scenario).

Paired per-world differences are computed on the *same* worlds, so world-to-world
difficulty cancels. A pair is only called a supported winner when the 95% paired
bootstrap interval excludes zero, the mean difference exceeds the
0.02 practical-equivalence
margin, and the winner is consistent across worlds.

| metric | algorithm_a | algorithm_b | n_paired_worlds | mean_paired_difference | ci_low | ci_high | monte_carlo_se_of_mean | win_rate_a | support_status |
|---|---|---|---|---|---|---|---|---|---|
| pair_f1_end_to_end | current_weighted_composite | fellegi_sunter_style | 16 | 0.0364 | 0.0242 | 0.0480 | 0.0061 | 1.0000 | SUPPORTED |
| pair_f1_end_to_end | current_weighted_composite | gradient_boosting | 16 | -0.1290 | -0.1528 | -0.1028 | 0.0129 | 0.0000 | SUPPORTED |
| pair_f1_end_to_end | current_weighted_composite | logistic_regression | 16 | -0.0903 | -0.1156 | -0.0635 | 0.0133 | 0.0000 | SUPPORTED |
| pair_f1_end_to_end | fellegi_sunter_style | gradient_boosting | 16 | -0.1653 | -0.1999 | -0.1281 | 0.0186 | 0.0000 | SUPPORTED |
| pair_f1_end_to_end | fellegi_sunter_style | logistic_regression | 16 | -0.1267 | -0.1633 | -0.0881 | 0.0192 | 0.0000 | SUPPORTED |
| pair_f1_end_to_end | gradient_boosting | logistic_regression | 16 | 0.0386 | 0.0326 | 0.0451 | 0.0032 | 1.0000 | SUPPORTED |
| pair_f1_fixed_candidate | current_weighted_composite | fellegi_sunter_style | 16 | 0.0393 | 0.0258 | 0.0523 | 0.0068 | 1.0000 | SUPPORTED |
| pair_f1_fixed_candidate | current_weighted_composite | gradient_boosting | 16 | -0.3709 | -0.4241 | -0.3115 | 0.0292 | 0.0000 | SUPPORTED |
| pair_f1_fixed_candidate | current_weighted_composite | logistic_regression | 16 | -0.2111 | -0.2762 | -0.1418 | 0.0342 | 0.0000 | SUPPORTED |
| pair_f1_fixed_candidate | fellegi_sunter_style | gradient_boosting | 16 | -0.4102 | -0.4743 | -0.3400 | 0.0347 | 0.0000 | SUPPORTED |
| pair_f1_fixed_candidate | fellegi_sunter_style | logistic_regression | 16 | -0.2504 | -0.3282 | -0.1677 | 0.0408 | 0.0000 | SUPPORTED |
| pair_f1_fixed_candidate | gradient_boosting | logistic_regression | 16 | 0.1598 | 0.1275 | 0.1959 | 0.0177 | 1.0000 | SUPPORTED |
| pair_precision | current_weighted_composite | fellegi_sunter_style | 16 | 0.0162 | 0.0107 | 0.0217 | 0.0028 | 1.0000 | PRACTICALLY_TIED |
| pair_precision | current_weighted_composite | gradient_boosting | 16 | -0.4359 | -0.5202 | -0.3420 | 0.0461 | 0.0000 | SUPPORTED |
| pair_precision | current_weighted_composite | logistic_regression | 16 | -0.2240 | -0.3082 | -0.1351 | 0.0442 | 0.0000 | SUPPORTED |
| pair_precision | fellegi_sunter_style | gradient_boosting | 16 | -0.4521 | -0.5419 | -0.3533 | 0.0486 | 0.0000 | SUPPORTED |
| pair_precision | fellegi_sunter_style | logistic_regression | 16 | -0.2402 | -0.3290 | -0.1458 | 0.0468 | 0.0000 | SUPPORTED |
| pair_precision | gradient_boosting | logistic_regression | 16 | 0.2119 | 0.1745 | 0.2502 | 0.0196 | 1.0000 | SUPPORTED |
| pair_recall_end_to_end | current_weighted_composite | fellegi_sunter_style | 16 | 0.0658 | 0.0514 | 0.0795 | 0.0072 | 1.0000 | SUPPORTED |
| pair_recall_end_to_end | current_weighted_composite | gradient_boosting | 16 | -0.0025 | -0.0113 | 0.0064 | 0.0046 | 0.3750 | PRACTICALLY_TIED |
| pair_recall_end_to_end | current_weighted_composite | logistic_regression | 16 | -0.0088 | -0.0132 | -0.0040 | 0.0023 | 0.1250 | PRACTICALLY_TIED |
| pair_recall_end_to_end | fellegi_sunter_style | gradient_boosting | 16 | -0.0684 | -0.0892 | -0.0463 | 0.0111 | 0.0625 | SUPPORTED |
| pair_recall_end_to_end | fellegi_sunter_style | logistic_regression | 16 | -0.0746 | -0.0917 | -0.0561 | 0.0092 | 0.0000 | SUPPORTED |
| pair_recall_end_to_end | gradient_boosting | logistic_regression | 16 | -0.0063 | -0.0115 | -0.0015 | 0.0026 | 0.2500 | PRACTICALLY_TIED |

Pooled ranking reproduced in 1.000 of worlds; the top-ranked method reproduced in 1.000.

### v0.3 versus v0.4 algorithm results

| algorithm | end-to-end F1 v0.3 | end-to-end F1 v0.4 | candidate-conditional precision v0.3 | candidate-conditional precision v0.4 | end-to-end recall v0.3 | end-to-end recall v0.4 |
|---|---|---|---|---|---|---|
| gradient_boosting | 0.394 | 0.354 | 0.729 | 0.719 | 0.270 | 0.235 |
| logistic_regression | 0.319 | 0.280 | 0.388 | 0.339 | 0.270 | 0.238 |
| current_weighted_composite | 0.203 | 0.165 | 0.168 | 0.130 | 0.257 | 0.225 |
| fellegi_sunter_style | 0.161 | 0.128 | 0.153 | 0.113 | 0.169 | 0.147 |

This is the question the revision could not answer before: v0.4 made buyer names
substantially harder (a ~24% zero-token-overlap alias share against v0.3's 0.5%)
and buyer keys substantially less fragmented (4.3x fewer SIRET keys). Those pull
name-dependent and identifier-dependent methods in opposite directions, so a
change in the ordering is a result about the benchmark, not a defect. Both
versions use the same fit/calibration/evaluation split: supervised models fit on
central worlds 001-004, thresholds calibrated on 005-006, evaluated on held-out
worlds 007-010.

### Duplicate scenario

`moderate` is a documented alias of `central_provisional` with the same seeds and
produces identical worlds. Statistics above are reported on the **deduplicated**
scope; the pooled scope is also written to
`seed_stability/paired_algorithm_differences.csv` for comparability with v0.3,
which included the duplicate. Pooling over-weights central and understates
interval width, so it is not the figure to quote.

### Secondary view: the frozen probe linkers

The validation framework separately evaluates three frozen probe linkers on all
50 generated artifacts, five times the coverage of the trained-model benchmark.
They are rule-based with hardcoded thresholds, so they measure the *world* using a
fixed instrument. Their ranking statistics are in
`validation_framework/probe_ranking_stability.csv` and feed the robustness gate;
they cannot support a claim about gradient boosting or logistic regression, which
is what the table above is for.

## 13. Readiness

| readiness level | v0.3 | v0.4 |
|---|---|---|
| PIPELINE_TECHNICALLY_VALID | PASS_WITH_LIMITATIONS | PASS |
| READY_FOR_PRELIMINARY_MODELING | PASS_WITH_LIMITATIONS | PASS_WITH_LIMITATIONS |
| READY_FOR_CONTROLLED_ALGORITHM_COMPARISON | FAIL | PASS_WITH_LIMITATIONS |
| READY_FOR_FINAL_ALGORITHM_RANKING | FAIL | FAIL |
| READY_FOR_VALIDATED_SYNTHETIC_BENCHMARK_RELEASE | FAIL | FAIL |

Readiness is reassessed against the whole evidence base. Resolving observable
fidelity failures does not on its own make controlled algorithm comparison or
final ranking supportable; those levels also depend on seed stability and
cross-scenario spread, which this revision did not target.

## 14. Declared residuals

* **Text length is no longer a release-gate failure, but it remains a warning.**
  The v0.4 buyer-population correction moved many more notices into the `6-20`
  and `21+` activity tiers that can receive the short same-buyer administrative
  template. The original v0.4 scalar therefore over-fired that template: the
  release artifacts showed a 30.6% same-buyer-template share against v0.3's 25.9%.

  The regenerated configuration now declares
  `same_buyer_admin_template_target_share`, and the corruption layer solves the
  effective per-world rate from the realised high-activity tier composition and
  the earlier exact/near/weak generic-text replacement probabilities. In the
  regenerated central release grid, the same-buyer-template share is back at
  25.9%, `text_length / q50_relative_error` passes, and
  `marginals / text_length / W1_scaled` is a WARNING rather than a FAIL.

  This is still not a full text-realism fix. The text-length distribution keeps a
  warning-level W1 gap, the q75 remains short, and the fresh-seed acceptance table
  still reports `text_length_w1_scaled` above its strict 0.10 tolerance. The
  consequence is now narrower: `READY_FOR_CONTROLLED_ALGORITHM_COMPARISON` can
  pass with limitations, but text-dependent claims must keep the documented
  lexical-distribution caveat.

* **`buyer_activity / relative_notices_per_buyer / q99` is resolved on the release
  validation world, but remains seed-variable.** Three pieces of evidence still
  support not tuning it further. First, the metric is genuinely unstable: twelve
  candidate parameter sets sharing one world seed and differing only in a
  candidate-environment knob produced q99 deviations spanning -1.46 to -2.94,
  a range larger than the +/-1.0 tolerance itself. Second, the trade-off is real
  and was measured: the one swept configuration that passed q99 on both
  development seeds (5,500 buyers at dispersion tempering 1.08) failed six
  candidate-environment metrics including the cap-hit rate, which is exactly the
  "fixes one metric, breaks another" case the acceptance rule rejects. Third,
  continuing to sweep against a small seed set would fit seed noise -- the failure
  mode this revision already caught once, when a parameter set scored zero
  critical failures on one development seed and two on the next.

  The seed-level spread of this metric across the release and fresh-seed grids is
  reported in `holdout/holdout_fidelity_summary.csv` and
  `fresh_seed_evaluation/fresh_seed_summary.csv` and must be quoted with it. The
  tolerance was **not** loosened and the metric was **not** redefined.



* **`notice_type_normalized == OTHER`** is 4.46% of the real corpus and absent from
  the synthetic one. Modelling it requires a new notice role (rectification and
  cancellation notices attach to an existing procedure rather than opening one),
  which is a truth-model expansion beyond this revision's scope.
* **Real `buyer_siren_raw` is entirely empty**, so `siren_invalid_among_present`
  has no real-side estimate and remains INCONCLUSIVE. This is a property of the
  real corpus, not of the generator.

## 15. Reproduction

```bash
.venv/bin/python scripts/build_real_buyer_holdout.py           # frozen; --force to redraw
.venv/bin/python scripts/calibrate_v0_4_observables.py
.venv/bin/python scripts/sweep_v0_4_mechanism_parameters.py --stage scoped
.venv/bin/python scripts/write_v0_4_scenario_config.py
.venv/bin/python scripts/generate_synthetic_benchmark_v0_4_population_alias_revision.py
.venv/bin/python scripts/validate_synthetic_benchmark.py --version v0_4_population_alias_revision
.venv/bin/python scripts/replay_synthetic_benchmark_replicates.py --version v0_4_population_alias_revision --output reports/tables/synthetic_benchmark/v0_4_population_alias_revision/validation_framework/replay_replicates.json
.venv/bin/python scripts/evaluate_v0_4_real_holdout.py
.venv/bin/python scripts/build_v0_4_revision_figures.py
.venv/bin/python scripts/assess_synthetic_benchmark_readiness.py --version v0_4_population_alias_revision
.venv/bin/python scripts/build_v0_4_revision_report.py
```

Generated 2026-08-05T08:45:24.458826+00:00.
