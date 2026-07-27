"""Top-level orchestration for the synthetic benchmark v0.1 (Phase 4-7).

Two independent, explicit random-number generators are used throughout:
`world_rng` for the clean latent world (buyers -> establishments -> needs ->
cycles -> relations -> notice families -> clean text) and `corruption_rng`
for observation/corruption (missingness.py, corruption.py). Kept separate so
a future run can hold one fixed while sweeping the other (spec
benchmark_defaults_v0_1.yaml).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from boamp.synthetic import schemas
from boamp.synthetic.buyers import generate_latent_buyers
from boamp.synthetic.conditional_observation import build_conditional_observation_model
from boamp.synthetic.corruption import corrupt_notices
from boamp.synthetic.corruption_logging import CorruptionLogger
from boamp.synthetic.cycles import generate_latent_cycles
from boamp.synthetic.establishments import generate_latent_establishments
from boamp.synthetic.needs import generate_latent_needs
from boamp.synthetic.notices import generate_notice_families_and_clean_notices
from boamp.synthetic.parameters import load_calibration_parameters
from boamp.synthetic.relations import build_true_relations
from boamp.synthetic.scenarios import load_benchmark_defaults, load_scenario, to_plain_dict
from boamp.synthetic.validation import run_full_structural_validation

GENERATOR_VERSION = "0.3.0-temporal-candidate-revision"


def generate_clean_world(scenario_id: str, project_root: Path, n_buyers: int,
                          world_seed: int, scenario_override=None) -> dict[str, pd.DataFrame]:
    """Phases 4.1-4.7: buyers -> establishments -> needs -> cycles ->
    relations -> notice families -> clean notices. Raises ValueError if
    structural validation (Phase 5) fails; caller must not proceed to
    corruption on a failed world."""
    rng = np.random.default_rng(world_seed)
    calib = load_calibration_parameters(project_root)
    scenario = scenario_override or load_scenario(project_root, scenario_id)
    benchmark_defaults = load_benchmark_defaults(project_root)

    buyer_cfg = getattr(scenario, "buyers", None)
    buyers = generate_latent_buyers(
        n_buyers,
        benchmark_defaults,
        rng,
        pareto_shape=float(getattr(buyer_cfg, "activity_pareto_shape", 1.0)),
        pareto_offset=float(getattr(buyer_cfg, "activity_pareto_offset", 0.15)),
    )
    establishments = generate_latent_establishments(buyers, rng)
    needs = generate_latent_needs(
        buyers, establishments, calib, rng,
        base_recurrence_propensity=scenario.recurrence.base_recurrence_propensity,
        scenario=scenario,
    )
    observation_end = pd.Timestamp(benchmark_defaults.observation_window.end_date)
    cycles = generate_latent_cycles(needs, buyers, scenario, observation_end, rng)
    true_relations = build_true_relations(cycles, scenario_id)
    mix = calib.value("notice_types", "mix")
    notice_family_membership, clean_notices = generate_notice_families_and_clean_notices(
        cycles, needs, buyers, establishments, rng,
        award_probability=mix.ATTRIBUTION / mix.APPEL_OFFRE,
        same_cycle_variation_severity=scenario.text.same_cycle_variation_severity,
    )

    for df, schema, name in (
        (buyers, schemas.LATENT_BUYERS, "latent_buyers"),
        (establishments, schemas.LATENT_ESTABLISHMENTS, "latent_establishments"),
        (needs, schemas.LATENT_NEEDS, "latent_needs"),
        (cycles, schemas.LATENT_CYCLES, "latent_cycles"),
        (true_relations, schemas.TRUE_RELATIONS, "true_relations"),
        (notice_family_membership, schemas.NOTICE_FAMILY_MEMBERSHIP, "notice_family_membership"),
        (clean_notices, schemas.CLEAN_NOTICES, "clean_notices"),
    ):
        schemas.validate_columns(df, schema, name)

    world = dict(
        buyers=buyers, establishments=establishments, needs=needs, cycles=cycles,
        true_relations=true_relations, notice_family_membership=notice_family_membership,
        clean_notices=clean_notices,
    )
    result = run_full_structural_validation(world)
    if not result.passed:
        raise ValueError(f"clean-world structural validation FAILED: {result.failures()}")
    world["_validation"] = result
    return world


def generate_observed_world(world: dict[str, pd.DataFrame], scenario_id: str, project_root: Path,
                             corruption_seed: int, scenario_override=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Phase 6: clean_notices -> (observed_notices, corruption_log)."""
    rng = np.random.default_rng(corruption_seed)
    scenario = scenario_override or load_scenario(project_root, scenario_id)
    conditional_cfg = getattr(scenario, "conditional_observation", None)
    observation_model = (
        build_conditional_observation_model(project_root)
        if getattr(conditional_cfg, "enabled", False) else None
    )
    logger = CorruptionLogger(scenario_id=scenario_id, seed=corruption_seed)
    observed = corrupt_notices(world["clean_notices"], world["buyers"], world["establishments"],
                                scenario, rng, logger, observation_model=observation_model)
    schemas.validate_columns(observed, schemas.OBSERVED_NOTICES, "observed_notices")
    schemas.assert_no_truth_leakage(observed)
    return observed, logger.to_frame()


def _config_hash(project_root: Path, scenario_id: str) -> dict[str, str]:
    def _hash(rel_path: str) -> str:
        p = Path(project_root) / rel_path
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "MISSING"

    return {
        "calibration_parameters_v0_1.yaml": _hash("config/synthetic/calibration_parameters_v0_1.yaml"),
        "benchmark_defaults_v0_1.yaml": _hash("config/synthetic/benchmark_defaults_v0_1.yaml"),
        "recurrence_ontology_v0_1.yaml": _hash("config/synthetic/recurrence_ontology_v0_1.yaml"),
        f"scenarios/{scenario_id}.yaml": _hash(f"config/synthetic/scenarios/{scenario_id}.yaml"),
        "boamp_common_prepared.csv": _hash("data/interim/boamp_common_prepared.csv"),
    }


def _git_commit(project_root: Path) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root,
                              capture_output=True, text=True, timeout=5, check=True)
        return out.stdout.strip()
    except Exception:
        return None


def write_pilot_outputs(world: dict[str, pd.DataFrame], observed: pd.DataFrame, corruption_log: pd.DataFrame,
                         scenario_id: str, project_root: Path, world_seed: int, corruption_seed: int,
                         world_rep: int = 1, corruption_rep: int = 1,
                         benchmark_version: str = "v0_1_provisional",
                         resolved_scenario=None) -> Path:
    """Phase 7: write the full traceability output tree for one
    scenario/world/corruption replication."""
    project_root = Path(project_root)
    out_dir = (project_root / "data" / "processed" / "synthetic_benchmark" / benchmark_version
               / scenario_id / f"world_{world_rep:03d}" / f"corruption_{corruption_rep:03d}")
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, df in (
        ("latent_buyers", world["buyers"]), ("latent_establishments", world["establishments"]),
        ("latent_needs", world["needs"]), ("latent_cycles", world["cycles"]),
        ("true_relations", world["true_relations"]),
        ("notice_family_membership", world["notice_family_membership"]),
        ("clean_notices", world["clean_notices"]), ("observed_notices", observed),
        ("corruption_log", corruption_log),
    ):
        df.to_parquet(out_dir / f"{name}.parquet", index=False)

    validation = world.get("_validation")
    resolved_scenario = resolved_scenario or load_scenario(project_root, scenario_id)
    metadata = dict(
        generator_version=GENERATOR_VERSION,
        benchmark_id=f"synthetic_benchmark_{benchmark_version}",
        scenario=scenario_id,
        world_seed=world_seed,
        corruption_seed=corruption_seed,
        world_replication=world_rep,
        corruption_replication=corruption_rep,
        config_hashes=_config_hash(project_root, scenario_id),
        row_counts={k: len(v) for k, v in world.items() if k != "_validation"} | {
            "observed_notices": len(observed), "corruption_log": len(corruption_log),
        },
        execution_timestamp_utc=datetime.now(timezone.utc).isoformat(),
        git_commit=_git_commit(project_root),
        resolved_scenario=to_plain_dict(resolved_scenario),
        resolved_benchmark_defaults=to_plain_dict(load_benchmark_defaults(project_root)),
        validation_status="PASS" if (validation is None or validation.passed) else "FAIL",
        validation_failures=validation.failures() if validation is not None else {},
        warnings=[],
    )
    with open(out_dir / "generation_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, default=str)

    return out_dir


def generate_pilot(scenario_id: str, project_root: Path, n_buyers: int | None = None,
                    world_seed: int | None = None, corruption_seed: int | None = None,
                    benchmark_version: str = "v0_1_provisional",
                    world_rep: int = 1, corruption_rep: int = 1,
                    scenario_override=None) -> Path:
    """Full Phase 4-7 pipeline for one scenario, using benchmark_defaults_v0_1.yaml
    unless overridden. Returns the output directory."""
    project_root = Path(project_root)
    defaults = load_benchmark_defaults(project_root)
    n_buyers = n_buyers or defaults.target_n_buyers
    world_seed = world_seed or defaults.seed.latent_world_seed
    corruption_seed = corruption_seed or defaults.seed.corruption_seed

    resolved_scenario = scenario_override or load_scenario(project_root, scenario_id)
    world = generate_clean_world(scenario_id, project_root, n_buyers, world_seed, scenario_override=resolved_scenario)
    observed, log = generate_observed_world(
        world, scenario_id, project_root, corruption_seed, scenario_override=resolved_scenario
    )
    return write_pilot_outputs(
        world, observed, log, scenario_id, project_root, world_seed, corruption_seed,
        world_rep=world_rep, corruption_rep=corruption_rep, benchmark_version=benchmark_version,
        resolved_scenario=resolved_scenario,
    )
