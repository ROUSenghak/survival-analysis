"""Generate the v0.4 population/alias-revision synthetic benchmark.

Materialises the release artifact tree for `v0_4_population_alias_revision` from
the already-selected v0.4 configuration family. This script selects nothing: the
observable parameters come from `scripts/calibrate_v0_4_observables.py` and the
mechanism parameters from `scripts/sweep_v0_4_mechanism_parameters.py`, both of
which must have run first. Keeping selection out of the release generator is what
makes the fresh-seed evaluation meaningful -- the seeds change, the parameters
cannot.

v0.3 artifacts, configuration and reports are never touched.

Order:
  1. record the conditional-observation parameter table actually used
  2. clean_sanity smoke world
  3. central_provisional + the four required scenarios, over the release seeds
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.conditional_observation import build_conditional_observation_model  # noqa: E402
from boamp.synthetic.pipeline import generate_pilot  # noqa: E402
from boamp.synthetic.scenarios import load_benchmark_defaults, load_scenario  # noqa: E402
from boamp.synthetic.validation_framework.loaders import benchmark_output_dir  # noqa: E402

VERSION = "v0_4_population_alias_revision"
FAMILY = "v0_4"
CENTRAL_SCENARIO = "central_provisional"
SANITY_SCENARIO = "clean_sanity"
SANITY_N_BUYERS = 300
REQUIRED_SCENARIOS = ("easier", "moderate", "difficult", "stress")

# Release seeds. These are the v0.3 seeds, reused so that v0.3-versus-v0.4
# comparisons are paired on the latent world seed rather than confounded by a
# different seed grid. The fresh-seed evaluation uses a disjoint set.
RELEASE_SEEDS: tuple[tuple[int, int], ...] = (
    (20260721, 20260722), (20260731, 20260732), (20260810, 20260811),
    (20260820, 20260821), (20260830, 20260831), (20260909, 20260910),
    (20260919, 20260920), (20260929, 20260930), (20261009, 20261010),
    (20261019, 20261020),
)

OUT_TABLES = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", default=None, help="Comma-separated subset to generate.")
    parser.add_argument("--n-seeds", type=int, default=len(RELEASE_SEEDS))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-sanity", action="store_true")
    args = parser.parse_args()

    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    defaults = load_benchmark_defaults(ROOT, family=FAMILY)
    n_buyers = int(defaults.target_n_buyers)

    scenarios = (
        [s.strip() for s in args.scenarios.split(",") if s.strip()]
        if args.scenarios
        else [CENTRAL_SCENARIO, *REQUIRED_SCENARIOS]
    )
    for scenario_id in scenarios:
        load_scenario(ROOT, scenario_id, family=FAMILY)  # fail before any write

    central = load_scenario(ROOT, CENTRAL_SCENARIO, family=FAMILY)
    calibration_split = getattr(central.conditional_observation, "calibration_split", None)
    observation_model = build_conditional_observation_model(
        ROOT, calibration_split=calibration_split
    )
    observation_model.to_parameter_frame().to_csv(
        OUT_TABLES / "conditional_observation_parameters.csv", index=False
    )
    print(
        f"conditional observation model: split={observation_model.calibration_split} "
        f"n_notices={observation_model.n_calibration_notices}"
    )

    rows = []
    if not args.skip_sanity:
        path = generate_pilot(
            SANITY_SCENARIO, ROOT, n_buyers=SANITY_N_BUYERS,
            world_seed=defaults.seed.latent_world_seed,
            corruption_seed=defaults.seed.corruption_seed,
            benchmark_version=VERSION, config_family=FAMILY,
        )
        rows.append(
            {
                "scenario": SANITY_SCENARIO, "world": "001", "corruption": "001",
                "world_seed": defaults.seed.latent_world_seed,
                "corruption_seed": defaults.seed.corruption_seed,
                "n_buyers": SANITY_N_BUYERS, "path": str(path.relative_to(ROOT)),
                "status": "GENERATED",
            }
        )
        print(f"  {SANITY_SCENARIO} world_001 -> {path.relative_to(ROOT)}")

    seeds = RELEASE_SEEDS[: args.n_seeds]
    for scenario_id in scenarios:
        for index, (world_seed, corruption_seed) in enumerate(seeds, start=1):
            out_dir = benchmark_output_dir(ROOT, VERSION, scenario_id, f"{index:03d}", f"{index:03d}")
            if out_dir.exists() and not args.force:
                rows.append(
                    {
                        "scenario": scenario_id, "world": f"{index:03d}", "corruption": f"{index:03d}",
                        "world_seed": world_seed, "corruption_seed": corruption_seed,
                        "n_buyers": n_buyers, "path": str(out_dir.relative_to(ROOT)),
                        "status": "SKIPPED_EXISTS",
                    }
                )
                continue
            path = generate_pilot(
                scenario_id, ROOT, n_buyers=n_buyers, world_seed=world_seed,
                corruption_seed=corruption_seed, benchmark_version=VERSION,
                world_rep=index, corruption_rep=index, config_family=FAMILY,
            )
            rows.append(
                {
                    "scenario": scenario_id, "world": f"{index:03d}", "corruption": f"{index:03d}",
                    "world_seed": world_seed, "corruption_seed": corruption_seed,
                    "n_buyers": n_buyers, "path": str(path.relative_to(ROOT)),
                    "status": "GENERATED",
                }
            )
            print(f"  {scenario_id} world_{index:03d} -> {path.relative_to(ROOT)}")

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": VERSION,
        "config_family": FAMILY,
        "target_n_buyers": n_buyers,
        "conditional_observation_split": observation_model.calibration_split,
        "real_holdout": {
            "path": defaults.real_holdout.path,
            "sha256": defaults.real_holdout.sha256,
        },
        "release_seeds": [list(seed) for seed in seeds],
        "rows": rows,
    }
    (OUT_TABLES / "generation_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    generated = sum(1 for row in rows if row["status"] == "GENERATED")
    print(f"\n{generated} artifacts generated, {len(rows) - generated} skipped")


if __name__ == "__main__":
    main()
