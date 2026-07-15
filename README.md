# BOAMP Recurrence Linkage Pipeline

A reproducible pipeline that retrieves, cleans, and links French public
procurement notices from BOAMP (Bulletin officiel des annonces des marchés
publics) to build a **first deterministic linkage algorithm (M0)** for
studying procurement recurrence. M0 remains the official BOAMP-only baseline.
A separate buyer-enriched M1 branch is retained only as a sensitivity analysis.

This is a fresh, independent project. It does not reuse or compare against
any previous BOAMP study, report, or event count.

## Scope

This pipeline targets an internship guide's "Recommended Scope" (BOAMP-only,
no external enrichment, digital contracts in Pays de la Loire, 2015-latest):

- **Period**: 2015-01-01 to the latest available date (~2026-07).
- **Geography**: Pays de la Loire only (buyer department in
  {44, 49, 53, 72, 85}), applied server-side at retrieval time.
- **Themes**: digital/ICT contracts (CPV divisions 32, 35, 48, 72 and
  subcategories), applied as a hard filter on the M0 source population.

See `reports/boamp_m0_preprocessing_report.md` §3 for the full rationale,
including why the geographic filter (not a shorter date range) is what
makes the full 2015-2026 window tractable, and
`reports/run_logs/run_log.md` (Run 2) for how this scope was chosen.

## Current analysis decision

The current reporting position is:

- **M0 balanced is the main result and official survival handoff.**
- **M1 buyer SIREN enrichment is a sensitivity analysis, not a replacement.**
- The event is a constructed proxy recurrence, not verified legal renewal.
- M1 is useful evidence that buyer-name fragmentation affects coverage, but its
  incremental links need manual validation before it can become a primary
  specification.

Current headline results:

| specification | role | eligible sources | sources with candidates | candidate pairs | accepted links | proxy-recurrence rate |
|---|---|---:|---:|---:|---:|---:|
| M0 balanced | primary | 3,159 | 1,236 | 6,137 | 618 | 19.6% |
| M1 buyer-enriched | sensitivity | 3,159 | 1,504 | 8,228 | 847 | 26.8% |

See `reports/current_analysis_position.md` for the full decision memo and
`reports/m1_integrated_enrichment_pipeline_report.md` for the M1 enrichment
audit. The concise quantitative survival-sensitivity conclusion is in
`reports/survival_sensitivity_conclusion.md`.

## What this project does, and does not, do

- It retrieves raw BOAMP notices from the official DILA Opendatasoft API.
- It cleans notice-level fields (dates, notice type, buyer name, CPV, duration,
  free text) for the official M0 baseline without any external enrichment.
- It keeps and validates **raw, BOAMP-provided** SIRET/SIREN identifiers when
  present in the source data.
- It builds candidate "recurrence" pairs between an initial notice (source)
  and a later notice from the same buyer (candidate), and scores them with a
  transparent, documented rule (M0).
- The resulting links are **proxy recurrence candidates**, not verified legal
  renewals or contract continuations.

**The official M0 baseline does not perform external SIREN/SIRET enrichment.**
It never calls the INSEE SIRENE API or the data.gouv.fr entreprise search, and
it never infers a missing SIREN/SIRET from an external company database. Any
SIREN/SIRET used by M0 comes only from fields already present in the BOAMP
notice itself. The separate M1 branch uses the
`Data-Gouv-ML/jointure-boamp-siren-cote-acheteurs-2024-2025-et-2026`
dataset only to test buyer-identity enrichment as a sensitivity analysis.

## Data source

- Primary source: DILA Opendatasoft Explore API v2.1, dataset `boamp`
  (`https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/`).
  Verified live and used for retrieval (see `scripts/download_boamp.py` and
  `reports/tables/boamp_download_summary.csv`).
- Reference documentation inspected: the DILA BOAMP open-data directory
  (`https://echanges.dila.gouv.fr/OPENDATA/BOAMP/`), its `Documentation/`,
  `Schemas/`, and `FluxHistorique/` subfolders, and the DILA API presentation
  PDF. These confirm the DILA-published yearly/monthly XML archive as an
  alternative/fallback source; the Opendatasoft API was used because it is
  live, queryable by date range, and returns structured JSON.

## Project layout

```
data/
  raw/boamp/pdl/         # raw monthly JSON exports, Pays-de-la-Loire-filtered (never overwritten)
  raw/boamp_national_2024_2026_archive/  # superseded Run 1 national raw files (kept, not used)
  raw/buyer_siren_enrichment_m1/          # external SIREN data used only by M1 sensitivity analysis
  raw/procurement_profiles/               # procurement-profile data used only as M1 audit evidence
  interim/               # flattened, not-yet-cleaned notice table
  processed/             # cleaned M0 datasets, candidate pairs, links; separate M1 sensitivity outputs

scripts/                       # data retrieval + reproducible batch backend
  download_boamp.py            # Step 3: retrieval (geographic + date-range filter)
  parse_boamp.py               # Step 4: adaptive parsing / flattening
  preprocess_boamp_m0.py       # Step 5-6: batch equivalent of notebook 05
  build_m0_candidate_pairs.py  # Step 7: batch equivalent of notebook 07
  run_m0_linkage.py            # Step 8-9: batch equivalent of notebook 08
  make_figures.py              # Step 10: academic-style plots (also inlined in notebooks)
  _build_schema_summary.py     # Step 2: schema documentation table
  _build_source_trace.py       # Step 12: traces every reported number to its source
  _build_final_audit.py        # Step 13: checks all deliverables exist and are consistent
  build_m1_buyer_siren_experiment.py      # M1 sensitivity: SIREN buyer enrichment
  build_m1_profile_domain_audit.py        # M1 audit: procurement-profile domain evidence
  make_m1_academic_diagrams.py            # M1 reporting diagrams

notebooks/                     # the interactive front-end: preprocessing, feature
                               # engineering, and all analysis run HERE, with results inline
  05_preprocess_boamp_m0.ipynb           # Step 5-6: cleaning + M0 source population
  07_build_m0_candidate_pairs.ipynb      # Step 7: candidate pairs + scoring features
  08_run_m0_linkage.ipynb                # Step 8-9: linkage variants + survival dataset + QA
  11_eval_m3_fellegi_sunter_mixture.ipynb
  12_eval_m4_corruption_recovery.ipynb
  13_audit_current_project.ipynb
  14_eval_m6d_temporal_window_sensitivity.ipynb
  15_eval_duration_leakage.ipynb
  16_survival_robustness.ipynb

reports/
  boamp_m0_preprocessing_report.md
  current_analysis_position.md
  survival_sensitivity_conclusion.md
  m1_integrated_enrichment_pipeline_report.md
  source_values_used.csv
  final_audit_m0_preprocessing.csv
  figures/, tables/, run_logs/
```

## Reproducing the pipeline

Data retrieval from the external source stays in scripts; everything after it
(preprocessing, feature engineering, linkage, and all analysis) runs in the
notebooks, so every intermediate result, table, and figure is visible inline
and re-runs instantly when you tweak a rule.

```bash
pip install -r requirements.txt

# 1. Retrieval + parsing (external source -> flat interim table): scripts
python scripts/download_boamp.py
python scripts/parse_boamp.py

# 2. Preprocessing, feature engineering, linkage, analysis: notebooks
#    (open interactively, or execute headless in this order)
jupyter nbconvert --to notebook --execute --inplace \
  notebooks/05_preprocess_boamp_m0.ipynb \
  notebooks/07_build_m0_candidate_pairs.ipynb \
  notebooks/08_run_m0_linkage.ipynb
jupyter nbconvert --to notebook --execute --inplace \
  notebooks/14_eval_m6d_temporal_window_sensitivity.ipynb \
  notebooks/15_eval_duration_leakage.ipynb \
  notebooks/16_survival_robustness.ipynb

# Optional batch equivalents / report utilities
python scripts/make_figures.py
python scripts/_build_schema_summary.py
python scripts/_build_source_trace.py
python scripts/_build_final_audit.py
```

The pipeline notebooks (05/07/08) and their script counterparts implement the
same logic and write the same official output files; the notebooks are the
primary workflow, the scripts remain as a headless batch backend.

Each script is idempotent with respect to `data/raw` (raw files are never
overwritten) and logs its actions to `reports/run_logs/run_log.md`. If you
change the geographic or date-range scope in `download_boamp.py`, move or
rename the existing raw directory first - the "skip if file exists" logic
keys only on `boamp_YYYYMM.json`, so files from a different scope but the
same year-month would otherwise be silently reused (see run_log.md Run 2).

## Key terminology used throughout this project

- **Raw BOAMP-provided SIREN/SIRET**: an identifier taken as-is from a BOAMP
  notice field. Never enriched, inferred, or looked up externally.
- **Proxy recurrence candidate**: a pair of notices from the same buyer that
  the M0 rule judged similar enough in time, text, and CPV to plausibly
  represent a recurring procurement need. This is a modeling hypothesis, not
  a verified legal renewal.
- **Deterministic M0 linkage rule**: a fixed, documented, weighted scoring
  rule (no supervised learning) used to pick at most one candidate per
  source notice, at broad/balanced/strict thresholds.

See `reports/boamp_m0_preprocessing_report.md` for full methodology,
limitations, and next steps.

## Credibility audit and survival robustness addendum

The current credibility audit is summarized in reports/credibility_audit_report.md. Machine-readable outputs are in reports/tables/, especially:

- audit_credibility_implementation_matrix.csv
- audit_dataset_inventory.csv
- audit_blocking_coverage.csv
- audit_candidate_source_diagnostics.csv
- audit_duplicate_candidate_summary.csv
- duration_leakage_linkage_sensitivity.csv
- m6d_temporal_window_sensitivity.csv
- survival_km_summary.csv
- survival_cox_models.csv

After the original M0 pipeline, run:

    python3 scripts/audit_current_project.py
    python3 scripts/eval_m6d_temporal_window_sensitivity.py
    python3 scripts/eval_duration_leakage.py
    python3 scripts/run_survival_analysis.py

The balanced M0 link and survival files remain the official reference handoff. Alternative files with names such as boamp_survival_m0_window_12m.csv, boamp_survival_m0_no_temporal_score_reference_pool.csv, and boamp_survival_m0_forward_24m_no_duration.csv are sensitivity datasets, not replacements for the reference specification.

Notebook workflow: the temporal-window sensitivity (14), duration-leakage audit (15), and survival robustness (16) notebooks now contain the analysis code inline — running them regenerates the corresponding link/survival datasets and reports/tables/ outputs directly, with the results and diagnostic figures displayed in the notebook. They import the shared M0 scoring machinery from scripts/ so the linkage rule has a single definition. notebooks/13_audit_current_project.ipynb remains a viewer over scripts/audit_current_project.py (repository inventory, not analysis).

## Comprehensive technical report

`reports/boamp_m0_technical_report.tex` / `.pdf` is the single detailed
technical reference for the whole pipeline: raw-data column dictionary,
missing-value handling, the M0 preprocessing and recurrence-linking
algorithm (with full worked examples), the survival handoff's column
dictionary, all credibility diagnostics (blocking coverage, score margins,
the Fellegi-Sunter mixture, corruption recovery), the KM/Cox/AFT survival
results, and every sensitivity check (temporal-window, duration-leakage,
threshold, feature ablation, alternative event definitions), each tied to
its source CSV under `reports/tables/` or `data/processed/`. It also
documents the study's research questions, the observed computational
workflow (including where scripts and notebooks duplicate logic), and a
current implementation-status classification of every method (verified /
pending validation / partial / deferred / proposed). It embeds the figures
under `reports/figures/`: figures 01-18 from the figure scripts (including
two report-only figures from `scripts/make_report_figures.py` - an overall
Kaplan-Meier comparison across variants and a Cox hazard-ratio forest plot)
plus the `nb14_*`/`nb15_*`/`nb16_*` diagnostic figures written inline by
notebooks 14-16. Rebuild with:

    cd reports && pdflatex boamp_m0_technical_report.tex && pdflatex boamp_m0_technical_report.tex
