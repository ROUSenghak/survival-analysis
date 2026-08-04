"""Out-of-sample observable-fidelity evaluation on held-out real BOAMP buyers.

Every observable parameter of the v0.4 generator was estimated from the 70%
*calibration* side of `config/synthetic/real_holdout_buyer_keys.csv`. This script
scores the generated worlds against the 30% *holdout* side, which no calibration,
sweep or deconvolution step ever read, and against the calibration side for
comparison. A fidelity metric that is close on calibration buyers and far on
holdout buyers is in-sample tuning; one that is close on both is not.

Run this ONCE, after the parameters are frozen. Re-running it and then changing a
parameter would convert the holdout into a second calibration set and destroy the
only out-of-sample evidence the benchmark has.

Reported caveats, both of which are stated on every figure and table:
* The holdout carries 22,501 of 84,623 real notices, so its own quantile
  estimates are noisier than the calibration side's. Only scale-free metrics are
  compared.
* The real candidate-environment baseline is filtered to holdout buyers, which
  shrinks its source count; candidate metrics are reported as rates and
  quantiles, never as counts.
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

from boamp.synthetic.acceptance import evaluate_observed  # noqa: E402
from boamp.synthetic.holdout import CALIBRATION, HOLDOUT, load_real_buyer_holdout  # noqa: E402
from boamp.synthetic.validation_framework.loaders import (  # noqa: E402
    available_replicates,
    load_benchmark_data,
)

VERSION = "v0_4_population_alias_revision"
OUT = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION / "holdout"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--scenario", default="central_provisional")
    parser.add_argument("--max-worlds", type=int, default=10)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    holdout = load_real_buyer_holdout(ROOT)
    replicates = [
        (scenario, world, corruption)
        for scenario, world, corruption in available_replicates(ROOT, args.version)
        if scenario == args.scenario
    ][: args.max_worlds]
    if not replicates:
        raise SystemExit(f"no generated artifacts for {args.version}/{args.scenario}")

    frames = []
    for scenario, world, corruption in replicates:
        data = load_benchmark_data(ROOT, args.version, scenario, world, corruption)
        for split in (CALIBRATION, HOLDOUT):
            result = evaluate_observed(data.observed, ROOT, split=split)
            frame = result.to_frame()
            frame.insert(0, "split", split)
            frame.insert(0, "world", world)
            frame.insert(0, "scenario", scenario)
            frames.append(frame)
        print(f"  scored {scenario}/world_{world} on both splits")

    long = pd.concat(frames, ignore_index=True)
    long.to_csv(OUT / "holdout_fidelity_long.csv", index=False)

    gated = long.loc[long["status"].ne("CONTEXT")]
    summary = (
        gated.groupby(["metric", "split"])
        .agg(
            mean_value=("value", "mean"),
            sd_value=("value", "std"),
            min_value=("value", "min"),
            max_value=("value", "max"),
            mean_real=("real", "mean"),
            mean_synthetic=("synthetic", "mean"),
            tolerance=("tolerance", "first"),
            critical=("critical", "first"),
            n_worlds=("value", "size"),
        )
        .reset_index()
    )
    summary["pass_rate"] = (
        gated.assign(passed=gated["status"].eq("PASS"))
        .groupby(["metric", "split"])["passed"]
        .mean()
        .reindex(pd.MultiIndex.from_frame(summary[["metric", "split"]]))
        .to_numpy()
    )
    wide = summary.pivot(index="metric", columns="split", values="mean_value")
    wide.columns = [f"mean_{c}" for c in wide.columns]
    wide["calibration_minus_holdout"] = wide.get("mean_calibration") - wide.get("mean_holdout")
    wide = wide.join(
        summary.drop_duplicates("metric").set_index("metric")[["tolerance", "critical"]]
    )
    # A metric whose deviation is much larger out of sample than in sample is the
    # signature of in-sample tuning. The threshold is half a tolerance, chosen so
    # it flags gaps that would matter for a pass/fail decision.
    wide["in_sample_gap_flag"] = (
        wide["calibration_minus_holdout"].abs() > 0.5 * wide["tolerance"]
    )
    wide.reset_index().to_csv(OUT / "holdout_vs_calibration_summary.csv", index=False)
    summary.to_csv(OUT / "holdout_fidelity_summary.csv", index=False)

    flagged = wide.loc[wide["in_sample_gap_flag"]].index.tolist()
    provenance = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": args.version,
        "scenario": args.scenario,
        "n_worlds": len(replicates),
        "holdout_sha256": holdout.content_sha256,
        "n_calibration_buyer_keys": int(holdout.assignments["split"].eq(CALIBRATION).sum()),
        "n_holdout_buyer_keys": int(holdout.assignments["split"].eq(HOLDOUT).sum()),
        "metrics_with_material_in_sample_gap": flagged,
        "interpretation": (
            "Metrics absent from the flagged list behave the same on real buyers the generator "
            "was calibrated on and on real buyers it never saw, which is evidence against pure "
            "in-sample tuning. Flagged metrics are reported as in-sample only."
        ),
        "limitations": [
            "The holdout carries roughly a quarter of real notices, so its quantile estimates "
            "are noisier; only scale-free metrics are compared.",
            "The real candidate baseline is filtered to holdout buyers, reducing its source "
            "count; candidate metrics are compared as rates and quantiles, never as counts.",
            "Synthetic buyers are not split: the same synthetic corpus is scored against both "
            "real sides, so this tests parameter transfer, not synthetic-side generalisation.",
        ],
    }
    (OUT / "holdout_evaluation_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\nscored {len(replicates)} worlds on both real splits")
    print(f"metrics with a material calibration-vs-holdout gap: {flagged or 'none'}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
