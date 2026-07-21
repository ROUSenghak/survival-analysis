# eForms CPV Discontinuity Audit

## Technical Summary

The approximately-zero eForms CPV coverage is a parser discontinuity, not source-level missingness. The pre-fix extractor only accepted 8-digit values whose JSON path contained `cpv`; eForms stores CPV under UBL commodity classification paths such as `MainCommodityClassification/ItemClassificationCode`, so those valid codes were skipped.

After the extractor correction, eForms cleaned CPV coverage rises from 0.0% to 100.0%. Legacy coverage remains 80.5%, unchanged except for normal source-level missingness. Among 10,682 eForms records, 10,682 had raw CPV that the old parser missed; 0 still appear genuinely absent after correction; and 4,599 carry multiple CPV codes after recovery.

## Evidence

- Raw eForms records contain valid CPV codes under `cbc:ItemClassificationCode/#text`, usually within `MainCommodityClassification` or `AdditionalCommodityClassification`.
- The recovery is narrow: other 8-digit eForms leaves, such as monetary amounts and reference IDs, remain excluded from CPV extraction.
- Multiple-CPV handling is preserved as a semicolon-delimited candidate list in the flattened data; the prepared corpus keeps the first valid token as `cpv_clean`, as before.

## eForms Notice-Type Coverage After Correction

- ContractAwardNotice: 100.0% (3,803 records)
- ContractNotice: 100.0% (6,821 records)
- PriorInformationNotice: 100.0% (58 records)

## Outputs

- `reports/tables/synthetic_calibration/eforms_cpv_path_audit.csv`
- `reports/tables/synthetic_calibration/eforms_cpv_recovery.csv`
- `reports/tables/synthetic_calibration/eforms_cpv_sample_classification.csv`
- `reports/figures/synthetic_calibration/cpv/`

## Limitation

Downstream candidate-pair, scoring, linkage, survival, and calibration outputs that depend on CPV should be regenerated from the corrected flattened/prepared corpus before final modeling claims are frozen.
