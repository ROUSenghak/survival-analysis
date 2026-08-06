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
- `NEEDS_SECOND_REVIEW`

The canonical sample currently has blank reviewer labels. Therefore:

```text
real precision and recall = UNKNOWN_REAL_PRECISION_RECALL
manual audit gate = BLOCKED_BY_MANUAL_AUDIT
```

The broader `real_audit_sample_100.csv` is retained as noncanonical review
evidence.
