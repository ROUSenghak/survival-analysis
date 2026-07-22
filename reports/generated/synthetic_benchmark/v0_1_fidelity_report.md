# Synthetic benchmark v0.1 — fidelity report

Generated from `notebooks/06_synthetic_fidelity_validation.ipynb`, comparing
the `central_provisional` pilot (`data/processed/synthetic_benchmark/v0_1_provisional/central_provisional/world_001/corruption_001/`,
2,000 buyers, 9,624 observed notices — this count shifted from the original
9,534 once `same_cycle_variation_severity` was recalibrated in §0.3, since
that changes how many random draws are consumed per notice and shifts the
shared RNG stream for everything generated afterward; deterministic and
reproducible given the current code+config+seeds, not run-to-run noise)
against the real corpus's
OBSERVABLE-tier calibration tables (`reports/tables/synthetic_calibration/`).
Full numeric table: `reports/tables/synthetic_benchmark/v0_1/v0_1_fidelity_summary.csv`.
Figures: `reports/figures/synthetic_benchmark/v0_1/`.

This is a **first-pass** fidelity check for a provisional pilot, not a
tuned-to-convergence calibration. One adaptive-calibration correction was
applied during this build (buyer-activity Gini, §3 below); every other
discrepancy below is reported honestly and left as v0.2 follow-up work
rather than iteratively re-tuned in this session (spec: "The immediate
success criterion is... not a final perfect simulator").

## 0. v0.2 recalibration pass (this session)

Four of the discrepancies below were investigated as a follow-up pass, all
three pilots regenerated after each fix (`world_seed=20260721,
corruption_seed=20260722, n_buyers=2000` unchanged), and the full test
suite re-run each time (124 passed by the final pass):

1. **`duration_present_rate` — FIXED** (0.324 -> 0.136, real target 0.1365).
   Root cause was structural, not a simple parameter typo: the shared
   identifier/CPV/text `SEVERITY_MULTIPLIER` (0.35/1.0/2.2 by latent quality
   class) made the configured `duration.missing_rate` mathematically unable
   to reach the real target — the HIGH-quality class alone (0.35x
   multiplier, ~30% of notices) produced more present-duration notices than
   the entire real-corpus target allows, and the plateau held even when
   `missing_rate` was swept well past 1.0. This says something substantive
   about the real data: duration appears to be omitted near-uniformly across
   BOAMP notices regardless of overall record quality (an editorial/template
   choice), unlike identifiers/CPV/text, which do vary with quality. Fixed
   by giving duration its own, flatter severity spread
   (`missingness.DURATION_SEVERITY_MULTIPLIER`, 0.89/1.0/1.15 — still driven
   by the same per-notice latent quality class, so co-occurrence with other
   fields' corruption is preserved), then empirically re-swept
   `central_provisional.yaml`'s `duration.missing_rate` (0.8635 -> 0.885)
   against that new multiplier. Now moved to §1 (good fidelity).
2. **`siret_present_share` — FIXED** (0.412 naive -> 0.273, real target
   0.272). First, the synthetic-side computation was fixed to use the same
   checksum-validated presence (`utils.identifiers.validate_siret`) as the
   real metric's definition, instead of naive `.notna()` — this alone
   dropped the value to 0.39 (still above 0.272, revealing a genuine
   residual gap, not just a measurement artifact). That gap turned out to
   have the same shape as the duration issue: `scenario.identifiers`' rates
   (`siren_only_rate`, `both_missing_rate`, `invalid_identifier_rate`) are
   scaled per-notice by the shared identifier/CPV/text
   `SEVERITY_MULTIPLIER`, so the documented EMPIRICAL rate
   (`siret_missing_rate: 0.728`) under-delivered once run through it.
   Unlike duration, no new per-field severity multiplier was needed here —
   there was enough headroom that simply scaling `siren_only_rate`,
   `both_missing_rate`, and `invalid_identifier_rate` by ~1.285x (while
   holding `wrong_establishment_siret_rate` fixed, since it still yields a
   checksum-valid SIRET and correctly counts as "present") closed the gap.
   Now moved to §1 (good fidelity).
3. **`exact_duplicate_template_rate` / `median_text_length_chars` — BOTH
   FIXED** (0.282 -> 0.518 vs target 0.5143; 120 -> 94 vs target 98.0).
   `render_text`'s template was trimmed (dropped the
   "(département {department})" clause) to address length on its own.
   Separately, `same_cycle_variation_severity` was tightened (0.15 -> 0.03)
   since the real `same_cycle_publication_similarity_target=1.000` anchor
   implies near-total identity within a CALL/AWARD family, stronger than the
   original 15%-drift-chance allowed. Neither was enough alone: real BOAMP's
   51.4% duplication rate is far higher than same-family reuse can produce —
   the dominant real driver is shared official boilerplate reused across
   *unrelated* buyers. Expanded the single fixed boilerplate string into a
   3-phrase pool (`corruption.GENERIC_BOILERPLATE_POOL`, avoiding one string
   monoculture) and empirically re-swept `boilerplate_rate` (0.10 -> 0.44)
   jointly against both targets at once, since boilerplate corruption also
   shortens affected notices and pulls the median down — a rate too high
   overshoots duplication while undershooting length, so both had to be
   tuned together, not independently. Now moved to §1 (good fidelity).
4. **`schema_family_mix` — attempted, no improvement found; still open.**
   Hypothesized cause (uniform notice density across the full window) was
   tested directly: the real corpus's by-year notice volume is actually
   close to *flat* (not markedly skewed), while the synthetic clean-world
   generator produces a *ramping* density that rises through the middle of
   the observation window and tapers near the end (TVD~0.146 against the
   real by-year distribution). Several buyer-active-window reparametrizations
   were tried (spreading `active_start` across the full window instead of
   its first 60%, with various caps on how far a single buyer's cycle chain
   can cascade) — every one tested made the fit *worse* (TVD 0.14-0.26),
   because injecting fresh buyer activity later in the window adds to,
   rather than corrects, the successor-cascade accumulation that already
   piles cycles into the middle years. `generate_latent_buyers` now exposes
   `active_start_fraction`/`min_active_days`/`span_days_max_fraction` as
   tunable parameters (defaulted to the original, unregressed behaviour) for
   a future pass, but the real fix needs to attack the recurrence/cycle-gap
   cascade mechanism itself (`needs.py`/`cycles.py`), not the buyer
   active-window heuristic. Left open, still in §2 below.

   **Follow-up (deeper investigation, still this session):** confirmed the
   buyer-active-window approach could never have worked — successor cycle
   continuation in `cycles.py` is capped only by the *global*
   `observation_end`, never by anything buyer-specific, so capping a
   buyer's own active window doesn't bound how far their needs' recurrence
   chains cascade. The real lever is `scenario.recurrence.cycle_gap_distribution`
   and/or `max_cycles_per_need` — but those parameters don't just control
   corruption/observation, they **define what a true NEXT_CYCLE recurrence
   relation looks like** for the whole benchmark's ground truth (and must
   keep satisfying the existing spec requirement that a meaningful share of
   true gaps fall outside the real pipeline's 6-month blocking window).
   Changing them is a ground-truth-semantics design decision, not a
   corruption-layer parameter sweep, and was intentionally **not** attempted
   this session pending that decision — left open for a deliberate v0.2
   design pass, not a quick empirical fix.

4. **`schema_family_mix` — FIXED, but not via the mechanism above** (73%/27%
   -> 86%/14%, real target 87.4%/12.6%). §6 below built systematic
   by-year/by-schema conditional checks (the `conditional_fidelity` freeze-
   gate item), which found that duration/SIRET/CPV missingness are strongly
   conditional on `schema_family` and `publication_year` in the real
   corpus, and that `notices.py`'s hard Oct-2023 `EFORMS_MANDATE_DATE`
   cutoff was itself wrong — real notices are 100% LEGACY through 2023
   (even the Oct-Dec 2023 window nominally covered by the mandate) and
   EFORMS adoption is *gradual* even after 2024 (53.8% in 2024, rising to
   59.9% by 2026 — still ~40% LEGACY today). Replacing the hard cutoff with
   a probabilistic draw using real by-year adoption shares
   (`notices._EFORMS_ADOPTION_SHARE_BY_YEAR`) fixed `schema_family_mix` as
   a *side effect*, without touching the recurrence-cascade mechanism at
   all — meaning the by-year density-ramp problem (item 3 above) was real
   but was **not** the dominant driver of this particular gap; the hard
   schema cutoff was. `schema_family_mix` moves to §1 (good fidelity); the
   density-ramp problem remains open on its own terms.
5. **Duration, SIRET, and CPV missingness recalibrated to be conditional on
   `schema_family`/`notice_type`/year, closing the `conditional_fidelity`
   gap this session confirmed (§6).** This is the most substantial fix this
   session: replaced flat, time-invariant corruption rates with rates
   conditioned on the real corpus's actual structure (schema-conditional
   duration, year-regime-conditional SIRET, schema+notice-type-conditional
   CPV — see §6 for full detail and residual gaps). One deliberate,
   documented trade-off: `duration_present_rate`'s *marginal* moved from
   0.135 (close to the 0.1365 target) to 0.181 (further away) as the
   accepted cost of getting the by-year/by-schema conditional behaviour
   right — the earlier close marginal was fitting the right aggregate
   number to a mechanism now known to be wrong (see §6). This is the
   clearest example in this whole session of prioritizing conditional
   correctness over a better-looking marginal number.

## 1. Good fidelity (within a reasonable band of the real corpus)

| Dimension | Real | Synthetic | Read |
|---|---|---|---|
| `notice_type_mix` | APPEL_OFFRE 68.9% / ATTRIBUTION 26.7% | APPEL_OFFRE 72.5% / ATTRIBUTION 27.5% | close |
| `buyer_activity_gini` | 0.832 | 0.814 | close, within tolerance after §3's recalibration |
| `zero_candidate_source_rate` (Phase 12 compatibility check, real production code) | 0.609 | 0.622 | close |
| `candidates_per_source_median` | 3 | 2 | close |
| `siret_present_share` | 0.272 | 0.289 | close — recalibrated this session (see §0.2, §6); was 0.412 (naive metric) |
| `exact_duplicate_template_rate` | 0.5143 | 0.516 | matches almost exactly — recalibrated this session (see §0.3); was 0.281 |
| `median_text_length_chars` | 98.0 | 94.0 | close — recalibrated this session (see §0.3); was 120.0 |
| `schema_family_mix` | LEGACY 87.4% / EFORMS 12.6% | LEGACY 86.0% / EFORMS 14.0% | matches closely — **fixed this session as a side effect of §0.5/§6's conditional-fidelity work**, not the recurrence-cascade fix originally thought necessary; was 72.2%/27.8% |
| `cpv_missing_rate` | 0.1706 | 0.151 | close — recalibrated conditionally this session (see §0.5, §6); the per-condition (schema x notice_type) cells are a closer match than this marginal number alone suggests |

Note `duration_present_rate` is deliberately **not** in this table anymore
despite its marginal (0.181 vs target 0.1365) being in a similar ballpark to
the dimensions above — see §6 for why: the previous close marginal (0.135)
was matching the right number via a mechanism now known to be wrong
(flat, schema-blind corruption), and the current, mechanistically-correct
version trades a slightly worse marginal for correct by-year/by-schema
behaviour. Listing it here without that caveat would misrepresent what
changed.

## 2. Discrepancies requiring v0.2 follow-up (reported, not silently accepted)

| Dimension | Real | Synthetic | Likely cause | Suggested v0.2 fix |
|---|---|---|---|---|
| by-year notice-volume density (drives residual `candidates_per_source_p90`, and a small residual in every by-year conditional check in §6) | real by-year notice volume is close to *flat* | synthetic's is a *ramping* curve (rises through the mid-window, tapers near the end) | successor-cascade accumulation in `needs.py`/`cycles.py` — buyer-active-window reparametrization was tried this session and made it worse (§0.4); NOT the cause of `schema_family_mix` (that was the hard schema cutoff, now fixed, see §0.5) but still a real, separate, open issue | Attack the recurrence/cycle-gap cascade mechanism directly (e.g. dampen how strongly cycle_number>1 timing compounds) — this is the ground-truth-semantics design decision flagged in §0.3, still not attempted |
| `candidates_per_source_p90` | 12 | 30 (unchanged by this session's work) | synthetic top-activity buyers cluster many needs/cycles within the same buyer more tightly in time than the real corpus's equivalent tail buyers | **Not to be closed by generator recalibration** — this metric is an emergent output of running the real, unmodified Layer 1 candidate-generation code on synthetic data (§4's compatibility check), not a property of the data alone. Tuning `needs.py` specifically to move this number would mean calibrating the generator against real linkage-adjacent code output, which this report's own §8 already prohibits ("Do not tune the generator to make a preferred linkage method win"). Left open permanently, not as a v0.2 TODO. |
| duration/CPV pre-2024 year-trend not modeled | CPV missingness declines monotonically 30.1% (2015) -> 7.9% (2026); duration's LEGACY-era residual (~5-6% present, §6) doesn't vary by year either | flat within each schema/notice-type cell (no year term) | not modeled — would require a third conditioning axis on top of schema/notice-type, not attempted this session | Add a year term (or a smooth trend) to `_cpv_missing_rate`/duration's LEGACY rate |
| 2025/2026 duration presence undershoot | 0.649 / 0.681 | 0.550 / 0.565 (§6) | mathematically, closing this fully would require EFORMS duration presence >100% given LEGACY's near-zero rate — real LEGACY notices in 2025/2026 apparently also gained some duration reporting, which this two-parameter (LEGACY/EFORMS) model doesn't capture | Add year-conditioning within the EFORMS/LEGACY split (three parameters instead of two), or accept as a known residual of the simplified model |
| `cpv_generic_rate_among_present` | 0.0714 | 0.089 (marginal, not among-present — see note) | comparison computed on the marginal population, not conditioned on CPV-present, in the notebook; not a true apples-to-apples comparison | Recompute conditional on `cpv_clean.notna()` in v0.2's fidelity notebook |

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
(§1: zero-candidate rate 0.622 vs real 0.609). This demonstrates
compatibility and gives an emergent-candidate-count fidelity read; it makes
**no** claim about linkage precision/recall on synthetic or real data (no
ground truth was used by the candidate generator, and this session did not
run Layer 1's scoring/threshold/linking stages at all).

## 5. Seed-robustness check (this session)

To test whether the recalibrated marginal fits (§0) are genuine calibration
or an artifact of fitting to one specific fixed-seed draw, `central_provisional`
was regenerated with a different, unrelated seed pair
(`world_seed=31415926, corruption_seed=27182818` vs the official
`world_seed=20260721, corruption_seed=20260722`), written to a separate
`world_002/corruption_002` directory (the official `world_001/corruption_001`
pilot was not touched), and the same metrics recomputed:

| Dimension | Real target | Official (world_001) | Alt-seed (world_002) |
|---|---|---|---|
| `siret_present_share` | 0.272 | 0.277 | 0.271 |
| `cpv_missing_rate` | 0.1706 | 0.169 | 0.166 |
| `duration_present_rate` | 0.1365 | 0.135 | 0.132 |
| `median_text_length_chars` | 98.0 | 94.0 | 94.0 |
| `exact_duplicate_template_rate` | 0.5143 | 0.518 | 0.524 |
| `buyer_activity_gini` | 0.832 | 0.814 | 0.827 |
| `notice_type_mix` (ATTRIBUTION share) | 26.7% | 28.2% | 27.8% |
| `schema_family_mix` (EFORMS share, *not* recalibrated) | 12.6% | 27.8% | 26.7% |
| `candidates_per_source_p90` (*not* recalibrated) | 12 | 30 | 30 |

Every recalibrated dimension lands close to both the real target and its
official-pilot value under a completely different seed — this is the
expected signature of genuine calibration, not overfitting to one lucky
draw. As a control, the two dimensions that were deliberately *not*
recalibrated (`schema_family_mix`, `candidates_per_source_p90`) also stay
consistent with their known gap under the alt seed rather than randomly
drifting closer to real — reinforcing that the gaps there are structural,
not seed noise, and that the recalibrated dimensions' improvement isn't
seed noise either.

**Scope note:** this check was run *before* §6's conditional-fidelity fixes
(duration/SIRET/CPV schema-and-year conditioning, and the schema-assignment
fix that also closed `schema_family_mix`). The numbers above are preserved
as-is, as valid evidence for the state at that point in the session, not
re-run against the current pilot. A fresh seed-robustness pass against the
current, conditionally-recalibrated pilot has not been done and would be a
reasonable next check before treating §6's fixes with the same confidence
as §0's.

## 6. Conditional fidelity — CONFIRMED gap (first pass), then FIXED (follow-up, same session)

This was previously `NEEDS_REVISION` only because it hadn't been built. It
went through two passes in this session:

### 6a. First pass: confirmed a real gap the marginals were masking

Built by-year/by-schema/by-notice-type/by-identifier-source comparisons
against real corpus tables (`calib_cpv_missingness_by_conditioning.csv`,
`calib_field_completeness_by_year.csv`, `calib_notice_type_by_year.csv`).
Found that the §0 marginal fixes, while hitting the right aggregate
numbers, were doing so via a mechanism that didn't match reality: real
`duration_raw` presence was exactly 0.0% every year 2015-2023, jumping to
52-68% only in 2024-2026, and real CPV missingness was strongly schema-
and notice-type-conditional (EFORMS ~0%, LEGACY 19.5%; ATTRIBUTION 7.1%,
APPEL_OFFRE 21.4%) — none of which the then-flat, time-invariant corruption
rates could reproduce, even though their *averages* looked fine.

### 6b. Follow-up: fixed with schema/year-conditional corruption + a root-cause schema-assignment fix

Rather than leave this as a v0.2 item, this session implemented the fix:

- **Duration** (`corruption._corrupt_duration`): now schema-conditional
  (`scenario.duration.missing_rate_by_schema`: LEGACY=0.995, EFORMS=0.06),
  replacing the flat rate.
- **SIRET** (`corruption._corrupt_identifier` /
  `_identifier_year_regime_scale`): now year-regime-conditional
  (`scenario.identifiers.year_regime_scale`: early <=2021, mid 2022-2023,
  late 2024+), since the real SIRET-presence regime shift is centered on
  2022 and is **independent of the EFORMS schema cutover** (2022/2023 are
  both 100% LEGACY in this corpus, yet real SIRET presence jumps from
  ~9-17% to ~53-56% there).
- **CPV** (`corruption._cpv_missing_rate`): now schema x notice-type
  conditional (`scenario.cpv.missing_rate_by_condition`), replacing the
  flat rate.
- **Root cause, found while calibrating the above**: `notices.py`'s
  `_schema_family` used a hard `publication_date >= 2023-10-01` cutoff for
  EFORMS classification. The real corpus shows 100% LEGACY through 2023
  (even the Oct-Dec 2023 window nominally covered by the mandate) and
  *gradual* EFORMS adoption thereafter (53.8% in 2024, rising to 59.9% by
  2026 — still ~40% LEGACY today). Replaced with a probabilistic draw
  using real by-year adoption shares
  (`notices._EFORMS_ADOPTION_SHARE_BY_YEAR`). This one change also fixed
  `schema_family_mix` (§2's former top entry) as a side effect, without
  touching the recurrence-cascade mechanism at all.

All three parameter sets were empirically swept against the real per-cell
targets (not derived by hand-algebra alone, for the same caps/renormalization
reasons discussed earlier in this session), then verified end-to-end: all
pilots regenerated, full test suite re-run (124 passing), and the
conditional comparisons re-run against the corrected pilot.

**Results (official `central_provisional` pilot, final state):**

| Check | Real | Synthetic | Read |
|---|---|---|---|
| CPV missing: EFORMS | 0.000 | 0.010 | excellent |
| CPV missing: LEGACY | 0.195 | 0.174 | close |
| CPV missing: APPEL_OFFRE | 0.214 | 0.184 | close |
| CPV missing: ATTRIBUTION | 0.071 | 0.064 | close |
| SIRET present: early (<=2021) | ~0.09-0.17 | 0.10-0.14 by year | close, most years within a few points |
| SIRET present: mid (2022-2023) | 0.527 / 0.560 | 0.529 / 0.539 | excellent |
| SIRET present: late (2024-2026) | 0.39-0.49 | 0.42-0.47 | close |
| Duration present: LEGACY years (2015-2023) | 0.000 every year | 0.04-0.06 | close, small residual |
| Duration present: 2024 | 0.523 | 0.529 | excellent |
| Duration present: 2025 / 2026 | 0.649 / 0.681 | 0.550 / 0.565 | undershoots by 0.10-0.12 (see residual note) |

**Residual, honestly documented limitations (not chased further this session):**

1. **2025/2026 duration presence undershoots.** Mathematically, closing
   this fully would require EFORMS-notice duration presence above 100%
   given LEGACY's near-zero rate — i.e., the real corpus's LEGACY notices
   in 2025/2026 apparently *also* gained some duration reporting over time,
   which this two-parameter (flat LEGACY/EFORMS split) model can't capture.
   A three-parameter model (LEGACY rate itself varying by year) would close
   this; not attempted here.
2. **Pre-2024 year trend in CPV missingness not modeled.** Real CPV
   missingness declines monotonically from 30.1% (2015) to 7.9% (2026)
   within what's otherwise a flat LEGACY/APPEL_OFFRE cell; synthetic is
   flat within that cell (no year term).
3. **The by-year notice-volume density-ramp problem is separate and still
   open** (§2) — fixing the schema-assignment mechanism corrected *which*
   schema a notice gets, not *how many* notices exist in each year, so
   `candidates_per_source_p90` and the residual few-point misses in the
   table above still partly reflect that unrelated, still-open issue.
4. **A deliberate marginal trade-off**: `duration_present_rate`'s marginal
   moved from 0.135 (close) to 0.181 (a real gap) as the accepted cost of
   the fix above — see §1's note on why it's not listed as "good fidelity"
   despite being in a similar numeric ballpark to dimensions that are.

**What this means for the stated goal (a benchmark credible for evaluating
a linking method):** the three fields most likely to affect blocking/
scoring decisions (SIRET, CPV, duration) now vary with `schema_family`/
`notice_type`/year the way they do in the real corpus, closing the main gap
between "good aggregate numbers" and "trustworthy per-era/per-schema
behaviour" identified earlier in this session.

## 7. Censoring fidelity (this session)

`calibration_parameters_v0_1.yaml#censoring.followup_evaluable_share_12m_24m`
(real: 91.8% of records have >=12 months of runway before the observation
window closes; 82.5% have >=24 months) was computed on the official pilot's
`observed_notices.publication_date` against `benchmark_defaults_v0_1.yaml`'s
`observation_window.end_date` (2026-07-31):

| Horizon | Real target | Synthetic |
|---|---|---|
| 12-month evaluable share | 0.918 | 0.911 |
| 24-month evaluable share | 0.825 | 0.809 |

Both close, no recalibration needed. Notably, this is close *despite* §6's
finding that the by-year notice-density shape is wrong (a ramp instead of
flat) — this particular statistic is a right-tail mass measure that turns
out to be fairly robust to that shape mismatch, not evidence that the
by-year shape problem is resolved.

## 8. What this report does NOT do

- It does not claim v0.1 is production-ready or fully calibrated.
- It does not compare Layer 1/Layer 2's actual *linkage* output against
  synthetic truth (that is explicitly deferred, spec Phase 12/13, to a
  future notebook after the generator is frozen).
- It does not retune any generator or scenario parameter based on §4's
  candidate-count result (spec: "Do not tune the generator to make a
  preferred linkage method win").
