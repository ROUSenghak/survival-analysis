# Restructure summary — two-layer redesign (2026-07-17)

Companion to `pre_refactor_audit.md` (the "before" state). This records what
changed, what was renamed/archived, and how to reproduce.

## What changed

| Area | Before | After |
|---|---|---|
| Naming | M0 / M1 | Layer 1 `boamp_only` / Layer 2 `enriched` (mapping in README) |
| Logic | 28 scripts + 9 notebooks, constants hand-duplicated in notebooks 07/08 | single source of truth in `src/boamp/` (config/data/linkage/survival/validation/reporting), orchestrated by 3 notebooks |
| Parameters | scattered per-script constants | `config/pipeline.yaml` + `config/paths.yaml`, loaded by `boamp.config` |
| Outputs | flat `data/processed/boamp_m0_*` / `boamp_m1_*` | `data/processed/{boamp_only, enriched, comparison}/` with explicit names + `export_manifest.csv` (rows, md5, git sha) |
| Tests | none | 45 pytest tests: 36 fast unit tests + 9 slow parity tests vs `tests/fixtures/baseline_fingerprints.json` |
| Classification | binary link decision | three-way match / POTENTIAL / non-match tier (margin < 0.05) |
| Enrichment retrieval | manual, no script, tooling uninstalled | `scripts/download_enrichment.py` (pinned HF SHA) |

## Defects fixed (all discovered in the pre-refactor audit)

1. **84,623 vs 87,418 rows** — resolved: 84,623 is correct; the v1 manifest
   line-counted a CSV with embedded newlines. Same artifact behind "3,170" for
   the M1 table (true: 3,159; no dedup defect existed).
2. **139 vs 140 files** — 139 monthly data JSONs + `download_metadata.json`.
3. **Empty `survival_logrank_tests.csv`** — v1 compared float CPV divisions to
   string literals; fixed in `boamp.survival.models.normalize_cpv_division`;
   the table is now populated (incl. a new L1-vs-L2 log-rank test).
4. **`window_6m` never modeled** — now in `survival_km_summary_all_variants.csv`.
5. Notebook/script constant duplication — eliminated by construction.
6. Hardcoded `N_ELIGIBLE_SOURCES=3159` (m6a) and headline literals
   (`_build_source_trace.py`) — parametrized / not carried over.
7. Dead `if False` scaffolding in the M1 script — dropped at extraction.
8. Repeated 30.44 literal — single `run.month_days` config value.
9. Stale `parse_boamp.py` docstring — corrected in `boamp.data.flatten`.

## Files renamed / replaced (key mappings)

| Old | New |
|---|---|
| `boamp_m0_sources.csv` | `boamp_only/boamp_only_sources.csv` |
| `boamp_m0_candidate_pairs.csv` | `boamp_only/boamp_only_candidate_pairs.csv` |
| `boamp_m0_links_{broad,balanced,strict}.csv` | `boamp_only/boamp_only_links_*.csv` |
| `boamp_survival_m0_balanced.csv` | `boamp_only/boamp_only_survival.csv` |
| `boamp_clean_m1_buyer_enriched.csv` | `enriched/enriched_sources.csv` |
| `boamp_m1_candidate_pairs.csv` | `enriched/enriched_candidate_pairs.csv` |
| `boamp_m1_links_balanced.csv` | `enriched/enriched_links_balanced.csv` |
| `boamp_survival_m1_balanced.csv` | `enriched/enriched_survival.csv` |
| `m0_m1_linkage_comparison.csv` etc. | `comparison/layer_comparison_summary.csv`, `layer_link_comparison.csv`, `layer_changed_links.csv`, `layer_overlap_summary.csv`, `buyer_identity_crosswalk.csv`, `enrichment_quality_report.csv` |
| `m0_composite_score` / `m1_composite_score` columns | `composite_score` (layer-neutral) |
| `buyer_siren_m1`, `buyer_key_m1_primary` columns | `buyer_siren_l2`, `buyer_key_l2` |
| `boamp_m0_technical_report.tex/pdf` | `boamp_layer1_technical_report.tex/pdf` (v2 note) |
| `boamp_m1_technical_report.tex/pdf` | `boamp_layer2_technical_report.tex/pdf` (v2 note) |

## Archived (never deleted)

176 items moved to `archive/` with full provenance in
`archive/ARCHIVE_MANIFEST.csv`: 9 legacy notebooks, 24 legacy scripts, all
legacy processed CSVs, the superseded national raw archive (mostly broken LFS
pointer stubs), ~120 pre-refactor report tables (incl. the 4 never-labeled
manual-validation samples), 6 v1 markdown reports, 3 v1 PDFs, 2 v1 tex sources.
Two capabilities were archived *without* a port (flagged in the manifest):
`build_m1_profile_domain_audit.py` (procurement-profile corroboration overlay)
and `analyze_manual_validation_labels.py` (needs labels that never existed).

## Removed

Nothing deleted except regenerable byproducts (`scripts/__pycache__/`, LaTeX
aux files). The 123 MB legacy clean CSV stays LFS-tracked at its archive path.

## Reproduced results (verified)

3,159 sources; 6,137/8,228 pairs; 618/847 balanced links; thresholds
0.2642/0.3230/0.3931 within 1e-4 of frozen; all 9 slow parity tests green;
notebook 01 integrity checks 10/10.

## Remaining limitations (unchanged by the restructure)

Proxy event without ground truth; 88% duration imputation; unfitted weights;
enrichment external coverage 2024–2026 only; blocking recall (52–61% of sources
candidate-less); zero completed manual-validation labels — see
`docs/methodology.md` §9 and the layer-comparison report §7.

## Exact reproduction order

```bash
pip install -r requirements.txt
python scripts/download_boamp.py            # only on a fresh clone
python scripts/download_enrichment.py       # only on a fresh clone
pytest -q                                   # 36 fast tests
jupyter nbconvert --to notebook --execute --inplace notebooks/01_data_engineering_pipeline.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/02_eda.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/03_analysis.ipynb
pytest -q -m slow                           # parity gate
cd reports && latexmk -pdf boamp_layer1_technical_report.tex boamp_layer2_technical_report.tex linkage_quality_evaluation.tex
```
