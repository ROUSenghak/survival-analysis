"""Run the BOAMP synthetic benchmark minimum validation suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.validation_framework import write_validation_outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v0_3_temporal_candidate_revision")
    parser.add_argument("--scenario", default="central_provisional")
    parser.add_argument("--world", default="001")
    parser.add_argument("--corruption", default="001")
    parser.add_argument("--strict-60m", action="store_true", help="Treat the 60-month runway discrepancy as release-blocking.")
    parser.add_argument(
        "--bootstrap-reps",
        type=int,
        default=200,
        help="Cluster-bootstrap replicates for equivalence intervals; 0 disables intervals, "
        "which downgrades affected checks from 'equivalent' to 'not obviously discrepant'.",
    )
    parser.add_argument(
        "--no-robustness",
        action="store_true",
        help="Skip the cross-scenario/seed sweep, which re-evaluates every generated replicate.",
    )
    parser.add_argument(
        "--no-replay",
        action="store_true",
        help="Skip regenerating the benchmark from its recorded seeds and configuration, which "
        "downgrades the canonical replay check to inconclusive.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = write_validation_outputs(
        ROOT,
        args.version,
        args.scenario,
        world=args.world,
        corruption=args.corruption,
        output_dir=args.output_dir,
        strict_60m=args.strict_60m,
        bootstrap_reps=args.bootstrap_reps,
        robustness=not args.no_robustness,
        replay=not args.no_replay,
    )
    gates = result["gates"]
    summary = {
        "output_dir": str(result["output_dir"].relative_to(ROOT) if result["output_dir"].is_relative_to(ROOT) else result["output_dir"]),
        "overall_status": result["manifest"]["overall_status"],
        "blocking_gates": gates.loc[gates["critical"] & gates["status"].eq("FAIL"), "gate"].tolist(),
        "gate_statuses": gates.set_index("gate")["status"].to_dict(),
        "n_discrepancies": int(len(result["discrepancies"])),
        "n_metric_failures": result["manifest"]["n_metric_failures"],
        "n_metric_failures_in_noncritical_gates": result["manifest"][
            "n_metric_failures_in_noncritical_gates"
        ],
        "canonical_replay_checked": result["manifest"]["canonical_replay_checked"],
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
