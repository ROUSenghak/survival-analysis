# Layer comparison report — boamp_only vs enriched

*Generated from the 2026-07-27 end-to-end rerun. Every number below is traceable
to `data/processed/comparison/*`, `data/processed/{boamp_only,enriched}/*`, and
`reports/tables/*`.*

## 1. Setup

Both layers share the identical source population: 3,380 eligible digital-scope
APPEL_OFFRE contracts. They also share the 6-month temporal window, TF-IDF text
model, CPV ladder, composite weights (0.35/0.30/0.25/0.10), and the refreshed
balanced threshold (0.343167, derived from Layer 1 rank-1 percentiles). The
single controlled difference is buyer identity.

## 2. Identity coverage

| Quantity | Layer 1 | Layer 2 | Source table |
|---|---:|---:|---|
| Unique buyer keys | 819 | 808 | `layer_comparison_summary.csv` |
| SIREN known in source scope | native BOAMP only | 2,147 / 3,380 (64%) | `enriched_sources.csv` |
| Identity source (L2) | - | 1,233 name-fallback / 919 alias / 826 BOAMP SIRET / 354 direct join / 48 conflict-flagged | `enriched_sources.csv` |
| External join coverage | - | 18,098 / 84,623 notices (2024-2026 only) | NB01 Part E |

## 3. Candidate generation

| Quantity | Layer 1 | Layer 2 |
|---|---:|---:|
| Candidate pairs | 10,862 | 13,524 |
| Sources with >=1 candidate | 2,005 (59.3%) | 2,165 (64.1%) |
| Zero-candidate sources | 1,375 | 1,215 |

Blocking remains the binding constraint in both layers: 40.7% of Layer-1
sources and 35.9% of Layer-2 sources never see a candidate and are structurally
censored.

## 4. Linkage outcomes

| Quantity | Layer 1 | Layer 2 |
|---|---:|---:|
| Accepted links / rate | 1,003 / 29.7% | 1,188 / 35.1% |
| Confidence tiers HIGH/MEDIUM/POTENTIAL | 320 / 356 / 327 | 360 / 398 / 430 |
| POTENTIAL share (margin < 0.05) | 33% | 36% |

Source-view decomposition from `layer_link_comparison.csv`: 962 sources link to
the same candidate in both layers, 189 are added by enrichment, 37 change
candidate, and 4 are removed by enrichment.

Added-link quality from `enrichment_added_links_quality.csv`: median text
similarity is 0.087 for links added by enrichment versus 0.209 for links shared
with Layer 1. Enrichment plausibly recovers buyer-identity blocking failures,
but the recovered links rest less on text evidence.

## 5. Quality risks specific to enrichment

- Cross-establishment same-SIREN matches are flagged, not resolved.
- 48 source rows carry native-vs-enriched SIREN conflicts; conflicts are never
  overwritten.
- Generic or ambiguous aliases are excluded from propagation.
- The external file covers 2024-2026 only; historical identity gains rest on the
  exact name+department alias bridge.

## 6. Downstream survival effects

| Quantity | Layer 1 | Layer 2 |
|---|---:|---:|
| Events / censoring | 1,003 / 70.3% | 1,188 / 64.9% |
| S(12m) | 0.7209 | 0.6786 |
| S(24m) | 0.6908 | 0.6332 |
| RMST(60m) | 43.51 mo | 40.57 mo |
| Median survival | not reached | not reached |
| Cox log-duration HR | 0.3173 | 0.3258 |
| Log-normal AFT C-index | 0.6231 | 0.6203 |
| Log-rank L1 vs L2 | p = 4.52e-06 | |

## 7. Verdict

More links is not automatically better. Layer 2 is a sensitivity layer that
quantifies how much buyer-identity fragmentation changes the candidate universe
and survival handoff. Layer 1 remains the primary specification because it is
BOAMP-native. Promoting Layer 2 would require completed manual validation or
another external truth source for the enrichment-added links.

## 8. Reproduction

```bash
jupyter nbconvert --to notebook --execute --inplace notebooks/01_data_engineering_pipeline.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/02_eda.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/03_analysis.ipynb
```
