# Methodology — two-layer BOAMP renewal linkage and survival analysis

*This document describes the current two-layer pipeline. Layer 1 =
`boamp_only` (formerly M0); Layer 2 = `enriched` (formerly M1).*

## 1. Problem and data

**Scientific objective.** Estimate the time from a public call for tender
(APPEL_OFFRE notice) to its *renewal* — the next comparable tender by the same
buyer — and measure how buyer-identity enrichment changes that estimate.

**Data.** BOAMP notices (DILA Opendatasoft API), Pays de la Loire buyers
(departments 44/49/53/72/85), 2015-01 → 2026-07: 84,623 unique notices after
cleaning. Digital/ICT scope: CPV division ∈ {32, 35, 48, 72} OR one of ~18
French digital keywords in the cleaned contract object → **3,380 eligible source
contracts**. There is no verified legal-renewal field anywhere in BOAMP: the
event is a *proxy* constructed by record linkage, and its quality is evaluated,
not assumed.

## 2. Notation

For an eligible source contract $i$ and a candidate later notice $j$ from the
same buyer block:

| Symbol | Meaning |
|---|---|
| $t_i, t_j$ | publication dates |
| $d_i$ | declared duration in months (observed 12%, otherwise imputed) |
| $e_i$ | estimated end date $= \text{start}_i + d_i$ |
| $W$ | temporal window (months) |
| $o_i$ | cleaned contract-object text |
| $s_{text}, s_{cpv}, s_{time}, s_{buyer}$ | component scores $\in [0,1]$ |
| $S_{ij}$ | composite score |
| $m_i$ | best-minus-second-best margin $S_{i,(1)} - S_{i,(2)}$ |
| $\delta_i$ | event indicator |
| $T_i$ | time to event or censoring (months, 30.44 days/month) |

Start date: the earliest ATTRIBUTION notice referencing $i$ via `annonce_lie`
(BOAMP-native linkage), else the publication date.

Duration: cleaned to 1–120 months; missing values imputed with the median
observed duration of the same CPV division within the in-scope APPEL_OFFRE
population (global median fallback). **83% of sources are imputed** — the
highest-leverage assumption in the pipeline, stress-tested in `03_analysis`.

## 3. Buyer identity — the only controlled difference

**Layer 1 (`boamp_only`).** `buyer_key` from BOAMP-native fields only:
`SIRET:x` if a format+Luhn-valid SIRET exists, else `SIREN:x` (given or derived
from SIRET), else `NAME:normalized name`. 27% of notices are SIRET-keyed; 73%
fall back to names, which fragments buyers across spelling variants.

**Layer 2 (`enriched`).** Same population, identity upgraded by:
1. an **offline exact join** (one-to-one on `idweb`) to the pinned Hugging Face
   dataset `Data-Gouv-ML/jointure-boamp-siren-cote-acheteurs-2024-2025-et-2026`
   (SHA `4bff9b1c…`; covers 2024–2026 only — 18,098 of 84,623 notices join);
2. an **alias bridge**: exact (normalized name, department) groups among
   direct-enriched rows propagate a SIREN to pre-2023 notices with no native
   identifier, only when the group maps to exactly one SIREN, is conflict-free,
   non-generic (stoplist: mairie, commune, …) and has support ≥ 2.

No fuzzy matching is used. Conflicts (native SIRET-derived SIREN ≠ enriched
SIREN) are flagged, never overwritten; unresolved identities remain transparent
(`NAME_FALLBACK`, `CONFLICT_UNRESOLVED`). Every row carries provenance
(`buyer_identity_source`) and a confidence grade (HIGH … LOW / CONFLICT).
Coverage: SIREN known for 2,147/3,380 sources (64%) — mostly via the alias
bridge (919), native BOAMP SIRET (826), and direct enrichment joins (354), with
48 native/enriched conflicts flagged rather than overwritten.

## 4. Candidate generation (indexing/blocking)

Shared by both layers: candidate published strictly after the source, within
$\pm W$ of $e_i$, at most 30 temporally-nearest candidates per source.
$W = \mathrm{clip}(\mathrm{round}(0.5 \cdot \mathrm{median\ observed\ duration}), 6, 24)$;
with the current corpus (median 6 months) this **collapses to the 6-month
floor** — the derivation is retained and asserted so future data can move it.

Blocking identity: Layer 1 blocks on `buyer_key`. Layer 2 blocks on four
reconciliation mechanisms in priority order — exact SIRET, same validated
SIREN, historical alias, Layer 1 name fallback.

## 5. Comparison and classification

Component scores (identical in both layers):

- $s_{text}$: cosine similarity of TF-IDF vectors (50k features, 1–2-grams,
  min_df 2) of the cleaned objects — sentence-transformers were evaluated and
  rejected for CPU-only runtime;
- $s_{cpv}$: hierarchy ladder — exact 1.0 / category 0.8 / class 0.6 /
  group 0.4 / division 0.2 / different 0.0; **missing 0.1** (absence of
  information is weak-neutral evidence, not proof of mismatch);
- $s_{time} = \max(0, 1 - |t_j - e_i| / W)$;
- $s_{buyer}$: reliability of the blocking identity — Layer 1: SIRET 1.0 /
  SIREN 0.85 / name 0.6; Layer 2 by mechanism: 1.0 / 0.9 / 0.75 / 0.6.

Composite: $S_{ij} = 0.35\,s_{text} + 0.30\,s_{cpv} + 0.25\,s_{time} + 0.10\,s_{buyer}$.
The weights are **fixed a priori, not fitted** — no defensible labeled data
exists to fit them; their influence is quantified by ablation (dropping any one
component and re-linking changes the balanced link set with Jaccard 0.5–0.8)
and threshold/window sensitivity in `03_analysis`.

**Decision.** Only the rank-1 candidate can be linked. Thresholds were derived
once from the Layer 1 rank-1 score distribution — p25/p50/p75 =
0.278387 / **0.343167** / 0.442070 (broad/balanced/strict) — then **frozen in config
and shared by both layers** so the layer comparison is not confounded by
threshold re-derivation; the pipeline re-derives them at every run and fails if
they drift beyond ±0.002.

**Three-way classification** (matches / potential matches / non-matches):
linked pairs with margin $m_i <$ 0.05 are tiered **POTENTIAL** — kept in the
linked set but flagged; 327 of Layer 1's 1,003 balanced links (33%) and 430 of
Layer 2's 1,188 (36%) are POTENTIAL, and robustness of survival conclusions to
their exclusion is part of the analysis. Remaining links are HIGH
($S \ge 0.50$) or MEDIUM.

## 6. Event and censoring

$\delta_i = 1$ with $T_i = t_{j^*} - t_i$ (months) if source $i$'s rank-1
candidate $j^*$ clears the balanced threshold; otherwise $\delta_i = 0$ with
$T_i = (\text{study end} - t_i)/30.44$, study end = max publication date
observed (2026-07-13). One row per eligible source, both layers: 3,380 rows;
1,003 events (29.7%) in Layer 1, 1,188 (35.1%) in Layer 2.

## 7. Evaluation (deliberately not a feedback loop)

The classical record-linkage evaluation→comparison feedback loop is left
**open**: tuning weights or thresholds on links selected by the same score is
circular. Instead `03_analysis` reports, with explicit evidence classes:

- Fellegi–Sunter Beta-mixture EM over all blocked pairs (model-based
  precision̂/recall̂ — *not ground truth*; recall conditional on blocking);
- corruption/recovery on strict links (synthetic; R(0)=1 sanity-gated);
- threshold, window (6/9/12/18 m), and weight-ablation sensitivity;
- duration-leakage counterfactuals (no-temporal rescoring; forward-24m
  generation without duration) — the **log-duration hazard ratio reverses**
  under the forward specification, so the duration covariate must not be
  interpreted causally;
- enrichment-specific diagnostics: native-vs-external SIREN agreement,
  confidence tiers, added-link quality (added links have markedly weaker text
  similarity), cross-establishment flags;
- manual-validation samples exist but carry **zero completed labels** — no
  human-verified precision claim is made anywhere.

## 8. Survival analysis

Per layer: Kaplan–Meier with CIs (median survival not reached — censoring
70.3%/64.9% — so RMST at 60 months is the summary statistic), log-rank between
layers and across CPV divisions, Cox PH (penalizer 0.01, robust SEs clustered
on the layer's buyer key; covariates log1p duration, imputation flag, CPV
dummies, key-type dummies; PH tests; quadratic-duration functional-form check),
Weibull vs log-normal AFT (AIC + concordance), 12/24-month risk calibration,
and temporal validation (train ≤ 2021, test > 2021).

## 8b. Synthetic benchmark (v0.3, controlled calibration benchmark)

> The full specification — calibration, the data-generating process with its
> implemented distributions, the validation methodology, the comparison with
> real BOAMP, and the current readiness decision — is
> `reports/synthetic_benchmark_technical_report.tex` and its compiled PDF.
> Every statistic there is generated from the artifacts, so it does not go
> stale the way a hand-written summary does. This section is the short version.


We adapt the gold-standard-and-corruption framework of Lam et al. (2024,
*Generating synthetic identifiers to support development and evaluation of
data linkage methods*, IJPDS 9:1:18) to public-procurement recurrence
linkage. A clean latent procurement population containing buyers,
establishments, procurement needs, contract cycles and known recurrence
relations is generated first (`src/boamp/synthetic/buyers.py`,
`establishments.py`, `needs.py`, `cycles.py`, `relations.py`). BOAMP-like
publication notices are then produced (`notices.py`, `text_generation.py`)
and subjected to schema-dependent, attribute-dependent and co-occurring
corruption in identifiers, names, CPV, duration, text and lifecycle
references (`missingness.py`, `corruption.py`). Multiple corrupted linkage
files can be generated (`n_corruption_replications` in
`config/synthetic/benchmark_defaults_v0_1.yaml`) while retaining separate
known-truth tables (`true_relations.parquet`, latent entities, family
membership, and corruption history) that linkage algorithms never receive.

**Clean world vs observed world.** Every `*_true` column lives only in the
latent tables and `clean_notices.parquet`; `observed_notices.parquet` is
structurally verified to carry no truth column
(`schemas.assert_no_truth_leakage`, `tests/test_synthetic_schemas.py`).

**Recurrence ontology.** The real corpus's calibration work independently
built a full 8-relation ontology (`config/synthetic/recurrence_ontology.yaml`:
NEXT_CYCLE, PARTIAL_RECURRENCE, SPLIT, MERGE, SAME_THEME_DIFFERENT_NEED,
UNRELATED, NO_SUCCESSOR, UNCERTAIN). The current generator is deliberately
restricted to two relations only (`recurrence_ontology_v0_1.yaml`:
NEXT_CYCLE, NO_SUCCESSOR) — every cycle has exactly one outgoing edge,
verified structurally. The broader ontology remains defined and tested for
a future generator version.

**Parameter provenance.** Every generator input is classified into one of
four actions in `reports/tables/synthetic_calibration/generator_parameter_actions.csv`:
`USE_DIRECTLY` (OBSERVABLE/EMPIRICAL, consumed as-is — 55 parameters),
`USE_AS_FIDELITY_TARGET` (algorithm-conditioned or structural-comparison
values the generator should reproduce but never assign directly, e.g.
candidate counts, buyer Gini, text-similarity distributions — 9 parameters),
`SCENARIO_PARAMETER` (unidentified quantities like true recurrence
prevalence, swept across scenarios, never calibrated to a point — 7
parameters), and `DO_NOT_USE` (algorithm-conditioned pipeline internals —
frozen thresholds, score weights, the 6-month temporal window, the
30-candidate cap — which must not define synthetic-world truth even though
several are `ready_to_freeze=True` for *replicating the linker's own
scoring* — 9 parameters). Precision and recall are never generator inputs
under any action.

**Scenario assumptions.** Seven scenarios are configured
(`config/synthetic/scenarios/`: `clean_sanity`, `central_provisional`,
`adverse_identity`, `easier`, `moderate`, `difficult`, `stress`), which
operationalize the pre-existing, more detailed WP13 scenario family
(`01_clean_sanity.yaml` .. `06_adverse_combined.yaml`) into concrete numeric
knobs. All but `adverse_identity` have generated artifacts;
`registries/scenario_manifest.csv` records which are `CONFIG_ONLY` so a
loadable scenario is never mistaken for multi-seed evidence. `central_provisional` uses calibrated BOAMP observation mechanisms
wherever an empirical anchor exists (identifier/CPV/duration/name
missingness rates) and explicit, labeled scenario assumptions everywhere
else (recurrence prevalence, cycle-gap distribution, text drift severity) —
never a claim about true BOAMP recurrence.

**Dependent corruption.** Rather than sampling each field's corruption
independently, every notice draws one latent record-quality class
(HIGH/MEDIUM/LOW, correlated with its buyer's `identifier_quality_propensity`,
`missingness.py::assign_quality_class`) whose severity multiplier scales
every field's corruption rate at once, so identifier loss, CPV degradation,
duration missingness and text weakness co-occur on the same notices —
matching Lam et al.'s core corruption-design principle.

**Truth-table isolation.** `true_relations.parquet` and every `*_true`
column are structurally excluded from `observed_notices.parquet`; the leakage
gate also rejects unsuffixed hidden-entity aliases, exact or normalised
truth-ID values, and direct MD5/SHA1/SHA256 hashes of hidden truth IDs. Phase
12 compatibility checks (`boamp.synthetic.compatibility`) run the *existing*
Layer 1 candidate-generation code on synthetic `observed_notices` without ever
consulting synthetic truth.

**Fidelity and benchmark validation.** The active version is
`v0_3_temporal_candidate_revision`. It compares synthetic observed notices
against real-corpus calibration tables on schema/notice type, calendar shape,
buyer activity, identifiers, CPV, duration, text, missingness co-occurrence,
names, privacy/memorisation, and the production Layer-1 candidate environment.
Hidden-truth diagnostics additionally measure blocking completeness,
hard-negative overlap, true-match rank, and frozen probe-linker utility. The
validation framework reports `PASS_WITH_WARNINGS`, with no
blocking gates under its current gate policy; the internal-integrity,
specification-recovery,
candidate-environment, conditional-fidelity, privacy, and algorithm-utility
gates pass, while observable-fidelity warnings remain visible in the
discrepancy register; the current regenerated run has 2 metric-level failures
in noncritical SIRET missing/present rates. This framework status is deliberately narrower than
benchmark readiness. `scripts/assess_synthetic_benchmark_readiness.py` now
reports the required five-level decision: the pipeline is technically valid and
usable for preliminary synthetic-only modeling with limitations, but it is not
ready for controlled synthetic algorithm comparison, final algorithm ranking, or
validated synthetic benchmark release.

Blocking and scoring are reported separately. `PRODUCTION_BLOCKING` measures
candidate recall before scoring; `ORACLE_CANDIDATE_SCORING` inserts hidden true
successors into the production-distractor environment to evaluate ranking when
truth is reachable; and `END_TO_END` reports probe-linker recall after both
blocking and scoring, with the explicit identity
`R_end_to_end = R_blocking * R_scoring_given_reachable`.

Scenario coverage is now split into executable configuration coverage and
generated-artifact coverage. The required `easier`, `moderate`, `difficult`,
and `stress` scenarios are loadable generator configurations and have 10
generated seeds each. The central scenario also has 10 generated seeds, while
`clean_sanity` remains a single-seed smoke test. Final algorithm-ranking
readiness still fails because cross-scenario headline difficulty and
probe-linker rankings remain scenario-specific; observable warning-level gaps
and the 2 noncritical SIRET failures remain. Replicate-level probe
results are written to `probe_replicate_results.csv`, and rank intervals, mean
F1, and rank-1 frequencies are written to `probe_ranking_stability.csv`.

Specification recovery includes a Monte Carlo check that the realized true gaps
match the declared recurrence mixture. It censors each simulated draw at
`observation_end - source_expected_end`, matching the rule the generator uses
to stop a chain; measuring that window from the cycle start instead overstates
the headroom by a full cycle duration and biases the interval. The metric
carries no status softening, and a negative control asserts it still fails on an
injected gap shift while hard-negative chain alignment is enabled.

**Reproducibility.**
```bash
PYTHONPATH=src python3 scripts/generate_synthetic_benchmark_v0_3_temporal_candidate_revision.py
PYTHONPATH=src python3 scripts/generate_synthetic_benchmark_replicates.py \
  --scenarios easier,moderate,difficult,stress \
  --world-seeds 20260721,20260731,20260741,20260751,20260761,20260771,20260781,20260791,20260801,20260811 \
  --force \
  --manifest reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/required_scenario_10_seed_generation_manifest.json
PYTHONPATH=src python3 scripts/generate_synthetic_benchmark_replicates.py \
  --scenarios central_provisional \
  --world-seeds 20260721,20260731,20260741,20260751,20260761,20260771,20260781,20260791,20260801,20260811 \
  --force \
  --manifest reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/central_10_seed_generation_manifest.json
PYTHONPATH=src python3 scripts/validate_synthetic_benchmark.py
PYTHONPATH=src python3 scripts/replay_synthetic_benchmark.py \
  --output reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/replay_comparison.json
PYTHONPATH=src python3 scripts/replay_synthetic_benchmark_replicates.py \
  --output reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/replay_replicates.json
PYTHONPATH=src python3 scripts/build_source_state_manifest.py
PYTHONPATH=src python3 scripts/build_benchmark_registries.py
PYTHONPATH=src python3 scripts/build_mechanism_tradeoff_log.py
PYTHONPATH=src python3 scripts/assess_synthetic_benchmark_readiness.py
PYTHONPATH=scripts python3 scripts/build_dirty_state_overlay_archive.py
PYTHONPATH=scripts python3 scripts/verify_dirty_state_overlay_archive.py
PYTHONPATH=src python3 -m pytest -q tests/test_synthetic_*.py
```
The current all-artifact replay result is `PASS` for 51 generated artifacts
across central, sanity, easier, moderate, difficult, and stress scenarios. The
current readiness assessment is the source of truth for whether generated
artifacts, source-state hashes, and release packaging identify the current
repository state. In the latest checked state, generated artifact metadata
records commit `436c9bdec8446043cab317531ad6f9bd34901cef`, while the clean
repository HEAD is `8f1ea054a3f36ac385990b62819d33da57669d6a`; this does not
replace the release requirement for a refreshed clean commit or standalone
release package.

**Current limitations.** No manually-validated CPV/technological taxonomy
exists in this repo, so needs use broad CPV-division-derived segments as a
placeholder. Duration-value and long-horizon recurrence timing remain partly
scenario-controlled. The synthetic buyer-activity tail, department mix, text
duplication/lexical distribution, and some identifier missingness rates still
differ from the real corpus. Those discrepancies are not tuned away; they are
kept as warnings and should be reflected in algorithm-calibration claims.
An attempted split of family-level identifier persistence by notice type
reduced one attribution-specific mismatch but produced a critical conditional
text failure and degraded widened blocking reachability in the tested central
run, so the current generator retains family/need-level identifier persistence
as an explicit reachability-vs-conditional-fidelity trade-off.
`mechanism_tradeoff_log.csv` and `mechanism_tradeoff_log.json` record this as a
machine-readable rejected-local-audit decision rather than as an accepted
benchmark artifact.

## 9. Known limitations

1. The renewal event is an unverified proxy; all downstream inference is
   conditional on linkage quality.
2. 83% duration imputation propagates into blocking, scoring, and covariates.
3. Composite weights are unfitted; thresholds are percentile conventions.
4. External enrichment covers 2024–2026 only; historical gains rest on the
   alias bridge's exactness assumptions (name+department uniqueness).
5. Buyer merges by SIREN can conflate establishments that tender independently
   (flagged as `cross_establishment_same_siren`, not resolved).
6. Zero-candidate sources remain structurally censored: 1,375/3,380 in Layer 1
   and 1,215/3,380 in Layer 2 have no generated candidate — blocking recall is
   the binding constraint in both layers.
7. No completed manual validation labels yet.
