"""Generate the v0.2 conditional-revision synthetic benchmark outputs.

This script keeps the previous v0.1 provisional outputs intact and writes a
new versioned directory:

  data/processed/synthetic_benchmark/v0_2_conditional_revision/

It regenerates:
- a small clean_sanity smoke dataset; and
- the full central_provisional dataset with conditional observation enabled.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.conditional_observation import build_conditional_observation_model
from boamp.synthetic.pipeline import generate_pilot
from boamp.synthetic.scenarios import load_benchmark_defaults

VERSION = "v0_2_conditional_revision"
CENTRAL_SCENARIO = "central_provisional"
SANITY_SCENARIO = "clean_sanity"
SANITY_N_BUYERS = 300


def main() -> None:
    defaults = load_benchmark_defaults(ROOT)
    reports_dir = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION
    reports_dir.mkdir(parents=True, exist_ok=True)

    observation_model = build_conditional_observation_model(ROOT)
    parameters = observation_model.to_parameter_frame()
    parameters.to_csv(reports_dir / "conditional_observation_parameters.csv", index=False)

    sanity_dir = generate_pilot(
        SANITY_SCENARIO,
        ROOT,
        n_buyers=SANITY_N_BUYERS,
        world_seed=defaults.seed.latent_world_seed,
        corruption_seed=defaults.seed.corruption_seed,
        benchmark_version=VERSION,
    )
    central_dir = generate_pilot(
        CENTRAL_SCENARIO,
        ROOT,
        n_buyers=defaults.target_n_buyers,
        world_seed=defaults.seed.latent_world_seed,
        corruption_seed=defaults.seed.corruption_seed,
        benchmark_version=VERSION,
    )

    # Save the exact observable-rate table beside the generated data as well
    # as in reports, so the benchmark directory is self-describing.
    parameters.to_csv(central_dir / "conditional_observation_parameters.csv", index=False)

    manifest = {
        "benchmark_version": VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "fixed_seeds": {
            "latent_world_seed": defaults.seed.latent_world_seed,
            "corruption_seed": defaults.seed.corruption_seed,
        },
        "outputs": {
            "small_sanity": str(sanity_dir.relative_to(ROOT)),
            "central_provisional": str(central_dir.relative_to(ROOT)),
        },
        "conditional_observation_parameters": {
            "report_table": str((reports_dir / "conditional_observation_parameters.csv").relative_to(ROOT)),
            "central_output_copy": str((central_dir / "conditional_observation_parameters.csv").relative_to(ROOT)),
            "source_path": observation_model.source_path,
            "smoothing": "beta-binomial global prior, prior_strength=25",
        },
        "scope": [
            "latent truth unchanged",
            "CPV missingness unchanged",
            "linkage algorithm and thresholds unchanged",
            "SIRET/duration/text observation revised from observable real-data conditionals",
        ],
    }
    (reports_dir / "generation_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
