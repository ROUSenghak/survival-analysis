"""Select the frozen v0.4 mechanism parameters from a completed sweep.

Kept separate from the sweep itself so the selection rule is explicit, auditable
and re-runnable without regenerating any world. The rule, in order:

1. prefer candidates that fail no critical acceptance metric;
2. among the rest, prefer the fewest failing critical metrics -- a candidate that
   misses one is strictly better than one that misses two, regardless of the
   summed deviation, which can be dominated by non-critical terms;
3. break remaining ties on the tolerance-normalised total deviation.

The chosen row's parameters are written into `mechanism_parameters.json` together
with the selection status, so a later reader can see whether the release was
frozen on a fully-passing candidate or on a documented best effort.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from write_v0_4_scenario_config import (  # noqa: E402
    load_mechanism_parameters,
    save_mechanism_parameters,
)

VERSION = "v0_4_population_alias_revision"
CALIB = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION / "calibration"

SCOPED_KEYS = (
    "recurrence_propensity_multiplier",
    "scoped_need_probability_high",
    "scoped_buyer_affinity_share",
)
DIRECT_KEYS = (
    "target_n_buyers",
    "dominant_alias_share",
    "dispersion_tempering",
    "needs_per_buyer_mean_used",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="scoped")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = CALIB / f"mechanism_parameter_sweep_{args.stage}.csv"
    if not path.exists():
        raise SystemExit(f"{path} not found; run the {args.stage} sweep first")
    sweep = pd.read_csv(path)
    # Count criticals that fail on *any* development seed when the sweep recorded
    # them, falling back to the mean-vector failures for older single-seed sweeps.
    failure_column = (
        "critical_failures_any_seed" if "critical_failures_any_seed" in sweep.columns
        else "critical_failures"
    )
    sweep["n_critical_failures"] = (
        sweep[failure_column].fillna("").astype(str).str.split(";").map(
            lambda parts: sum(1 for part in parts if part.strip())
        )
    )
    ranked = sweep.sort_values(["n_critical_failures", "score"]).reset_index(drop=True)
    best = ranked.iloc[0]
    if bool(best.get("accepted_every_seed", False)):
        status = "ACCEPTED_EVERY_SEED"
    elif bool(best["accepted"]):
        status = "ACCEPTED_ON_MEAN_ONLY"
    else:
        status = "BEST_EFFORT_NO_FULL_PASS"

    mechanism = load_mechanism_parameters()
    for key in DIRECT_KEYS:
        if key in best.index and pd.notna(best[key]):
            target = "needs_per_buyer_mean" if key == "needs_per_buyer_mean_used" else key
            value = best[key]
            mechanism[target] = int(value) if target == "target_n_buyers" else float(value)
    scoped = dict(mechanism["scoped_candidate_environment"])
    for key in SCOPED_KEYS:
        if key in best.index and pd.notna(best[key]):
            scoped[key] = float(best[key])
    mechanism["scoped_candidate_environment"] = scoped
    mechanism["selection_note"] = (
        f"stage {args.stage}; candidate {int(best['candidate'])} of {len(sweep)}; status {status}; "
        f"{int(best['n_critical_failures'])} critical metric(s) failing on at least one "
        f"development seed ({best[failure_column] if isinstance(best[failure_column], str) else 'none'}); "
        f"tolerance-normalised deviation {float(best['score']):.3f}; selected "
        f"{datetime.now(timezone.utc).date()} by scripts/select_v0_4_mechanism_parameters.py on the "
        f"joint observable acceptance vector against calibration-split real BOAMP"
    )

    print(f"ranked {len(sweep)} candidates from {path.relative_to(ROOT)}")
    columns = [c for c in (
        "candidate", "target_n_buyers", "dominant_alias_share", "dispersion_tempering",
        *SCOPED_KEYS, "n_notices", "n_seeds", "n_critical_failures", "score",
        "accepted_every_seed", failure_column,
    ) if c in ranked.columns]
    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 60)
    print(ranked.loc[:4, columns].to_string(index=False))
    print(f"\nselected candidate {int(best['candidate'])} ({status})")
    if args.dry_run:
        print("dry run: mechanism_parameters.json not written")
        return
    save_mechanism_parameters(mechanism)
    print("wrote mechanism_parameters.json; rerun scripts/write_v0_4_scenario_config.py")


if __name__ == "__main__":
    main()
