"""Generate configured synthetic benchmark scenario/world artifacts.

This script complements the v0.3 central sweep script. It does not tune or
select parameters; it only materializes already-versioned scenario
configurations under the standard
data/processed/synthetic_benchmark/<version>/<scenario>/world_XXX/corruption_YYY
tree. By default it refuses to overwrite existing artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.pipeline import generate_pilot  # noqa: E402
from boamp.synthetic.scenarios import VALID_SCENARIOS, load_benchmark_defaults, load_scenario  # noqa: E402
from boamp.synthetic.validation_framework.loaders import benchmark_output_dir  # noqa: E402

DEFAULT_VERSION = "v0_3_temporal_candidate_revision"
DEFAULT_REQUIRED_SCENARIOS = ("easier", "moderate", "difficult", "stress")


def _csv_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _int_csv_list(value: str) -> list[int]:
    out = []
    for part in _csv_list(value):
        out.append(int(part))
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--scenarios",
        default=",".join(DEFAULT_REQUIRED_SCENARIOS),
        help="Comma-separated scenario IDs. Defaults to the required benchmark scenarios.",
    )
    parser.add_argument(
        "--world-seeds",
        default="",
        help=(
            "Comma-separated latent-world seeds. Defaults to the benchmark default latent seed. "
            "Each seed becomes world_001, world_002, ..."
        ),
    )
    parser.add_argument(
        "--corruption-seeds",
        default="",
        help=(
            "Comma-separated corruption seeds. Defaults to benchmark corruption seed for one world, "
            "or world_seed + 1 when multiple world seeds are supplied."
        ),
    )
    parser.add_argument(
        "--n-buyers",
        type=int,
        default=None,
        help="Override benchmark_defaults.target_n_buyers.",
    )
    parser.add_argument(
        "--world-start-index",
        type=int,
        default=1,
        help="World/corruption index assigned to the first supplied seed. Use to resume a partial grid.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing output directories.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without writing artifacts.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional JSON path for the generation run manifest.",
    )
    return parser.parse_args()


def _resolve_seed_grid(args: argparse.Namespace, defaults) -> list[tuple[int, int, int, int]]:
    world_seeds = _int_csv_list(args.world_seeds) if args.world_seeds else [int(defaults.seed.latent_world_seed)]
    if args.corruption_seeds:
        corruption_seeds = _int_csv_list(args.corruption_seeds)
        if len(corruption_seeds) != len(world_seeds):
            raise ValueError("--corruption-seeds must have the same length as --world-seeds")
    elif len(world_seeds) == 1:
        corruption_seeds = [int(defaults.seed.corruption_seed)]
    else:
        corruption_seeds = [seed + 1 for seed in world_seeds]
    return [
        (idx, idx, world_seed, corruption_seed)
        for idx, (world_seed, corruption_seed) in enumerate(
            zip(world_seeds, corruption_seeds), start=args.world_start_index
        )
    ]


def main() -> None:
    args = parse_args()
    defaults = load_benchmark_defaults(ROOT)
    scenarios = _csv_list(args.scenarios)
    unknown = [scenario for scenario in scenarios if scenario not in VALID_SCENARIOS]
    if unknown:
        raise SystemExit(f"unknown scenario(s): {unknown}; expected one of {VALID_SCENARIOS}")

    seed_grid = _resolve_seed_grid(args, defaults)
    n_buyers = int(args.n_buyers or defaults.target_n_buyers)
    rows = []
    for scenario in scenarios:
        # Load now so missing/inherited configs fail before any write occurs.
        load_scenario(ROOT, scenario)
        for world_rep, corruption_rep, world_seed, corruption_seed in seed_grid:
            out_dir = benchmark_output_dir(
                ROOT, args.version, scenario, f"{world_rep:03d}", f"{corruption_rep:03d}"
            )
            exists = out_dir.exists()
            row = {
                "scenario": scenario,
                "world": f"{world_rep:03d}",
                "corruption": f"{corruption_rep:03d}",
                "world_seed": world_seed,
                "corruption_seed": corruption_seed,
                "n_buyers": n_buyers,
                "path": str(out_dir.relative_to(ROOT)),
                "status": "PLANNED",
            }
            if exists and not args.force:
                row["status"] = "SKIPPED_EXISTS"
                rows.append(row)
                continue
            if args.dry_run:
                row["status"] = "DRY_RUN_EXISTS" if exists else "DRY_RUN_CREATE"
                rows.append(row)
                continue
            generate_pilot(
                scenario,
                ROOT,
                n_buyers=n_buyers,
                world_seed=world_seed,
                corruption_seed=corruption_seed,
                benchmark_version=args.version,
                world_rep=world_rep,
                corruption_rep=corruption_rep,
            )
            row["status"] = "OVERWRITTEN" if exists else "GENERATED"
            rows.append(row)

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": args.version,
        "dry_run": args.dry_run,
        "force": args.force,
        "rows": rows,
    }
    manifest_path = args.manifest or (
        ROOT
        / "reports"
        / "tables"
        / "synthetic_benchmark"
        / args.version
        / "scenario_artifact_generation_manifest.json"
    )
    if not args.dry_run:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
