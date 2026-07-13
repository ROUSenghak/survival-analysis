# BOAMP M0 Preprocessing Report

**Run date:** 2026-07-13 (Run 2 - re-scoped)
**Scope:** a fresh, independent BOAMP retrieval/cleaning/linkage pipeline. No
previous repository, report, or event count was reused or compared against.

This is the second run of this pipeline (see `reports/run_logs/run_log.md`).
Run 1 used a national, all-sector, 2024-2026 window. This run re-scopes the
study to match an internship guide's "Recommended Scope for the Internship"
(Pays de la Loire, digital contracts, 2015-latest), which the original
national/2.5-year window did not align with.

Every number in this report is reproduced in
[`reports/source_values_used.csv`](source_values_used.csv), traced to the
generated table/file it came from.

---

## 1. Data source used

**DILA Opendatasoft Explore API v2.1, dataset `boamp`**, confirmed live at
`https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/`.
Unchanged from Run 1 - see that source's discovery notes in the run log.

## 2. API vs. downloadable files

Unchanged from Run 1: the Opendatasoft API's `.../exports/json` endpoint was
used (no 10,000-row offset cap), with a `select=` field projection dropping
the redundant `gestion` block while keeping `donnees`.

## 3. Study period, geographic scope, and thematic scope

This run applies all three parts of a "recommended scope" bundle rather than
just a date range, following an internship guide's §3.2.2 that ties them
together:

- **Period: 2015-01-01 to 2026-07-13** (latest available). The guide's
  literal recommendation was 2015-2024 ("10 years... allowing at least one
  full renewal cycle to be observed for four-year contracts"); the end date
  was extended past 2024 to the latest available data for more follow-up/
  censoring time on recently-launched contracts.
- **Geography: Pays de la Loire only** - buyer department in
  `{44 Loire-Atlantique, 49 Maine-et-Loire, 53 Mayenne, 72 Sarthe, 85 Vendee}`,
  applied **server-side** via `code_departement in ("44","49","53","72","85")`
  in the API `where` clause (the guide's stated priority area; its "Grand
  Ouest extension" fallback was not applied, since volume did not require
  it - see §6). `code_departement` is the notice/buyer department; the
  alternative field `code_departement_prestation` (place of performance) was
  found to be 100% null in the retrieved data and is unusable.
- **Themes: digital contracts** - CPV divisions `{32 telecommunications
  equipment, 35 security, 48 software, 72 IT services}` and their
  subcategories, applied as a **hard filter** on the APPEL_OFFRE source
  population (Run 1 computed this as an informational-only flag; it is now
  a real filter, and the CPV division set was corrected to match the guide
  exactly - Run 1 used an incorrect broader guess `{30,32,48,72,79}`).

**Why the geographic filter matters beyond just narrowing scope**: the full
national archive (~1.69M notices, 2015-2026) was judged too large for a
first pass in Run 1, which is why Run 1 shrank the *date range* instead
(2024-2026 only). Applying the geographic filter resolves the size problem
directly without shrinking the time window - confirmed live against the API
before committing to the full download:

| Query | total_count |
|---|---|
| Jan 2024, national (no filter) | 8,728 |
| Jan 2024, Pays de la Loire filter | 531 (~6.1%) |
| **Full period 2015-01-01 to 2026-07-13, Pays de la Loire filter** | **84,623** |

**Actual retrieved**: 84,623 unique notices, 139 monthly files, 0 duplicates,
0 failed requests (`reports/tables/boamp_download_summary.csv`). Raw files
live under `data/raw/boamp/pdl/`; the earlier national 2024-2026 files were
moved (not deleted) to `data/raw/boamp_national_2024_2026_archive/`.

## 4. Parsing and schema

Unchanged mechanism from Run 1 (adaptive recursive extractor in
`src/utils/boamp_schema.py`, handling both the LEGACY BOAMP-XSD-derived JSON
structure and the EU eForms/UBL JSON structure). Extending the window back
to 2015 shifts the schema mix: LEGACY notices (73,941, 87.4%) now dominate
over EFORMS notices (10,682, 12.6%), the reverse of Run 1's 2024-2026-only
mix, since most of the newly-included years predate the EU eForms mandate
(~Oct 2023). No extractor changes were needed - it was already built
schema-family-agnostic, not date-range-agnostic-by-luck.

## 5. Preprocessing choices

Cleaning logic (notice ID, notice type, dates, text, CPV hierarchy,
duration) is unchanged from Run 1 - see that run's description in the run
log for the full rationale. What changed:
- `DIGITAL_CPV_DIVISIONS` corrected to `{32, 35, 48, 72}` (was
  `{30, 32, 48, 72, 79}`).
- Duration-imputation medians (median observed duration by CPV division,
  falling back to a global median) are now computed **on the digital +
  Pays-de-la-Loire APPEL_OFFRE population only**, not the whole cleaned
  dataset, so imputed durations reflect the actual in-scope contracts.
- A defense-in-depth diagnostic (`is_in_pdl`) checks that every cleaned
  notice's department is actually in the Pays de la Loire set, to catch a
  stale pre-rescope raw file slipping in. Result: 0 notices flagged
  outside scope.

## 6. No external SIREN/SIRET enrichment

Unchanged from Run 1: no INSEE SIRENE API, no data.gouv.fr entreprise
search, no external company database anywhere. Only BOAMP-provided
identifiers are used, format/checksum-validated (`src/utils/identifiers.py`).

## 7. Raw BOAMP buyer-key construction

Unchanged logic from Run 1 (RAW_SIRET > RAW_SIREN > SIREN-derived-from-SIRET
> NAME_FALLBACK > MISSING). Observed distribution across all 84,623 cleaned
Pays-de-la-Loire notices: **RAW_SIRET 23,038 (27.2%)**, **NAME_FALLBACK
61,585 (72.8%)**, **MISSING 0**. The NAME_FALLBACK share is higher than in
Run 1's national sample (60.5%), plausibly because smaller regional/local
buyers (small communes, local public bodies) are less likely to publish a
recoverable SIRET than large national bodies.

## 8. APPEL_OFFRE source population

58,292 APPEL_OFFRE notices exist in the Pays-de-la-Loire, all-sector
cleaned dataset. Applying the digital-scope hard filter (CPV-or-keyword)
narrows this to **3,159 APPEL_OFFRE sources** -
`data/processed/boamp_m0_sources.csv` - which lands within the guide's
target range of 2,000-5,000 contracts. A stricter CPV-division-only
definition gives 1,882 (reported as a sensitivity check, not the headline
population - CPV coverage among APPEL_OFFRE notices is well below 100%, so
requiring an exact CPV match alone would drop genuine digital notices that
simply lack a recoverable CPV code).

All 3,159 sources have a usable buyer key (0 `MISSING`), so all are
eligible for candidate generation. `start_date`/`estimated_end_date` logic
is unchanged from Run 1 (linked-ATTRIBUTION-date priority, then publication
date fallback; `study_end_date` = max observed publication date, 2026-07-13).

## 9. ATTRIBUTION use

22,560 ATTRIBUTION notices retrieved (Pays de la Loire, all sectors) and
cleaned alongside APPEL_OFFRE; unchanged role from Run 1 - only used for the
`annonce_lie` reverse-lookup that supplies `start_date`, not as M0
candidates themselves and not sector-filtered (a digital APPEL_OFFRE's
linked ATTRIBUTION is looked up regardless of the ATTRIBUTION's own sector
tag, since the reverse-lookup only matches on `annonce_lie` -> `idweb`).

## 10. CPV cleaning

CPV coverage jumped from 39.4% (Run 1, national all-sector) to **78.4%**
among the digital-scope sources - unsurprising, since digital/IT
procurement in this corpus is more often given an explicit CPV code than
the general population. Generic (division-only) CPV codes: 9.15% of
sources (also up from 2.46% nationally, worth noting as a milder data-
quality caveat alongside the coverage improvement).

CPV coverage by year (`reports/figures/04_cpv_coverage_by_year.png`) is not
flat, however: it rises steadily from 74% (2015) to 92% (2022-2023), then
drops sharply to 51% (2024), 51% (2025), and 45% (2026). This timing lines
up with the EU eForms/UBL schema transition for JOUE notices (~late 2023) -
the working hypothesis is that the CPV-extraction pattern used for the
eForms structure (searching for an 8-digit code near a key containing
"cpv") is less reliable than the legacy structure's direct
`CPV.objetPrincipal.classPrincipale` path, though this has not been
root-caused further in this run. Recent-year CPV-dependent figures
(coverage, `s_cpv` scores, generic-CPV share) should be read with this drop
in mind.

## 11. Duration cleaning

**Median observed (non-imputed) duration: 6.0 months**, based on only
**378 of 3,159 sources (12.0%)** having a directly observed, in-range
duration; the remaining **88.0% required imputation**
(`duration_imputation_rate_sources`), sharply higher than Run 1's national
rate (22.8%). This was checked for an extraction bug (spot-checked observed-
duration rates by `famille`: FNS 12.2%, JOUE 13.3%, MAPA 5.6% - consistently
low across all publication tiers and both schema families, not an
EFORMS-specific artifact) and appears to be a genuine data-completeness
characteristic of how digital/IT contracts are described in BOAMP notices
in this region, not a pipeline defect. This directly answers the internship
guide's own "Scientific question of the week" (Week 1: "to what extent is
the 'contract duration' variable reliable in BOAMP data?") - the answer
here is: not very, for this specific (digital, Pays de la Loire) population,
and the 6-month median should be read with the n=378 sample size in mind.

## 12. M0 candidate generation

Same mechanism as Run 1 (same buyer_key, later publication date, within a
temporal window around `estimated_end_date`), recomputed on the new
population:

`TEMPORAL_WINDOW_MONTHS = clip(0.5 x 6.0, 6, 24) = 6` (same value as Run 1,
since the median observed duration is unchanged at 6.0 months - though now
based on only 378 observations instead of Run 1's larger observed-duration
sample).

`MAX_CANDIDATES_PER_SOURCE = 30` (unchanged constant) was not expected to
bind given much smaller buyer groups in this scope, and did not in practice.

**Result:** 6,137 candidate pairs (down from 2.2M in Run 1, consistent with
the ~74x smaller source population), covering 1,236 of 3,159 sources (39.1%)
- 1,923 sources had no same-buyer digital APPEL_OFFRE notice inside the
temporal window in this scope/period.

## 13. M0 scoring

Unchanged method and weights from Run 1: TF-IDF + cosine similarity for
text (sentence-transformers still not used, for the same CPU-runtime
reasoning as Run 1 - now even less necessary given the much smaller corpus,
but kept consistent for comparability); the same CPV hierarchy score; the
same linear time-decay score; the same buyer-agreement score by
`buyer_key_type`; and the same composite weights
(`0.35*s_text + 0.30*s_cpv + 0.25*s_time + 0.10*s_buyer`). The new
score distribution (mean 0.25, vs. Run 1's mean 0.29) was reviewed and the
weights were kept as-is rather than re-tuned, since re-tuning against a
single run's distribution without a validation set would risk overfitting
to this particular sample.

## 14. M0 broad/balanced/strict results

Thresholds re-derived from the new rank-1 score distribution (25th/50th/75th
percentile):

| variant  | threshold | linked events | event rate |
|----------|-----------|----------------|------------|
| broad    | 0.2642    | 927            | 29.3%      |
| balanced | 0.3230    | 618            | 19.6%      |
| strict   | 0.3931    | 309            | 9.8%       |

**Median gap between linked pairs (balanced variant): ~37.7 months (~3.1
years)** - a striking contrast with Run 1's national all-sector median gap
of ~6.1 months, and directly consistent with the guide's own framing of
"a four-year contract... typically renewed around plus or minus six months
from its expected end date." This is a meaningful internal validation that
narrowing to digital/framework-agreement-heavy procurement surfaces the
longer renewal cycles the guide's survival-analysis framing assumes,
whereas the unfiltered national population (dominated by short MAPA/works
contracts) did not.

Top buyer by linked events (balanced): `NAME:nantes metropole` (125 events)
- notably a `NAME_FALLBACK`-keyed buyer rather than a `RAW_SIRET`-keyed one,
unlike Run 1's top buyer. This is a reminder that `NAME_FALLBACK` matches
still carry the false-merge/false-split risk described in §15 even when
they dominate the top of the ranking.

**These are proxy recurrence candidates, not verified legal renewals** -
unchanged caveat from Run 1.

## 15. Data limitations

- **Duration completeness is low for this scope** (88.0% imputed, n=378
  observed) - see §11. The 6-month median duration should be treated as
  low-confidence; it is also the value driving the 6-month temporal window
  in §12, so that window inherits the same uncertainty.
- **CPV coverage (78.4%) is much better than Run 1 but not complete** -
  21.6% of sources still fall back to the neutral "missing CPV" score
  (0.1) in `s_cpv`. Coverage is also not stable over time: it drops from
  ~92% (2022-2023) to ~45-51% (2024-2026), plausibly tied to the eForms
  schema transition's CPV field being harder to extract with the current
  generic pattern-matcher (see §10) - recent years' CPV-dependent figures
  should be read with this in mind.
- **SIRET extraction is still best-effort and generic** (unchanged
  limitation from Run 1 - the recursive extractor can occasionally pick a
  non-buyer identifier from a notice listing several organizations).
- **`NAME_FALLBACK` buyer keys (72.8% of notices, up from 60.5% nationally)**
  carry a higher false-merge/false-split risk in this scope than in Run 1,
  and the top-ranked buyer by event count is itself name-keyed (see §14) -
  worth prioritizing if this pipeline is extended.
- **Candidate notices claimed by multiple sources**: 121 of 618 balanced-
  variant linked candidates are the top match for more than one source
  (down proportionally from Run 1's 15,818/74,547, but still ~19.6% of
  links) - flagged, not silently accepted.
- **Small-sample effects**: 3,159 sources and 618 balanced-variant events is
  much smaller than Run 1's 234,868/74,547. Yearly and CPV-division
  breakdowns in the figures should be read with this in mind - some strata
  will have very few observations.
- **Geographic scope reflects buyer department, not place of performance**
  (`code_departement_prestation` is unusable - 100% null). A Pays-de-la-
  Loire buyer procuring work performed elsewhere is still in scope; a
  non-regional buyer procuring work performed in Pays de la Loire is not.
- **No verified ground truth** exists for what counts as a true renewal;
  precision/recall of the M0 rule remain unknown, as in Run 1.
- The study period (2015-01 to 2026-07) still excludes Jan-Feb 2015 data
  that does not exist in the source (BOAMP's Opendatasoft corpus starts
  2015-03-02) - those two months' raw files are empty by construction, not
  a retrieval failure.

## 16. Next steps

- If more recurrence signal is needed, apply the guide's "Grand Ouest
  extension" fallback (adding Brittany/Normandy/Centre-Val de Loire
  departments) - current volume (3,159 sources, 618 balanced events) did
  not require it, but a future analysis targeting rarer digital
  subcategories might.
- Investigate the low duration-field completeness for digital contracts
  specifically (§11) - e.g. whether specific CPV subcategories or
  procedure types are systematically missing `dureeMois`/`DurationMeasure`.
- Root-cause the 2024-2026 CPV coverage drop (§10/§15) - likely requires
  widening the eForms CPV extraction pattern in `src/utils/boamp_schema.py`
  beyond the current generic "8-digit code near a key containing 'cpv'"
  rule, e.g. targeting the eForms `cbc:ItemClassificationCode` structure
  directly once its exact shape is confirmed on more sample notices.
- Validate a sample of M0-linked pairs manually, focusing especially on the
  `NAME_FALLBACK`-keyed links given their higher share in this scope.
- Consider sentence-transformer embeddings for text similarity now that the
  corpus is far smaller (3,159 sources) - the original CPU-runtime
  objection is much weaker at this scale, though TF-IDF was kept here for
  continuity with Run 1's documented method.
- Feed `data/processed/boamp_survival_m0_balanced.csv` into a Cox /
  Kaplan-Meier survival model, following the guide's Phase 3 - the ~3-year
  median gap for linked pairs is a plausible, guide-consistent starting
  point for choosing a modeling horizon.
