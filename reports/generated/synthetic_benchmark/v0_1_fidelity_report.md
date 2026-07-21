# Synthetic benchmark v0.1 — fidelity report

Generated from `notebooks/06_synthetic_fidelity_validation.ipynb`, comparing
the `central_provisional` pilot (`data/processed/synthetic_benchmark/v0_1_provisional/central_provisional/world_001/corruption_001/`,
2,000 buyers, 9,534 observed notices) against the real corpus's
OBSERVABLE-tier calibration tables (`reports/tables/synthetic_calibration/`).
Full numeric table: `reports/tables/synthetic_benchmark/v0_1/v0_1_fidelity_summary.csv`.
Figures: `reports/figures/synthetic_benchmark/v0_1/`.

This is a **first-pass** fidelity check for a provisional pilot, not a
tuned-to-convergence calibration. One adaptive-calibration correction was
applied during this build (buyer-activity Gini, §3 below); every other
discrepancy below is reported honestly and left as v0.2 follow-up work
rather than iteratively re-tuned in this session (spec: "The immediate
success criterion is... not a final perfect simulator").

## 1. Good fidelity (within a reasonable band of the real corpus)

| Dimension | Real | Synthetic | Read |
|---|---|---|---|
| `notice_type_mix` | APPEL_OFFRE 68.9% / ATTRIBUTION 26.7% | APPEL_OFFRE 72.5% / ATTRIBUTION 27.5% | close |
| `buyer_activity_gini` | 0.832 | 0.814 | close, within tolerance after §3's recalibration |
| `cpv_missing_rate` | 0.1706 | 0.170 | matches almost exactly (directly calibrated, central_provisional.yaml) |
| `zero_candidate_source_rate` (Phase 12 compatibility check, real production code) | 0.609 | 0.643 | close |
| `candidates_per_source_median` | 3 | 2 | close |

## 2. Discrepancies requiring v0.2 follow-up (reported, not silently accepted)

| Dimension | Real | Synthetic | Likely cause | Suggested v0.2 fix |
|---|---|---|---|---|
| `schema_family_mix` | LEGACY 87.4% / EFORMS 12.6% | LEGACY 72.6% / EFORMS 27.4% | v0.1 assumes a *uniform* notice density across the 2015-2026.5 observation window and a hard Oct-2023 schema cutoff; the real corpus's notice volume is not uniform over time | Calibrate cycle start-date density to `calib_population_counts_by_year_schema.csv`'s actual by-year volume instead of uniform sampling |
| `duration_present_rate` | 0.1365 | 0.324 | multiplicative Bernoulli chain in `corruption._corrupt_duration` under-delivers the configured `missing_rate` at the realized quality-class mix | Re-derive `central_provisional.yaml`'s `duration.missing_rate` empirically against realized output, or strengthen `LOW`-class severity in `missingness.SEVERITY_MULTIPLIER` |
| `siret_present_share` | 0.272 | 0.412 | **partly a metric-definition mismatch**: the real value requires format+Luhn-*validated* SIRET; the synthetic check here is a naive `.notna()`, which also counts corrupted-but-non-null (`INVALID_CHECKSUM`) SIRETs as "present" | Recompute the synthetic side with the same format+checksum validation the real metric uses (`utils.identifiers.validate_siret`) before re-assessing whether a real gap remains |
| `exact_duplicate_template_rate` | 0.5143 | 0.281 | real BOAMP's literal duplication is driven by shared official boilerplate reused across many unrelated buyers; v0.1's per-division vocabulary/template combinatorics produce more unique strings on average | Add a small shared cross-buyer boilerplate-phrase pool sampled independently of division, not only the existing `boilerplate_rate` corruption mechanism |
| `candidates_per_source_p90` | 12 | 29 | synthetic top-activity buyers cluster many needs/cycles within the same buyer more tightly in time than the real corpus's equivalent tail buyers | Spread `needs.py`'s per-need `start_date_true` sampling further for the highest-activity buyers, or lower `_TIER_LAMBDA["21+"]` |
| `cpv_generic_rate_among_present` | 0.0714 | 0.088 (marginal, not among-present — see note) | comparison computed on the marginal population, not conditioned on CPV-present, in the notebook; not a true apples-to-apples comparison | Recompute conditional on `cpv_clean.notna()` in v0.2's fidelity notebook |
| `median_text_length_chars` | 98.0 | 120.0 | template+vocabulary sentences run slightly longer than real BOAMP `objet` free text | Trim template verbosity in `text_generation.render_text` |

## 3. Adaptive calibration already applied (Phase 10)

Buyer-activity Gini: initial `pareto_shape=1.10, offset=1.0` gave a
simulated Gini of 0.641 at n=2,000 (vs the real corpus's 0.832); re-tuned to
`pareto_shape=1.0, offset=0.15` (empirically swept, not derived from the
asymptotic Pareto-Gini formula, which is a poor guide at this n) —
resulting Gini 0.814, within the declared ±0.15 tolerance band. See
`reports/generated/synthetic_benchmark/v0_1_clean_world_validation.md` §3
for the full sweep.

## 4. Phase 12 compatibility check (diagnostic only, no accuracy claim)

`boamp.synthetic.compatibility.adapt_observed_notices_to_sources` maps
`observed_notices.parquet` into the exact column shape
`boamp.linkage.candidates.generate_pairs_single_key` (the real, unmodified
Layer 1 production code) expects, reusing the real `build_boamp_buyer_key`,
`cpv_is_generic`, and `utils.identifiers` validators directly. The real
production candidate generator ran successfully on synthetic data
(§1: zero-candidate rate 0.643 vs real 0.609). This demonstrates
compatibility and gives an emergent-candidate-count fidelity read; it makes
**no** claim about linkage precision/recall on synthetic or real data (no
ground truth was used by the candidate generator, and this session did not
run Layer 1's scoring/threshold/linking stages at all).

## 5. What this report does NOT do

- It does not claim v0.1 is production-ready or fully calibrated.
- It does not compare Layer 1/Layer 2's actual *linkage* output against
  synthetic truth (that is explicitly deferred, spec Phase 12/13, to a
  future notebook after the generator is frozen).
- It does not retune any generator or scenario parameter based on §4's
  candidate-count result (spec: "Do not tune the generator to make a
  preferred linkage method win").
