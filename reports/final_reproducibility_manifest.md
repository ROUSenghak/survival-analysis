# Final Reproducibility Manifest

Generated: 2026-07-16

Repository state:

- Branch: `main`
- Commit: `cd3dbddd0f2f70ed5f99a05acf72f0f26302afb8`
- Short status at audit generation: `M reports/boamp_m0_technical_report.pdf
 M reports/boamp_m1_technical_report.pdf
 M reports/boamp_m1_technical_report.tex
 M reports/linkage_quality_evaluation.pdf
?? reports/final_method_selection_record.md
?? reports/final_reproducibility_manifest.md
?? reports/final_single_reviewer_audit_guide.md
?? reports/tables/final_authoritative_files.csv
?? reports/tables/final_blinded_single_reviewer_sample.csv
?? reports/tables/final_consistency_audit.csv
?? reports/tables/final_linkage_funnel.csv
?? reports/tables/final_linkage_funnel_stratified.csv
?? reports/tables/final_m0_m1_profile_source_comparison.csv
?? reports/tables/final_m0_m1_profile_status_summary.csv
?? reports/tables/final_method_comparison.csv
?? reports/tables/final_method_inventory.csv
?? reports/tables/final_source_linkage_diagnostics.csv
?? reports/tables/final_temporal_variant_comparison.csv
?? reports/tables/final_validation_technical_join_table.csv
?? scripts/analyze_manual_validation_labels.py
?? scripts/build_final_scientific_audit.py`

## Authoritative Files

| role | path | exists | row_count | column_count | sha256 |
| --- | --- | --- | --- | --- | --- |
| primary_clean_data | data/processed/boamp_clean_m0_no_enrichment.csv | True | 87418 | 93 | 3e69c5176e229fcc31e814baf9450c4bbccb22ad9b3e6201d208de79697f9e25 |
| primary_sources | data/processed/boamp_m0_sources.csv | True | 3159 | 22 | 9fc77d7ca6da0fb3914a90284ca3da0b3eeb7bcc238e907b27d1dd305a36e9a8 |
| primary_candidate_pairs | data/processed/boamp_m0_candidate_pairs.csv | True | 6137 | 19 | 3ce33cb13531046f56ee96e472f5cac1222e923357245d6eb8637866884aecdd |
| primary_links | data/processed/boamp_m0_links_balanced.csv | True | 618 | 21 | 59fd8434baed5aab6963c8c793c289e6b045514f3b740e878c3b6604dfba7458 |
| primary_survival | data/processed/boamp_survival_m0_balanced.csv | True | 3159 | 18 | 93c05a0c767b7264f2ed7669c7b70775f1ec86b7eeddbcee8adfe4a3c958a687 |
| m1_enriched_notices | data/processed/boamp_clean_m1_buyer_enriched.csv | True | 3170 | 45 | e228e775b3562578143b26474d9b9af28288c68dcc237beb4627a35832cae9cc |
| m1_candidate_pairs | data/processed/boamp_m1_candidate_pairs.csv | True | 8228 | 30 | 849757940ab817a032cef5aa40e14bda3cb5b05f4fb16d79a26dd7984c20e4fb |
| m1_links | data/processed/boamp_m1_links_balanced.csv | True | 847 | 32 | 39e6b94e68d4b3b0207ed3ddece78acc6fdeaec11b4a3b0ab00a6e8c25f713f1 |
| m1_survival | data/processed/boamp_survival_m1_balanced.csv | True | 3159 | 21 | 412b6268b1d86d6a5e3b7204559c295bd13250ff94011671f087f3bb28ca11f9 |
| profile_audit_links | data/processed/boamp_m1_profile_audited_links.csv | True | 847 | 40 | 3474cf6a8b8be6575653172ccb4880e92e544be60e9c5623e9ff00cb37f0b126 |
| source_level_diagnostics | reports/tables/final_source_linkage_diagnostics.csv | True | 3159 | 31 | 5eeee803314e405a52f9c5d33760dfd400fec1f8d88b583053c18045ba58373e |
| linkage_funnel | reports/tables/final_linkage_funnel.csv | True | 6 | 4 | a19644b6cad6330e09a1d8b5afcbfe1f524fb7a5138afdf05946de531d99c8ca |
| method_inventory | reports/tables/final_method_inventory.csv | True | 5 | 20 | 1159fe20f19a307b5c8fa23a24565d0480bde804e69311b6235d36ef37a75d81 |
| decision_record | reports/final_method_selection_record.md | True | 174 | 1 | f8adeca99e929be491004697830ca38520276d3f5a50541b621b950c42ad5f21 |
| repro_manifest | reports/final_reproducibility_manifest.md | True | 89 | 1 | 3965cb2fb5119ba57a1ff326be15b45761cac18ace1c48cbd0b608de953b67b1 |
| validation_template | scripts/analyze_manual_validation_labels.py | True | 86 | 1 | dcb13d2f36c713d02d1f7a516c591ae7ee42d18420ac27b75ceb5aad224d77f4 |

## Reproduction Commands

Run from the repository root:

```bash
python3 scripts/download_boamp.py
python3 scripts/parse_boamp.py
python3 scripts/preprocess_boamp_m0.py
python3 scripts/build_m0_candidate_pairs.py
python3 scripts/run_m0_linkage.py
python3 scripts/audit_current_project.py
python3 scripts/build_m1_buyer_siren_experiment.py
python3 scripts/build_m1_profile_domain_audit.py
python3 scripts/eval_m6d_temporal_window_sensitivity.py
python3 scripts/eval_duration_leakage.py
python3 scripts/run_survival_analysis.py
python3 scripts/make_figures.py
python3 scripts/make_evaluation_figures.py
python3 scripts/make_report_figures.py
python3 scripts/build_final_scientific_audit.py
```

External downloads are only needed if raw BOAMP or M1 enrichment/profile files
are absent. The final audit script itself is additive and reads existing
outputs.

## Consistency Checks

| check | passed | value | expected | severity |
| --- | --- | --- | --- | --- |
| m0_sources_unique_notice_id | True | 0 | 0 duplicates | error |
| m0_survival_one_row_per_source | True | 3159 | one row per nonmissing-buyer source | error |
| m0_survival_events_equal_balanced_links | True | 618 | 618 | error |
| m0_event_rows_have_candidate | True | 0 | 0 | error |
| m0_no_nonpositive_survival_time | True | 0 | 0 | error |
| m1_same_source_population_size | True | 3159 | 3159 | error |
| profile_audit_does_not_change_link_count | True | 847 | 847 | warning |
| final_source_diagnostics_one_row_per_source | True | 3159 | 3159 | error |
| manual_labels_not_fabricated | True | 0 | 0 completed labels in generated reviewer file | info |
