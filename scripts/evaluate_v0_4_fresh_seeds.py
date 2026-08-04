"""Score the fresh-seed evaluation set against real BOAMP. Run once, no retuning.

The seeds used here appear in neither the development sweep nor the release set.
Their only purpose is to answer one question: do the frozen parameters behave on
worlds nobody looked at while choosing them?

The reference is the **full** real corpus, matching the validation framework's own
gate reference, so these numbers are directly comparable to the release gates
rather than to the calibration-split figures the sweep used.

Nothing here may be fed back into parameter selection. If a metric looks bad, it
is reported as a fresh-seed result.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.acceptance import evaluate_observed  # noqa: E402
from boamp.synthetic.validation_framework.loaders import (  # noqa: E402
    available_replicates,
    load_benchmark_data,
)

RELEASE_VERSION = "v0_4_population_alias_revision"
FRESH_VERSION = "v0_4_fresh_seed_evaluation"
OUT = ROOT / "reports" / "tables" / "synthetic_benchmark" / RELEASE_VERSION / "fresh_seed_evaluation"

# Seeds used while choosing the parameters. Recorded here so the disjointness of
# the fresh set is checkable rather than asserted.
DEVELOPMENT_SEEDS = {20260721, 20260731}
RELEASE_SEEDS = {
    20260721, 20260731, 20260810, 20260820, 20260830,
    20260909, 20260919, 20260929, 20261009, 20261019,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=FRESH_VERSION)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    replicates = available_replicates(ROOT, args.version)
    if not replicates:
        raise SystemExit(f"no generated artifacts for {args.version}")

    frames, seeds = [], set()
    for scenario, world, corruption in replicates:
        data = load_benchmark_data(ROOT, args.version, scenario, world, corruption)
        seeds.add(int(data.metadata["world_seed"]))
        # split=None -> the full real corpus, the same reference the release
        # validation gates use.
        result = evaluate_observed(data.observed, ROOT, split=None)
        frame = result.to_frame()
        frame.insert(0, "world_seed", int(data.metadata["world_seed"]))
        frame.insert(0, "world", world)
        frame.insert(0, "scenario", scenario)
        frames.append(frame)
        print(f"  scored {scenario}/world_{world} (seed {data.metadata['world_seed']})")

    long = pd.concat(frames, ignore_index=True)
    long.to_csv(OUT / "fresh_seed_metrics_long.csv", index=False)

    gated = long.loc[long["status"].ne("CONTEXT")]
    summary = (
        gated.groupby(["scenario", "metric"])
        .agg(
            mean_value=("value", "mean"),
            sd_value=("value", "std"),
            min_value=("value", "min"),
            max_value=("value", "max"),
            tolerance=("tolerance", "first"),
            critical=("critical", "first"),
            n_worlds=("value", "size"),
            n_pass=("status", lambda s: int((s == "PASS").sum())),
        )
        .reset_index()
    )
    summary["pass_rate"] = summary["n_pass"] / summary["n_worlds"]
    # Monte Carlo standard error of the reported mean, so a fresh-seed mean is
    # never quoted as if it were exact.
    summary["monte_carlo_se"] = summary["sd_value"] / np.sqrt(summary["n_worlds"].clip(lower=1))
    summary.to_csv(OUT / "fresh_seed_summary.csv", index=False)

    central = summary.loc[summary["scenario"].eq("central_provisional")]
    critical = central.loc[central["critical"].astype(bool)]
    provenance = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "fresh_version": args.version,
        "release_version": RELEASE_VERSION,
        "real_reference": "full prepared corpus (same reference as the release validation gates)",
        "n_artifacts": len(replicates),
        "scenarios": sorted({scenario for scenario, _, _ in replicates}),
        "fresh_world_seeds": sorted(seeds),
        "disjoint_from_development_seeds": bool(not (seeds & DEVELOPMENT_SEEDS)),
        "disjoint_from_release_seeds": bool(not (seeds & RELEASE_SEEDS)),
        "central_critical_pass_rates": dict(
            zip(critical["metric"], critical["pass_rate"].round(3), strict=False)
        ),
        "central_critical_means": dict(
            zip(critical["metric"], critical["mean_value"].round(4), strict=False)
        ),
        "rule": (
            "Run once, after the parameters were frozen. No parameter was changed after these "
            "numbers were produced."
        ),
    }
    (OUT / "fresh_seed_provenance.json").write_text(
        json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8"
    )

    pd.set_option("display.width", 200)
    print(f"\nfresh seeds {sorted(seeds)}; disjoint from development: "
          f"{provenance['disjoint_from_development_seeds']}, from release: "
          f"{provenance['disjoint_from_release_seeds']}")
    print("\ncentral_provisional, critical metrics, full-corpus reference:")
    print(
        critical[["metric", "mean_value", "sd_value", "monte_carlo_se", "min_value",
                  "max_value", "tolerance", "pass_rate"]].round(3).to_string(index=False)
    )
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
