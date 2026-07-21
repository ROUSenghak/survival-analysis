# Synthetic benchmark v0.1 — Phase 0/1 audit

Audit performed before any generator code was written, per the v0.1
build instructions. Read-only inspection; no data or code modified in this
phase.

## 1. What already exists (do not duplicate)

Contrary to a from-scratch reading of the task, this repository already has a
mature calibration/audit layer, built across two prior commits
(`3f5b278 initialise synthetic data generation`, `e8c663a finish work 1 to 13
packages`), organized as 13 "work packages" (WP1-WP13) rather than the
"Phase 0-12" numbering used here. The two are largely equivalent in intent.
Existing, active artifacts:

- `notebooks/04_synthetic_benchmark_calibration.ipynb` (27 code cells) — reads
  `cfg.paths.interim_common_prepared` (`data/interim/boamp_common_prepared.csv`)
  as its primary corpus, plus `data/processed/boamp_only/*` for the
  explicitly SILVER_STANDARD-tagged Section 15 only.
- `reports/generated/synthetic_benchmark_calibration_report.md` — a full
  OBSERVABLE / SILVER_STANDARD / UNIDENTIFIED tiering report, already
  matching this task's "observable / unidentified / silver-standard"
  distinction almost exactly (different label, same three-way split).
- `reports/generated/eforms_cpv_discontinuity_report.md` — documents the
  eForms CPV parser bug and its fix (see §2 below).
- `reports/tables/synthetic_calibration/` — 80+ calibration CSVs, including
  `parameter_inventory.csv` (34 generator-facing parameters with
  `ready_to_freeze`), `calib_parameter_provenance_inventory.csv` (47
  section-level rows with explicit tiers), and
  `calib_unidentified_parameters_scenarios.csv` (5 explicit scenario knobs).
- `config/synthetic/recurrence_ontology.yaml` — a frozen 7-relation ontology
  (NEXT_CYCLE, PARTIAL_RECURRENCE, SPLIT, MERGE, SAME_THEME_DIFFERENT_NEED,
  UNRELATED, NO_SUCCESSOR, UNCERTAIN), fully tested
  (`tests/test_recurrence_ontology.py`).
- `config/synthetic/scenarios/01_clean_sanity.yaml` .. `06_adverse_combined.yaml`
  — 6 scenario families with required-field/provenance validation
  (`tests/test_scenario_families.py`).
- `src/boamp/validation/corruption.py` — an existing, unrelated
  semi-synthetic corruption/recovery test (`run_corruption_recovery`) built
  for the *real* Layer 1 pipeline's own strict links, not the v0.1 generator
  requested here. Reused only for its `cpv_pair_score`/`build_tfidf_matrix`
  imports where convenient; its own corruption functions (`corrupt_cpv`,
  `corrupt_duration`, `corrupt_text`) are pipeline-diagnostic code, not part
  of the clean-world generator.

**Decision**: per the instruction "do not assume filenames from the prompt
if equivalent active files already exist," v0.1 config/report artifacts
below are built as new, explicitly-versioned (`_v0_1`) files that
*reference and subset* this existing material, not as parallel duplicates of
it. `generator_parameter_actions.csv` (Phase 2's specific requested name)
is genuinely new (no existing file has that exact 4-way USE_DIRECTLY /
USE_AS_FIDELITY_TARGET / SCENARIO_PARAMETER / DO_NOT_USE decision column) and
was built by `scripts/build_generator_parameter_actions.py` directly from
the three tables above, not by re-deriving calibration numbers.

## 2. Phase 1 — eForms CPV consistency gate

**Finding: the correction is already implemented in production code.**

`src/utils/boamp_schema.py::extract_cpv_codes` already contains
`_EFORMS_CPV_PATH_HINTS` (matches
`(main|additional)commodityclassification/.+itemclassificationcode`,
case-insensitive) alongside the legacy `_CPV_HINTS` path. This function is
imported and called by `src/boamp/data/flatten.py` (production flattening,
not notebook-only code). `tests/test_boamp_schema.py` already covers both
paths (`test_extract_cpv_codes_from_eforms_item_classification_paths`,
`test_extract_cpv_codes_preserves_legacy_cpv_paths`).

**Empirical verification against the current interim corpus:**

```
schema_family  cpv_candidates_raw non-null rate
EFORMS         1.000000   (10,682 rows)
LEGACY         0.804736   (73,941 rows)
```

This matches `eforms_cpv_recovery.csv`'s `flattened_after_fix` /
`cleaned_prepared_after_fix` rows exactly (EFORMS 0.0% -> 100.0%). So
`data/interim/boamp_raw_flattened.csv` and `data/interim/boamp_common_prepared.csv`
**already reflect the corrected extraction** — no code change was required
in this session.

**Finding: Layer 1/Layer 2 processed outputs are stale relative to this fix.**

File mtimes:

| File | mtime |
|---|---|
| `data/interim/boamp_raw_flattened.csv` | 2026-07-20 15:10:47 |
| `data/interim/boamp_common_prepared.csv` | 2026-07-20 15:10:56 |
| `data/processed/boamp_only/*.csv` (candidate pairs, links, survival) | 2026-07-17 14:36-14:39 |
| `data/processed/enriched/*.csv` | (same 2026-07-17 generation as boamp_only) |

The interim corpus was regenerated **three days after** the Layer 1/Layer 2
processed outputs currently on disk. Those processed outputs were therefore
built from a pre-fix (or at least pre-regeneration) interim corpus and **must
be treated as stale** until notebook 01 Parts C-H are re-executed. This
repository's existing calibration report already isolates everything sourced
from these processed outputs into the SILVER_STANDARD tier
(`generator_use_status: DO_NOT_CALIBRATE`), so no generator-input parameter
in `parameter_inventory.csv` is contaminated by the staleness. However, the
staleness is **newly confirmed here with mtime evidence** (the existing
report only warned regeneration was needed, without confirming whether it
had happened) and must also block any Phase 12-style "compatibility check"
claim that reads real accuracy off `data/processed/{boamp_only,enriched}/*`
until they are regenerated.

**Action taken**: no code changes (already correct); documented staleness
here and reflected it in `generator_parameter_actions.csv` (SILVER_STANDARD
rows sourced from these files are `DO_NOT_USE`). Full pipeline regeneration
(`jupyter nbconvert --execute` on notebook 01, ~15-20 min) was **not** run in
this session — regenerating `data/processed/{boamp_only,enriched}/*` is
independent of building the v0.1 synthetic generator and is not a
prerequisite for it (the generator never reads those files). This is flagged
as a remaining item, not silently skipped.

## 3. Answers to the six required audit questions

1. **Exact prepared dataset used by notebook 04**: `data/interim/boamp_common_prepared.csv`
   (`cfg.paths.interim_common_prepared`), the shared layer-neutral prepared
   corpus (84,623 notices), for all OBSERVABLE-tier statistics. Section 15
   only additionally reads `data/processed/boamp_only/*` for SILVER_STANDARD
   diagnostics.
2. **Paths of all generator-relevant calibration tables**:
   `reports/tables/synthetic_calibration/*.csv` (80+ files; the two primary
   indexes are `parameter_inventory.csv` and
   `calib_parameter_provenance_inventory.csv`, now merged into
   `generator_parameter_actions.csv`).
3. **eForms CPV correction present in production preparation code?** Yes
   (confirmed above).
4. **Layer 1/Layer 2 outputs generated before or after the correction?**
   Before — stale by 3 days (confirmed above via mtime + empirical CPV
   coverage check).
5. **Observable / unidentified / silver-standard / algorithm-conditioned
   classification of notebook outputs**: already performed by the existing
   tiering framework; re-expressed as the 4-way `action` column in
   `generator_parameter_actions.csv`.
6. **Duplicate/inconsistent/obsolete calibration tables**: none found to be
   contradictory. Two near-duplicate CSVs exist by design, not by accident:
   `buyer_name_ambiguity.csv` (root) vs
   `calib_buyer_name_ambiguity_summary.csv`/`_examples.csv` (more granular
   breakdown, same underlying measurement) and similarly for
   `missingness_marginal_rates.csv`/`missingness_phi_matrix.csv` (§15c, 7
   flags) vs `calib_missingness_marginal_rates.csv`/`calib_missingness_correlation_heatmap.png`
   (§11, 5 flags, `name_fallback` excluded) — these measure different flag
   sets over different populations and are correctly documented as such in
   the calibration report; not treated as duplicates.
