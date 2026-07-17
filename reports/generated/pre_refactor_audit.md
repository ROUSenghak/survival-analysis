# Pre-refactor repository audit — BOAMP renewal-linkage & survival analysis

*Generated 2026-07-17 on branch `restructure/two-layer` (from `main` @ 262fc64). This audit freezes the
state of the repository before the two-layer restructure. Baseline output fingerprints are recorded in
`tests/fixtures/baseline_fingerprints.json`.*

---

## 1. What the project is

A renewal-linkage and survival-analysis pipeline over French BOAMP public-procurement notices:
Pays de la Loire (departments 44/49/53/72/85), 2015-01 → 2026-07, digital/ICT scope
(CPV divisions {32, 35, 48, 72} ∪ ~18 French keywords). For each eligible "source" contract the
pipeline searches later BOAMP notices from the same buyer for a plausible renewal (proxy event),
then models time-to-renewal with survival methods (KM, Cox, AFT).

Two methodological layers already exist:

| Legacy name | New name (this refactor) | Buyer identity | Status |
|---|---|---|---|
| **M0** | `boamp_only` (Layer 1) | BOAMP-native only: SIRET > SIREN > normalized name | Primary result |
| **M1** | `enriched` (Layer 2) | + external SIREN enrichment (data.gouv/HF Parquets) + alias bridge | Sensitivity branch |

## 2. Current pipeline (reconstructed execution order)

1. `scripts/download_boamp.py` — DILA Opendatasoft API → `data/raw/boamp/pdl/boamp_YYYYMM.json` (140 files)
2. `scripts/parse_boamp.py` — flatten → `data/interim/boamp_raw_flattened.csv` (84,623 notices × 42)
3. `scripts/preprocess_boamp_m0.py` — clean, dedup, dates, durations (88% imputed by CPV-division median),
   CPV levels, buyer_key, digital scope → `boamp_clean_m0_no_enrichment.csv` (84,623 × 93),
   `boamp_m0_sources.csv` (3,159 × 22)
4. `scripts/build_m0_candidate_pairs.py` — buyer-key blocking + temporal window (±6 months around
   estimated end date), TF-IDF cosine, CPV & temporal scores → `boamp_m0_candidate_pairs.csv` (6,137)
5. `scripts/run_m0_linkage.py` — composite score, rank-1 selection, thresholds
   broad/balanced/strict = 0.2642/0.3230/0.3931 (rank-1 score p25/p50/p75) → links 927/618/309,
   `boamp_survival_m0_balanced.csv` (3,159 rows, 618 events, 80.4% censoring)
6. `scripts/run_survival_analysis.py` — KM (median not reached; RMST60 = 53.5 mo), Cox
   (cluster(buyer_key), penalizer 0.01), Weibull/log-normal AFT (log-normal wins, C = 0.725),
   PH tests, temporal validation, 12/24-month calibration
7. Evaluation scripts: `eval_m3_fellegi_sunter_mixture.py` (beta-mixture EM; precision̂ ≈ 0.455,
   recall̂ ≈ 0.253 over blocked pairs), `eval_m4_corruption_recovery.py`, `eval_m6a_threshold_sensitivity.py`,
   `eval_m6b_feature_ablation.py`, `eval_m6c_variant_km_robustness.py`, `eval_m6d_temporal_window_sensitivity.py`
   (6/9/12/18 m), `eval_duration_leakage.py` (forward-24m variant reverses log_duration HR 0.62 → 1.34)
8. M1 branch: `build_m1_buyer_siren_experiment.py` (enrichment + re-linkage → 8,228 pairs, 847 links, 26.8%),
   `build_m1_profile_domain_audit.py` (procurement-profile corroboration overlay)
9. Figures/audit/report: `make_figures.py`, `make_evaluation_figures.py`, `make_report_figures.py`,
   `make_m1_academic_diagrams.py`, `audit_current_project.py`, `build_final_scientific_audit.py`,
   `_build_*` helpers, `analyze_manual_validation_labels.py` (awaiting human labels)

Shared library: `src/utils/boamp_schema.py` (LEGACY vs EFORMS/UBL adaptive extraction),
`src/utils/identifiers.py` (SIREN/SIRET Luhn validation, name normalization), `src/utils/text_clean.py`.

Notebooks 05/07/08/11/12/13/14/15/16 mirror the scripts; all are cleanly executed top-to-bottom.

## 3. Key frozen parameters

| Parameter | Value | Origin / justification |
|---|---|---|
| Composite weights | text 0.35, CPV 0.30, time 0.25, buyer 0.10 | **Fixed a priori, not fitted** (documented limitation) |
| Text model | TF-IDF, 50k features, 1–2-grams, min_df 2, cosine | sentence-transformers evaluated then dropped |
| CPV ladder | exact 1.0 / category 0.8 / class 0.6 / group 0.4 / division 0.2 / different 0.0 / missing 0.1 | heuristic |
| Temporal window | clip(0.5·median duration, 6, 24) → **collapses to floor 6** | median duration = 6 mo ⇒ formula inert in practice |
| Thresholds | 0.2642 / 0.3230 / 0.3931 (broad/balanced/strict) | rank-1 composite p25/p50/p75, frozen; **shared by M1** |
| Duration | bounds 1–120 mo; median-by-CPV-division imputation; only 378/3,159 (12%) observed | high-leverage assumption |
| Event / censoring | rank-1 ≥ threshold ⇒ event, time = gap; else censored at (study_end − publication)/30.44 | proxy event, not verified legal renewal |
| Buyer mechanism scores (M1) | EXACT_SIRET 1.0 / SAME_SIREN 0.9 / HISTORICAL_ALIAS 0.75 / NAME_FALLBACK 0.6 | heuristic |

## 4. Enrichment methodology (as actually implemented)

- **Not an API pipeline.** Offline exact join to three pre-downloaded Parquets from Hugging Face
  `Data-Gouv-ML/jointure-boamp-siren-cote-acheteurs-2024-2025-et-2026` (pinned SHA
  `4bff9b1c5d2f4ad12834174e042828b7e52013d9`, downloaded 2026-07-15, ~1.1 GB, gitignored,
  **no download script exists**; `huggingface_hub` is not installed).
- Join on `idweb`, enforced `one_to_one`; SIREN/SIRET Luhn-validated; conflicts with BOAMP-native
  SIRET flagged, never overwritten. Provenance columns already exist
  (`buyer_identity_source`, `buyer_identity_confidence`, `buyer_match_mechanism`, conflict flags).
- **Alias bridge**: exact (normalized name, department) groups from direct-enriched rows propagate a SIREN
  only when unambiguous; generic names (mairie, commune…) and support < 2 held for review;
  historical propagation restricted to pre-2023 notices without direct identifiers. City/postcode unused.
- Coverage: 1,928/3,159 sources (61%) get a SIREN, but the external file covers only **2024–2026** of a
  2015–2026 corpus — only 458 sources join directly (296 gain SIREN that way); most lift comes from the
  internal alias bridge. Blocking coverage 39.1% → 47.6%; accepted links 618 → 847.

## 5. Verified headline numbers (parity oracle)

From `tests/fixtures/baseline_fingerprints.json` (recomputed 2026-07-17 from the files themselves):

| Quantity | M0 (boamp_only) | M1 (enriched) |
|---|---|---|
| Clean notices | 84,623 | (reuses M0) |
| Eligible sources | 3,159 | 3,159 |
| Candidate pairs | 6,137 | 8,228 |
| Links broad/balanced/strict | 927 / **618** / 309 | — / **847** / — |
| Event rate (balanced) | 19.6% | 26.8% |
| Source-ID overlap of balanced links | common 617, M0-only 1, M1-only 230 (Jaccard 0.728 by source) | |

Note: the previously reported "+273 added / −44 removed, Jaccard 0.644" counts **(source, candidate) pairs**;
by source ID only 1 M0 link loses linkage entirely — 43 of the 44 "removed" links are re-linked to a
different candidate. Both views will be reported explicitly in the redesigned comparison tables.

## 6. Defects and contradictions found

### Corrected during this audit
1. **84,623 vs 87,418 row-count contradiction — RESOLVED: 84,623 is correct.**
   `final_reproducibility_manifest.md` / `final_authoritative_files.csv` counted raw file lines;
   embedded newlines in quoted text fields inflate the count (87,418 lines vs 84,623 logical rows).
   The same artifact explains the "3,170 rows" entry for `boamp_clean_m1_buyer_enriched.csv`
   (actual logical rows: 3,159 — **no dedup defect exists**; the manifest generator is what needs fixing).

### To fix in the refactor
2. Notebooks 07/08 hand-duplicate scoring weights/thresholds instead of importing the scripts (drift risk).
3. `reports/tables/survival_logrank_tests.csv` is empty (1 byte) — log-rank tests never written.
4. `window_6m` survival dataset is generated by eval_m6d but missing from `run_survival_analysis.VARIANTS`.
5. Hardcoded constants: `N_ELIGIBLE_SOURCES = 3159` in `eval_m6a`; literal headline numbers in
   `_build_source_trace.py` (84623, 139 files…); 30.44 days/month repeated as a literal in every module.
6. Dead scaffolding: `if False` placeholder block in `build_m1_buyer_siren_experiment.py` (~line 836).
7. Stale docstring in `parse_boamp.py` (reads `…/boamp/pdl/`, docstring says `…/boamp/`).
8. File-count confusion — RESOLVED during refactor: `data/raw/boamp/pdl/` holds **139 monthly
   `boamp_*.json` data files** (2 of them empty `[]` placeholder months) plus
   `download_metadata.json`; the "140" in some audit tables counted directory entries.
9. No config files, no tests, no CI; parameters scattered across scripts and notebooks.
10. Enrichment Parquets are not re-downloadable from the repo (no script, package not installed).
11. `*.parquet.parquet` double extensions on the enrichment files.

### Reproducibility risks (ranked)
1. 29 of 31 national-archive JSONs (`data/raw/boamp_national_2024_2026_archive/`) are broken
   134-byte git-LFS pointer stubs — superseded data, but misleading in-tree.
2. Enrichment Parquets: gitignored, no downloader, tooling uninstalled (only the pinned SHA documents provenance).
3. Raw pdl JSONs (732 MB) and interim CSV are untracked/gitignored — fresh clone cannot rerun upstream
   without re-downloading via `download_boamp.py`.
4. Loose dependency pins; installed versions newer than "tested" comment implies.
5. Four manual-validation sample CSVs exist, **zero labels completed** — no ground-truth claims are possible.

### Duplicated / stale artifacts
- Two generations of comparison/audit tables: `m0_m1_*` (2026-07-15) vs `final_*` (2026-07-16); the
  `final_*` prefix means "final audit layer", not final results.
- `final_method_comparison.csv` ≡ `final_method_inventory.csv` (byte-identical size, overlapping content).
- Redundant `*_stdout.log` vs `*_stdout_pdl.log` run-log pairs (Run 1 national vs Run 2 PDL).
- `run_log.md` still shows superseded Run 1 numbers (340,772 notices / 74,547 events) beside Run 2.

## 7. File inventory (classification summary)

| Class | Items |
|---|---|
| Active source code | 3 `src/utils/*.py`; pipeline scripts 1–9 above (28 scripts) |
| Active notebooks | 05, 07, 08, 11, 12, 13, 14, 15, 16 (to be superseded by the 3-notebook redesign) |
| Raw input (active) | `data/raw/boamp/pdl/` (140 JSON), `data/raw/buyer_siren_enrichment_m1/` (3 Parquet), `data/raw/procurement_profiles/` |
| Raw input (superseded) | `data/raw/boamp_national_2024_2026_archive/` (mostly LFS stubs) → archive |
| Intermediate | `data/interim/boamp_raw_flattened.csv` |
| Processed outputs | ~34 CSVs in `data/processed/` (M0/M1 + sensitivity variants) + 2 window txt stubs |
| Generated tables | ~110 CSVs/JSON in `reports/tables/` (incl. overlapping `m0_m1_*`/`final_*` generations) |
| Figures | 26 PNG+PDF pairs in `reports/figures/` |
| Reports | 3 LaTeX+PDF (M0 tech, M1 tech, linkage quality), 5 Markdown, run logs |
| Tests | none (added by this refactor) |
| Config | none (added by this refactor) |
| Uncertain/pending | 4 unlabeled manual-validation CSVs → archive until labeled |

## 8. Attached-image ↔ repository ↔ redesign mapping

| Image stage (record-linkage diagram) | Current repo | Redesign disposition |
|---|---|---|
| Data pre-processing (per source) | `preprocess_boamp_m0.py` (common) + M1 enrichment prep | **Merged**: one common preparation; enrichment validation as a distinct stage (NB01 Part E) |
| Indexing / blocking | buyer_key blocking + ±6-month temporal window | **Preserved**, parametrized in `config/pipeline.yaml` |
| Comparison | component scores (text / CPV / time / buyer) | **Preserved**, single source of truth in `src/linkage/` |
| Classification (matches / non-matches / **potential matches**) | thresholds + rank-1; margins partially computed | **Extended**: explicit confidence tiers + best-vs-second margins + POTENTIAL tier (margin < 0.05, with sensitivity) |
| Evaluation | m3/m4/m6a–d, duration leakage, unlabeled manual samples | **Preserved & consolidated** into `03_analysis.ipynb` |
| Evaluation → Comparison feedback loop | absent | **Deliberately not closed** — tuning weights on score-selected links is circular; sensitivity analyses replace the loop |

## 9. Redesign summary (approved plan)

Strangler refactor: legacy scripts stay untouched as the oracle until the new `src/` package +
three notebooks (`01_data_engineering_pipeline`, `02_eda`, `03_analysis`) reproduce the baseline
fingerprints; then legacy notebooks/scripts/tables are archived with `archive/ARCHIVE_MANIFEST.csv`.
Naming: M0 → `boamp_only`, M1 → `enriched`, with this mapping table carried in the README.
Outputs move to `data/processed/{boamp_only,enriched,comparison}/` with explicit names
(`boamp_only_survival.csv`, `layer_comparison_summary.csv`, …). All parameters centralize into
`config/pipeline.yaml`. All three LaTeX reports are regenerated from reproduced numbers;
v1 PDFs archived.
