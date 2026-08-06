# Manual Audit Instructions

This package is for human review of real BOAMP linkage transfer. It does not
contain labels and must not be used to claim real precision or recall until a
human reviewer fills `reviewer_label`.

Canonical review file:
`reports/tables/real_linkage_freeze/real_audit_sample_30.csv`

Blank entry template:
`reports/tables/real_linkage_freeze/manual_audit_entry_template.csv`

## Allowed Labels

- `CORRECT_LINK`
- `CORRECT_REJECTION`
- `INSUFFICIENT_INFORMATION`
- `MISSED_LINK`
- `NEEDS_SECOND_REVIEW`
- `WRONG_LINK`

## Review Procedure

1. Read the source notice evidence first: buyer, dates, CPV, duration flag, and
   source text.
2. If a candidate is present, compare the candidate notice against the source on
   buyer evidence, CPV evidence, chronology, text reuse, and substantive scope.
3. Use scores and method decisions only as context. Do not infer correctness
   from GBM, composite, thresholds, confidence tier, or acceptance status.
4. For no-candidate and rejected cases, decide whether the absence/rejection is
   credible from the evidence available in the row. Use `MISSED_LINK` only when
   the row evidence identifies a plausible successor that the method missed.
5. Leave uncertain cases as `INSUFFICIENT_INFORMATION` or
   `NEEDS_SECOND_REVIEW`; do not force a binary answer.

## Scientific Gate

Before the audit is complete, real precision and recall remain `UNKNOWN`. Event
and censoring datasets are provisional because an unlinked notice is operationally
censored, not a confirmed non-renewal.
