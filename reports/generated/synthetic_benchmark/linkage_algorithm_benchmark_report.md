# Synthetic BOAMP Linkage Algorithm Benchmark Report

Generated: 2026-07-30  
Benchmark version: `v0_3_temporal_candidate_revision`  
Primary source notebook: `notebooks/14_linkage_algorithm_benchmark.ipynb`

## Technical Summary

Gradient boosting is the strongest current linker on the corrected synthetic benchmark. It reaches
precision **0.729**, end-to-end recall **0.270**,
and end-to-end pair-F1 **0.394** across the held-out evaluation grid.

The result is not mainly a "which classifier can separate pairs" story. It is a pipeline story:
the production candidate generator exposes only **10,825** of **31,426**
in-scope truth links to scoring, a weighted blocking recall of **34.4%**
and an unweighted world-average recall of **0.323**. This is why gradient boosting has
fixed-candidate F1 **0.756** but end-to-end F1 only
**0.394**.

Logistic regression recovers essentially the same number of true links as gradient boosting
(8,496 versus 8,494), but accepts far more
links (21,878 versus 11,648). The extra volume lowers
precision from **0.729** to **0.388**. The current weighted
composite and Fellegi-Sunter-style baseline remain useful comparators, but they are not the preferred
scorers under this benchmark.

## Gradient Boosting Wins, Mostly By Reducing False Positives

The four algorithms were evaluated on the same held-out candidate-pair universe. Gradient boosting
accepts fewer links than logistic regression and the composite baseline, while retaining nearly the
same true-positive count as logistic regression. That makes it the best current choice for synthetic
benchmark ranking and the least risky of the tested options for downstream survival-analysis pilots.

![Pair-F1 by evaluation mode](reports/figures/synthetic_benchmark/v0_3_temporal_candidate_revision/linkage_algorithm_benchmark/pair_f1_by_mode.png)

| Algorithm | Predicted links | True positives | Precision | Fixed-candidate recall | End-to-end recall | End-to-end F1 |
| --- | --- | --- | --- | --- | --- | --- |
| Gradient boosting | 11,648 | 8,494 | 0.729 | 0.785 | 0.270 | 0.394 |
| Logistic regression | 21,878 | 8,496 | 0.388 | 0.785 | 0.270 | 0.319 |
| Current weighted composite | 48,072 | 8,061 | 0.168 | 0.745 | 0.257 | 0.203 |
| Fellegi-Sunter style | 34,581 | 5,308 | 0.153 | 0.490 | 0.169 | 0.161 |

Interpretation: logistic regression and gradient boosting have nearly identical end-to-end recall
(0.270 versus 0.270), but gradient boosting
is much more selective. Compared with the current weighted composite, gradient boosting improves
precision by **4.3x** and end-to-end F1 by
**1.9x**.

## Candidate Generation Is The Binding Constraint

End-to-end performance is much lower than fixed-candidate performance because most truth links never
enter the candidate set. The evaluation run scored **767,431** candidate pairs over
**31,426** in-scope truth links, but only **10,825** truth links were
reachable by the production candidate generator.

| Scenario | Worlds | Candidate pairs | Truth links | Reachable truth | Mean blocking recall | Min | Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| central_provisional | 4 | 68,528 | 6,635 | 2,586 | 0.394 | 0.341 | 0.427 |
| difficult | 4 | 140,698 | 3,999 | 1,039 | 0.262 | 0.214 | 0.284 |
| easier | 4 | 103,267 | 10,127 | 3,966 | 0.397 | 0.342 | 0.424 |
| moderate | 4 | 68,528 | 6,635 | 2,586 | 0.394 | 0.341 | 0.427 |
| stress | 4 | 386,410 | 4,030 | 648 | 0.166 | 0.132 | 0.204 |

The stress scenario makes this clearest: it creates **386,410** candidate pairs but exposes only
**648** of **4,030** truth links to scoring. No scoring model can recover links that were never
generated. Therefore the next major gain should come from candidate generation, not only from another
classifier.

## Scenario Results Show Robust Ranking But Different Difficulty

Gradient boosting ranks first in every evaluated scenario. The ranking is stable, but the absolute
performance changes sharply as the benchmark gets harder.

![Scenario F1](reports/figures/synthetic_benchmark/v0_3_temporal_candidate_revision/linkage_algorithm_benchmark/scenario_pair_f1.png)

| Scenario | Algorithm | Mean F1 | Mean precision | Mean recall | SD F1 |
| --- | --- | --- | --- | --- | --- |
| central_provisional | Gradient boosting | 0.457 | 0.800 | 0.321 | 0.033 |
| central_provisional | Logistic regression | 0.427 | 0.646 | 0.319 | 0.038 |
| central_provisional | Current weighted composite | 0.305 | 0.309 | 0.303 | 0.050 |
| central_provisional | Fellegi-Sunter style | 0.235 | 0.284 | 0.202 | 0.043 |
| difficult | Gradient boosting | 0.246 | 0.493 | 0.165 | 0.026 |
| difficult | Logistic regression | 0.192 | 0.212 | 0.176 | 0.037 |
| difficult | Current weighted composite | 0.110 | 0.085 | 0.160 | 0.031 |
| difficult | Fellegi-Sunter style | 0.087 | 0.082 | 0.098 | 0.027 |
| easier | Gradient boosting | 0.481 | 0.861 | 0.334 | 0.038 |
| easier | Logistic regression | 0.451 | 0.727 | 0.328 | 0.038 |
| easier | Current weighted composite | 0.322 | 0.334 | 0.313 | 0.051 |
| easier | Fellegi-Sunter style | 0.248 | 0.307 | 0.209 | 0.040 |
| moderate | Gradient boosting | 0.457 | 0.800 | 0.321 | 0.033 |
| moderate | Logistic regression | 0.427 | 0.646 | 0.319 | 0.038 |
| moderate | Current weighted composite | 0.305 | 0.309 | 0.303 | 0.050 |
| moderate | Fellegi-Sunter style | 0.235 | 0.284 | 0.202 | 0.043 |
| stress | Gradient boosting | 0.122 | 0.260 | 0.080 | 0.028 |
| stress | Logistic regression | 0.065 | 0.052 | 0.090 | 0.020 |
| stress | Current weighted composite | 0.037 | 0.024 | 0.089 | 0.013 |
| stress | Fellegi-Sunter style | 0.028 | 0.020 | 0.051 | 0.010 |

The easier, central, and moderate settings support useful discrimination among algorithms. The
difficult and stress settings are more diagnostic of failure modes. In stress, gradient boosting still
leads, but end-to-end F1 falls to **0.122** because blocking recall and candidate ambiguity both worsen.
Central and moderate are identical in this executed run, so they should not be interpreted as separate
difficulty levels until their scenario definitions diverge.

## Mechanical Bias Remains Visible

The benchmark shows systematic performance differences by identifier quality, candidate count, schema,
and CPV availability. These are expected linkage failure modes, but they matter because survival analysis
could inherit them.

![Recall by candidate count bin](reports/figures/synthetic_benchmark/v0_3_temporal_candidate_revision/linkage_algorithm_benchmark/recall_by_candidate_count_bin.png)

For gradient boosting, end-to-end recall is **0.600**
when a source has exactly one candidate, but only **0.115**
when it has sixteen or more candidates. This is the strongest bias diagnostic: crowded candidate
environments are under-linked.

![Recall by buyer key type](reports/figures/synthetic_benchmark/v0_3_temporal_candidate_revision/linkage_algorithm_benchmark/recall_by_buyer_key_type_heatmap.png)

Identifier quality also matters. Gradient boosting recall is
**0.329** for `RAW_SIRET` truth links versus
**0.251** for `NAME_FALLBACK`. CPV availability
matters as well: recall is **0.286** when CPV is present
and **0.133** when CPV is missing.

## Thresholds And Model Setup

The current composite and Fellegi-Sunter thresholds are frozen. Logistic regression and gradient
boosting thresholds are selected on central calibration worlds `005` and `006` by F1 maximization.
Training uses central worlds `001` through `004`; evaluation uses worlds `007` through `010` across
central provisional, easier, moderate, difficult, and stress scenarios.

| Algorithm | Score column | Threshold | Threshold source |
| --- | --- | --- | --- |
| Current weighted composite | composite_score | 0.343167 | production primary threshold |
| Fellegi-Sunter style | fs_log_odds | 0 | frozen zero log-odds threshold |
| Logistic regression | logistic_score | 0.824308 | calibration F1 maximum |
| Gradient boosting | gradient_boosting_score | 0.265103 | calibration F1 maximum |

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

- Executed notebook: `notebooks/14_linkage_algorithm_benchmark.ipynb`
- Summary table: `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/linkage_algorithm_benchmark/summary_metrics.csv`
- Scenario table: `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/linkage_algorithm_benchmark/scenario_summary_metrics.csv`
- Bias diagnostics: `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/linkage_algorithm_benchmark/recall_slices.csv`
