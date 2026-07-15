# Quantitative Survival-Sensitivity Conclusion

Generated: 2026-07-15

## Main Conclusion

The survival results are directionally informative, but not stable enough to be
treated as definitive. The event definition is sensitive to temporal-window and
duration-design choices. RMST changes moderately across duration-centered
window variants, but the underlying linked-event set changes substantially.

All results below refer to the constructed BOAMP proxy-recurrence event, not to
verified legal renewal.

## M0 Balanced Reference

Source tables:

- `reports/tables/m0_m1_linkage_comparison.csv`
- `reports/tables/survival_km_summary.csv`

| Quantity | Value |
|---|---:|
| Eligible sources | 3,159 |
| Events | 618 |
| Event rate | 19.6% |
| Censoring rate | 80.4% |
| Median survival | Not reached / infinite |
| Survival at 24 months | 0.914 |
| RMST at 60 months | 53.5 months |

Because the Kaplan-Meier curve does not cross 50% survival, median survival is
not informative in the reference design. The main descriptive survival summary
is therefore RMST at 60 months:

> RMST60 = 53.5 months.

## Temporal-Window Sensitivity

Source table: `reports/tables/m6d_temporal_window_sensitivity.csv`.

Changing the candidate window changes event counts and survival summaries:

| Window | Links | Event rate | Blocking coverage | Jaccard vs 6m | Status changes | S(24m) | RMST60 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 6 months | 618 | 19.6% | 39.1% | 1.000 | 0 | 0.914 | 53.5 |
| 9 months | 693 | 21.9% | 43.9% | 0.736 | 97 | 0.905 | 52.8 |
| 12 months | 754 | 23.9% | 47.7% | 0.579 | 196 | 0.899 | 52.2 |
| 18 months | 834 | 26.4% | 52.8% | 0.453 | 306 | 0.890 | 51.4 |

Conclusion:

> Wider windows increase detected recurrence and slightly reduce survival/RMST.
> But the link set changes a lot: at 18 months, more than 300 source event
> statuses change.

The survival curve is therefore not simply "more complete" under wider windows.
It is based on a materially different constructed event.

## Duration-Leakage Sensitivity

Source table: `reports/tables/duration_leakage_linkage_sensitivity.csv`.

| Design | Links | Event rate | Jaccard vs reference | Status changes | Median event time |
|---|---:|---:|---:|---:|---:|
| Balanced reference | 618 | 19.6% | 1.000 | 0 | 37.7 months |
| No-temporal-score, same candidate pool | 618 | 19.6% | 0.414 | 246 | 42.6 months |
| Forward 24m, no-duration design | 1,105 | 35.0% | 0.064 | 901 | 5.8 months |

Conclusion:

> Duration/design choices strongly affect which links become events. The forward
> no-duration design produces many more and much earlier events.

This means the duration variable is partly built into the event construction.
Therefore duration effects in survival models must be interpreted very
cautiously.

## Duration Effect in Cox Audit

Source table: `reports/tables/duration_leakage_cox_duration_effect.csv`.

For `log_duration`, using buyer-clustered inference:

| Design | Clustered hazard ratio | Interpretation |
|---|---:|---|
| Balanced reference | 0.620 | Longer duration associated with lower proxy-event hazard |
| No-temporal-score, same candidate pool | 0.698 | Longer duration still associated with lower proxy-event hazard |
| Forward 24m, no-duration design | 1.344 | Longer duration associated with higher proxy-event hazard |

Conclusion:

> The sign of the duration effect reverses under the forward no-duration
> design. Duration is therefore not a stable substantive predictor under the
> current linkage design.

This is one of the strongest quantitative warnings in the project.

## AFT Model Comparison

Source table: `reports/tables/survival_aft_models.csv`.

For the balanced reference:

| Model | AIC | Concordance |
|---|---:|---:|
| Weibull AFT | 8,059.8 | 0.714 |
| Log-normal AFT | 7,949.0 | 0.725 |

Conclusion:

> The log-normal AFT model fits better than Weibull for the constructed M0
> balanced event.

This comparison remains conditional on the proxy event definition and should
not be interpreted as validation of true renewal timing.

## Final Quantitative Conclusion

Under the M0 balanced reference, 618 of 3,159 sources are linked to a proxy
recurrence event, with 80.4% censoring and RMST60 of 53.5 months. Survival
summaries are moderately sensitive to temporal-window width: moving from 6 to
18 months raises the event rate from 19.6% to 26.4% and lowers RMST60 from 53.5
to 51.4 months. However, the underlying event set changes substantially, with
Jaccard overlap falling to 0.453 and 306 source event-status changes.
Duration-based sensitivity checks are more severe: removing temporal scoring or
using a forward no-duration design changes event identities sharply, and the
estimated duration effect reverses sign. Therefore, survival results should be
reported as robustness diagnostics for a constructed proxy recurrence event, not
as stable evidence of verified renewal timing.
