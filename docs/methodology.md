# Methodology — two-layer BOAMP renewal linkage and survival analysis

*This document describes the redesigned pipeline (branch `restructure/two-layer`).
Layer 1 = `boamp_only` (formerly M0); Layer 2 = `enriched` (formerly M1).*

## 1. Problem and data

**Scientific objective.** Estimate the time from a public call for tender
(APPEL_OFFRE notice) to its *renewal* — the next comparable tender by the same
buyer — and measure how buyer-identity enrichment changes that estimate.

**Data.** BOAMP notices (DILA Opendatasoft API), Pays de la Loire buyers
(departments 44/49/53/72/85), 2015-01 → 2026-07: 84,623 unique notices after
cleaning. Digital/ICT scope: CPV division ∈ {32, 35, 48, 72} OR one of ~18
French digital keywords in the cleaned contract object → **3,159 eligible source
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
population (global median fallback). **88% of sources are imputed** — the
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
Coverage: SIREN known for 1,928/3,159 sources (61%) — mostly via the alias
bridge (919) and native SIRET (686), only 296 via the direct external join.

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
0.2642 / **0.3230** / 0.3931 (broad/balanced/strict) — then **frozen in config
and shared by both layers** so the layer comparison is not confounded by
threshold re-derivation; the pipeline re-derives them at every run and fails if
they drift beyond ±0.002.

**Three-way classification** (matches / potential matches / non-matches):
linked pairs with margin $m_i <$ 0.05 are tiered **POTENTIAL** — kept in the
linked set but flagged; 235 of Layer 1's 618 balanced links (38%) and 328 of
Layer 2's 847 (39%) are POTENTIAL, and robustness of survival conclusions to
their exclusion is part of the analysis. Remaining links are HIGH
($S \ge 0.50$) or MEDIUM.

## 6. Event and censoring

$\delta_i = 1$ with $T_i = t_{j^*} - t_i$ (months) if source $i$'s rank-1
candidate $j^*$ clears the balanced threshold; otherwise $\delta_i = 0$ with
$T_i = (\text{study end} - t_i)/30.44$, study end = max publication date
observed (2026-07-13). One row per eligible source, both layers: 3,159 rows;
618 events (19.6%) in Layer 1, 847 (26.8%) in Layer 2.

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
~80%/73% — so RMST at 60 months is the summary statistic), log-rank between
layers and across CPV divisions, Cox PH (penalizer 0.01, robust SEs clustered
on the layer's buyer key; covariates log1p duration, imputation flag, CPV
dummies, key-type dummies; PH tests; quadratic-duration functional-form check),
Weibull vs log-normal AFT (AIC + concordance), 12/24-month risk calibration,
and temporal validation (train ≤ 2021, test > 2021).

## 9. Known limitations

1. The renewal event is an unverified proxy; all downstream inference is
   conditional on linkage quality.
2. 88% duration imputation propagates into blocking, scoring, and covariates.
3. Composite weights are unfitted; thresholds are percentile conventions.
4. External enrichment covers 2024–2026 only; historical gains rest on the
   alias bridge's exactness assumptions (name+department uniqueness).
5. Buyer merges by SIREN can conflate establishments that tender independently
   (flagged as `cross_establishment_same_siren`, not resolved).
6. Zero-candidate sources (1,923/3,159) are structurally censored — blocking
   recall is the binding constraint in both layers.
7. No completed manual validation labels yet.
