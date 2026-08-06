# Canonical Linkage Outputs

Candidate generator:

```text
dur_w6_same_buyer_expected_end_window_top30
```

Canonical candidate-pair outputs:

- `data/processed/boamp_only/boamp_only_candidate_pairs.csv`
- `reports/tables/real_linkage_freeze/real_candidate_pairs_reproduced.csv`

Canonical method roles:

- provisional primary practical method: GBM transfer
- transparent baseline: composite balanced
- conservative policy: composite strict with `POTENTIAL` links dropped
- sensitivity: composite broad and logistic regression transfer

Canonical real-linkage outputs:

- `reports/tables/real_linkage_freeze/real_primary_gbm_links.csv`
- `reports/tables/real_linkage_freeze/real_linkage_strategy_summary.csv`
- `reports/tables/real_linkage_freeze/real_linkage_strategy_manifest.json`
- `reports/tables/real_linkage_freeze/real_linkage_method_agreement.csv`
- `reports/tables/real_linkage_freeze/linkage_integrity_checks.json`

Do not describe GBM as the best BOAMP algorithm. The defensible wording is:

```text
best practical method under the predefined synthetic benchmark assumptions and
operational criteria
```
