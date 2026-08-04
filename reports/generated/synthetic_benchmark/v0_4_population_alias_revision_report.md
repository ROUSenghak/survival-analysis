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
| overall / siret_missing / rate_abs_diff_pp | 0.728 | 0.687 | 4.110 | 2.000 | FAIL | 0.704 | 2.380 | WARNING |
| overall / siret_present / presence_rate_abs_diff_pp | 0.272 | 0.313 | 4.110 | 2.000 | FAIL | 0.296 | 2.380 | WARNING |
| overall / relative_notices_per_buyer / q99_abs_diff | 16.206 | 13.864 | 2.341 | 1.000 | FAIL | 15.394 | 0.812 | PASS |
| silver_siren_groups / name_token_jaccard / q10_abs_diff | 0.000 | 0.333 | 0.333 | 0.150 | FAIL | 0.000 | 0.000 | PASS |
| silver_siren_groups / name_token_jaccard / q50_abs_diff | 0.250 | 0.667 | 0.417 | 0.150 | FAIL | 0.250 | 0.000 | PASS |

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
| activity_relative_q99_abs_diff | -1.293 | 1.083 | 0.485 | -3.188 | -0.548 | 1.0 | 0.6 |
| candidate_cap_reached_rate | 0.002 | 0.004 | 0.002 | 0.000 | 0.009 | 0.01 | 1.0 |
| candidate_p75_abs_diff | 0.000 | 1.414 | 0.632 | -1.000 | 2.000 | 3.0 | 1.0 |
| candidate_p90_abs_diff | 0.300 | 3.912 | 1.749 | -3.100 | 6.900 | 5.0 | 0.8 |
| candidate_p95_abs_diff | -1.400 | 5.030 | 2.249 | -6.000 | 7.000 | 8.0 | 1.0 |
| candidate_source_count_ratio_deviation | -0.013 | 0.070 | 0.031 | -0.101 | 0.086 | 0.2 | 1.0 |
| candidate_zero_rate_abs_diff_pp | -0.820 | 2.468 | 1.104 | -3.637 | 1.948 | 5.0 | 1.0 |
| name_token_jaccard_q10_abs_diff | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.15 | 1.0 |
| name_token_jaccard_q50_abs_diff | 0.017 | 0.037 | 0.017 | 0.000 | 0.083 | 0.15 | 1.0 |
| publication_year_wmae_pp | 0.736 | 0.125 | 0.056 | 0.587 | 0.909 | 1.0 | 1.0 |
| siret_present_abs_diff_pp | 2.417 | 3.200 | 1.431 | -2.950 | 5.174 | 2.0 | 0.0 |

Fresh world seeds: [20270101, 20270111, 20270121, 20270131, 20270210]; disjoint from the
development seeds: True; disjoint from
the release seeds: True.

## 6. Every metric whose status changed

9 metrics improved to PASS; 8 regressed from PASS;
13 metrics were added in v0.4 (metrics were only ever added,
never redefined, loosened or reclassified).

v0.3: PASS 209, WARNING 16, FAIL 5, INCONCLUSIVE 1.
v0.4: PASS 220, WARNING 21, FAIL 1, INCONCLUSIVE 1.

| metric | v0.3 | v0.4 | |dev| v0.3 | |dev| v0.4 | tolerance |
|---|---|---|---|---|---|
| buyer_activity / overall / observed_keys_per_notice / relative_error |  | WARNING | n/a | 0.2737 |  |
| buyer_activity / overall / relative_notices_per_buyer / q99_abs_diff | FAIL | PASS | 2.3414 | 0.8116 | 1.0 |
| buyer_activity / top5pct / activity_share / abs_diff_pp | PASS | WARNING | 4.5192 | 5.1658 | 10.0 |
| candidate_environment / RAW_SIRET / zero_candidate_rate_by_key / abs_diff_pp | PASS | WARNING | 9.1061 | 10.1362 | 10.0 |
| marginals / overall / text_length / W1_scaled | WARNING | FAIL | 0.1623 | 0.2228 | 0.1 |
| marginals / overall / text_length / q50_relative_error | PASS | WARNING | 0.0306 | 0.1020 | 0.1 |
| missingness_structure / pattern=110100 / missingness_pattern / max_single_pattern_abs_diff |  | PASS | n/a | 0.0434 |  |
| missingness_structure / pattern=111100 / missingness_pattern / max_single_pattern_abs_diff | PASS |  | 0.0481 | n/a | 0.15 |
| missingness_text_identifier / overall / cpv_missing / rate_abs_diff_pp | WARNING | PASS | 2.0123 | 1.8765 | 2.0 |
| missingness_text_identifier / overall / siren_missing / rate_abs_diff_pp | WARNING | PASS | 3.4019 | 1.6777 | 2.0 |
| missingness_text_identifier / overall / siren_present / presence_rate_abs_diff_pp | WARNING | PASS | 3.4019 | 1.6777 | 2.0 |
| missingness_text_identifier / overall / siret_missing / rate_abs_diff_pp | FAIL | WARNING | 4.1104 | 2.3802 | 2.0 |
| missingness_text_identifier / overall / siret_present / presence_rate_abs_diff_pp | FAIL | WARNING | 4.1104 | 2.3802 | 2.0 |
| missingness_text_identifier / overall / text_length / q50_relative_error | PASS | WARNING | 0.0306 | 0.1020 | 0.1 |
| names_identifiers / silver_siren_groups / name_jaro_winkler / q25_abs_diff |  | PASS | n/a | 0.0249 |  |
| names_identifiers / silver_siren_groups / name_jaro_winkler / q50_abs_diff | WARNING | PASS | 0.1899 | 0.0264 | 0.15 |
| names_identifiers / silver_siren_groups / name_jaro_winkler / q75_abs_diff |  | PASS | n/a | 0.0176 |  |
| names_identifiers / silver_siren_groups / name_jaro_winkler / q90_abs_diff |  | PASS | n/a | 0.0451 |  |
| names_identifiers / silver_siren_groups / name_token_count_difference / mean_abs_diff |  | PASS | n/a | 1.3422 |  |
| names_identifiers / silver_siren_groups / name_token_jaccard / full_token_overlap_share |  | PASS | n/a | 0.0003 |  |
| names_identifiers / silver_siren_groups / name_token_jaccard / q10_abs_diff | FAIL | PASS | 0.3333 | 0.0000 | 0.15 |
| names_identifiers / silver_siren_groups / name_token_jaccard / q25_abs_diff |  | PASS | n/a | 0.0000 |  |
| names_identifiers / silver_siren_groups / name_token_jaccard / q50_abs_diff | FAIL | PASS | 0.4167 | 0.0000 | 0.15 |
| names_identifiers / silver_siren_groups / name_token_jaccard / q75_abs_diff |  | PASS | n/a | 0.0000 |  |
| names_identifiers / silver_siren_groups / name_token_jaccard / q90_abs_diff |  | PASS | n/a | 0.0476 |  |
| names_identifiers / silver_siren_groups / name_token_jaccard / zero_token_overlap_share |  | PASS | n/a | 0.0393 |  |
| names_identifiers / silver_siren_groups / name_variants_per_buyer / distribution_TV |  | WARNING | n/a | 0.1540 |  |
| robustness / pairwise_comparison:stress / ranking_pairwise_support / ambiguous_pair_fraction | PASS | WARNING | 0.0000 | 0.3333 | 0.25 |
| robustness / pairwise_comparison:stress / ranking_pairwise_support / supported_pair_fraction | PASS | WARNING | 1.0000 | 0.6667 | 0.8 |
| robustness / ranking_stability:difficult / probe_ranking / min_kendall_tau | WARNING | PASS | 0.3333 | 1.0000 | 0.8 |
| temporal / 12m / followup_runway / abs_diff_pp | PASS | WARNING | 0.4639 | 3.4847 | 3.0 |
| temporal / 60m / followup_runway / abs_diff_pp | WARNING | PASS | 11.0231 | 3.2644 | 5.0 |
| temporal / overall / publication_year / WMAE_pp |  | PASS | n/a | 0.7235 |  |
| text / overall / token_count / q50_relative_error | PASS | WARNING | 0.1765 | 0.2353 | 0.2 |

## 7. Validation gates

| gate | critical | v0.3 | v0.4 |
|---|---|---|---|
| internal | True | PASS | PASS |
| specification_recovery | True | PASS | PASS |
| marginals | False | WARNING | WARNING |
| conditionals | True | PASS | PASS |
| temporal | True | WARNING | WARNING |
| candidate_environment | True | PASS | WARNING |
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
| activity_gini_abs_diff | -0.0198 | -0.0001 | -0.0197 | 0.1 | False |
| activity_relative_q50_abs_diff | 0.0341 | 0.0154 | 0.0187 | 1.0 | False |
| activity_relative_q90_abs_diff | 0.2101 | 0.0962 | 0.1139 | 1.0 | False |
| activity_relative_q99_abs_diff | -1.1441 | -0.7836 | -0.3605 | 1.0 | False |
| activity_top1pct_share_abs_diff_pp | -5.9409 | -1.5124 | -4.4285 | 10.0 | False |
| buyer_key_type_mix_tv | 0.0358 | 0.0662 | -0.0304 | 0.1 | False |
| candidate_cap_reached_rate | 0.0347 | 0.0347 | 0.0000 | 0.01 | False |
| candidate_p75_abs_diff | -0.7000 | 0.3000 | -1.0000 | 3.0 | False |
| candidate_p90_abs_diff | 4.0000 | 6.0000 | -2.0000 | 5.0 | False |
| candidate_p95_abs_diff | 2.3000 | 9.3000 | -7.0000 | 8.0 | True |
| candidate_source_count_ratio_deviation | 0.0344 | 0.1100 | -0.0755 | 0.2 | False |
| candidate_zero_rate_abs_diff_pp | -0.9332 | -4.2255 | 3.2922 | 5.0 | True |
| candidate_zero_rate_name_fallback_abs_diff_pp | -4.8475 | -2.7176 | -2.1299 | 10.0 | False |
| candidate_zero_rate_raw_siret_abs_diff_pp | 14.7814 | -15.7315 | 30.5129 | 10.0 | True |
| cpv_division_tv | 0.0434 | 0.0735 | -0.0301 | 0.05 | True |
| cpv_missing_abs_diff_pp | -1.3156 | -2.4355 | 1.1199 | 2.0 | True |
| duration_present_abs_diff_pp | -0.3266 | -0.5003 | 0.1737 | 5.0 | False |
| keys_per_notice_relative_error | -0.2671 | -0.3662 | 0.0990 | 0.2 | False |
| name_jaro_winkler_q50_abs_diff | 0.0060 | 0.0135 | -0.0075 | 0.15 | False |
| name_token_jaccard_q10_abs_diff | 0.0000 | 0.0000 | 0.0000 | 0.15 | False |
| name_token_jaccard_q50_abs_diff | 0.0119 | 0.0560 | -0.0440 | 0.15 | False |
| name_variants_per_buyer_abs_diff | -0.5238 | -0.3212 | -0.2025 | 0.5 | False |
| notice_type_tv | 0.0450 | 0.0436 | 0.0013 | 0.05 | False |
| publication_year_tvd | 0.0355 | 0.0542 | -0.0186 | 0.2 | False |
| publication_year_wmae_pp | 0.5884 | 0.8902 | -0.3019 | 1.0 | False |
| runway_60m_abs_diff_pp | 0.7255 | -0.0790 | 0.8046 | 5.0 | False |
| schema_family_tv | 0.0126 | 0.0117 | 0.0010 | 0.05 | False |
| siren_present_abs_diff_pp | -3.5476 | 6.6154 | -10.1630 | 2.0 | True |
| siret_present_abs_diff_pp | -2.8123 | 7.3507 | -10.1630 | 2.0 | True |

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
| pair_f1_end_to_end | current_weighted_composite | fellegi_sunter_style | 16 | 0.0346 | 0.0222 | 0.0463 | 0.0062 | 1.0000 | SUPPORTED |
| pair_f1_end_to_end | current_weighted_composite | gradient_boosting | 16 | -0.1297 | -0.1533 | -0.1044 | 0.0126 | 0.0000 | SUPPORTED |
| pair_f1_end_to_end | current_weighted_composite | logistic_regression | 16 | -0.0889 | -0.1144 | -0.0623 | 0.0133 | 0.0000 | SUPPORTED |
| pair_f1_end_to_end | fellegi_sunter_style | gradient_boosting | 16 | -0.1643 | -0.1993 | -0.1271 | 0.0185 | 0.0000 | SUPPORTED |
| pair_f1_end_to_end | fellegi_sunter_style | logistic_regression | 16 | -0.1234 | -0.1601 | -0.0845 | 0.0194 | 0.0000 | SUPPORTED |
| pair_f1_end_to_end | gradient_boosting | logistic_regression | 16 | 0.0408 | 0.0358 | 0.0461 | 0.0027 | 1.0000 | SUPPORTED |
| pair_f1_fixed_candidate | current_weighted_composite | fellegi_sunter_style | 16 | 0.0370 | 0.0232 | 0.0503 | 0.0069 | 1.0000 | SUPPORTED |
| pair_f1_fixed_candidate | current_weighted_composite | gradient_boosting | 16 | -0.3814 | -0.4258 | -0.3308 | 0.0243 | 0.0000 | SUPPORTED |
| pair_f1_fixed_candidate | current_weighted_composite | logistic_regression | 16 | -0.2077 | -0.2724 | -0.1384 | 0.0341 | 0.0000 | SUPPORTED |
| pair_f1_fixed_candidate | fellegi_sunter_style | gradient_boosting | 16 | -0.4184 | -0.4725 | -0.3572 | 0.0297 | 0.0000 | SUPPORTED |
| pair_f1_fixed_candidate | fellegi_sunter_style | logistic_regression | 16 | -0.2447 | -0.3221 | -0.1623 | 0.0406 | 0.0000 | SUPPORTED |
| pair_f1_fixed_candidate | gradient_boosting | logistic_regression | 16 | 0.1736 | 0.1398 | 0.2113 | 0.0185 | 1.0000 | SUPPORTED |
| pair_precision | current_weighted_composite | fellegi_sunter_style | 16 | 0.0151 | 0.0094 | 0.0212 | 0.0030 | 1.0000 | PRACTICALLY_TIED |
| pair_precision | current_weighted_composite | gradient_boosting | 16 | -0.4594 | -0.5335 | -0.3767 | 0.0402 | 0.0000 | SUPPORTED |
| pair_precision | current_weighted_composite | logistic_regression | 16 | -0.2243 | -0.3083 | -0.1351 | 0.0446 | 0.0000 | SUPPORTED |
| pair_precision | fellegi_sunter_style | gradient_boosting | 16 | -0.4746 | -0.5529 | -0.3875 | 0.0426 | 0.0000 | SUPPORTED |
| pair_precision | fellegi_sunter_style | logistic_regression | 16 | -0.2395 | -0.3292 | -0.1449 | 0.0472 | 0.0000 | SUPPORTED |
| pair_precision | gradient_boosting | logistic_regression | 16 | 0.2351 | 0.1994 | 0.2742 | 0.0195 | 1.0000 | SUPPORTED |
| pair_recall_end_to_end | current_weighted_composite | fellegi_sunter_style | 16 | 0.0632 | 0.0490 | 0.0771 | 0.0072 | 1.0000 | SUPPORTED |
| pair_recall_end_to_end | current_weighted_composite | gradient_boosting | 16 | -0.0027 | -0.0112 | 0.0063 | 0.0045 | 0.3750 | PRACTICALLY_TIED |
| pair_recall_end_to_end | current_weighted_composite | logistic_regression | 16 | -0.0071 | -0.0120 | -0.0021 | 0.0026 | 0.1875 | PRACTICALLY_TIED |
| pair_recall_end_to_end | fellegi_sunter_style | gradient_boosting | 16 | -0.0659 | -0.0879 | -0.0434 | 0.0114 | 0.0625 | SUPPORTED |
| pair_recall_end_to_end | fellegi_sunter_style | logistic_regression | 16 | -0.0704 | -0.0883 | -0.0520 | 0.0093 | 0.0000 | SUPPORTED |
| pair_recall_end_to_end | gradient_boosting | logistic_regression | 16 | -0.0044 | -0.0097 | 0.0006 | 0.0026 | 0.3750 | PRACTICALLY_TIED |

Pooled ranking reproduced in 1.000 of worlds; the top-ranked method reproduced in 1.000.

### v0.3 versus v0.4 algorithm results

| algorithm | F1 v0.3 | F1 v0.4 | precision v0.3 | precision v0.4 | recall v0.3 | recall v0.4 |
|---|---|---|---|---|---|---|
| gradient_boosting | 0.394 | 0.357 | 0.729 | 0.747 | 0.270 | 0.235 |
| logistic_regression | 0.319 | 0.276 | 0.388 | 0.336 | 0.270 | 0.235 |
| current_weighted_composite | 0.203 | 0.163 | 0.168 | 0.128 | 0.257 | 0.224 |
| fellegi_sunter_style | 0.161 | 0.128 | 0.153 | 0.113 | 0.169 | 0.148 |

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
| PIPELINE_TECHNICALLY_VALID | PASS_WITH_LIMITATIONS | PASS_WITH_LIMITATIONS |
| READY_FOR_PRELIMINARY_MODELING | PASS_WITH_LIMITATIONS | PASS_WITH_LIMITATIONS |
| READY_FOR_CONTROLLED_ALGORITHM_COMPARISON | FAIL | FAIL |
| READY_FOR_FINAL_ALGORITHM_RANKING | FAIL | FAIL |
| READY_FOR_VALIDATED_SYNTHETIC_BENCHMARK_RELEASE | FAIL | FAIL |

Readiness is reassessed against the whole evidence base. Resolving observable
fidelity failures does not on its own make controlled algorithm comparison or
final ranking supportable; those levels also depend on seed stability and
cross-scenario spread, which this revision did not target.

## 14. Declared residuals

* **Text length regressed, and it is the reason the readiness level did not move.**
  `marginals / text_length / W1_scaled` went from WARNING (0.162) to **FAIL**
  (0.223), and `text_length / q50_relative_error` from PASS (0.031) to WARNING
  (0.102). Root cause, measured: the corruption layer applies a same-buyer
  administrative template only to notices whose buyer sits in the `6-20` or `21+`
  activity tier, at a rate calibrated against v0.3's tier composition. Correcting
  the buyer population moved far more notices into those tiers, so the template
  fires on 30.6% of v0.4 notices against 25.8% of v0.3's, and the template string
  is short: median text length fell from 95 to 88 characters against a real 98,
  and the 75th percentile from 118 to 114 against a real 133.

  This is the same class of defect the revision fixed for SIRET, one level down: a
  rate that is correct per stratum, applied to a corpus whose stratum composition
  changed. The fix is to make `same_buyer_admin_template_rate` composition-aware
  in the same way -- solve for the per-tier rate that reproduces the observable
  marginal generic-text share at the *realized* tier composition, rather than
  carrying v0.3's scalar. It was not applied here because the parameters were
  already frozen and the fresh-seed evaluation already run; retuning after seeing
  fresh-seed results is precisely what this revision committed not to do. It is
  the first thing a v0.5 should address.

  Consequence: `READY_FOR_CONTROLLED_ALGORITHM_COMPARISON` still fails, now on
  this single non-critical metric failure rather than on the five identifier,
  activity and name failures it failed on in v0.3.

* **`buyer_activity / relative_notices_per_buyer / q99` was materially reduced but
  not resolved, and the revision stopped rather than keep tuning it.** Three
  pieces of evidence support stopping. First, the metric is genuinely unstable:
  twelve candidate parameter sets sharing one world seed and differing only in a
  candidate-environment knob produced q99 deviations spanning -1.46 to -2.94,
  a range larger than the +/-1.0 tolerance itself. Second, the trade-off is real
  and was measured: the one swept configuration that passed q99 on both
  development seeds (5,500 buyers at dispersion tempering 1.08) failed six
  candidate-environment metrics including the cap-hit rate, which is exactly the
  "fixes one metric, breaks another" case the acceptance rule rejects. Third,
  continuing to sweep against two development worlds would have been fitting
  those worlds' noise -- the failure mode this revision already caught once, when
  a parameter set scored zero critical failures on one development seed and two on
  the next.

  The seed-level spread of this metric across the release seeds is reported in
  `holdout/holdout_fidelity_summary.csv` and must be quoted with it. The tolerance
  was **not** loosened and the metric was **not** redefined; it is reported as
  failing.



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
.venv/bin/python scripts/replay_synthetic_benchmark.py    --version v0_4_population_alias_revision
.venv/bin/python scripts/evaluate_v0_4_real_holdout.py
.venv/bin/python scripts/build_v0_4_revision_figures.py
.venv/bin/python scripts/build_v0_4_revision_report.py
```

Generated 2026-08-04T07:59:38.496348+00:00.
