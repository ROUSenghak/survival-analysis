# Synthetic linkage benchmark: calibration report

Generated from `notebooks/04_synthetic_benchmark_calibration.ipynb`, corpus: 84,623 BOAMP notices, 2015-2026, Pays de la Loire (departments 44, 49, 53, 72, 85).

## 1. Purpose & scope
This report summarizes the real-corpus properties a synthetic BOAMP-like linkage benchmark generator should reproduce, and draws a hard line around what may and may not be used to construct synthetic ground truth.

## 2. Tiering framework
- **OBSERVABLE** — measured directly from raw fields or the shared, layer-neutral preparation logic on the full corpus.
- **SILVER_STANDARD** — visible only through Layer 1/Layer 2 accepted links (Section 15 of the notebook only); always conditional on threshold acceptance, never an unconditional error/accuracy rate.
- **UNIDENTIFIED** — cannot be estimated from any BOAMP output in this repo; must be exposed as a swept scenario parameter in the generator, not calibrated to a point.

## 3. Population structure
- 84,623 notices, years 2015-2026.
- Schema transition (LEGACY -> EFORMS) around the ~Oct 2023 eForms mandate; see `calib_schema_transition_shift.csv` for the field-completeness shift it caused.
- 5,268 distinct buyer_key values; activity Gini=0.832, top-1 buyer share=3.8%.

## 4. Observable distributions the synthetic generator should reproduce
- **Total notices in prepared corpus** (1): `84623` [unconditional] -> `n/a`. Full corpus, all sectors, all notice types, not scope-filtered.
- **Notice share by department (multi-valued, exploded)** (2): `see table` [marginal, by department] -> `calib_department_coverage.csv`. code_departement can list several departments per notice; shares sum to >1.
- **Notice type composition by year** (2): `see table` [by year] -> `calib_notice_type_by_year.csv`. notice_type_normalized collapses rare types to OTHER.
- **Non-null rate, all 94 columns** (3): `see table` [marginal] -> `calib_field_completeness_marginal.csv`. Includes both raw and derived columns.
- **Completeness of key fields by year** (3): `see table` [by publication_year] -> `calib_field_completeness_heatmap.png`. Trend, not a validated forecast.
- **LEGACY vs EFORMS field completeness delta** (4): `see table` [by schema_family] -> `calib_schema_transition_shift.csv`. schema_family is detected heuristically from the raw donnees payload (src/utils/boamp_schema.py); not a declared field.
- **Gini coefficient, notices per buyer_key** (5): `0.832` [unconditional] -> `calib_buyer_activity_distribution.png`. buyer_key is BOAMP-native identity (SIRET/SIREN/name fallback); NAME_FALLBACK buyers aggregate multiple real entities under one key, inflating apparent concentration.
- **buyer_identifier_source distribution** (6): `see table` [marginal] -> `calib_identifier_quality_summary.csv`. RAW_SIRET_FIELD/RAW_SIREN_FIELD/DERIVED_FROM_SIRET/NONE; format+Luhn checksum validated.
- **Share of normalized buyer names mapping to >1 buyer_key** (7): `0.2901` [marginal] -> `calib_buyer_name_fragmentation_summary.csv`. A data-quality measure of BOAMP-native identity resolution, not a linkage-accuracy claim; generic institutional names (mairie, commune, ...) fragment for a different reason than genuine spelling/legal-form variants and are reported separately.
- **CPV code missing rate** (8): `0.2968` [marginal + by year/schema/notice_type/department/buyer_activity/identifier_source] -> `calib_cpv_missingness_by_conditioning.csv`. cpv_clean requires exact 8-digit format; malformed/multi-code strings are treated as missing.
- **Duration field present, full corpus** (9): `0.1365` [marginal + conditional] -> `calib_duration_quality_summary.csv`. Distinct from the pipeline's 88%-imputed figure, which is computed only over the APPEL_OFFRE & digital-scope eligible-source subset, not the full corpus.
- **Exact-duplicate objet_clean rate** (10): `0.5143` [among non-missing text] -> `calib_text_near_duplicate_rate.csv`. Exact-string duplication only; near-duplicate detection via fuzzy/semantic similarity would find a higher rate. This is a lower bound on text-based candidate ambiguity.
- **Phi-coefficient correlation among 6 quality flags** (11): `see table` [marginal + by year/schema/dept/cpv/buyer_activity] -> `calib_missingness_correlation_heatmap.png`. siret_or_siren_missing and name_fallback are definitionally linked by the buyer_key construction ladder (identity_boamp.py), not an independent empirical association.
- **Quality metrics split by digital-scope / PDL-scope eligibility** (12): `see table` [by is_digital_scope, is_in_pdl] -> `calib_scope_conditioning_crosstab.csv`. is_digital_scope combines a CPV-division rule with a French keyword search over objet_normalized (config/pipeline.yaml scope block); it is a scope-tagging heuristic.
- **Same-buyer candidate-set size vs window width** (13): `see table` [by window_months x buyer_key_type] -> `calib_candidate_environment_complexity_by_window.csv`. Publication-date-based, not estimated-end-date-based; independent of the pipeline's 6-month convention. NAME_FALLBACK buyer_key aggregates distinct real entities, inflating candidate density for that stratum specifically.

## 5. Silver-standard-only observations (Section 15)
These describe accepted-link populations only; they are NOT unconditional error rates and must not be used to set synthetic ground-truth error/accuracy parameters.
- **Data-quality-defect co-occurrence among accepted links**: `see table` -> `calib_silver_error_cooccurrence_by_tier.csv`. Conditional on the pipeline's own threshold-based acceptance; selection bias by construction; must not be used as an unconditional error rate or to estimate true linkage accuracy.
- **Candidate-set size/margin at rank-1, by identifier/CPV quality**: `see table` -> `calib_silver_candidate_ambiguity_by_quality.csv`. Reflects the pipeline's own 6-month window and 30-candidate cap (config/pipeline.yaml); compare against Section 13's independent window sweep, do not treat as the 'true' candidate density.

## 6. Unidentified parameters / required scenario knobs
- **true recurrence prevalence**: No verified legal-renewal field exists in BOAMP; the pipeline's own event rate (19.6%/26.8%) is itself the output of an unvalidated scoring+threshold procedure, not a measurement of real renewal behaviour. Proposed scenario range: `e.g. sweep true recurrence prevalence in {10%, 25%, 40%, 60%}`.
- **true linkage precision recall**: Zero completed manual-validation labels exist; Fellegi-Sunter EM estimates in 03_analysis are explicitly model-based, not ground-truth-validated. Proposed scenario range: `sweep precision/recall of the *injected* synthetic linker across a grid, e.g. precision in {0.6,0.75,0.9}, recall in {0.5,0.7,0.9}`.
- **true buyer entity resolution rate**: No registry cross-validation of BOAMP-native buyer identity exists in this repo; the Layer 2 external SIREN join covers only 2024-2026 and the alias bridge is an unvalidated heuristic. Proposed scenario range: `sweep the fraction of buyer-name variants correctly resolved to one entity, e.g. {50%, 70%, 90%}`.
- **true candidate ambiguity resolution**: Which candidate among several plausible same-buyer notices is the *correct* renewal is never verified; §15's rank-1 selection is a modelling choice, not ground truth. Proposed scenario range: `vary the number of plausible-but-wrong candidates per true link, e.g. {0, 1-2, 3-5, 6+}, informed by §13's window-sweep candidate-density numbers`.
- **true text corruption process**: No ground truth exists for how procurement text varies between a true renewal pair vs. an unrelated notice; §10's near-duplicate rate only measures exact repetition. Proposed scenario range: `sweep text-similarity degradation severity for true-pair synthetic text, e.g. cosine similarity target ranges {0.3-0.5, 0.5-0.7, 0.7-0.9}`.

## 7. Do NOT use for synthetic ground truth
- `data/processed/{boamp_only,enriched}/*_candidate_pairs.csv` composite_score / confidence_tier
- `data/processed/{boamp_only,enriched}/*_links_{broad,balanced,strict,window_*}.csv`
- The frozen thresholds 0.2642 / 0.3230 / 0.3931 (`config/pipeline.yaml`, `thresholds:`)
- The six-month (and 9/12/18-month variant) temporal window (`config/pipeline.yaml`, `temporal_window:`)
- Event/censoring rates in `*_survival*.csv` (19.6% Layer 1 / 26.8% Layer 2) as true recurrence prevalence

## 8. Calibration checklist
| Observable table | Generator knob |
|---|---|
| `calib_population_counts_by_year_schema.csv` | year/schema volume mix |
| `calib_buyer_activity_distribution.csv` | buyer-activity (Zipf/Gini) distribution |
| `calib_identifier_quality_summary.csv` | SIRET/SIREN presence & validity rates |
| `calib_buyer_name_fragmentation_summary.csv` | buyer-name variant generation rate |
| `calib_cpv_quality_summary.csv` | CPV missingness/genericity rates |
| `calib_duration_quality_summary.csv` | duration missingness/plausibility rates |
| `calib_text_characteristics_summary.csv` | text length/near-duplicate rates |
| `calib_missingness_joint_matrix.csv` | joint/correlated missingness injection |
| `calib_candidate_environment_complexity_by_window.csv` | candidate-block size by window scenario |

## 9. Known limitations (carried over from docs/methodology.md §9)
1. No verified renewal/linkage ground truth exists anywhere in this repo.
2. External SIREN enrichment covers 2024-2026 only; historical coverage rests on alias-bridge assumptions.
3. Composite weights and thresholds are unfitted/percentile conventions, not validated cutoffs.
4. SIREN-based buyer merges can conflate independently-tendering establishments.
5. Zero manual-validation labels exist; all quality diagnostics are model-based, not human-verified.

## 10. Appendix: output files
- Figures: `reports/figures/calib_*.png` / `.pdf` (18 figures)
- Tables: `reports/tables/calib_*.csv`
- Provenance inventory: `reports/tables/calib_parameter_provenance_inventory.csv`