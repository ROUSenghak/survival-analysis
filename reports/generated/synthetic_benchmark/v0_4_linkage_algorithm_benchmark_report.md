# Synthetic BOAMP Linkage Algorithm Benchmark Report

Generated: 2026-08-04  
Benchmark version: `v0_4_population_alias_revision`  
Primary source notebook: `notebooks/14_linkage_algorithm_benchmark_v0_4.ipynb`

## Technical Summary

Gradient boosting is the strongest current linker on the corrected synthetic benchmark. It reaches
precision **0.747**, end-to-end recall **0.235**,
and end-to-end pair-F1 **0.357** across the held-out evaluation grid.

The result is not mainly a "which classifier can separate pairs" story. It is a pipeline story:
the production candidate generator exposes only **10,315** of **32,050**
in-scope truth links to scoring, a weighted blocking recall of **32.2%**
and an unweighted world-average recall of **0.293**. This is why gradient boosting has
fixed-candidate F1 **0.738** but end-to-end F1 only
**0.357**.

Logistic regression recovers essentially the same number of true links as gradient boosting
(7,519 versus 7,517), but accepts far more
links (22,408 versus 10,057). The extra volume lowers
precision from **0.747** to **0.336**. The current weighted
composite and Fellegi-Sunter-style baseline remain useful comparators, but they are not the preferred
scorers under this benchmark.

## Gradient Boosting Wins, Mostly By Reducing False Positives

The four algorithms were evaluated on the same held-out candidate-pair universe. Gradient boosting
accepts fewer links than logistic regression and the composite baseline, while retaining nearly the
same true-positive count as logistic regression. That makes it the best current choice for synthetic
benchmark ranking and the least risky of the tested options for downstream survival-analysis pilots.

![Pair-F1 by evaluation mode](reports/figures/synthetic_benchmark/v0_4_population_alias_revision/linkage_algorithm_benchmark/pair_f1_by_mode.png)

| Algorithm | Predicted links | True positives | Precision | Fixed-candidate recall | End-to-end recall | End-to-end F1 |
| --- | --- | --- | --- | --- | --- | --- |
| Gradient boosting | 10,057 | 7,517 | 0.747 | 0.729 | 0.235 | 0.357 |
| Logistic regression | 22,408 | 7,519 | 0.336 | 0.729 | 0.235 | 0.276 |
| Current weighted composite | 56,017 | 7,189 | 0.128 | 0.697 | 0.224 | 0.163 |
| Fellegi-Sunter style | 42,040 | 4,739 | 0.113 | 0.459 | 0.148 | 0.128 |

Interpretation: logistic regression and gradient boosting have nearly identical end-to-end recall
(0.235 versus 0.235), but gradient boosting
is much more selective. Compared with the current weighted composite, gradient boosting improves
precision by **5.8x** and end-to-end F1 by
**2.2x**.

## Candidate Generation Is The Binding Constraint

End-to-end performance is much lower than fixed-candidate performance because most truth links never
enter the candidate set. The evaluation run scored **876,190** candidate pairs over
**32,050** in-scope truth links, but only **10,315** truth links were
reachable by the production candidate generator.

| Scenario | Worlds | Candidate pairs | Truth links | Reachable truth | Mean blocking recall | Min | Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| central_provisional | 4 | 81,457 | 6,435 | 2,183 | 0.340 | 0.307 | 0.359 |
| difficult | 4 | 175,881 | 3,723 | 851 | 0.231 | 0.196 | 0.267 |
| easier | 4 | 142,948 | 11,526 | 4,449 | 0.387 | 0.350 | 0.402 |
| moderate | 4 | 81,457 | 6,435 | 2,183 | 0.340 | 0.307 | 0.359 |
| stress | 4 | 394,447 | 3,931 | 649 | 0.166 | 0.157 | 0.182 |

The stress scenario makes this clearest: it creates **386,410** candidate pairs but exposes only
**648** of **4,030** truth links to scoring. No scoring model can recover links that were never
generated. Therefore the next major gain should come from candidate generation, not only from another
classifier.

## Scenario Results Show Robust Ranking But Different Difficulty

Gradient boosting ranks first in every evaluated scenario. The ranking is stable, but the absolute
performance changes sharply as the benchmark gets harder.

![Scenario F1](reports/figures/synthetic_benchmark/v0_4_population_alias_revision/linkage_algorithm_benchmark/scenario_pair_f1.png)

| Scenario | Algorithm | Mean F1 | Mean precision | Mean recall | SD F1 |
| --- | --- | --- | --- | --- | --- |
| central_provisional | Gradient boosting | 0.387 | 0.778 | 0.258 | 0.019 |
| central_provisional | Logistic regression | 0.354 | 0.561 | 0.259 | 0.020 |
| central_provisional | Current weighted composite | 0.223 | 0.204 | 0.247 | 0.020 |
| central_provisional | Fellegi-Sunter style | 0.172 | 0.183 | 0.163 | 0.018 |
| difficult | Gradient boosting | 0.178 | 0.487 | 0.109 | 0.011 |
| difficult | Logistic regression | 0.123 | 0.127 | 0.120 | 0.017 |
| difficult | Current weighted composite | 0.063 | 0.044 | 0.111 | 0.013 |
| difficult | Fellegi-Sunter style | 0.047 | 0.036 | 0.068 | 0.012 |
| easier | Gradient boosting | 0.462 | 0.881 | 0.314 | 0.019 |
| easier | Logistic regression | 0.426 | 0.711 | 0.304 | 0.017 |
| easier | Current weighted composite | 0.280 | 0.271 | 0.290 | 0.014 |
| easier | Fellegi-Sunter style | 0.215 | 0.242 | 0.193 | 0.015 |
| moderate | Gradient boosting | 0.387 | 0.778 | 0.258 | 0.019 |
| moderate | Logistic regression | 0.354 | 0.561 | 0.259 | 0.020 |
| moderate | Current weighted composite | 0.223 | 0.204 | 0.247 | 0.020 |
| moderate | Fellegi-Sunter style | 0.172 | 0.183 | 0.163 | 0.018 |
| stress | Gradient boosting | 0.083 | 0.226 | 0.051 | 0.022 |
| stress | Logistic regression | 0.043 | 0.032 | 0.066 | 0.008 |
| stress | Current weighted composite | 0.026 | 0.016 | 0.072 | 0.005 |
| stress | Fellegi-Sunter style | 0.019 | 0.012 | 0.043 | 0.002 |

The easier, central, and moderate settings support useful discrimination among algorithms. The
difficult and stress settings are more diagnostic of failure modes. In stress, gradient boosting still
leads, but end-to-end F1 falls to **0.122** because blocking recall and candidate ambiguity both worsen.
Central and moderate are identical in this executed run, so they should not be interpreted as separate
difficulty levels until their scenario definitions diverge.

## Mechanical Bias Remains Visible

The benchmark shows systematic performance differences by identifier quality, candidate count, schema,
and CPV availability. These are expected linkage failure modes, but they matter because survival analysis
could inherit them.

![Recall by candidate count bin](reports/figures/synthetic_benchmark/v0_4_population_alias_revision/linkage_algorithm_benchmark/recall_by_candidate_count_bin.png)

For gradient boosting, end-to-end recall is **0.552**
when a source has exactly one candidate, but only **0.113**
when it has sixteen or more candidates. This is the strongest bias diagnostic: crowded candidate
environments are under-linked.

![Recall by buyer key type](reports/figures/synthetic_benchmark/v0_4_population_alias_revision/linkage_algorithm_benchmark/recall_by_buyer_key_type_heatmap.png)

Identifier quality also matters. Gradient boosting recall is
**0.278** for `RAW_SIRET` truth links versus
**0.224** for `NAME_FALLBACK`. CPV availability
matters as well: recall is **0.251** when CPV is present
and **0.088** when CPV is missing.

## Thresholds And Model Setup

The current composite and Fellegi-Sunter thresholds are frozen. Logistic regression and gradient
boosting thresholds are selected on central calibration worlds `005` and `006` by F1 maximization.
Training uses central worlds `001` through `004`; evaluation uses worlds `007` through `010` across
central provisional, easier, moderate, difficult, and stress scenarios.

| Algorithm | Score column | Threshold | Threshold source |
| --- | --- | --- | --- |
| Current weighted composite | composite_score | 0.343167 | production primary threshold |
| Fellegi-Sunter style | fs_log_odds | 0 | frozen zero log-odds threshold |
| Logistic regression | logistic_score | 0.757136 | calibration F1 maximum |
| Gradient boosting | gradient_boosting_score | 0.221966 | calibration F1 maximum |

The supervised models use pair-level scoring features already produced by the project pipeline:
text similarity, CPV similarity, time score, buyer reliability score, gap features, candidate count,
schema family, buyer key type, CPV missingness, and duration missingness indicators. The report does
not claim these features are unbiased; the bias diagnostics above show that several are mechanically
important.

## Limitations And Robustness Notes

These results are valid for the current synthetic benchmark, not for real BOAMP ground truth. The
synthetic truth labels are generated, so model ranking can still contain generator-mechanism bias.
The report supports the claim that gradient boosting is best among the four tested linkers on this
synthetic benchmark; it does not prove real-world BOAMP linkage accuracy.

The aggregate metrics are corrected to use a global pair key containing scenario, world, and notice
pair. This avoids collisions from repeated synthetic notice IDs across generated worlds. The notebook
was rerun after that correction and all tables in this report use the corrected outputs.

The fixed-candidate view is useful for comparing scorers, but the end-to-end view is the decision-relevant
pipeline metric. If downstream survival analysis needs low false positives, gradient boosting is the
best candidate among the tested models. If it needs high recall, the current candidate generation must
be widened or redesigned.

## Recommended Next Steps

1. Use gradient boosting as the primary supervised linker for the next synthetic benchmark round.
2. Keep logistic regression as the interpretable supervised baseline, and keep the current composite
   and Fellegi-Sunter style models as frozen reference baselines.
3. Improve candidate generation before treating linkage as production-ready. Test wider temporal
   windows, alternate buyer-name blocking, CPV fallback blocking, and high-activity buyer handling.
4. Add a manually labeled real BOAMP validation set before making claims about real BOAMP accuracy.
5. Run survival-analysis sensitivity with at least three linkage layers: current composite, gradient
   boosting, and a high-precision conservative subset.

## Further Questions

1. How much end-to-end recall is recovered by widening candidate generation without creating too many
   false-positive candidates?
2. Are high-activity buyers under-linked enough to bias survival estimates?
3. Can a conservative gradient-boosting threshold provide a high-precision survival layer while a broader
   threshold supports recall sensitivity?
4. Do manually labeled real BOAMP pairs preserve the same algorithm ranking observed in synthetic truth?

## Source Artifacts

- Executed notebook: `notebooks/14_linkage_algorithm_benchmark_v0_4.ipynb`
- Summary table: `reports/tables/synthetic_benchmark/v0_4_population_alias_revision/linkage_algorithm_benchmark/summary_metrics.csv`
- Scenario table: `reports/tables/synthetic_benchmark/v0_4_population_alias_revision/linkage_algorithm_benchmark/scenario_summary_metrics.csv`
- Bias diagnostics: `reports/tables/synthetic_benchmark/v0_4_population_alias_revision/linkage_algorithm_benchmark/recall_slices.csv`
