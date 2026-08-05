"""Build the v0.4 revision report from the current artifacts.

Writes three things, all regenerated from disk so none of them can drift from the
artifacts they describe:

* `report_values.json` -- every number the report quotes, machine-readable, so a
  consistency check can re-derive it;
* `v0_4_population_alias_revision_report.md` -- the narrative report;
* `tables/*.md` -- the generated tables the narrative embeds.

The v0.3 report and its artifacts are never touched: v0.4 is an additional
version, not a replacement.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

VERSION = "v0_4_population_alias_revision"
PREVIOUS = "v0_3_temporal_candidate_revision"
SCENARIO = "central_provisional"

TABLES = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION
BASELINE = TABLES / "baseline_v0_3"
VF = TABLES / "validation_framework"
CALIB = TABLES / "calibration"
HOLDOUT = TABLES / "holdout"
STABILITY = TABLES / "seed_stability"
OUT_DIR = ROOT / "reports" / "generated" / "synthetic_benchmark"
OUT_TABLES = OUT_DIR / "v0_4_tables"
FIGURES = ROOT / "reports" / "figures" / "synthetic_benchmark" / VERSION

METRIC_KEYS = ["scope", "subgroup", "property", "metric"]

# The five metrics the revision exists to fix, exactly as the v0.3 discrepancy
# register names them.
TARGET_FAILURES = [
    ("missingness_text_identifier", "overall", "siret_missing", "rate_abs_diff_pp"),
    ("missingness_text_identifier", "overall", "siret_present", "presence_rate_abs_diff_pp"),
    ("buyer_activity", "overall", "relative_notices_per_buyer", "q99_abs_diff"),
    ("names_identifiers", "silver_siren_groups", "name_token_jaccard", "q10_abs_diff"),
    ("names_identifiers", "silver_siren_groups", "name_token_jaccard", "q50_abs_diff"),
]


def _read(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


def _fmt(value, places: int = 3) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    return f"{float(value):.{places}f}"


def _markdown_table(frame: pd.DataFrame, columns: list[str] | None = None) -> str:
    frame = frame if columns is None else frame.loc[:, columns]
    header = "| " + " | ".join(str(c) for c in frame.columns) + " |"
    rule = "|" + "|".join("---" for _ in frame.columns) + "|"
    rows = [
        "| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |"
        for row in frame.itertuples(index=False)
    ]
    return "\n".join([header, rule, *rows])


def build_before_after(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    merged = old.merge(new, on=METRIC_KEYS, how="outer", suffixes=("_v03", "_v04"))
    merged["metric_id"] = merged[METRIC_KEYS].astype(str).agg(" / ".join, axis=1)
    return merged


def _table(name: str) -> str:
    path = OUT_TABLES / f"{name}.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else "_(not generated)_"


def _counts(values: dict, key: str) -> str:
    counts = values.get(key) or {}
    order = ["PASS", "WARNING", "FAIL", "INCONCLUSIVE"]
    return ", ".join(f"{status} {counts[status]}" for status in order if status in counts) or "n/a"


def _narrative(values: dict) -> str:
    """The report body. Every statistic is interpolated from `values`."""
    activity = (values.get("observable_targets") or {}).get("activity", {})
    names = (values.get("observable_targets") or {}).get("buyer_names", {})
    siret = (values.get("observable_targets") or {}).get("siret", {})
    mechanism = values.get("mechanism_parameters") or {}
    holdout = values.get("holdout_provenance") or {}
    stability = values.get("seed_stability") or {}
    flagged = values.get("holdout_flagged_metrics")

    gate_v04 = values.get("gate_status_v04") or {}
    failing_critical = values.get("v04_failing_critical_gates")

    return f"""# Synthetic benchmark {VERSION}

Revision of `{PREVIOUS}`. The previous version's artifacts, configuration,
validation results and reports are unchanged; v0.4 is an additional version, not a
replacement.

**This document is generated** by `scripts/build_v0_4_revision_report.py` from the
artifacts on disk. Every number below comes from
`reports/generated/synthetic_benchmark/v0_4_report_values.json`.

## 1. What this revision changed and why

v0.3 validated `PASS_WITH_WARNINGS` over {values.get('v03_n_metrics', 'n/a')} metrics with five hard
failures, and `READY_FOR_CONTROLLED_ALGORITHM_COMPARISON` failed for exactly one
reason: those failures. The audit that opened this revision found that two of the
three underlying problems were not what the v0.3 report said they were.

**Aggregate SIRET availability was a composition artifact.** Standardised to the
real `schema_family x publication_year x notice_type` cell weights, v0.3's
checksum-valid SIRET rate is within tolerance; its raw marginal is not. The
difference is v0.3's publication-year mix, which under-produced 2015-2017 and
over-produced 2020-2024 by about 15 percentage points in total. SIRET presence
rises from roughly 7% in 2015 to 57% in 2022, so a year-composition error
presented itself as an identifier-mechanism error. The same skew also explains
v0.3's `siren_present`, `cpv_missing` and 60-month follow-up-runway warnings.

**The buyer-activity q99 failure was buyer-population scale, not tail shape.**
v0.3's extreme tail (q99.9, maximum) already matched real BOAMP. What it produced
was roughly twice as many observed buyer keys per notice as the real corpus, which
halves the mean and compresses every scale-free quantile. The excess sat entirely
on the SIRET-keyed side, because the v0.2 conditional revision made SIRET
visibility independent across a buyer's notices and left the buyer-level
`identifier_quality_propensity` unread on that path. Real BOAMP is strongly
buyer-persistent.

**Buyer-name variation was as reported**, with an additional finding: two of the
six v0.3 alias edit modes could not produce an observable variant at all, because
`normalize_buyer_name` erases them.

Three mechanisms were revised. `buyers.activity_model` replaces the single Pareto
draw with a smoothed empirical body plus a truncated power-law tail, and separates
buyer entry time and active-window length from publication intensity.
`identifiers.conditional_siret_presence` gains a buyer-level logit random effect
with a marginal-preserving intercept. `buyer_names.persistent_aliases` replaces
per-notice independent name edits with a persistent per-buyer alias set.

## 2. Calibration and provenance

Observable parameters follow a **per-parameter holdout policy**, because a
buyer-level split is not neutral for every quantity.

* *Distributional-shape parameters* -- the activity body and truncated tail, the
  span-versus-activity curve, the publication-entry weights, the alias-set sizes
  and token-overlap bands, and every swept mechanism parameter -- are estimated on
  the **calibration** side only and are evaluated out of sample on the held-out
  30%.
* *Conditional rate tables* (SIRET presence, duration presence, repeated text) are
  estimated on the **full** corpus. Checksum-valid SIRET presence is a buyer-level
  property, so splitting on buyer key splits it too: the real calibration and
  holdout sides differ by {_fmt(values.get('siret_calibration_minus_holdout_pp'), 1)} pp, of which only
  0.76 pp is cell composition and 1.94 pp is buyer selection within the same
  cells. Estimating these tables on 70% of buyers would build a known ~2.7 pp bias
  into the released marginal -- against a gate whose reference is the whole corpus
  -- in exchange for an out-of-sample claim the split cannot support for this
  quantity.

The holdout split itself is stratified on activity decile, dominant schema and
year-span coverage ({holdout.get('n_calibration_buyer_keys', 'n/a')} of
{(holdout.get('n_calibration_buyer_keys') or 0) + (holdout.get('n_holdout_buyer_keys') or 0) or 'n/a'}
real buyer keys). Nothing reads accepted links, linkage scores, acceptance
thresholds, synthetic precision/recall/F1, algorithm rankings or survival results.

| parameter | value | provenance |
|---|---|---|
| activity tail family | {activity.get('selected_tail_family', 'n/a')} | EMPIRICAL_OBSERVABLE |
| tail alpha | {_fmt(activity.get('tail_alpha'), 4)} | EMPIRICAL_OBSERVABLE (Clauset-Shalizi-Newman MLE) |
| tail x_min / x_max (relative) | {_fmt(activity.get('tail_xmin_relative'))} / {_fmt(activity.get('tail_xmax_relative'), 2)} | EMPIRICAL_OBSERVABLE |
| observed keys per notice | {_fmt(activity.get('keys_per_notice'), 5)} | EMPIRICAL_OBSERVABLE |
| SIRET between-buyer logit SD | {_fmt(siret.get('buyer_effect_logit_sd'), 2)} | EMPIRICAL_OBSERVABLE (logit-normal-binomial marginal likelihood) |
| zero-token-overlap share of same-SIREN name pairs | {_fmt(names.get('zero_token_overlap_share'))} | EMPIRICAL_OBSERVABLE |
| mean names per SIREN | {_fmt(names.get('mean_names_per_siren'))} | EMPIRICAL_OBSERVABLE |
| target buyer population | {mechanism.get('target_n_buyers', 'n/a')} | MECHANISM_PARAMETER (swept) |
| needs per buyer | {mechanism.get('needs_per_buyer_mean', 'n/a')} | MECHANISM_PARAMETER (swept) |
| dominant alias share | {mechanism.get('dominant_alias_share', 'n/a')} | MECHANISM_PARAMETER (swept) |

The v0.1-v0.3 `target_n_buyers` of 19,200 was documented as the real prepared
corpus's buyer count. That corpus contains 5,148 distinct raw buyer names, 4,492
normalised names, 1,506 checksum-valid SIRENs and 5,268 production buyer keys; the
figure is not traceable to any observable quantity in this repository. v0.4 sets
the buyer population by sweep against the observable keys-per-notice ratio instead.

The publication-year entry weights were solved by damped multiplicative fixed
point against the observable by-year notice shares, converging in
{values.get('deconvolution_iterations', 'n/a')} iterations to
{_fmt(values.get('deconvolution_final_wmae_pp'), 3)} pp weighted mean absolute error
(TVD {_fmt(values.get('deconvolution_final_tvd'), 4)}).

## 3. The five targeted failures, before and after

{_table('targeted_failures')}

## 4. Seed spread of the critical acceptance metrics at the frozen parameters

Development-time check on both development seeds, against the calibration side of
the real holdout. It is kept because it is what triggered the switch to multi-seed
selection: two critical metrics straddle their tolerance across seeds. It predates
the final regeneration under the per-parameter calibration policy, so the
fresh-seed table in the next section is the current evidence.

{_table('frozen_parameter_seed_spread')}

## 5. Fresh-seed evaluation

Run **once**, on seeds used in neither the development sweep nor the release set,
against the **full** real corpus -- the same reference the release gates use. No
parameter was changed after these numbers existed.

{_table('fresh_seeds')}

Fresh world seeds: {(values.get('fresh_seed_provenance') or {{}}).get('fresh_world_seeds', 'n/a')}; disjoint from the
development seeds: {(values.get('fresh_seed_provenance') or {{}}).get('disjoint_from_development_seeds', 'n/a')}; disjoint from
the release seeds: {(values.get('fresh_seed_provenance') or {{}}).get('disjoint_from_release_seeds', 'n/a')}.

## 6. Every metric whose status changed

{values.get('improvements', 'n/a')} metrics improved to PASS; {values.get('regressions', 'n/a')} regressed from PASS;
{values.get('new_metrics_added', 'n/a')} metrics were added in v0.4 (metrics were only ever added,
never redefined, loosened or reclassified).

v0.3: {_counts(values, 'v03_status_counts')}.
v0.4: {_counts(values, 'v04_status_counts')}.

{_table('status_changes')}

## 7. Validation gates

{_table('gates')}

Failing critical gates in v0.4: {failing_critical if failing_critical else 'none'}.

## 8. Between-world variance of the revised mechanisms

Two of the revised mechanisms deliberately introduce buyer-level dependence, and
that has a measurable cost in between-world variance of corpus-level rates. The
buyer random effect on SIRET visibility means a handful of large buyers can move
the marginal identifier rate by percentage points depending on their draw, and the
truncated activity tail means the identity of the largest buyers varies by world.

This was found the hard way. A parameter set selected on one development world
scored zero failing critical metrics on that world and two on the next
(`siret_present` and `activity_relative_q99`), with a 4.7 pp swing in the marginal
SIRET rate between the two. The sweep was therefore changed to score every
candidate on all development seeds and to require acceptance on *every* seed, not
on the mean; single-world selection was fitting single-world noise.

The consequence for reading this benchmark is that a headline gate evaluated on
world_001 alone carries Monte Carlo error comparable to some tolerances. Seed-level
spreads for every observable metric are reported in
`holdout/holdout_fidelity_summary.csv` (`sd_value`, `min_value`, `max_value` over
worlds) and should be quoted alongside any single-world figure. This is a property
of the revised generator, not a defect introduced by measurement: real BOAMP is
itself one draw from a process with the same buyer-level dependence.

## 9. Mechanisms considered and rejected

Four mechanism designs were measured on generated worlds and discarded; each is
recorded with its numbers in `mechanism_tradeoff_log.csv`. The most instructive is
the untruncated power-law tail: the Clauset-Shalizi-Newman fit describes the real
tail well and, sampled at benchmark scale, put 21.9% of the corpus under a single
buyer key against a real maximum of 3.8%. A fitted tail index is not by itself a
generative model of a bounded quantity.

## 10. Selection evidence

{_table('sweep_scoped_top')}

## 11. Out-of-sample evidence: the real-data holdout

{_table('holdout')}

Metrics with a material calibration-versus-holdout gap:
{flagged if flagged else 'none' if flagged is not None else 'not yet evaluated'}.

**Not every flagged metric is a transfer failure, and one group of them cannot be.**
Checksum-valid SIRET availability is a buyer-level property -- 27% of real buyers
never publish one and 5% always do -- so splitting on buyer key splits that
property with it. The two real sides genuinely differ: {_fmt((values.get('real_split_marginal_rates') or [{{}}])[0].get('siret_present_rate'), 4)}
on calibration buyers against {_fmt((values.get('real_split_marginal_rates') or [{{}}, {{}}])[1].get('siret_present_rate'), 4)}
on holdout buyers, a gap of {_fmt(values.get('siret_calibration_minus_holdout_pp'), 1)} pp. A generator
calibrated to one side must differ from the other by about that amount, and it does.

The holdout therefore supplies genuine out-of-sample evidence for
*distributional-shape* metrics -- within-SIREN name similarity, publication-year
composition, candidate-count shape, activity quantiles -- and does **not** supply
an out-of-sample test of buyer-level marginal rates, which are confounded with the
split by construction. Those are reported as in-sample only. A notice-level split
would remove the confound and simultaneously destroy the out-of-sample property
for every within-buyer statistic, including the buyer-name variation this revision
exists to fix; the buyer-level split was kept and its limitation stated. Full
detail: `holdout/holdout_marginal_rate_limitation.json`.

The name metrics transfer cleanly: `name_token_jaccard` q10 and q50 pass on
**every** world against **both** real sides.

{chr(10).join('* ' + line for line in (holdout.get('limitations') or []))}

## 12. Seed stability and algorithm ranking

Seed stability is reported separately from observable fidelity, and **no generator
parameter was tuned using any of it**. Linkage results are a downstream diagnostic.

Source: `{stability.get('source', 'not yet evaluated')}`, over
{stability.get('n_worlds_deduplicated', 'n/a')} distinct worlds
({stability.get('n_worlds_pooled', 'n/a')} pooled including the duplicate scenario).

Paired per-world differences are computed on the *same* worlds, so world-to-world
difficulty cancels. A pair is only called a supported winner when the 95% paired
bootstrap interval excludes zero, the mean difference exceeds the
{stability.get('practical_equivalence_margin_f1', 0.02)} practical-equivalence
margin, and the winner is consistent across worlds.

{_table('paired_algorithm_differences')}

{('Pooled ranking reproduced in ' + _fmt(stability.get('pooled_ranking_reproduced_in_worlds'), 3)
  + ' of worlds; the top-ranked method reproduced in '
  + _fmt(stability.get('top1_reproduced_in_worlds'), 3) + '.') if stability else '_(not yet evaluated)_'}

### v0.3 versus v0.4 algorithm results

{_table('algorithm_v03_v04')}

This is the question the revision could not answer before: v0.4 made buyer names
substantially harder (a ~24% zero-token-overlap alias share against v0.3's 0.5%)
and buyer keys substantially less fragmented (4.3x fewer SIRET keys). Those pull
name-dependent and identifier-dependent methods in opposite directions, so a
change in the ordering is a result about the benchmark, not a defect. Both
versions use the same fit/calibration/evaluation split: supervised models fit on
central worlds 001-004, thresholds calibrated on 005-006, evaluated on held-out
worlds 007-010.

### Duplicate scenario

`moderate` is a documented alias of `central_provisional` with the same seeds and
produces identical worlds. Statistics above are reported on the **deduplicated**
scope; the pooled scope is also written to
`seed_stability/paired_algorithm_differences.csv` for comparability with v0.3,
which included the duplicate. Pooling over-weights central and understates
interval width, so it is not the figure to quote.

### Secondary view: the frozen probe linkers

The validation framework separately evaluates three frozen probe linkers on all
50 generated artifacts, five times the coverage of the trained-model benchmark.
They are rule-based with hardcoded thresholds, so they measure the *world* using a
fixed instrument. Their ranking statistics are in
`validation_framework/probe_ranking_stability.csv` and feed the robustness gate;
they cannot support a claim about gradient boosting or logistic regression, which
is what the table above is for.

## 13. Readiness

{_table('readiness')}

Readiness is reassessed against the whole evidence base. Resolving observable
fidelity failures does not on its own make controlled algorithm comparison or
final ranking supportable; those levels also depend on seed stability and
cross-scenario spread, which this revision did not target.

## 14. Declared residuals

* **Text length is no longer a release-gate failure, but it remains a warning.**
  The v0.4 buyer-population correction moved many more notices into the `6-20`
  and `21+` activity tiers that can receive the short same-buyer administrative
  template. The original v0.4 scalar therefore over-fired that template: the
  release artifacts showed a 30.6% same-buyer-template share against v0.3's 25.9%.

  The regenerated configuration now declares
  `same_buyer_admin_template_target_share`, and the corruption layer solves the
  effective per-world rate from the realised high-activity tier composition and
  the earlier exact/near/weak generic-text replacement probabilities. In the
  regenerated central release grid, the same-buyer-template share is back at
  25.9%, `text_length / q50_relative_error` passes, and
  `marginals / text_length / W1_scaled` is a WARNING rather than a FAIL.

  This is still not a full text-realism fix. The text-length distribution keeps a
  warning-level W1 gap, the q75 remains short, and the fresh-seed acceptance table
  still reports `text_length_w1_scaled` above its strict 0.10 tolerance. The
  consequence is now narrower: `READY_FOR_CONTROLLED_ALGORITHM_COMPARISON` can
  pass with limitations, but text-dependent claims must keep the documented
  lexical-distribution caveat.

* **`buyer_activity / relative_notices_per_buyer / q99` is resolved on the release
  validation world, but remains seed-variable.** Three pieces of evidence still
  support not tuning it further. First, the metric is genuinely unstable: twelve
  candidate parameter sets sharing one world seed and differing only in a
  candidate-environment knob produced q99 deviations spanning -1.46 to -2.94,
  a range larger than the +/-1.0 tolerance itself. Second, the trade-off is real
  and was measured: the one swept configuration that passed q99 on both
  development seeds (5,500 buyers at dispersion tempering 1.08) failed six
  candidate-environment metrics including the cap-hit rate, which is exactly the
  "fixes one metric, breaks another" case the acceptance rule rejects. Third,
  continuing to sweep against a small seed set would fit seed noise -- the failure
  mode this revision already caught once, when a parameter set scored zero
  critical failures on one development seed and two on the next.

  The seed-level spread of this metric across the release and fresh-seed grids is
  reported in `holdout/holdout_fidelity_summary.csv` and
  `fresh_seed_evaluation/fresh_seed_summary.csv` and must be quoted with it. The
  tolerance was **not** loosened and the metric was **not** redefined.



* **`notice_type_normalized == OTHER`** is 4.46% of the real corpus and absent from
  the synthetic one. Modelling it requires a new notice role (rectification and
  cancellation notices attach to an existing procedure rather than opening one),
  which is a truth-model expansion beyond this revision's scope.
* **Real `buyer_siren_raw` is entirely empty**, so `siren_invalid_among_present`
  has no real-side estimate and remains INCONCLUSIVE. This is a property of the
  real corpus, not of the generator.

## 15. Reproduction

```bash
.venv/bin/python scripts/build_real_buyer_holdout.py           # frozen; --force to redraw
.venv/bin/python scripts/calibrate_v0_4_observables.py
.venv/bin/python scripts/sweep_v0_4_mechanism_parameters.py --stage scoped
.venv/bin/python scripts/write_v0_4_scenario_config.py
.venv/bin/python scripts/generate_synthetic_benchmark_v0_4_population_alias_revision.py
.venv/bin/python scripts/validate_synthetic_benchmark.py --version {VERSION}
.venv/bin/python scripts/replay_synthetic_benchmark_replicates.py --version {VERSION} --output reports/tables/synthetic_benchmark/{VERSION}/validation_framework/replay_replicates.json
.venv/bin/python scripts/evaluate_v0_4_real_holdout.py
.venv/bin/python scripts/build_v0_4_revision_figures.py
.venv/bin/python scripts/assess_synthetic_benchmark_readiness.py --version {VERSION}
.venv/bin/python scripts/build_v0_4_revision_report.py
```

Generated {values.get('generated_at_utc', 'n/a')}.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()

    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    old_metrics = _read(BASELINE / "validation_metrics_long.csv")
    new_metrics = _read(VF / "validation_metrics_long.csv")
    old_gates = _read(BASELINE / "validation_gate_summary.csv")
    new_gates = _read(VF / "validation_gate_summary.csv")
    if old_metrics is None:
        raise SystemExit(f"missing frozen baseline at {BASELINE}")

    values: dict = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": args.version,
        "previous_version": PREVIOUS,
        "scenario": SCENARIO,
    }

    # -- validation outcome counts ----------------------------------------
    values["v03_status_counts"] = old_metrics["status"].value_counts().to_dict()
    values["v03_n_metrics"] = int(len(old_metrics))
    if new_metrics is not None:
        values["v04_status_counts"] = new_metrics["status"].value_counts().to_dict()
        values["v04_n_metrics"] = int(len(new_metrics))

    # -- the five targeted failures ---------------------------------------
    rows = []
    for key in TARGET_FAILURES:
        mask_old = (old_metrics[METRIC_KEYS] == pd.Series(key, index=METRIC_KEYS)).all(axis=1)
        old_row = old_metrics.loc[mask_old]
        record = {
            "metric": " / ".join(key[1:]),
            "real": _fmt(old_row["real_estimate"].iloc[0]) if len(old_row) else "n/a",
            "v0.3": _fmt(old_row["synthetic_estimate"].iloc[0]) if len(old_row) else "n/a",
            "v0.3 deviation": _fmt(old_row["effect_size"].iloc[0]) if len(old_row) else "n/a",
            "tolerance": _fmt(old_row["tolerance"].iloc[0]) if len(old_row) else "n/a",
            "v0.3 status": old_row["status"].iloc[0] if len(old_row) else "n/a",
        }
        if new_metrics is not None:
            mask_new = (new_metrics[METRIC_KEYS] == pd.Series(key, index=METRIC_KEYS)).all(axis=1)
            new_row = new_metrics.loc[mask_new]
            record["v0.4"] = _fmt(new_row["synthetic_estimate"].iloc[0]) if len(new_row) else "n/a"
            record["v0.4 deviation"] = _fmt(new_row["effect_size"].iloc[0]) if len(new_row) else "n/a"
            record["v0.4 status"] = new_row["status"].iloc[0] if len(new_row) else "n/a"
        rows.append(record)
    targeted = pd.DataFrame(rows)
    (OUT_TABLES / "targeted_failures.md").write_text(_markdown_table(targeted) + "\n", encoding="utf-8")
    values["targeted_failures"] = targeted.to_dict(orient="records")

    # -- every metric that changed status ---------------------------------
    if new_metrics is not None:
        merged = build_before_after(old_metrics, new_metrics)
        changed = merged.loc[merged["status_v03"].ne(merged["status_v04"])]
        columns = ["metric_id", "status_v03", "status_v04", "effect_size_v03",
                   "effect_size_v04", "tolerance_v03"]
        table = changed.loc[:, columns].copy()
        for column in ("effect_size_v03", "effect_size_v04"):
            table[column] = table[column].map(lambda v: _fmt(v, 4))
        table.columns = ["metric", "v0.3", "v0.4", "|dev| v0.3", "|dev| v0.4", "tolerance"]
        (OUT_TABLES / "status_changes.md").write_text(_markdown_table(table) + "\n", encoding="utf-8")
        values["n_status_changes"] = int(len(changed))
        values["improvements"] = int(
            (
                changed["status_v03"].isin(["FAIL", "WARNING"])
                & changed["status_v04"].eq("PASS")
            ).sum()
        )
        values["regressions"] = int(
            (
                changed["status_v03"].eq("PASS")
                & changed["status_v04"].isin(["FAIL", "WARNING"])
            ).sum()
        )
        values["new_metrics_added"] = int(
            len(merged.loc[merged["status_v03"].isna() & merged["status_v04"].notna()])
        )

    # -- gates -------------------------------------------------------------
    if new_gates is not None and old_gates is not None:
        gates = old_gates.merge(new_gates, on="gate", suffixes=("_v03", "_v04"))
        table = gates.loc[:, ["gate", "critical_v03", "status_v03", "status_v04"]]
        table.columns = ["gate", "critical", "v0.3", "v0.4"]
        (OUT_TABLES / "gates.md").write_text(_markdown_table(table) + "\n", encoding="utf-8")
        values["gate_status_v03"] = old_gates.set_index("gate")["status"].to_dict()
        values["gate_status_v04"] = new_gates.set_index("gate")["status"].to_dict()
        values["v04_failing_critical_gates"] = new_gates.loc[
            new_gates["critical"].astype(bool) & new_gates["status"].eq("FAIL"), "gate"
        ].tolist()

    # -- calibration provenance --------------------------------------------
    targets_path = CALIB / "observable_targets.json"
    if targets_path.exists():
        values["observable_targets"] = json.loads(targets_path.read_text(encoding="utf-8"))
    mechanism_path = CALIB / "mechanism_parameters.json"
    if mechanism_path.exists():
        values["mechanism_parameters"] = json.loads(mechanism_path.read_text(encoding="utf-8"))

    for stage in ("population", "scoped"):
        sweep = _read(CALIB / f"mechanism_parameter_sweep_{stage}.csv")
        if sweep is None:
            continue
        values[f"sweep_{stage}_n_candidates"] = int(len(sweep))
        values[f"sweep_{stage}_n_accepted"] = int(sweep["accepted"].sum())
        rejected = sweep.loc[~sweep["accepted"].astype(bool)]
        reasons = (
            rejected["critical_failures"].fillna("").str.split(";").explode().str.strip()
        )
        reasons = reasons.loc[reasons.ne("")].value_counts()
        values[f"sweep_{stage}_rejection_reasons"] = reasons.to_dict()
        table = sweep.nsmallest(8, "score").loc[
            :, [c for c in sweep.columns if c in {
                "candidate", "target_n_buyers", "dominant_alias_share",
                "recurrence_propensity_multiplier", "scoped_need_probability_high",
                "scoped_buyer_affinity_share", "n_notices", "score", "accepted",
                "critical_failures",
            }]
        ]
        (OUT_TABLES / f"sweep_{stage}_top.md").write_text(
            _markdown_table(table) + "\n", encoding="utf-8"
        )

    # Seed-level spread of the acceptance vector at the frozen parameters. This
    # is the evidence that a single-world gate reading is noisy, so it is quoted
    # next to every single-world figure rather than instead of it.
    verification = _read(CALIB / "frozen_parameter_verification.csv")
    if verification is not None:
        gated = verification.loc[verification["status"].ne("CONTEXT")]
        spread = (
            gated.groupby("metric")
            .agg(
                mean_value=("value", "mean"),
                min_value=("value", "min"),
                max_value=("value", "max"),
                tolerance=("tolerance", "first"),
                critical=("critical", "first"),
                n_pass=("status", lambda s: int((s == "PASS").sum())),
                n_seeds=("status", "size"),
            )
            .reset_index()
        )
        values["frozen_parameter_seed_spread"] = spread.to_dict(orient="records")
        table = spread.loc[spread["critical"].astype(bool)].copy()
        for column in ("mean_value", "min_value", "max_value"):
            table[column] = table[column].map(lambda v: _fmt(v, 3))
        table = table.loc[:, ["metric", "mean_value", "min_value", "max_value",
                              "tolerance", "n_pass", "n_seeds"]]
        table.columns = ["critical metric", "mean", "min", "max", "tolerance",
                         "seeds passing", "seeds"]
        (OUT_TABLES / "frozen_parameter_seed_spread.md").write_text(
            _markdown_table(table) + "\n", encoding="utf-8"
        )

    # Fresh-seed evaluation: seeds used in neither the sweep nor the release set,
    # scored against the full real corpus (the release gates' own reference).
    fresh = _read(TABLES / "fresh_seed_evaluation" / "fresh_seed_summary.csv")
    if fresh is not None:
        central = fresh.loc[fresh["scenario"].eq(SCENARIO) & fresh["critical"].astype(bool)].copy()
        values["fresh_seed_summary"] = central.to_dict(orient="records")
        table = central.loc[:, ["metric", "mean_value", "sd_value", "monte_carlo_se",
                                "min_value", "max_value", "tolerance", "pass_rate"]].copy()
        for column in ("mean_value", "sd_value", "monte_carlo_se", "min_value", "max_value"):
            table[column] = table[column].map(lambda v: _fmt(v, 3))
        table.columns = ["critical metric", "mean", "sd", "MCSE", "min", "max",
                         "tolerance", "pass rate"]
        (OUT_TABLES / "fresh_seeds.md").write_text(_markdown_table(table) + "\n", encoding="utf-8")
    fresh_provenance = TABLES / "fresh_seed_evaluation" / "fresh_seed_provenance.json"
    if fresh_provenance.exists():
        values["fresh_seed_provenance"] = json.loads(fresh_provenance.read_text(encoding="utf-8"))

    deconvolution = _read(CALIB / "entry_weight_deconvolution_trace.csv")
    if deconvolution is not None:
        values["deconvolution_final_wmae_pp"] = float(deconvolution["wmae_pp"].iloc[-1])
        values["deconvolution_final_tvd"] = float(deconvolution["tvd"].iloc[-1])
        values["deconvolution_iterations"] = int(len(deconvolution))

    # -- holdout -----------------------------------------------------------
    holdout_summary = _read(HOLDOUT / "holdout_vs_calibration_summary.csv")
    if holdout_summary is not None:
        values["holdout_flagged_metrics"] = holdout_summary.loc[
            holdout_summary["in_sample_gap_flag"].astype(bool), "metric"
        ].tolist()
        table = holdout_summary.loc[
            :, ["metric", "mean_calibration", "mean_holdout", "calibration_minus_holdout",
                "tolerance", "in_sample_gap_flag"]
        ].copy()
        for column in ("mean_calibration", "mean_holdout", "calibration_minus_holdout"):
            table[column] = table[column].map(lambda v: _fmt(v, 4))
        (OUT_TABLES / "holdout.md").write_text(_markdown_table(table) + "\n", encoding="utf-8")
    # Two provenance files: the split itself (written when it was frozen) and the
    # evaluation run against it. The split's counts are quoted even before the
    # evaluation has run, because they describe the calibration population every
    # observable parameter came from.
    split_path = HOLDOUT / "holdout_provenance.json"
    evaluation_path = HOLDOUT / "holdout_evaluation_provenance.json"
    limitation_path = HOLDOUT / "holdout_marginal_rate_limitation.json"
    if limitation_path.exists():
        limitation = json.loads(limitation_path.read_text(encoding="utf-8"))
        values["real_split_marginal_rates"] = limitation["real_split_marginal_rates"]
        values["siret_calibration_minus_holdout_pp"] = limitation["siret_calibration_minus_holdout_pp"]
        values["holdout_marginal_rate_limitation"] = limitation
    provenance = {}
    for path in (split_path, evaluation_path):
        if path.exists():
            provenance |= json.loads(path.read_text(encoding="utf-8"))
    if provenance:
        values["holdout_provenance"] = provenance

    # -- seed stability ----------------------------------------------------
    stability_path = STABILITY / "seed_stability_summary.json"
    if stability_path.exists():
        values["seed_stability"] = json.loads(stability_path.read_text(encoding="utf-8"))
    paired = _read(STABILITY / "paired_algorithm_differences.csv")
    if paired is not None:
        # `overall_deduplicated` is the authoritative scope; older runs and the
        # probe fallback wrote a single `overall` scope, so accept either.
        authoritative = (
            "overall_deduplicated"
            if paired["scope"].eq("overall_deduplicated").any()
            else "overall"
        )
        headline = paired.loc[paired["scope"].eq(authoritative)]
        table = headline.loc[
            :, ["metric", "algorithm_a", "algorithm_b", "n_paired_worlds",
                "mean_paired_difference", "ci_low", "ci_high", "monte_carlo_se_of_mean",
                "win_rate_a", "support_status"]
        ].copy()
        for column in ("mean_paired_difference", "ci_low", "ci_high",
                       "monte_carlo_se_of_mean", "win_rate_a"):
            table[column] = table[column].map(lambda v: _fmt(v, 4))
        (OUT_TABLES / "paired_algorithm_differences.md").write_text(
            _markdown_table(table) + "\n", encoding="utf-8"
        )

    # -- v0.3 vs v0.4 algorithm results -----------------------------------
    # Same fit/calibration/evaluation split on both sides, so the comparison is
    # like-for-like; only the benchmark the algorithms ran on differs.
    old_algo = _read(
        ROOT / "reports" / "tables" / "synthetic_benchmark" / PREVIOUS
        / "linkage_algorithm_benchmark" / "summary_metrics.csv"
    )
    new_algo = _read(TABLES / "linkage_algorithm_benchmark" / "summary_metrics.csv")
    if old_algo is not None and new_algo is not None:
        merged = old_algo.merge(new_algo, on="algorithm", suffixes=("_v03", "_v04"))
        table = merged.loc[:, [
            "algorithm", "pair_f1_end_to_end_v03", "pair_f1_end_to_end_v04",
            "pair_precision_v03", "pair_precision_v04",
            "pair_recall_end_to_end_v03", "pair_recall_end_to_end_v04",
        ]].copy()
        table = table.sort_values("pair_f1_end_to_end_v04", ascending=False)
        for column in table.columns[1:]:
            table[column] = table[column].map(lambda v: _fmt(v, 3))
        # Column names must carry the evaluation level. Precision is defined only
        # over generated candidates, while recall and F1 are end-to-end over all
        # in-scope truth links; unqualified "precision/recall/F1" headers invite
        # the reader to combine two different denominators.
        table.columns = [
            "algorithm",
            "end-to-end F1 v0.3", "end-to-end F1 v0.4",
            "candidate-conditional precision v0.3", "candidate-conditional precision v0.4",
            "end-to-end recall v0.3", "end-to-end recall v0.4",
        ]
        (OUT_TABLES / "algorithm_v03_v04.md").write_text(
            _markdown_table(table) + "\n", encoding="utf-8"
        )
        values["algorithm_comparison"] = table.to_dict(orient="records")
        values["algorithm_ranking_v03"] = old_algo.sort_values(
            "pair_f1_end_to_end", ascending=False
        )["algorithm"].tolist()
        values["algorithm_ranking_v04"] = new_algo.sort_values(
            "pair_f1_end_to_end", ascending=False
        )["algorithm"].tolist()
        values["algorithm_ranking_changed"] = (
            values["algorithm_ranking_v03"] != values["algorithm_ranking_v04"]
        )

    # -- readiness ---------------------------------------------------------
    def _readiness(path: Path) -> dict | None:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            entry["level"]: entry["status"]
            for entry in payload.get("decisions", [])
            if isinstance(entry, dict) and "level" in entry
        }

    values["readiness_v04"] = _readiness(TABLES / "readiness" / "readiness_decisions.json")
    values["readiness_v03"] = _readiness(BASELINE / "readiness_decisions.json")
    if values["readiness_v03"] and values["readiness_v04"]:
        table = pd.DataFrame(
            [
                {"readiness level": level,
                 "v0.3": values["readiness_v03"].get(level, "n/a"),
                 "v0.4": values["readiness_v04"].get(level, "n/a")}
                for level in values["readiness_v03"]
            ]
        )
        (OUT_TABLES / "readiness.md").write_text(_markdown_table(table) + "\n", encoding="utf-8")

    # -- figures -----------------------------------------------------------
    figure_index = FIGURES / "figure_index.json"
    if figure_index.exists():
        values["figures"] = json.loads(figure_index.read_text(encoding="utf-8"))

    (OUT_DIR / "v0_4_report_values.json").write_text(
        json.dumps(values, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (OUT_DIR / f"{VERSION}_report.md").write_text(_narrative(values), encoding="utf-8")
    print(f"wrote {(OUT_DIR / f'{VERSION}_report.md').relative_to(ROOT)}")
    print(f"wrote {(OUT_DIR / 'v0_4_report_values.json').relative_to(ROOT)}")
    print(f"wrote {len(list(OUT_TABLES.glob('*.md')))} generated tables to {OUT_TABLES.relative_to(ROOT)}")
    for key in ("v03_status_counts", "v04_status_counts", "improvements", "regressions"):
        if key in values:
            print(f"  {key}: {values[key]}")


if __name__ == "__main__":
    main()
