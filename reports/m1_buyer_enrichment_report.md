# M1 buyer SIREN enrichment experiment

Generated: 2026-07-15

## Inputs

- M0 remained read-only: `boamp_m0_sources.csv`, `boamp_m0_candidate_pairs.csv`, `boamp_m0_links_balanced.csv`, and `boamp_survival_m0_balanced.csv`.
- External dataset: `Data-Gouv-ML/jointure-boamp-siren-cote-acheteurs-2024-2025-et-2026` at Hugging Face commit `4bff9b1c5d2f4ad12834174e042828b7e52013d9`.
- Download date: `2026-07-15`.
- Join key: `B_17_idweb -> notice_id`; no duplicate enrichment notice identifiers were observed in the raw 2024, 2025, or 2026 files.

## Enrichment coverage

- External rows audited: 323,938.
- Overlap with current cleaned BOAMP corpus: 18,098 notices.
- Overlap with M0 source notices: 458 notices.
- Overlap with M0 candidate universe: 220 notices.
- Identifier conflicts where BOAMP SIRET-derived SIREN disagrees with enriched SIREN: 1,002.
- Agreement among notices with both BOAMP SIRET-derived SIREN and valid enriched SIREN: 87.379% (6,937/7,939).

## M0 versus M1

- Blocking coverage: M0 39.126%; M1 47.610%.
- Candidate pairs: M0 6,137; M1 8,228.
- Balanced links at the M0 score threshold: M0 618; M1 847.
- Overall proxy-recurrence rate: M0 19.563%; M1 26.812%.
- M0-zero-candidate sources recovered by M1: 269.
- Link-set Jaccard overlap: 0.644.
- Incremental M1 links: 273; M0 links lost under M1 ranking/threshold: 44; identical links: 574.
- Same source but different selected candidate: 43.

## Alias bridge

- Historical aliases eligible for automatic propagation: 1,247.
- Ambiguous or review-only aliases: 1,912.
- Historical 2015-2023 M0 sources gaining an inferred SIREN: 919.
- M0 name-fallback sources becoming SIREN-keyed: 1,215.
- New links by recovery mechanism: {"HISTORICAL_ALIAS_RECONCILIATION": 198, "SAME_SIREN_RECONCILIATION": 75}.

## Credibility

Incremental M1 links were exported separately and not pooled with M0 as ground truth. Internal score and margin diagnostics are in `reports/tables/m1_incremental_link_score_diagnostics.csv`; these are consistency checks, not precision estimates.

## Recommendation

M1 should remain a sensitivity specification for now, not replace M0. It improves buyer reconciliation coverage through direct SIREN joins and conservative historical aliases, but the incremental links still require manual validation, conflict review, and survival sensitivity checks before the official baseline can change.

Final consistency checks passed: 10/10.

## Pipeline Figures

These figures place the SIREN enrichment experiment in the full M0 -> M1 -> profile-audit workflow.

- `reports/figures/m1_enrichment_profile_pipeline.png`
- `reports/figures/m1_enrichment_profile_pipeline.pdf`
- `reports/figures/m1_reproducible_runflow.png`
- `reports/figures/m1_reproducible_runflow.pdf`
- Integrated synthesis: `reports/m1_integrated_enrichment_pipeline_report.md`
