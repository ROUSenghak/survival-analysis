# Layer comparison report — boamp_only vs enriched

*Generated from the 2026-07-17 end-to-end rerun. Every number below is traceable
to a generated table: `data/processed/comparison/*`, `reports/tables/*` (new
naming), and the executed notebooks 01/03.*

## 1. Setup

Both layers share the identical source population (3,159 eligible digital-scope
APPEL_OFFRE contracts, verified column-by-column by `assert_layer_parity`), the
same temporal window (6 months), TF-IDF text model, CPV ladder, composite
weights (0.35/0.30/0.25/0.10), and the same frozen balanced threshold
(0.3230, derived once from Layer 1 rank-1 percentiles). The single controlled
difference is buyer identity.

## 2. Identity coverage

| Quantity | Layer 1 | Layer 2 | Source table |
|---|---|---|---|
| Unique buyer keys | 1,872* | fewer (merges) | `layer_comparison_summary.csv` |
| SIREN known | 1,404 (native effective) | **1,928 (61%)** | `enriched_sources.csv` |
| Identity source (L2) | — | 1,231 name-fallback / 919 alias / 686 SIRET / 296 direct join / 27 conflict-flagged | `enriched_identity_source_summary.csv` |
| External join coverage | — | 18,098 / 84,623 notices (2024–2026 only) | NB01 Part E |

*see `layer_comparison_summary.csv` for the exact key counts; enrichment merges
name-fragmented buyers into SIREN keys and never splits a native SIRET key.

## 3. Candidate generation

| Quantity | Layer 1 | Layer 2 |
|---|---|---|
| Candidate pairs | 6,137 | 8,228 |
| Sources with ≥1 candidate | 1,236 (39.1%) | 1,504 (47.6%) |
| Zero-candidate sources | 1,923 | 1,655 |

Blocking recall remains the binding constraint in both layers: even enriched,
52% of sources never see a candidate and are structurally censored.

## 4. Linkage outcomes (balanced threshold)

| Quantity | Layer 1 | Layer 2 |
|---|---|---|
| Accepted links / rate | 618 / 19.6% | 847 / 26.8% |
| Confidence tiers HIGH/MEDIUM/POTENTIAL | 120 / 263 / 235 | 159 / 360 / 328 |
| POTENTIAL share (margin < 0.05) | 38% | 39% |

**Source-view decomposition** (`layer_link_comparison.csv`): 617 sources linked
in both layers (574 to the same candidate, **43 to a different candidate**),
**230 added** by enrichment, **1 removed**. The pair-view Jaccard is 0.644; the
source-view Jaccard is 0.728 — the earlier "−44 removed" figure counted
re-linked sources as losses.

**Added-link quality** (`layer_changed_links.csv`, 03 §1.7): 170 historical-alias
+ 60 same-SIREN. Median text similarity **0.070 vs 0.169** for Layer 1 links;
median composite score correspondingly lower. Enrichment plausibly recovers
blocking failures (fragmented buyer names), but the recovered links rest more on
temporal+buyer agreement and less on content evidence.

## 5. Quality risks specific to enrichment

- Cross-establishment merges (same SIREN, different SIRETs) are flagged
  (`cross_establishment_same_siren`), not resolved: procurement may genuinely be
  run at establishment level.
- 27 sources carry a native-vs-external SIREN **conflict** (flagged, never
  overwritten; see `enrichment_conflicts.csv`).
- Generic names (mairie, commune, …) and ambiguous multi-SIREN aliases are
  excluded from propagation (79 + 48 alias groups held for review;
  `alias_bridge_ambiguous.csv`).
- The external file covers 2024–2026 only; all pre-2023 identity gains rest on
  the alias bridge's exact name+department uniqueness assumption.

## 6. Downstream survival effects

From `survival_layer_conclusions_comparison.csv` and
`survival_logrank_tests.csv`:

| Quantity | Layer 1 | Layer 2 |
|---|---|---|
| Events / censoring | 618 / 80.4% | 847 / 73.2% |
| S(24m) | 0.914 | 0.897 |
| RMST(60m) | 53.5 mo | 51.7 mo |
| Median survival | not reached | not reached |
| Cox log-duration HR (full model) | 0.923 | 0.995 |
| Log-normal AFT C-index | 0.725 | 0.677 |
| Log-rank L1 vs L2 | p = 1.7×10⁻¹¹ (curves differ) | |

## 7. Verdict — is the enriched layer "better"?

**More links is not better by itself.** The evidence:

- *For enrichment*: it repairs a real, demonstrated defect (buyer-name
  fragmentation), raises blocking coverage by 8.5 points, and its direct joins
  agree strongly with native SIRET-derived SIRENs where both exist
  (`enrichment_agreement_by_dimension.csv`).
- *Against treating it as primary*: the 230 added links carry systematically
  weaker text evidence; model discrimination degrades (C 0.725 → 0.677); the
  survival curve shifts significantly downward — which is exactly what adding
  a block of lower-precision events would also do; and none of the added links
  has a completed manual label.

**Recommendation (unchanged from v1, now with sharper evidence):** Layer 1
remains the primary specification; Layer 2 is the sensitivity layer that bounds
how much buyer-identity fragmentation is costing. Promoting Layer 2 requires a
completed manual-validation round over the 230 added links (the sample
machinery exists; zero labels have ever been recorded).

## 8. Reproduction

```
notebooks/01_data_engineering_pipeline.ipynb   (Parts A–H; writes all inputs of this report)
notebooks/03_analysis.ipynb                    (quality + survival tables)
pytest -m slow                                 (parity gate vs frozen fingerprints)
```
