"""Bounded development sweep for the v0.4 mechanism parameters.

Two stages, both scored only on observable BOAMP quantities computed against the
*calibration* side of the frozen real buyer-key holdout:

1. **Entry-weight deconvolution.** The emergent publication-year distribution is
   the convolution of buyer entry time with the successor cascade and the
   window's right censoring, so the entry weights that reproduce a target year
   profile are not that profile. A damped multiplicative fixed point
   (`w <- w * (target / achieved) ** damping`, renormalised) recovers them in a
   handful of iterations. This is the standard iterative-proportional-fitting
   update, and it converges here because the map from entry weight to notice
   share is monotone and near-diagonal.

2. **Bounded grid sweep** over the mechanism parameters that have no observable
   counterpart: buyer population size, needs per buyer, alias usage, activity
   dispersion tempering, and the carried scoped-candidate-environment block.
   Every candidate is scored on the *whole* acceptance vector
   (`boamp.synthetic.acceptance`); a candidate that fixes one metric while
   breaking another is rejected and the rejection is recorded with its numbers.

Nothing here reads accepted links, linkage scores, thresholds, algorithm
rankings, precision/recall/F1 or survival results. Candidate-environment gates
are observable properties of the real corpus's own blocking output, not linkage
accuracy.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.acceptance import (  # noqa: E402
    ACCEPTANCE_TOLERANCES,
    evaluate_observed,
    load_real_reference,
)
from boamp.synthetic.holdout import CALIBRATION  # noqa: E402
from boamp.synthetic.pipeline import generate_clean_world, generate_observed_world  # noqa: E402
from boamp.synthetic.scenarios import load_benchmark_defaults, load_scenario  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from write_v0_4_scenario_config import (  # noqa: E402
    load_mechanism_parameters,
    save_mechanism_parameters,
)

VERSION = "v0_4_population_alias_revision"
FAMILY = "v0_4"
SCENARIO = "central_provisional"
OUT = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION / "calibration"

# Development seeds. The fresh-seed evaluation deliberately uses none of these.
DEV_SEEDS: tuple[tuple[int, int], ...] = ((20260721, 20260722), (20260731, 20260732))

DECONVOLUTION_ITERATIONS = 8
DECONVOLUTION_DAMPING = 0.85
# Deconvolve at the buyer population the release will actually use. An earlier
# pass ran at 2,500 buyers for speed and its weights did not transfer: the
# truncated activity tail changes which buyers are alive in which year, so the
# entry-to-notice-year map is population-dependent.
DECONVOLUTION_N_BUYERS = None


def _apply_mechanism(scenario, mechanism: dict):
    """Overlay one candidate parameter set onto the resolved v0.4 scenario."""
    scenario = copy.deepcopy(scenario)
    activity = scenario.buyers.activity_model
    activity.dispersion_tempering = float(mechanism["dispersion_tempering"])
    activity.span_jitter_concentration = float(mechanism["span_jitter_concentration"])
    if mechanism.get("entry_year_weights"):
        activity.entry_year_weights = {
            int(k): float(v) for k, v in mechanism["entry_year_weights"].items()
        }
    scenario.needs.needs_per_buyer_mean = float(mechanism["needs_per_buyer_mean"])
    scenario.buyer_names.persistent_aliases.dominant_alias_share = float(
        mechanism["dominant_alias_share"]
    )
    scenario.identifiers.conditional_siret_presence.presence_scale = float(
        mechanism["presence_scale"]
    )
    scoped = scenario.recurrence.scoped_candidate_environment
    for key, value in mechanism["scoped_candidate_environment"].items():
        setattr(scoped, key, value)
    return scenario


def _run_world(mechanism: dict, world_seed: int, corruption_seed: int, base_scenario):
    scenario = _apply_mechanism(base_scenario, mechanism)
    world = generate_clean_world(
        SCENARIO, ROOT, int(mechanism["target_n_buyers"]), world_seed,
        scenario_override=scenario, config_family=FAMILY,
    )
    observed, _log = generate_observed_world(
        world, SCENARIO, ROOT, corruption_seed, scenario_override=scenario, config_family=FAMILY,
    )
    return observed


# ---------------------------------------------------------------------------
# stage 1: entry-weight deconvolution
# ---------------------------------------------------------------------------


def deconvolve_entry_weights(mechanism: dict, base_scenario) -> tuple[dict, pd.DataFrame]:
    reference = load_real_reference(str(ROOT), CALIBRATION)
    target = reference.year_share.copy()
    target.index = target.index.astype(int)
    target = target.sort_index()

    weights = mechanism.get("entry_year_weights")
    weights = (
        {int(k): float(v) for k, v in weights.items()}
        if weights
        else {int(year): float(share) for year, share in target.items()}
    )

    trace = []
    working = dict(mechanism)
    if DECONVOLUTION_N_BUYERS is not None:
        working["target_n_buyers"] = DECONVOLUTION_N_BUYERS
    for iteration in range(DECONVOLUTION_ITERATIONS):
        working["entry_year_weights"] = weights
        observed = _run_world(working, DEV_SEEDS[0][0], DEV_SEEDS[0][1], base_scenario)
        achieved = (
            pd.to_datetime(observed["publication_date"]).dt.year.value_counts(normalize=True).sort_index()
        )
        achieved = achieved.reindex(target.index, fill_value=1e-6)
        wmae = float((target / target.sum() * (achieved - target).abs() * 100).sum())
        tvd = float(0.5 * (achieved - target).abs().sum())
        trace.append(
            {
                "iteration": iteration,
                "wmae_pp": wmae,
                "tvd": tvd,
                "n_notices": int(len(observed)),
                **{f"achieved_{year}": float(achieved.loc[year]) for year in target.index},
                **{f"weight_{year}": float(weights[int(year)]) for year in target.index},
            }
        )
        print(f"  deconvolution iter {iteration}: WMAE={wmae:.3f}pp TVD={tvd:.4f} n={len(observed)}")
        if wmae <= 0.75:
            break
        updated = {
            int(year): weights[int(year)]
            * float((target.loc[year] / max(achieved.loc[year], 1e-6)) ** DECONVOLUTION_DAMPING)
            for year in target.index
        }
        total = sum(updated.values())
        weights = {year: value / total for year, value in updated.items()}

    mechanism = dict(mechanism)
    mechanism["entry_year_weights"] = weights
    return mechanism, pd.DataFrame(trace)


# ---------------------------------------------------------------------------
# stage 2: bounded grid over the mechanism parameters
# ---------------------------------------------------------------------------


# Corpus size is held near the real corpus's 84,623 notices while the buyer
# population varies, so `target_n_buyers` sweeps *concentration* rather than
# scale. The reference point is the deconvolution run: 6,000 buyers at 7.3 needs
# per buyer produced ~88.4k notices, so needs per buyer is scaled inversely.
_NOTICES_PER_BUYER_NEED_REFERENCE = (6000, 7.3, 88438)
_TARGET_N_NOTICES = 84623


def _needs_per_buyer_for(n_buyers: int) -> float:
    ref_buyers, ref_needs, ref_notices = _NOTICES_PER_BUYER_NEED_REFERENCE
    return round(ref_needs * (ref_buyers / n_buyers) * (_TARGET_N_NOTICES / ref_notices), 3)


def population_grid(base: dict) -> list[dict]:
    """Stage A: how concentrated the buyer population and its names are.

    `target_n_buyers` sets how concentrated the observed buyer-key population is
    and `dominant_alias_share` how often a buyer publishes under a non-primary
    name. Everything else in the model is calibrated, not swept.
    """
    candidates = []
    for n_buyers in (4500, 5500, 6500):
        for dominant_alias in (0.55, 0.70, 0.82):
            for multiplier in (1.30, 1.60):
                candidate = copy.deepcopy(base)
                candidate["target_n_buyers"] = n_buyers
                candidate["needs_per_buyer_mean"] = _needs_per_buyer_for(n_buyers)
                candidate["dominant_alias_share"] = dominant_alias
                candidate["scoped_candidate_environment"] = dict(
                    base["scoped_candidate_environment"]
                ) | {"recurrence_propensity_multiplier": multiplier}
                candidates.append(candidate)
    return candidates


def scoped_grid(base: dict) -> list[dict]:
    """Stage B: the scoped-candidate block, at the population stage A selected.

    v0.3 tuned this block against a corpus whose 19,200 latent buyers fragmented
    into 10,532 observed keys. `scoped_need_probability_high` concentrates
    digital-scope needs into the `scoped_buyer_affinity_share` of buyers that
    have an affinity for them; at v0.3's scale that produced a plausible digital
    neighbourhood, but at a correctly-sized buyer population the same clustering
    piles the whole digital corpus onto a few large buyers and candidate sets hit
    the production cap. Total digital-source volume is unaffected -- the sampler
    renormalises the non-affinity probability so the scoped division mass is
    preserved -- so this grid trades concentration, not scale.
    """
    candidates = []
    for high_probability in (0.22, 0.30, 0.40):
        for affinity in (0.08, 0.12):
            for multiplier in (1.15, 1.45):
                candidate = copy.deepcopy(base)
                # Alias usage is raised here too: the calibrated alias-set sizes
                # are latent, but the metric that reads them
                # (name_variants_per_buyer) only ever sees the forms a buyer
                # actually published, so a buyer that almost always uses its
                # primary name looks like a buyer with one alias.
                candidate["dominant_alias_share"] = 0.55
                candidate["scoped_candidate_environment"] = dict(
                    base["scoped_candidate_environment"]
                ) | {
                    "scoped_need_probability_high": high_probability,
                    "scoped_buyer_affinity_share": affinity,
                    "recurrence_propensity_multiplier": multiplier,
                }
                candidates.append(candidate)
    return candidates


def concentration_grid(base: dict) -> list[dict]:
    """Stage C: the last lever on the activity q99, at the selected scoped block.

    After stage B every acceptance metric except `activity_relative_q99_abs_diff`
    is inside tolerance, and q99 is short (the synthetic upper-middle tail is
    still slightly flatter than real). `dispersion_tempering` exponentiates the
    log activity weights, so values above 1 sharpen the calibrated distribution
    without changing its family; a smaller buyer population concentrates the same
    notice volume onto fewer keys. Both push candidate density up, which is why
    this runs last and is scored on the whole vector rather than on q99 alone.
    """
    candidates = []
    for tempering in (1.00, 1.08, 1.16):
        for n_buyers in (5000, 5500):
            candidate = copy.deepcopy(base)
            candidate["dispersion_tempering"] = tempering
            candidate["target_n_buyers"] = n_buyers
            candidate["needs_per_buyer_mean"] = _needs_per_buyer_for(n_buyers)
            candidates.append(candidate)
    return candidates


GRIDS = {
    "population": population_grid,
    "scoped": scoped_grid,
    "concentration": concentration_grid,
}



def _aggregate(results: list) -> "object":
    """Mean acceptance vector over the development seeds.

    Averaging the signed deviations rather than the pass/fail labels keeps the
    direction of each miss, and a metric that fails on some seeds and passes on
    others shows up as a mean near its tolerance instead of being silently
    resolved either way. `accepted_every_seed` is recorded separately so the
    difference between "passes on average" and "passes always" is never lost.
    """
    from boamp.synthetic.acceptance import AcceptanceResult

    def mean_of(attribute: str) -> dict:
        keys = {k for r in results for k in getattr(r, attribute)}
        out = {}
        for key in keys:
            values = [
                getattr(r, attribute).get(key)
                for r in results
                if getattr(r, attribute).get(key) is not None
            ]
            values = [v for v in values if np.isfinite(v)]
            out[key] = float(np.mean(values)) if values else float("nan")
        return out

    return AcceptanceResult(
        values=mean_of("values"),
        real=mean_of("real"),
        synthetic=mean_of("synthetic"),
        context=mean_of("context"),
    )


def score(result) -> float:
    """Sum of tolerance-normalised absolute deviations, critical metrics doubled.

    A single scalar is only used to *order* accepted candidates; acceptance
    itself is the all-critical-metrics-pass rule, so a good score can never buy
    its way past a broken critical gate.
    """
    total = 0.0
    for tolerance in ACCEPTANCE_TOLERANCES:
        value = result.values.get(tolerance.metric)
        if value is None or not np.isfinite(value):
            continue
        ratio = abs(value) / tolerance.tolerance
        total += ratio * (2.0 if tolerance.critical else 1.0)
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-deconvolution", action="store_true")
    parser.add_argument("--stage", choices=sorted(GRIDS), default="population")
    parser.add_argument(
        "--n-seeds", type=int, default=len(DEV_SEEDS),
        help="Development seeds each candidate is scored on. Selection uses the mean.",
    )
    parser.add_argument("--max-candidates", type=int, default=None)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    base_scenario = load_scenario(ROOT, SCENARIO, family=FAMILY)
    defaults = load_benchmark_defaults(ROOT, family=FAMILY)
    mechanism = load_mechanism_parameters()
    mechanism.setdefault("target_n_buyers", defaults.target_n_buyers)

    if not args.skip_deconvolution:
        print("stage 1: entry-weight deconvolution against observable year shares")
        mechanism, trace = deconvolve_entry_weights(mechanism, base_scenario)
        trace.to_csv(OUT / "entry_weight_deconvolution_trace.csv", index=False)
        save_mechanism_parameters(mechanism)

    print(f"stage 2: bounded mechanism-parameter sweep ({args.stage})")
    candidates = GRIDS[args.stage](mechanism)
    if args.max_candidates:
        candidates = candidates[: args.max_candidates]

    rows = []
    detail_frames = []
    best = None
    seeds = DEV_SEEDS[: max(1, args.n_seeds)]
    for index, candidate in enumerate(candidates):
        started = time.time()
        # Score every candidate on *all* development seeds and aggregate. A
        # single world is not enough: the same parameter set was measured with
        # zero critical failures on one development seed and two on another,
        # because the buyer-level identifier random effect and the truncated
        # activity tail both put real between-world variance into corpus-level
        # rates. Selecting on one world selects that world's noise.
        results = [
            evaluate_observed(
                _run_world(candidate, world_seed, corruption_seed, base_scenario),
                ROOT, split=CALIBRATION,
            )
            for world_seed, corruption_seed in seeds
        ]
        n_notices = 0
        candidate_score = float(np.mean([score(r) for r in results]))
        result = _aggregate(results)
        row = {
            "candidate": index,
            "target_n_buyers": candidate["target_n_buyers"],
            "needs_per_buyer_mean": candidate["needs_per_buyer_mean"],
            "dominant_alias_share": candidate["dominant_alias_share"],
            "dispersion_tempering": candidate["dispersion_tempering"],
            "needs_per_buyer_mean_used": candidate["needs_per_buyer_mean"],
            "recurrence_propensity_multiplier": candidate["scoped_candidate_environment"][
                "recurrence_propensity_multiplier"
            ],
            "scoped_need_probability_high": candidate["scoped_candidate_environment"][
                "scoped_need_probability_high"
            ],
            "scoped_buyer_affinity_share": candidate["scoped_candidate_environment"][
                "scoped_buyer_affinity_share"
            ],
            "n_notices": int(result.context.get("n_synthetic_notices", 0)),
            "n_seeds": len(seeds),
            "score": candidate_score,
            "worst_seed_score": float(np.max([score(r) for r in results])),
            "accepted": result.accepted,
            "accepted_every_seed": all(r.accepted for r in results),
            "critical_failures": ";".join(result.critical_failures),
            "critical_failures_any_seed": ";".join(
                sorted({m for r in results for m in r.critical_failures})
            ),
            "failures": ";".join(result.failures),
            "seconds": round(time.time() - started, 1),
            **{f"m_{k}": v for k, v in result.values.items()},
        }
        rows.append(row)
        for seed_index, seed_result in enumerate(results):
            detail = seed_result.to_frame()
            detail.insert(0, "world_seed", seeds[seed_index][0])
            detail.insert(0, "candidate", index)
            detail_frames.append(detail)
        mean_detail = result.to_frame()
        mean_detail.insert(0, "world_seed", "MEAN")
        mean_detail.insert(0, "candidate", index)
        detail_frames.append(mean_detail)
        status = (
            "ACCEPT_ALL_SEEDS" if row["accepted_every_seed"]
            else "ACCEPT_ON_MEAN" if result.accepted
            else "REJECT"
        )
        print(
            f"  [{index + 1}/{len(candidates)}] n_buyers={candidate['target_n_buyers']} "
            f"alias={candidate['dominant_alias_share']} temper={candidate['dispersion_tempering']} "
            f"mult={row['recurrence_propensity_multiplier']} "
            f"high={row['scoped_need_probability_high']} aff={row['scoped_buyer_affinity_share']} "
            f"-> {status} score={candidate_score:.2f} ({row['seconds']}s) "
            f"any-seed criticals: {row['critical_failures_any_seed'] or 'none'}"
        )
        if row["accepted_every_seed"] and (best is None or candidate_score < best[1]):
            best = (candidate, candidate_score, index)

    if not rows:
        print("no candidates evaluated; nothing to select")
        return

    sweep = pd.DataFrame(rows)
    sweep.to_csv(OUT / f"mechanism_parameter_sweep_{args.stage}.csv", index=False)
    pd.concat(detail_frames, ignore_index=True).to_csv(
        OUT / f"mechanism_parameter_sweep_{args.stage}_detail.csv", index=False
    )

    if best is None:
        # Fall back among rejected candidates and say so loudly; silently
        # promoting a failing candidate would be exactly the kind of
        # PASS-manufacturing this revision is not allowed to do.
        #
        # Rank by *how many* critical metrics fail before total deviation: a
        # candidate that misses one critical metric is strictly preferable to one
        # that misses two, even if the second has a slightly smaller summed
        # deviation, because the summed score can be dominated by non-critical
        # terms.
        sweep["n_critical_failures"] = (
            sweep["critical_failures"].fillna("").str.split(";").map(
                lambda parts: sum(1 for part in parts if part.strip())
            )
        )
        fallback = sweep.sort_values(["n_critical_failures", "score"]).iloc[0]
        print(
            "\nNO CANDIDATE PASSED EVERY CRITICAL GATE. "
            f"Lowest total deviation is candidate {int(fallback['candidate'])} "
            f"(score {fallback['score']:.2f}, critical failures: {fallback['critical_failures']})."
        )
        best = (candidates[int(fallback["candidate"])], float(fallback["score"]), int(fallback["candidate"]))
        selected_status = "BEST_EFFORT_NO_FULL_PASS"
    else:
        selected_status = "ACCEPTED"

    selected, selected_score, selected_index = best
    selected = dict(selected)
    selected["selection_note"] = (
        f"selected by scripts/sweep_v0_4_mechanism_parameters.py on {datetime.now(timezone.utc).date()}; "
        f"stage {args.stage}; candidate {selected_index} of {len(candidates)}; status {selected_status}; "
        f"tolerance-normalised deviation {selected_score:.3f}; scored on the joint observable "
        f"acceptance vector against calibration-split real BOAMP"
    )
    save_mechanism_parameters(selected)
    print(f"\nselected candidate {selected_index} ({selected_status}), score {selected_score:.3f}")
    print("rerun scripts/write_v0_4_scenario_config.py to write the selected values into the family")


if __name__ == "__main__":
    main()
