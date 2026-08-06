# Manual Audit Validation Report

Generated at UTC: `2026-08-06T12:53:43.237577+00:00`

Source workbook: `reports/manual_audit/real_audit_sample_100_validated.xlsx`

Validation status: `PASS`

## Gate Result

The uploaded workbook contains `100` non-blank manual labels over
`100` reviewed cases. The label vocabulary is valid.

This opens the initial manual-audit evidence gate, but it does **not** by itself
support a final population precision/recall claim because the sample is
stratified/purposive and has overlapping strata without saved inclusion weights.

## Label Counts

| reviewer_label | n_cases |
| --- | --- |
| CORRECT_LINK | 8 |
| CORRECT_REJECTION | 21 |
| INSUFFICIENT_INFORMATION | 3 |
| MISSED_LINK | 4 |
| WRONG_LINK | 64 |

## Method Diagnostics

GBM linked reviewed cases with determinate link labels:
`6` correct and `48` wrong,
diagnostic precision `0.111`.

Composite linked reviewed cases with determinate link labels:
`8` correct and `44` wrong,
diagnostic precision `0.154`.

GBM not-linked/no-candidate reviewed cases with determinate rejection labels:
`21` correct rejections and `4` missed links,
diagnostic rejection-correct rate `0.840`.

Composite not-linked/no-candidate reviewed cases with determinate rejection labels:
`21` correct rejections and `4` missed links,
diagnostic rejection-correct rate `0.840`.

## Stratum By Label

| audit_stratum | CORRECT_LINK | CORRECT_REJECTION | INSUFFICIENT_INFORMATION | MISSED_LINK | WRONG_LINK | n_cases |
| --- | --- | --- | --- | --- | --- | --- |
| censored_no_candidate | 0 | 5 | 1 | 2 | 0 | 8 |
| composite_only | 2 | 0 | 0 | 0 | 16 | 18 |
| gbm_and_composite | 3 | 0 | 0 | 0 | 15 | 18 |
| gbm_borderline_score | 2 | 0 | 0 | 0 | 10 | 12 |
| gbm_only | 0 | 0 | 1 | 0 | 13 | 14 |
| gbm_small_margin | 1 | 0 | 1 | 0 | 10 | 12 |
| rejected_composite_top_candidate | 0 | 12 | 0 | 0 | 0 | 12 |
| rejected_far_below | 0 | 4 | 0 | 2 | 0 | 6 |

## Scientific Use

Supported:
- failure-mode analysis;
- qualitative synthetic-to-real transfer assessment;
- deciding whether the provisional linkage rule needs repair before final survival claims;
- designing the next statistically interpretable audit.

Not supported:
- final real BOAMP precision;
- final real BOAMP recall;
- final event/censoring dataset freeze;
- final survival conclusions.
