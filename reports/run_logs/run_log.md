# BOAMP M0 Pipeline — Run Log

This log records each pipeline execution. New runs are appended; earlier
entries are never edited.

---

## Run 1 — 2026-07-13

**Data source used**: DILA Opendatasoft Explore API v2.1, dataset `boamp`.
Base catalog verified live at
`https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/`.
Retrieval endpoint: `.../records/exports/json` (bulk export, no 10,000-row
offset cap), queried with a `where=dateparution in [...]` date filter and a
`select=...` field projection (drops the redundant `gestion` block, keeps
`donnees`, which carries CPV/SIRET/duration/attribution detail).

Reference documentation inspected before deciding on this source:
- `https://echanges.dila.gouv.fr/OPENDATA/BOAMP/` (directory listing: yearly
  folders 2015-2026, `Documentation/`, `Schemas/`, `FluxHistorique/`)
- `https://echanges.dila.gouv.fr/OPENDATA/BOAMP/2026/` (monthly subfolders
  01-07, confirming the DILA archive is organized as year/month ZIP/XML
  bundles — a viable fallback if the API had been unavailable)
- The Opendatasoft API was preferred over the raw DILA XML archive because it
  is queryable by date range and family, returns structured JSON directly
  (no XML parsing / ZIP handling needed), and was confirmed responsive.

**Full corpus discovered (not fully retrieved)**: 1,687,432-1,687,434 records
total (count drifts slightly as new notices publish), spanning
**2015-03-02 to 2026-07-13** (today). Nature breakdown across the full
corpus: APPEL_OFFRE 1,147,338 (68.0%), ATTRIBUTION 459,974 (27.3%),
RECTIFICATIF 70,562 (4.2%), and smaller categories (INTENTION_CONCLURE,
PRE-INFORMATION, MODIFICATION, ANNULATION, EX_ANTE_VOLONTAIRE).

**Study period actually retrieved**: 2024-01-01 to 2026-07-13.

Rationale for this window (full 11+ year archive was judged too large for a
first M0 pass):
1. Size: the full archive is ~1.69M notices; retrieving and embedding/scoring
   that volume is impractical for a first deterministic-linkage experiment.
2. Schema stability: BOAMP notices for the `JOUE` family (EU-threshold
   notices) switched from a legacy BOAMP XSD-derived JSON structure to the EU
   eForms/UBL JSON structure around the EU eForms mandate (Oct 2023).
   Starting the window at 2024-01-01 means JOUE notices in-scope are
   consistently in the eForms structure, simplifying (though not
   eliminating the need for) adaptive parsing. National-only notices
   (`FNS`, `MAPA`, `DSP`) keep the legacy structure throughout.
3. Follow-up: ending at the latest available date (2026-07-13, i.e. today)
   maximizes candidate/recurrence follow-up time for the most recent source
   notices while still leaving ~2.5 years of source notices with a
   meaningful follow-up window.

**Number of raw notices**: 340,772 (unique, 0 duplicates, 0 failed month
requests - see `reports/tables/boamp_download_summary.csv`).

**Number of cleaned notices**: 340,772 (`data/processed/boamp_clean_m0_no_enrichment.csv`;
no rows dropped during cleaning - deduplication already happened at parse
time on `notice_id`/`idweb`). Breakdown: APPEL_OFFRE 234,871, ATTRIBUTION
89,752, OTHER 16,149 (RECTIFICATIF/MODIFICATION/ANNULATION/PRE-INFORMATION/
EX_ANTE_VOLONTAIRE/PERIODIQUE/QUALIFICATION).

**Warnings**:
- CPV coverage among APPEL_OFFRE sources is 39.4% - the majority of sources
  have no recoverable CPV code, so `s_cpv` falls back to the neutral
  "missing" score (0.1) for most pairs.
- 22.8% of APPEL_OFFRE sources required duration imputation (median
  observed duration by CPV division, or global median as a fallback).
- The recursive SIRET/SIREN/CPV extractor is best-effort (pattern-matched,
  not schema-path-hardcoded); see `src/utils/boamp_schema.py` docstring and
  report §15 for known limitations.
- 15,818 of 74,547 balanced-variant linked candidate notices are claimed by
  more than one distinct source notice - flagged, not silently accepted
  (see `m0_preprocessing_quality_checks.csv`).
- A monkey-patch test of `parse_boamp.py` on a 200-record sample
  accidentally ran on the full raw dataset instead (module-level globals are
  reset by `exec_module`); it was killed and the real script was run
  directly. No output artifact was affected.
- An initial version of `build_m0_candidate_pairs.py` used a per-row
  `DataFrame.iloc` + element-wise sparse-similarity loop, which did not
  finish in a reasonable time for high-frequency buyers (up to 1,482
  APPEL_OFFRE notices from one buyer in this window); it was rewritten to
  use `searchsorted`-based temporal windowing, a documented per-source
  candidate cap (30), and batched sparse similarity before the run that
  actually produced `boamp_m0_candidate_pairs.csv`.
- An initial "suspicious repeated candidate" diagnostic incorrectly counted
  the same (source, candidate) link once per variant it survived in; it was
  corrected to check reuse only within the balanced variant before the
  quality-checks table was finalized.

**Scripts run** (in order): `download_boamp.py`, `parse_boamp.py`,
`preprocess_boamp_m0.py`, `build_m0_candidate_pairs.py`, `run_m0_linkage.py`,
`make_figures.py`, plus two one-off report-assembly helpers
(`scripts/_build_source_trace.py`, `scripts/_build_final_audit.py`).

**Final outputs**: see `reports/final_audit_m0_preprocessing.csv` (34/34
checks pass) and `reports/source_values_used.csv` for a full traced list.
Headline results: candidate pairs 2,204,398; M0 events - broad 111,712
(47.6%), balanced 74,547 (31.7%), strict 37,238 (15.9%); full methodology
and limitations in `reports/boamp_m0_preprocessing_report.md`.

---

## Run 2 — 2026-07-13 (re-scoped to match internship guide)

**Reason for this run**: after reviewing an internship guide
(`Internship_Guide___Predictive_Modeling.pdf`, not part of this repo) in
detail, the user flagged that Run 1's national, all-sector, 2024-2026 study
period did not align with the guide's §3.2.2 "Recommended Scope for the
Internship," which bundles a date range, a geographic filter, and a
thematic filter together. The user confirmed the project stays BOAMP-only
(no TED, data.gouv.fr DECP, FOPPA) and still performs no external SIREN/
SIRET enrichment - only the scope of the BOAMP retrieval itself changed.

**Scope decisions** (clarified with the user before implementation):
1. Study period: 2015-01-01 to latest available (~2026-07-13) - guide said
   2015-2024, extended past 2024 for more follow-up/censoring time.
2. Geography: Pays de la Loire only (departments 44, 49, 53, 72, 85) - no
   Grand Ouest extension.
3. Themes: digital contracts (CPV divisions 32, 35, 48, 72 and
   subcategories) as a **hard filter** on the M0 source population
   (Run 1 had this as an informational-only flag with an incorrect,
   broader CPV set).

**Data source used**: same as Run 1 (DILA Opendatasoft Explore API v2.1,
`boamp` dataset, `.../exports/json` bulk endpoint).

**API endpoint / query change**: added a server-side department filter to
the `where` clause: `code_departement in ("44","49","53","72","85")`.
Verified live before committing to the full download (read-only, no side
effects):

| Query | total_count |
|---|---|
| Jan 2024, national (no filter) | 8,728 |
| Jan 2024, Pays de la Loire filter | 531 (~6.1%) |
| Full period 2015-01-01..2026-07-13, Pays de la Loire filter | 84,623 |

This confirmed both the ODSQL syntax and that the full 11+ year window is
tractable once geographically filtered - resolving the size problem that
had forced Run 1 to shrink the *date range* instead.

**Actual study period retrieved**: 2015-01-01 to 2026-07-13 (Jan/Feb 2015
return empty results - the underlying corpus starts 2015-03-02, not a
retrieval failure).

**Raw file handling**: Run 1's national 2024-2026 raw files were moved
(not deleted) to `data/raw/boamp_national_2024_2026_archive/`, since the
new Pays-de-la-Loire-filtered files would otherwise collide with the same
`boamp_YYYYMM.json` filenames for the overlapping months and be silently
skipped as "already downloaded." New downloads went to `data/raw/boamp/pdl/`.

**Number of raw notices**: 84,623 (unique, 0 duplicates, 0 failed month
requests, 139 raw files - down from Run 1's 340,772/31 files, consistent
with the ~20x volume reduction from the geographic filter over a ~4.5x
longer period).

**Number of cleaned notices**: 84,623 (no rows dropped during cleaning).
Breakdown: APPEL_OFFRE 58,292 (all sectors), ATTRIBUTION 22,560, OTHER 3,771.
Schema family: LEGACY 73,941 (87.4%), EFORMS 10,682 (12.6%) - the reverse
mix from Run 1, since most of the newly-included 2015-2023 years predate
the EU eForms mandate.

**M0 source population** (APPEL_OFFRE, digital-scope hard filter applied):
**3,159** (CPV-or-keyword definition, used as the headline population -
within the guide's 2,000-5,000 target) vs. **1,882** (CPV-division-only,
reported as a sensitivity check).

**Warnings / notable findings**:
- Duration-field completeness for this scope is much worse than Run 1's
  national figure: only 378/3,159 sources (12.0%) have an observed,
  in-range duration vs. Run 1's 77.2% nationally. Spot-checked across
  `famille` categories (FNS 12.2%, JOUE 13.3%, MAPA 5.6% observed) to rule
  out an EFORMS-specific extraction bug - the low completeness appears
  consistent across schema families, i.e. a genuine data characteristic of
  how digital contracts are described in this region, not a pipeline
  defect. This directly answers the guide's own Week-1 "scientific question
  of the week" about duration-field reliability.
- CPV coverage improved sharply for this scope: 78.4% (vs. 39.4% nationally
  in Run 1), though generic (division-only) CPV codes are also a bit more
  common (9.15% vs 2.46%).
- Median gap between linked pairs (balanced variant) is ~37.7 months
  (~3.1 years), a sharp contrast with Run 1's ~6.1-month national median -
  consistent with the guide's own framing of multi-year framework
  agreements being renewed around their expected end date. This is treated
  as a validation signal that the re-scoping surfaced the intended
  renewal-cycle pattern, not assumed without checking.
- `NAME_FALLBACK` buyer-key share rose to 72.8% (vs. 60.5% nationally),
  and the single top buyer by M0 event count is itself name-keyed
  (`NAME:nantes metropole`, 125 events) - flagged as a higher false-merge/
  false-split risk area for this scope than Run 1's national data.
- 121 of 618 balanced-variant linked candidates (19.6%) are claimed by more
  than one distinct source - proportionally similar to Run 1's finding,
  still flagged rather than silently accepted.
- An empty raw file (`boamp_201501.json`, 0 records - Jan 2015 predates the
  corpus start) initially crashed `parse_boamp.py` with a `KeyError` on an
  empty DataFrame; fixed by skipping zero-row files before the dedup step.

**Scripts run** (in order): `download_boamp.py` (re-scoped constants),
`parse_boamp.py` (RAW_DIR repointed to `data/raw/boamp/pdl/`),
`preprocess_boamp_m0.py` (corrected CPV set, hard digital filter, in-scope
duration medians, PDL diagnostic), `build_m0_candidate_pairs.py`,
`run_m0_linkage.py`, `make_figures.py`, `scripts/_build_schema_summary.py`
(new - schema table generation was ad hoc in Run 1, now a proper script),
`scripts/_build_source_trace.py` (values updated), `scripts/_build_final_audit.py`
(hardcoded month filenames replaced with values derived from
`download_metadata.json`).

**Final outputs**: `reports/final_audit_m0_preprocessing.csv` - 34/34 checks
pass. Headline results: candidate pairs 6,137; M0 events - broad 927
(29.3%), balanced 618 (19.6%), strict 309 (9.8%); full methodology,
scope rationale, and limitations in
`reports/boamp_m0_preprocessing_report.md`.
