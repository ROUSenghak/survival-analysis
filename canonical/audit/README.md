# Canonical Manual Audit Package

Canonical initial review package:

- `reports/tables/real_linkage_freeze/real_audit_sample_30.csv`
- `reports/tables/real_linkage_freeze/manual_audit_entry_template.csv`
- `reports/generated/manual_audit_instructions.md`

Allowed labels:

- `CORRECT_LINK`
- `WRONG_LINK`
- `MISSED_LINK`
- `CORRECT_REJECTION`
- `INSUFFICIENT_INFORMATION`

Use the separate `needs_second_review` flag if a case should be revisited later.

Completed uploaded validation evidence:

- `reports/manual_audit/real_audit_sample_100_validated.xlsx`
- `reports/tables/manual_audit/real_audit_validated_labels.csv`
- `reports/tables/manual_audit/manual_audit_quality_checks.json`
- `reports/generated/manual_audit_validation_report.md`

The completed 100-case audit passes schema and label validation. Because the
sample is stratified/purposive with overlapping strata and no saved inclusion
weights, it supports transfer diagnostics and failure-mode analysis, not final
population precision/recall claims. Therefore:

```text
manual audit evidence gate = PASS
final population precision and recall = NOT_SUPPORTED_BY_THIS_AUDIT_DESIGN
```

The broader `real_audit_sample_100.csv` is retained as noncanonical review
evidence.

Reviewer-friendly 100-case artifacts:

- `reports/manual_audit/real_audit_sample_100.xlsx`
- `reports/manual_audit/real_audit_evidence_100.html`

Use the HTML file for reading evidence and the XLSX workbook for entering
labels with dropdown values.
