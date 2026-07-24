# BOAMP renewal linkage and survival analysis — two-layer design

Time-to-renewal analysis of French public procurement notices (BOAMP), built as
**two controlled, comparable layers** that differ in exactly one thing — buyer
identity:

| Layer | Name | Formerly | Buyer identity |
|---|---|---|---|
| 1 | `boamp_only` | M0 | BOAMP-native only: SIRET > SIREN > normalized name |
| 2 | `enriched` | M1 | + validated external SIREN enrichment + conservative alias bridge |

Scope: Pays de la Loire buyers (departments 44/49/53/72/85), 2015-01 → 2026-07,
digital/ICT contracts (CPV divisions 32/35/48/72 or keyword match). Layer 1
remains the primary specification; Layer 2 quantifies what buyer-identity
enrichment changes.

## Headline results (reproduced 2026-07-17, verified against frozen fingerprints)

| Quantity | Layer 1 (boamp_only) | Layer 2 (enriched) |
|---|---|---|
| Cleaned notices (shared) | 84,623 | same |
| Eligible source contracts (shared) | 3,159 | same |
| Candidate pairs | 6,137 | 8,228 |
| Sources with ≥1 candidate | 1,236 | 1,504 |
| Balanced links / rate | **618 / 19.6%** | **847 / 26.8%** |
| POTENTIAL-tier links (margin < 0.05) | 235 (38%) | 328 (39%) |
| Censoring rate | 80.4% | 73.2% |

Enrichment effect on the balanced link set (source view): **+230 added**
(170 historical-alias, 60 same-SIREN), **1 removed**, **43 changed candidate**.
Added links have markedly weaker text similarity (median s_text 0.070 vs 0.169)
— enrichment recovers plausible blocking failures but at lower evidence quality;
see `notebooks/03_analysis.ipynb` §1.7 and `data/processed/comparison/`.

Survival: median survival not reached in either layer (heavy censoring);
RMST(60m) ≈ 53.5 months in Layer 1. The duration covariate's hazard ratio is
**not robust** to the duration-leakage counterfactuals and must not be read
causally (03 §2.5).

## Repository layout

```
config/            paths.yaml, pipeline.yaml — every parameter, centralized
data/
  raw/boamp/pdl/   139 monthly BOAMP JSON files (+ download_metadata.json)
  raw/buyer_siren_enrichment_m1/  3 pinned HF enrichment Parquets (gitignored)
  interim/         flattened + common prepared corpus
  processed/
    boamp_only/    Layer 1: sources, candidate pairs, links, survival (+ variants)
    enriched/      Layer 2: same + validated enrichment, alias bridge, conflicts
    comparison/    layer_link_comparison, layer_changed_links, summaries, crosswalk
notebooks/
  01_data_engineering_pipeline.ipynb   Parts A–H: config → common prep → L1 → enrichment → L2 → comparison → integrity
  02_eda.ipynb                         descriptive EDA over 01's exports
  03_analysis.ipynb                    linkage-quality evaluation + survival, both layers
src/boamp/         the pipeline package (config / data / linkage / survival / validation / reporting)
src/utils/         BOAMP schema extraction, identifier validation, text cleaning
scripts/           retrieval only: download_boamp.py, download_enrichment.py
tests/             pytest suite incl. slow parity tests vs frozen fingerprints
reports/           figures, tables, generated reports, LaTeX sources
docs/              methodology.md, data dictionaries
archive/           superseded legacy code/outputs + ARCHIVE_MANIFEST.csv
```

## Reproduce from scratch

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# 1. retrieval (only if data/raw is empty; ~1 GB BOAMP + ~1.1 GB enrichment)
.venv/bin/python scripts/download_boamp.py
.venv/bin/python scripts/download_enrichment.py     # pinned HF revision

# 2. fast unit tests
.venv/bin/python -m pytest -q

# 3. the pipeline (order matters; ~15 min + ~5 min + ~20 min on CPU)
jupyter nbconvert --to notebook --execute --inplace notebooks/01_data_engineering_pipeline.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/02_eda.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/03_analysis.ipynb

# 4. parity gate (counts + link identities vs frozen baseline)
.venv/bin/python -m pytest -q -m slow
```

Everything is deterministic (no stochastic training; the recorded seed only
covers validation sampling). Execution metadata and file hashes land in
`data/processed/export_manifest.csv`.

## Method in one paragraph

For each eligible source contract, later notices from the same buyer within ±6
months of the contract's estimated end date are scored on
`S = 0.35·s_text + 0.30·s_cpv + 0.25·s_time + 0.10·s_buyer`
(TF-IDF cosine text similarity; CPV hierarchy ladder with missing = 0.1;
triangular temporal score; identity-reliability score). The rank-1 candidate is
linked if `S ≥ 0.3230` (the frozen "balanced" threshold — p50 of Layer 1 rank-1
scores; broad/strict = p25/p75 sensitivity variants). Linked sources are events
(time = gap to the linked notice); unlinked sources are censored at the study
end. Links with top1–top2 margin < 0.05 are tiered POTENTIAL, per the
three-way match / potential / non-match classification. Full details, notation,
and limitations: [docs/methodology.md](docs/methodology.md).

**Honest caveats.** The renewal event is an unverified proxy (no legal-renewal
ground truth exists in BOAMP; manual validation samples exist but have zero
completed labels). 88% of durations are imputed. Score weights are fixed a
priori, not fitted. External enrichment covers 2024–2026 only; historical
identity gains come from the exact name+department alias bridge. All quality
estimates in 03 are model-based or synthetic, each labeled with its evidence
class.

## Synthetic benchmark (v0.3, controlled linkage benchmark)

`src/boamp/synthetic/` implements a synthetic linkage benchmark, adapting
the gold-standard-and-corruption framework of Lam et al. (2024, *Generating
synthetic identifiers to support development and evaluation of data linkage
methods*, IJPDS 9:1:18) to public-procurement recurrence linkage. A clean
latent procurement population (buyers, establishments, procurement needs,
contract cycles, known recurrence relations) is generated first; BOAMP-like
publication notices are then produced and subjected to schema-dependent,
attribute-dependent and co-occurring corruption in identifiers, names, CPV,
duration, text and lifecycle references, while a separate known-truth
relation table (`true_relations.parquet`) is retained and never exposed to
the Layer 1/Layer 2 linkage code.

This exists to answer a question the real corpus cannot: whether candidate
linkage algorithms recover *known* synthetic recurrence relations under a
BOAMP-like observed structure. It does **not** estimate true BOAMP recurrence
prevalence, real-world precision, or real-world recall. The defensible claim is
conditional: if the benchmark reproduces the observable BOAMP structure and
candidate environment that materially affect linkage, then algorithm
performance across plausible synthetic scenarios is useful calibration and
comparison evidence.

- Current version: `v0_3_temporal_candidate_revision`, central scenario
  `central_provisional`, generated at
  `data/processed/synthetic_benchmark/v0_3_temporal_candidate_revision/`.
- Config: `config/synthetic/calibration_parameters_v0_1.yaml`,
  `benchmark_defaults_v0_1.yaml`, `recurrence_ontology_v0_1.yaml`, and
  `scenarios/{clean_sanity,central_provisional,adverse_identity}.yaml`.
  The v0.3 scoped-candidate parameters are now written directly in
  `central_provisional.yaml` and also snapshotted in `generation_metadata.json`.
- Validation status: `PASS_WITH_WARNINGS`, with no blocking gates. Internal
  integrity, specification recovery, candidate environment, conditional
  fidelity, missingness structure, privacy, and algorithm-utility gates pass.
  18 metrics still fail inside non-critical gates; that count is recorded in
  `validation_manifest.json` and the detail sits in
  `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/`.
- Reproducibility: `scripts/validate_synthetic_benchmark.py` regenerates the
  benchmark from saved seeds/config and compares canonical table-content hashes
  for observed notices, hidden truth, relationships, and corruption histories,
  so the headline status depends on replay. Pass `--no-replay` to skip it (the
  check then reports inconclusive). `scripts/replay_synthetic_benchmark.py`
  runs the same comparison standalone and writes `replay_comparison.json`.

Reproduce the current benchmark and validation:

```bash
python3 scripts/generate_synthetic_benchmark_v0_3_temporal_candidate_revision.py
python3 scripts/validate_synthetic_benchmark.py
python3 scripts/replay_synthetic_benchmark.py \
  --output reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/replay_comparison.json
python3 -m pytest -q tests/test_synthetic_*.py
```

## Name mapping vs earlier reports

Reports produced before 2026-07-17 (`boamp_m0_technical_report.pdf`,
`boamp_m1_technical_report.pdf`, `linkage_quality_evaluation.pdf`, `m0_*`/`m1_*`
tables) use the old naming: **M0 = Layer 1 = boamp_only**,
**M1 = Layer 2 = enriched**. Their headline numbers (618 and 847 balanced
links) are unchanged by the refactor; superseded artifacts live in `archive/`
with `ARCHIVE_MANIFEST.csv` recording origin and reason.
