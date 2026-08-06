# Manual Audit Failure Analysis

Generated at UTC: `2026-08-06T13:01:11.108972+00:00`

Input: `reports/tables/manual_audit/real_audit_validated_labels.csv`

## Verdict

The completed 100-case audit identifies a serious synthetic-to-real transfer
problem for accepted links. Among the reviewed determinate accepted-link cases,
the dominant failure is not weak chronology; it is substantive mismatch: the
same buyer issues several digital procurements, and the linker often treats a
different software, equipment, lot, beneficiary, or administrative notice update
as a renewal.

This is a diagnostic, stratified audit. It should drive rule repair and the next
weighted validation sample, not a final population precision/recall claim.

## Headline Counts

- Wrong links: `64`
- Correct links: `8`
- High-confidence wrong links: `48`
- Wrong links flagged as material scope mismatch: `55`
- Wrong links flagged as administrative version/rectificatif: `8`

## Method-Level Diagnostic Precision

| method | linked_reviewed | determinate_link_reviews | correct_links | wrong_links | diagnostic_precision | insufficient_link_reviews |
| --- | --- | --- | --- | --- | --- | --- |
| primary_gbm | 56 | 54 | 6 | 48 | 0.1111111111111111 | 2 |
| composite_balanced | 53 | 52 | 8 | 44 | 0.15384615384615385 | 1 |

## Failure Modes Among Wrong Links

| failure_mode | n_wrong_links | share_wrong_links | median_s_text | median_s_cpv | median_margin | median_n_candidates | median_buyer_n_sources |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MATERIAL_SCOPE_MISMATCH | 55 | 0.859375 | 0.065630527192823 | 0.2 | 0.1154175650535285 | 2.0 | 20.0 |
| NAME_FALLBACK_IDENTITY_RISK | 54 | 0.84375 | 0.10723364701040095 | 0.2 | 0.11932640741742055 | 2.0 | 19.0 |
| SAME_BUYER_BROAD_DIGITAL_SIGNAL | 52 | 0.8125 | 0.0655043966666353 | 0.2 | 0.11843680466588374 | 2.0 | 20.0 |
| LOW_TEXT_EVIDENCE | 44 | 0.6875 | 0.0318632119928825 | 0.2 | 0.10577314433808105 | 2.0 | 20.5 |
| METHOD_DISAGREEMENT_FALSE_POSITIVE | 36 | 0.5625 | 0.03632007794125135 | 0.1 | 0.14771611178299265 | 1.0 | 16.5 |
| HIGH_BUYER_ACTIVITY_AMBIGUITY | 34 | 0.53125 | 0.10095120711714234 | 0.8 | 0.0671114190744416 | 7.0 | 36.0 |
| HIGH_CPV_FALSE_SECURITY | 25 | 0.390625 | 0.1126273011757576 | 1.0 | 0.0549259290917627 | 7.0 | 28.0 |
| SMALL_MARGIN_AMBIGUITY | 18 | 0.28125 | 0.05207303766107045 | 0.8 | 0.0164328632912481 | 7.0 | 52.0 |
| ADMINISTRATIVE_VERSION_OR_RECTIFICATIF | 8 | 0.125 | 0.9169354519512396 | 1.0 | 0.22305974987442284 | 2.5 | 32.0 |

## Stratum-Level Pattern

| audit_stratum | n_cases | n_wrong_links | wrong_share | material_scope_mismatch | administrative_version_or_rectificatif | same_buyer_broad_digital_signal | high_buyer_activity_ambiguity | name_fallback_identity_risk | high_cpv_false_security | low_text_evidence | small_margin_ambiguity | method_disagreement_false_positive |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| composite_only | 18 | 16 | 0.8888888888888888 | 13 | 2 | 12 | 10 | 13 | 2 | 9 | 6 | 16 |
| gbm_and_composite | 18 | 15 | 0.8333333333333334 | 12 | 3 | 11 | 9 | 12 | 13 | 8 | 1 | 0 |
| gbm_only | 14 | 13 | 0.9285714285714286 | 13 | 1 | 13 | 5 | 12 | 0 | 12 | 1 | 13 |
| gbm_borderline_score | 12 | 10 | 0.8333333333333334 | 9 | 0 | 9 | 1 | 10 | 0 | 7 | 0 | 7 |
| gbm_small_margin | 12 | 10 | 0.8333333333333334 | 8 | 2 | 7 | 9 | 7 | 10 | 8 | 10 | 0 |
| censored_no_candidate | 8 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| rejected_composite_top_candidate | 12 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| rejected_far_below | 6 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Single-Filter Repair Signals

These are univariate diagnostics only. Do not freeze a new rule from these
alone; use them to define a repair candidate and then validate it on a new
probability-designed audit sample.

| candidate_repair_filter | reviewed_links_kept | correct_links_kept | wrong_links_kept | diagnostic_precision_if_filter_used_alone | wrong_links_removed | correct_links_removed |
| --- | --- | --- | --- | --- | --- | --- |
| s_text >= 0.20 | 28 | 8 | 20 | 0.2857142857142857 | 44 | 0 |
| s_text >= 0.30 | 15 | 7 | 8 | 0.4666666666666667 | 56 | 1 |
| s_text >= 0.40 | 13 | 6 | 7 | 0.46153846153846156 | 57 | 2 |
| s_cpv >= 0.80 | 30 | 5 | 25 | 0.16666666666666666 | 39 | 3 |
| top1_top2_margin >= 0.05 | 53 | 7 | 46 | 0.1320754716981132 | 18 | 1 |
| buyer_key_type != NAME_FALLBACK | 13 | 3 | 10 | 0.23076923076923078 | 54 | 5 |
| n_candidates_for_source < 10 | 56 | 7 | 49 | 0.125 | 15 | 1 |
| buyer_n_sources < 20 | 36 | 5 | 31 | 0.1388888888888889 | 33 | 3 |
| not administrative version/rectificatif | 64 | 8 | 56 | 0.125 | 8 | 0 |

## Immediate Scientific Interpretation

1. Same-buyer blocking is necessary but insufficient. High-activity buyers
   generate many false same-buyer candidates.
2. CPV agreement is not specific enough for real renewal evidence. Several
   wrong links have high CPV similarity.
3. The models over-trust broad digital language and administrative continuity.
4. `NAME_FALLBACK` identity is a major risk surface in the reviewed failures.
5. eForms versions and rectificatifs need explicit exclusion or down-weighting
   before treating a link as a survival event.

## Recommended Repair Direction

- Add an administrative-update exclusion feature/rule for rectificatifs,
  same-procedure versions, changed-notice references, and cancellation/update
  notices.
- Make text evidence stricter for accepted events, especially when buyer
  identity is `NAME_FALLBACK` or buyer activity is high.
- Penalize high candidate-count/high buyer-activity cases unless the text/CPV
  evidence is very specific.
- Treat CPV as supporting evidence only; do not let high CPV compensate for
  low text similarity and generic same-buyer context.
- After repair, draw a new validation sample with saved stratum populations and
  inclusion probabilities.
