"""One-off helper (Step 12): builds reports/source_values_used.csv, tracing
every headline number in the report to the file/column it came from.

Run 2 values (Pays de la Loire, digital scope, 2015-01 to latest)."""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

rows = [
    ("3. Study period", "full_corpus_total_notices", "1687432-1687434", "live API query (facet count)", "total_count field", "drifts slightly; queried at run time, not persisted to a file"),
    ("3. Study period", "full_corpus_date_range", "2015-03-02 to 2026-07-13", "live API query (order_by dateparution)", "dateparution min/max", "not persisted; queried at run time"),
    ("3. Study period", "pdl_filter_check_national_jan2024", "8728", "live API query (records, limit=0)", "total_count, no department filter", "verification check, not persisted to a file - see run_log.md Run 2"),
    ("3. Study period", "pdl_filter_check_filtered_jan2024", "531", "live API query (records, limit=0)", "total_count, code_departement in PDL set", "verification check confirming ODSQL syntax works, ~6.1% of national"),
    ("3. Study period", "retrieved_notice_count", "84623", "data/raw/boamp/pdl/download_metadata.json", "retained_notice_count", ""),
    ("3. Study period", "raw_file_count", "139", "reports/tables/boamp_download_summary.csv", "raw_file_count", ""),
    ("3. Study period", "duplicate_count", "0", "reports/tables/boamp_download_summary.csv", "duplicate_count", ""),
    ("3. Study period", "failed_requests", "0", "reports/tables/boamp_download_summary.csv", "failed_requests", ""),
    ("3. Study period", "geographic_scope_departments", "44;49;53;72;85", "reports/tables/boamp_download_summary.csv", "departments", "Pays de la Loire: Loire-Atlantique, Maine-et-Loire, Mayenne, Sarthe, Vendee"),
    ("4. Parsing", "schema_family_legacy_count", "73941", "reports/run_logs/parse_stdout_pdl.log", "schema_family value_counts print", ""),
    ("4. Parsing", "schema_family_eforms_count", "10682", "reports/run_logs/parse_stdout_pdl.log", "schema_family value_counts print", ""),
    ("5. Preprocessing", "duplicate_notice_ids", "0", "reports/tables/m0_preprocessing_quality_checks.csv", "duplicate_notice_ids", ""),
    ("5. Preprocessing", "cleaned_notice_count", "84623", "reports/tables/m0_preprocessing_quality_checks.csv", "cleaned_notice_count", ""),
    ("5. Preprocessing", "appel_offre_count_all_sectors", "58292", "reports/tables/m0_preprocessing_quality_checks.csv", "appel_offre_count", ""),
    ("5. Preprocessing", "attribution_count", "22560", "reports/tables/m0_preprocessing_quality_checks.csv", "attribution_count", ""),
    ("5. Preprocessing", "other_notice_type_count", "3771", "reports/tables/m0_preprocessing_quality_checks.csv", "other_notice_type_count", ""),
    ("6. Scope filtering", "appel_offre_digital_scope_count", "3159", "reports/run_logs/preprocess_stdout_pdl.log", "APPEL_OFFRE digital scope (CPV-or-keyword) print", "used as the M0 source population - within the guide's 2000-5000 target"),
    ("6. Scope filtering", "appel_offre_digital_cpv_only_count", "1882", "reports/run_logs/preprocess_stdout_pdl.log", "APPEL_OFFRE digital scope (CPV-division-only) print", "sensitivity check, stricter definition"),
    ("7. Buyer key", "buyer_key_type_raw_siret_count", "23038", "reports/tables/m0_buyer_key_type_summary.csv", "n_all_notices, row RAW_SIRET", ""),
    ("7. Buyer key", "buyer_key_type_name_fallback_count", "61585", "reports/tables/m0_buyer_key_type_summary.csv", "n_all_notices, row NAME_FALLBACK", ""),
    ("7. Buyer key", "buyer_key_type_missing_count", "0", "reports/tables/m0_preprocessing_quality_checks.csv", "missing_buyer_key_rate", ""),
    ("7. Buyer key", "buyer_key_type_raw_siret_rate", "0.2722", "reports/tables/m0_preprocessing_quality_checks.csv", "buyer_key_type_raw_siret_rate", ""),
    ("7. Buyer key", "buyer_key_type_name_fallback_rate", "0.7278", "reports/tables/m0_preprocessing_quality_checks.csv", "buyer_key_type_name_fallback_rate", ""),
    ("8. Source population", "appel_offre_source_count", "3159", "data/processed/boamp_m0_sources.csv", "row count", ""),
    ("8. Source population", "eligible_source_count", "3159", "reports/run_logs/candidate_pairs_stdout_pdl.log", "Eligible (non-missing buyer_key) sources print", ""),
    ("8. Source population", "study_end_date", "2026-07-13", "reports/tables/m0_preprocessing_quality_checks.csv", "date_range_max", ""),
    ("9. Attribution", "attribution_notice_count", "22560", "reports/tables/m0_preprocessing_quality_checks.csv", "attribution_count", ""),
    ("10. CPV", "cpv_coverage_sources", "0.7841", "reports/tables/m0_preprocessing_quality_checks.csv", "cpv_coverage_sources", ""),
    ("10. CPV", "generic_cpv_share_sources", "0.0915", "reports/tables/m0_preprocessing_quality_checks.csv", "generic_cpv_share_sources", ""),
    ("11. Duration", "median_observed_duration_months", "6.0", "reports/run_logs/preprocess_stdout_pdl.log", "Global median observed APPEL_OFFRE duration print", "n=378 observed (non-imputed) values"),
    ("11. Duration", "duration_observed_count", "378", "data/processed/boamp_m0_sources.csv", "dur_was_imputed == False row count", ""),
    ("11. Duration", "duration_imputation_rate_sources", "0.8803", "reports/tables/m0_preprocessing_quality_checks.csv", "duration_imputation_rate_sources", "much higher than the prior national run (0.2279) - see report limitations"),
    ("12. Candidate generation", "temporal_window_months", "6", "data/processed/_m0_window_months.txt", "file content", "also reports/run_logs/candidate_pairs_stdout_pdl.log"),
    ("12. Candidate generation", "max_candidates_per_source", "30", "scripts/build_m0_candidate_pairs.py", "MAX_CANDIDATES_PER_SOURCE constant", "cap not expected to bind given much smaller buyer groups"),
    ("12. Candidate generation", "candidate_pair_count", "6137", "reports/tables/m0_preprocessing_quality_checks.csv", "candidate_pair_count", ""),
    ("12. Candidate generation", "sources_with_candidates", "1236", "reports/run_logs/candidate_pairs_stdout_pdl.log", "Sources with >=1 candidate print", ""),
    ("12. Candidate generation", "sources_without_candidates", "1923", "reports/tables/m0_preprocessing_quality_checks.csv", "sources_without_candidates", ""),
    ("12. Candidate generation", "avg_candidates_per_source", "4.965", "reports/tables/m0_preprocessing_quality_checks.csv", "avg_candidates_per_source", ""),
    ("13. Scoring", "text_similarity_method", "TF-IDF cosine (scikit-learn)", "scripts/build_m0_candidate_pairs.py", "TfidfVectorizer usage", "sentence-transformers evaluated, not installed - see requirements.txt"),
    ("13. Scoring", "composite_weights", "text 0.35 / cpv 0.30 / time 0.25 / buyer 0.10", "scripts/build_m0_candidate_pairs.py", "W_TEXT, W_CPV, W_TIME, W_BUYER", "unchanged from the national run; re-examined against the new score distribution, kept as-is"),
    ("14. Linkage results", "broad_threshold", "0.2642", "reports/tables/m0_method_summary.csv", "threshold_composite_score, row broad", ""),
    ("14. Linkage results", "balanced_threshold", "0.3230", "reports/tables/m0_method_summary.csv", "threshold_composite_score, row balanced", ""),
    ("14. Linkage results", "strict_threshold", "0.3931", "reports/tables/m0_method_summary.csv", "threshold_composite_score, row strict", ""),
    ("14. Linkage results", "broad_event_count", "927", "reports/tables/m0_method_summary.csv", "n_linked_events, row broad", ""),
    ("14. Linkage results", "balanced_event_count", "618", "reports/tables/m0_method_summary.csv", "n_linked_events, row balanced", ""),
    ("14. Linkage results", "strict_event_count", "309", "reports/tables/m0_method_summary.csv", "n_linked_events, row strict", ""),
    ("14. Linkage results", "broad_event_rate", "0.2934", "reports/tables/m0_method_summary.csv", "event_rate, row broad", ""),
    ("14. Linkage results", "balanced_event_rate", "0.1956", "reports/tables/m0_method_summary.csv", "event_rate, row balanced", ""),
    ("14. Linkage results", "strict_event_rate", "0.0978", "reports/tables/m0_method_summary.csv", "event_rate, row strict", ""),
    ("14. Linkage results", "median_gap_months_linked_balanced", "37.70", "reports/tables/m0_method_summary.csv", "median_gap_months_linked, row balanced", "~3.1 years - consistent with multi-year framework agreements"),
    ("14. Linkage results", "top_buyer_balanced", "NAME:nantes metropole", "reports/tables/m0_preprocessing_quality_checks.csv", "top_buyer_by_event_count_balanced", ""),
    ("14. Linkage results", "top_buyer_balanced_event_count", "125", "reports/tables/m0_preprocessing_quality_checks.csv", "top_buyer_event_count_balanced", ""),
    ("15. Limitations", "candidates_claimed_by_multiple_sources_balanced", "121", "reports/tables/m0_preprocessing_quality_checks.csv", "candidate_notices_claimed_by_multiple_sources_balanced", ""),
]

df = pd.DataFrame(rows, columns=["section", "metric", "value", "source_file", "source_column_or_table", "note"])
out = PROJECT_ROOT / "reports" / "source_values_used.csv"
df.to_csv(out, index=False)
print(f"{len(df)} rows written -> {out}")
