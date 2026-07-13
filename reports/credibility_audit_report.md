# BOAMP M0 Credibility Audit

This audit treats the current repository as an independent study. Executable scripts and generated datasets are the evidence; prose-only claims are not counted as implementation.

## Official Current Data Lineage

Current raw input is data/raw/boamp/pdl/ (140 monthly JSON files). The national archive in data/raw/boamp_national_2024_2026_archive/ is marked superseded and is not part of the active lineage.

Detailed lineage: reports/tables/audit_data_lineage.csv. Dataset inventory with dimensions and checksums: reports/tables/audit_dataset_inventory.csv.

## Official Reference Specification

The frozen reference event definition is the current balanced M0 specification:

- sources: APPEL_OFFRE notices in digital/ICT scope, Pays de la Loire raw pull, no external SIREN/SIRET enrichment;
- eligibility for candidate generation: non-missing buyer_key;
- blocking: same buyer_key, later notice, within 6 months of estimated end date;
- score: 0.35*s_text + 0.30*s_cpv + 0.25*s_time + 0.10*s_buyer;
- selected link: rank-1 candidate if score is at or above the rank-1 median threshold, 0.323022 in the current run;
- survival handoff: data/processed/boamp_survival_m0_balanced.csv.

Official dimensions:

- data/interim/boamp_raw_flattened.csv: 84,623 rows, 42 columns.
- data/processed/boamp_clean_m0_no_enrichment.csv: 84,623 rows, 93 columns.
- data/processed/boamp_m0_sources.csv: 3,159 rows, 22 columns.
- data/processed/boamp_m0_candidate_pairs.csv: 6,137 rows, 19 columns.
- data/processed/boamp_m0_links_balanced.csv: 618 rows, 21 columns.
- data/processed/boamp_survival_m0_balanced.csv: 3,159 rows, 18 columns.

## Main Credibility Findings

The reference survival handoff is internally consistent: 3,159 rows, 618 events, no duplicated survival units, no missing linked candidates among events, no censored rows with linked candidates, no nonpositive times, and no events after study end. See reports/tables/audit_survival_construction_checks.csv.

Blocking is the biggest limitation before scoring. Only 1,236 of 3,159 eligible non-missing-buyer sources have at least one candidate, so blocking coverage is 39.1%; 1,923 sources have zero candidates. Coverage declines sharply in later years because recent sources have less follow-up. See reports/tables/audit_blocking_coverage.csv and reports/tables/audit_candidate_source_diagnostics.csv.

Candidate reuse is material. In the balanced links, 618 selected links use 443 unique later candidates; 121 selected candidates are reused by more than one source, with maximum multiplicity 6. This may be defensible for lots or framework-like procurement structures, but it needs manual review before claiming one-to-one renewal behavior. See reports/tables/audit_duplicate_candidate_*.csv.

Duration leakage is high priority. The reference design uses declared or imputed duration to estimate end dates, block candidates, compute temporal similarity, and define survival timing. Under a no-temporal-score reranking from the same candidate pool, the event count remains 618 by construction but Jaccard overlap with reference links falls to 0.414 and 246 sources change event status. Under a broad 24-month forward window that does not center blocking on duration, events rise to 1,105, overlap with reference links falls to 0.064, and median event time drops to 5.8 months. See reports/tables/duration_leakage_linkage_sensitivity.csv.

The duration effect is not stable across event definitions. In the duration-only Cox audit, log duration is associated with lower hazard in the reference design, clustered HR 0.620, remains lower in the no-temporal-score reference-pool design, clustered HR 0.698, but reverses under the forward-window no-duration design, clustered HR 1.344. This is strong evidence that declared duration should not be interpreted as an independent substantive predictor without redesigned linkage. See reports/tables/duration_leakage_cox_duration_effect.csv.

Temporal-window sensitivity is moderate to large. Moving from 6 to 18 months increases candidate pairs from 6,137 to 14,097, links from 618 to 834, blocking coverage from 39.1% to 52.8%, and source event-status changes versus reference from 0 to 306. See reports/tables/m6d_temporal_window_sensitivity.csv.

Unsupervised Fellegi-Sunter and corruption analyses are implemented, but remain internal/model-based. The Fellegi-Sunter precision/recall estimates are conditional on the blocked candidate universe, not all possible true renewals. Corruption recovery uses a fixed candidate pool, so it does not fully test corruption that would alter blocking.

Survival models are diagnostic, not confirmatory. KM median survival is infinite in the reference because censoring is heavy. Overall reference RMST at 60 months is 53.5 months and survival at 24 months is 0.914 against the constructed proxy event. Cox models generated sparse-category convergence warnings; clustered Cox output should be read as a sensitivity diagnostic. See reports/tables/survival_*.

Manual validation is not complete. A stratified unlabeled sample and guide were created at reports/tables/manual_validation_sample_unlabeled.csv and reports/manual_validation_guide.md. No manual labels were fabricated.

## Stable Conclusions

- The current balanced event dataset is reproducible and internally coherent.
- Blocking excludes a majority of eligible sources from the candidate universe.
- Linkage conclusions are sensitive to temporal design and duration use.
- Internal scores and model-based posterior probabilities should not be described as verified accuracy.
- Segment/ranking conclusions are exploratory; previous broad-vs-strict KM ranking already showed instability.

## Remaining Uncertainty

Manual validation is still required to estimate observed precision on real labels. A full reblocking corruption study, one-to-one/many-to-one adjudication, negative controls, full-pipeline bootstrap, and stronger temporal validation remain deferred.

## Reproduction Commands

Run these from the repository root:

python3 scripts/download_boamp.py
python3 scripts/parse_boamp.py
python3 scripts/preprocess_boamp_m0.py
python3 scripts/build_m0_candidate_pairs.py
python3 scripts/run_m0_linkage.py
python3 scripts/audit_current_project.py
python3 scripts/eval_m3_fellegi_sunter_mixture.py
python3 scripts/eval_m4_corruption_recovery.py
python3 scripts/eval_m6a_threshold_sensitivity.py
python3 scripts/eval_m6b_feature_ablation.py
python3 scripts/eval_m6c_variant_km_robustness.py
python3 scripts/eval_m6d_temporal_window_sensitivity.py
python3 scripts/eval_duration_leakage.py
python3 scripts/run_survival_analysis.py
python3 scripts/make_figures.py
python3 scripts/make_evaluation_figures.py
python3 scripts/_build_schema_summary.py
python3 scripts/_build_source_trace.py
python3 scripts/_build_final_audit.py
