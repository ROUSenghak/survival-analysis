# Manual-Audit Repair Rule v1

Generated at UTC: `2026-08-06T13:12:30.953600+00:00`

Rule version: `manual_audit_repair_v1_text030_initial_no_linked_ref_min4tokens`

## Verdict

The first completed manual audit showed that the existing accepted-link rules
transfer poorly to real BOAMP. Repair rule v1 is a conservative, interpretable
candidate designed to remove the dominant observed failure modes before building
new validation material.

This is **not** the final real-BOAMP linkage rule. It was derived after looking
at the first audit, so its same-audit diagnostic performance is optimistic until
validated on a fresh probability-designed sample.

## Rule

Keep a link only if the maintained method already accepted it and all conditions
hold:

- `s_text >= 0.3`;
- `source_etat == INITIAL`;
- `candidate_etat == INITIAL`;
- no explicit `annonce_lie` reference between source and candidate;
- source and candidate object texts each have at least `4` tokens.

## Real BOAMP Link Counts

| method | base_links | repaired_links | base_link_rate | repaired_link_rate | links_removed | median_s_text_repaired | median_composite_score_repaired | median_margin_repaired |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| primary_gbm | 411 | 123 | 0.12159763313609467 | 0.0363905325443787 | 288 | 0.7475511793813263 | 0.7410954762576875 | 0.4575471569470599 |
| composite_balanced | 1003 | 269 | 0.2967455621301775 | 0.07958579881656805 | 734 | 0.6142114018460783 | 0.5656922743088171 | 0.2731326773334184 |

## Same-Audit Diagnostic

| method | reviewed_determinate_linked_before_repair | reviewed_correct_before_repair | reviewed_wrong_before_repair | reviewed_determinate_linked_after_repair | reviewed_correct_after_repair | reviewed_wrong_after_repair | diagnostic_precision_after_repair_same_audit | wrong_reviewed_links_removed | correct_reviewed_links_removed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| primary_gbm | 54 | 6 | 48 | 5 | 5 | 0 | 1.0 | 48 | 1 |
| composite_balanced | 52 | 8 | 44 | 8 | 7 | 1 | 0.875 | 43 | 1 |

## Interpretation

The preferred repair candidate for fresh validation is
`composite_balanced_manual_audit_repair_v1_text030_initial_no_linked_ref_min4tokens` because it preserved more manually confirmed
correct links in the diagnostic audit than the GBM repair while removing most
wrong reviewed links.

Do not use this same-audit diagnostic as final precision. The next step is a
new validation sample with saved stratum populations and inclusion weights.
