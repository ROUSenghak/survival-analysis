# Canonical Classification Interface

The teammate classification export is not currently available.

Contract:

- `docs/classification_input_contract.md`

Validation and merge module:

- `src/boamp/data/classification.py`

Configured future export path:

- `data/raw/external/technology_classification/technology_classification_export.csv`

Required columns:

- `notice_id`
- `technology_label`
- `prediction_confidence`
- `low_confidence_flag`
- `classification_source`
- `taxonomy_version`
- `model_version`
- `classification_date`

Until the export exists and passes validation:

```text
technology-specific analysis = BLOCKED_BY_EXTERNAL_CLASSIFICATION
```

Do not train a replacement classifier or create fake production labels.
