# External Technology Classification Input Contract

This project does not train or replace the technological classifier. The
classification export is owned by the teammate responsible for that work.

## Required Schema

The production export must contain one row per classified BOAMP notice:

```text
notice_id
technology_label
prediction_confidence
low_confidence_flag
classification_source
taxonomy_version
model_version
classification_date
```

## Validation Rules

- `notice_id` must be non-empty, unique in the export, and mergeable to the
  canonical BOAMP `notice_id`.
- `technology_label` must be non-empty and, when a taxonomy is supplied, must be
  one of the known taxonomy values.
- `prediction_confidence` must be numeric in `[0, 1]`.
- `low_confidence_flag` must be boolean-like.
- `classification_source`, `taxonomy_version`, and `model_version` must be
  populated.
- `classification_date` must parse as a date.
- Outcome-like fields such as renewal labels, accepted links, successor IDs,
  manual labels, or synthetic truth must not appear in the export.

## Merge Behavior

The merge is left-joined onto the canonical BOAMP notice table. Unmatched notices
are retained with:

```text
technology_label = UNCLASSIFIED
low_confidence_flag = true
```

No fake production labels are created. Small artificial labels may appear only in
unit-test fixtures and must be clearly marked as test data.

## Scientific Gate

Until this export exists and passes validation, the following remain:

```text
BLOCKED_BY_EXTERNAL_CLASSIFICATION
```

- survival analysis by technological segment
- technological trend analysis
- change-point detection by technological segment
- segment-specific conclusions
