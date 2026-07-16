# BOAMP M0 Data Retrieval and Preprocessing Report

**Current run:** Run 2, 2026-07-13 (outputs last regenerated 2026-07-15 via the
notebook front-ends; key datasets byte-identical to the audited script run).
**Scope:** a fresh, independent BOAMP retrieval/cleaning/linkage pipeline. No
previous repository, report, or event count was reused or compared against.

This document is the standalone data-retrieval and preprocessing report. The
master reference for the whole study — algorithm, diagnostics, survival
analysis, sensitivity checks — is `reports/boamp_m0_technical_report.pdf`;
the credibility audit companion is `reports/linkage_quality_evaluation.pdf`
(summarized in `reports/credibility_audit_report.md`). Execution history,
including the superseded Run 1 (national, all-sector, 2024–2026), is in
`reports/run_logs/run_log.md`; where a design choice below was inherited from
Run 1, that is noted with its original rationale restated so this document
reads on its own.

Every number in this report is reproduced in
[`reports/source_values_used.csv`](source_values_used.csv), traced to the
generated table/file it came from, and checked by
`reports/final_audit_m0_preprocessing.csv` (34/34 checks pass).

---

## 1. Data source

**DILA Opendatasoft Explore API v2.1, dataset `boamp`**, confirmed live at
`https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/`.

The DILA open-data XML archive
(`https://echanges.dila.gouv.fr/OPENDATA/BOAMP/`, yearly/monthly ZIP/XML
bundles) was inspected and confirmed as a viable fallback, but the
Opendatasoft API was preferred: it is queryable by date range and family,
returns structured JSON directly (no XML/ZIP handling), and was confirmed
responsive.

Retrieval uses the `.../exports/json` bulk endpoint (no 10,000-row offset
cap) with a `select=` field projection that drops the redundant `gestion`
metadata block while keeping the full `donnees` payload (CPV, SIRET,
duration, attribution detail).

## 2. Study scope: period, geography, themes

The scope follows the internship guide's §3.2.2 "Recommended Scope for the
Internship", which bundles three filters together:

- **Period: 2015-01-01 to 2026-07-13** (latest available). The guide's
  literal recommendation was 2015–2024 ("10 years… allowing at least one
  full renewal cycle to be observed for four-year contracts"); the end date
  was extended past 2024 to the latest available data for more
  follow-up/censoring time on recently launched contracts. The underlying
  corpus starts 2015-03-02, so January–February 2015 contribute no notices
  by construction, not by retrieval failure.
- **Geography: Pays de la Loire only** — buyer department in
  `{44 Loire-Atlantique, 49 Maine-et-Loire, 53 Mayenne, 72 Sarthe, 85 Vendée}`,
  applied **server-side** via `code_departement in ("44","49","53","72","85")`
  in the API `where` clause. The guide's "Grand Ouest extension" fallback was
  not applied — volume did not require it (§7). Note this is the
  notice/buyer department: the place-of-performance field
  (`code_departement_prestation`) is 100% null in the retrieved data and
  unusable.
- **Themes: digital/ICT contracts** — CPV divisions `{32 telecommunications
  equipment, 35 security, 48 software, 72 IT services}` and their
  subcategories, applied as a **hard filter** on the APPEL_OFFRE source
  population, with a keyword fallback for notices lacking a recoverable CPV
  code (§7).

**Why the geographic filter matters beyond narrowing scope**: the full
national archive (~1.69M notices, 2015–2026) is too large for a first
deterministic-linkage pass; the superseded Run 1 had solved this by
shrinking the *date range* (2024–2026, national) instead, which conflicted
with the guide's recommended scope. The geographic filter resolves the size
problem while keeping the full 11+-year window — confirmed live against the
API before committing to the download:

| Query | total_count |
|---|---|
| Jan 2024, national (no filter) | 8,728 |
| Jan 2024, Pays de la Loire filter | 531 (~6.1%) |
| **Full period 2015-01-01 to 2026-07-13, Pays de la Loire filter** | **84,623** |

**Actually retrieved**: 84,623 unique notices, 139 monthly files, 0
duplicates, 0 failed requests (`reports/tables/boamp_download_summary.csv`).
Raw files live under `data/raw/boamp/pdl/` and are never overwritten; Run 1's
national files were moved (not deleted) to
`data/raw/boamp_national_2024_2026_archive/` and are not part of the active
lineage.

## 3. Parsing and schema

`scripts/parse_boamp.py` flattens the raw JSON into
`data/interim/boamp_raw_flattened.csv` (84,623 rows × 42 columns) using an
adaptive recursive extractor (`src/utils/boamp_schema.py`) that handles both
schema families in one pass:

- **LEGACY** (BOAMP-XSD-derived JSON): 73,941 notices (87.4%) — all
  FNS/MAPA/DSP notices, and JOUE notices before the EU eForms mandate
  (~Oct 2023).
- **EFORMS** (EU eForms/UBL JSON): 10,682 notices (12.6%) — JOUE notices
  from late 2023 on.

The extractor is pattern-based (e.g. SIRET-shaped values under keys
matching known identifier names, 8-digit codes near keys containing `cpv`),
not schema-path-hardcoded — best-effort by design, with known limitations
(§10, §11 of the technical report).

Notice-type composition of the cleaned corpus: APPEL_OFFRE 58,292 (68.9%),
ATTRIBUTION 22,560 (26.7%), other (rectificatif, modification, …) 3,771
(4.5%). No rows are dropped during cleaning; deduplication happens at parse
time on `idweb`.

## 4. Cleaning rules

`notebooks/05_preprocess_boamp_m0.ipynb` (interactive front-end) /
`scripts/preprocess_boamp_m0.py` (batch backend — same logic, same outputs)
produce `data/processed/boamp_clean_m0_no_enrichment.csv` (84,623 × 93):

- **Notice ID**: `idweb`, unique, primary key.
- **Notice type**: `nature` normalized to APPEL_OFFRE / ATTRIBUTION / OTHER.
- **Dates**: `dateparution` parsed; range observed 2015-03-02 to 2026-07-13;
  `study_end_date` = max observed publication date (2026-07-13).
- **Text**: `objet` cleaned (`src/utils/text_clean.py`: boilerplate strip,
  whitespace/accent normalization) into `objet_clean`; 0% text missingness.
- **CPV**: 8-digit codes kept; hierarchy derived by left truncation
  (`cpv_division`/`cpv_group`/`cpv_class`/`cpv_category`); division-only
  codes (`XX000000`) flagged `cpv_generic_flag`.
- **Duration**: declared values kept when in [1, 120] months; otherwise
  imputed with the median *observed* duration in the same CPV division,
  falling back to a global observed median. Medians are computed **on the
  digital + Pays-de-la-Loire APPEL_OFFRE population only** (not the whole
  cleaned dataset), so imputed durations reflect in-scope contracts;
  `dur_was_imputed` records the decision.
- **Defense-in-depth**: an `is_in_pdl` diagnostic checks every cleaned
  notice's department against the Pays-de-la-Loire set to catch a stale
  pre-rescope raw file slipping in. Result: 0 notices flagged out of scope.

### 4.1 Preprocessing recipe in notation

Let \(r_i\) be one raw BOAMP notice after download, with top-level fields such
as `idweb`, `nature`, `dateparution`, `nomacheteur`, `objet`, and the nested
JSON field `donnees`. The preprocessing scripts construct one cleaned record
\(x_i\) per notice; no row is dropped during this cleaning step.

The implemented transformations are:

1. **Identifier and notice type**

   \[
   \texttt{notice\_id}_i=\texttt{idweb}_i
   \]

   \[
   \texttt{notice\_type}_i =
   \begin{cases}
   \texttt{APPEL\_OFFRE} & \text{if } \texttt{nature}_i \text{ is an offer notice}\\
   \texttt{ATTRIBUTION} & \text{if } \texttt{nature}_i \text{ is an award notice}\\
   \texttt{OTHER} & \text{otherwise.}
   \end{cases}
   \]

2. **Publication dates**

   \[
   p_i=\texttt{publication\_date}_i=\mathrm{parse}(\texttt{dateparution}_i),
   \qquad
   \texttt{study\_end\_date}=\max_i p_i.
   \]

3. **Buyer identity**

   SIRET/SIREN candidates are searched inside `donnees` by recursive
   key-pattern matching, then validated with local format checks. The buyer
   name is also normalized:

   \[
   \nu_i=\phi(\texttt{nomacheteur}_i),
   \]

   where \(\phi(\cdot)\) lowercases, removes accents, removes punctuation
   noise, and collapses whitespace. The final `buyer_key` rule is detailed in
   §6.

4. **Object text**

   \[
   o_i=\psi(\texttt{objet}_i),
   \]

   where \(\psi(\cdot)\) is the project text-cleaning function: BOAMP
   boilerplate and whitespace/accent noise are normalized while preserving the
   procurement subject used later for text similarity and keyword filtering.

5. **CPV code and hierarchy**

   From CPV candidates in `donnees`, the first valid 8-digit code is kept as
   \(c_i\). Its hierarchy is deterministic left truncation:

   \[
   \begin{aligned}
   \texttt{cpv\_division}_i &= \mathrm{prefix}_2(c_i),\\
   \texttt{cpv\_group}_i &= \mathrm{prefix}_3(c_i),\\
   \texttt{cpv\_class}_i &= \mathrm{prefix}_4(c_i),\\
   \texttt{cpv\_category}_i &= \mathrm{prefix}_5(c_i).
   \end{aligned}
   \]

   A code is flagged generic when it only identifies the broad division:

   \[
   \texttt{cpv\_generic\_flag}_i =
   \mathbf{1}\{c_i \text{ has pattern } \texttt{XX000000}\}.
   \]

6. **Digital/ICT source scope**

   A notice is in the digital scope when the CPV division is one of the target
   divisions or the cleaned object text contains a digital keyword:

   \[
   \texttt{digital}_i =
   \mathbf{1}\{\texttt{cpv\_division}_i \in \{32,35,48,72\}
   \ \lor\  o_i \text{ contains a digital keyword}\}.
   \]

   The M0 source population is therefore

   \[
   \mathcal{S} =
   \{i:\texttt{notice\_type}_i=\texttt{APPEL\_OFFRE},
   \texttt{digital}_i=1\}.
   \]

7. **Start date from linked ATTRIBUTION notices**

   If an `ATTRIBUTION` notice \(j\) back-references source \(i\) through
   `annonce_lie`, the earliest such award publication date is used; otherwise
   the source publication date is used:

   \[
   a_i =
   \begin{cases}
   \min_j p_j & \text{if } j \in \texttt{ATTRIBUTION}
   \text{ and } \texttt{annonce\_lie}_j \ni i\\
   p_i & \text{otherwise.}
   \end{cases}
   \]

8. **Duration and expected end date**

   Let \(d_i^{raw}\) be the declared duration recovered from `donnees`.

   \[
   d_i =
   \begin{cases}
   d_i^{raw} & \text{if } d_i^{raw}\in[1,120]\text{ months}\\
   \mathrm{median}\{d_k^{raw}: k\in\mathcal{S},
   \texttt{cpv\_division}_k=\texttt{cpv\_division}_i\} & \text{if available}\\
   \mathrm{median}\{d_k^{raw}: k\in\mathcal{S}\} & \text{otherwise.}
   \end{cases}
   \]

   The imputation decision is stored as `dur_was_imputed`, and the estimated
   contract end used for linkage is

   \[
   \widehat e_i=a_i+d_i\text{ months}.
   \]

## 5. No external SIREN/SIRET enrichment

No INSEE SIRENE API, no data.gouv.fr entreprise search, no external company
database anywhere in the pipeline. Only BOAMP-provided identifiers are used,
format-validated, and separately audited with the Luhn checksum
(`src/utils/identifiers.py`). Across all 84,623 notices, 27.2% carry a
format-valid raw SIRET, of which 99.6% also pass the checksum.

## 6. Buyer-key construction

For notice \(i\), let \(s_i^{(14)}\) be the first format-valid 14-digit SIRET
candidate recovered from BOAMP, let \(s_i^{(9)}\) be the first format-valid
9-digit SIREN candidate recovered from BOAMP, and let \(\nu_i\) be the
normalized buyer name. The implemented rule is:

\[
\texttt{buyer\_key}_i =
\begin{cases}
\texttt{SIRET:}s_i^{(14)} & \text{if a format-valid SIRET exists}\\
\texttt{SIREN:}s_i^{(9)} & \text{else, if a format-valid SIREN exists}\\
\texttt{NAME:}\nu_i & \text{else, if a normalized buyer name exists}\\
\varnothing & \text{otherwise.}
\end{cases}
\]

The companion key type records which branch fired:

\[
\texttt{buyer\_key\_type}_i \in
\{\texttt{RAW\_SIRET},\texttt{RAW\_SIREN},
\texttt{NAME\_FALLBACK},\texttt{MISSING}\}.
\]

SIRET and SIREN are validated from BOAMP-provided values only. When a valid
SIRET exists, the script also derives `buyer_siren_clean` from its first nine
digits for diagnostics, but the key remains `SIRET:...` because SIRET has
priority. Checksum validity is recorded separately; the key construction
requires format-valid identifiers and does not call an external registry.

Observed distribution across all 84,623 cleaned notices: **RAW_SIRET 23,038
(27.2%)**, **NAME_FALLBACK 61,585 (72.8%)**, RAW_SIREN 0, **MISSING 0**. The
NAME_FALLBACK share is higher than in the (superseded) national sample
(60.5%), plausibly because smaller regional/local buyers are less likely to
publish a recoverable SIRET than large national bodies. Name-fallback matching
is **exact** on the normalized name — no fuzzy matching is implemented
(`rapidfuzz` is installed but unused), so spelling variants of the same buyer
split into separate keys.

## 7. APPEL_OFFRE source population

Of 58,292 all-sector APPEL_OFFRE notices, the digital-scope hard filter
(CPV division in {32,35,48,72} **or** a digital keyword hit in the cleaned
object text — keywords such as *informatique, logiciel, numérique, cloud,
cybersécurité, progiciel, infogérance*, see `DIGITAL_KEYWORDS` in
`scripts/preprocess_boamp_m0.py`) keeps **3,159 sources**
(`data/processed/boamp_m0_sources.csv`) — within the guide's 2,000–5,000
target range. A stricter CPV-division-only definition gives 1,882 and is
reported as a sensitivity figure only: CPV coverage among APPEL_OFFRE
notices is well below 100%, so a CPV-only rule would silently drop genuine
digital notices that simply lack a recoverable code.

All 3,159 sources have a usable buyer key (0 MISSING): 713 (22.6%)
SIRET-keyed, 2,446 (77.4%) name-keyed, across 790 unique buyers (top buyer:
Nantes Métropole, 182 sources).

## 8. ATTRIBUTION use and start dates

22,560 ATTRIBUTION notices (all sectors) are used **only** for the
`annonce_lie` reverse-lookup that refines `start_date`: when an ATTRIBUTION
notice back-references a source APPEL_OFFRE, the award publication date
becomes the source's start date (1,207 of 3,159 sources, 38.2%,
`start_date_source = LINKED_ATTRIBUTION_DATE`); the remaining 61.8% fall
back to their own publication date. ATTRIBUTIONs are never M0 candidates
and are not sector-filtered (the reverse-lookup matches on
`annonce_lie → idweb` regardless of the ATTRIBUTION's own sector).
`estimated_end_date = start_date + declared_duration_months`.

## 9. CPV data quality

CPV coverage among the 3,159 digital-scope sources is **78.4%** (vs. 39.4%
in the superseded national all-sector sample — digital/IT procurement is
more often given an explicit CPV code). Generic (division-only) codes: 9.15%
of sources.

Coverage is **not stable over time**
(`reports/figures/04_cpv_coverage_by_year.png`): it rises from 74% (2015) to
92% (2022–2023), then drops sharply to 51% (2024), 51% (2025), 45% (2026).
The timing lines up with the EU eForms/UBL schema transition (~late 2023);
the working hypothesis is that the generic eForms CPV-extraction pattern
("8-digit code near a key containing `cpv`") is less reliable than the
legacy structure's direct `CPV.objetPrincipal.classPrincipale` path. This
has **not** been root-caused in the current run; recent-year CPV-dependent
figures should be read with the drop in mind.

## 10. Duration data quality

**Only 378 of 3,159 sources (12.0%) have a directly observed, in-range
declared duration; 88.0% required imputation.** Median observed duration:
**6.0 months** (n=378). Observed values cluster at 4 months (25.9%),
48 months (21.4%), 6 months (11.9%), 5 and 12 months (9.0% each).

The low completeness was checked for an extraction bug: observed-duration
rates by publication tier are FNS 12.2%, JOUE 13.3%, MAPA 5.6% —
consistently low across tiers and both schema families, i.e. a genuine
data-completeness characteristic of how digital/IT contracts are described
in BOAMP for this region, not a pipeline defect. This directly answers the
internship guide's Week-1 "scientific question" ("to what extent is the
'contract duration' variable reliable in BOAMP data?"): **not very, for this
population** — and since the 6-month median drives the temporal blocking
window (§11), that window inherits the same uncertainty.

## 11. M0 candidate generation

Candidates for source *i*: same `buyer_key`, later publication date, within
a temporal window around `estimated_end_date`:

`TEMPORAL_WINDOW_MONTHS = clip(round(0.5 × median observed duration), 6, 24)
= clip(3, 6, 24) = 6 months`

`MAX_CANDIDATES_PER_SOURCE = 30` (runtime cap; did not bind in this scope).

**Result:** 6,137 candidate pairs covering 1,236 of 3,159 sources (**39.1%
blocking coverage**); 1,923 sources have zero candidates (798 with no later
same-buyer digital notice at all, 1,125 whose later same-buyer notices all
fall outside the ±6-month window). Blocking, not scoring, is the binding
constraint on the event rate — see the technical report §Linking
Diagnostics.

## 12. M0 scoring

TF-IDF (unigrams+bigrams, `max_features=50000`, `min_df=2`) + cosine for
text; CPV hierarchy ladder (exact 1.0 / category 0.8 / class 0.6 / group
0.4 / division 0.2 / different 0.0 / missing 0.1); linear time-decay from
the estimated end date; buyer-key reliability (SIRET 1.0 / SIREN 0.85 /
name 0.60); composite:

`S = 0.35·s_text + 0.30·s_cpv + 0.25·s_time + 0.10·s_buyer`

Weights are documented fixed choices, not fitted. The observed composite
distribution (mean 0.250 over all pairs) was reviewed and the weights kept
rather than re-tuned — re-tuning against a single run's distribution
without a validation set would risk overfitting. Sentence-transformer
embeddings were evaluated and not adopted (CPU-impractical at the original
national scale; TF-IDF kept for continuity), though the current 3,159-source
corpus would now make them tractable — listed as a next step.

## 13. M0 link variants and headline results

Thresholds are the 25th/50th/75th percentiles of the rank-1 composite-score
distribution (n=1,236), so strict ⊂ balanced ⊂ broad:

| variant  | threshold | linked events | event rate | median gap |
|----------|-----------|----------------|------------|------------|
| broad    | 0.2642    | 927            | 29.3%      | 37.9 mo    |
| **balanced (reference)** | **0.3230** | **618** | **19.6%** | **37.7 mo** |
| strict   | 0.3931    | 309            | 9.8%       | 44.7 mo    |

**Median gap between linked pairs (balanced): ~37.7 months (~3.1 years)** —
consistent with the guide's framing of multi-year contracts renewed around
their expected end date, and in sharp contrast with the superseded national
all-sector run (~6.1 months), which was dominated by short MAPA/works
contracts. This is treated as an internal validation signal that the
re-scoping surfaced the intended renewal-cycle pattern.

Top buyer by linked events (balanced): `NAME:nantes metropole` (125 of 618
events, 20.2%) — a name-keyed buyer, so it carries the false-merge/
false-split risk of §14 even at the top of the ranking.

**These are proxy recurrence candidates, not verified legal renewals.**

## 14. Data limitations

- **Duration completeness is low** (88.0% imputed, n=378 observed); the
  6-month median is low-confidence and drives the ±6-month blocking window.
- **CPV coverage (78.4%) is incomplete and decays after 2023** (§9); 21.6%
  of sources score `s_cpv` at the neutral missing value 0.1.
- **SIRET extraction is best-effort and generic** — the recursive extractor
  can occasionally pick a non-buyer identifier from a notice listing several
  organizations.
- **NAME_FALLBACK buyer keys (72.8% of notices, 77.4% of sources)** carry
  false-merge/false-split risk; no fuzzy or registry-based reconciliation is
  implemented.
- **Candidate reuse**: 121 of 618 balanced-linked candidates (443 unique)
  are the top match for more than one source (max multiplicity 6) —
  flagged, not silently accepted; prevents naive one-to-one renewal
  interpretation.
- **Small strata**: 3,159 sources / 618 events; yearly and CPV-division
  breakdowns can rest on very few observations.
- **Geography is buyer department, not place of performance**
  (`code_departement_prestation` is 100% null).
- **No ground truth** for true renewals; M0 precision/recall are unknown
  (model-based estimates only — see the technical report §Reliability).

## 15. Workflow note

Preprocessing, feature engineering, and linkage run primarily in notebooks
`05`/`07`/`08` with results inline; the scripts
(`preprocess_boamp_m0.py`, `build_m0_candidate_pairs.py`,
`run_m0_linkage.py`) remain as a headless batch backend implementing the
same logic. The two implementations are currently **verified equivalent in
output** (byte-identical key datasets per
`reports/tables/audit_dataset_inventory.csv` SHA-256), but the logic exists
in two places — a maintenance risk documented, with suggested remedies, in
the technical report §Computational Workflow.

## 16. Next steps

- Manual validation of a stratified sample of M0 links (sample and guide
  exist: `reports/tables/manual_validation_sample_unlabeled.csv`,
  `reports/manual_validation_guide.md`) — the highest-priority next step.
- Root-cause the 2024–2026 CPV coverage drop (§9), likely by targeting the
  eForms `ItemClassificationCode` structure directly in
  `src/utils/boamp_schema.py`.
- Investigate duration-field completeness for digital contracts (§10) — is
  the missingness concentrated in specific CPV subcategories or procedure
  types?
- Consider sentence-transformer text similarity at the current corpus scale.
- If more recurrence signal is needed, apply the guide's "Grand Ouest
  extension" (Brittany/Normandy/Centre-Val de Loire) — current volume did
  not require it.
- Feed the survival handoff into the Phase-3 modeling — **done**: see the
  technical report §Survival Results and `notebooks/16_survival_robustness.ipynb`.
