"""Generate the v0.3 temporal/candidate-revision synthetic benchmark.

This keeps v0.2 intact, runs a bounded pilot sweep for the central scenario,
and writes only the first parameter set that passes candidate-readiness gates.
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.config import load_config
from boamp.data.prepare import tag_digital_scope
from boamp.linkage.candidates import generate_pairs_single_key
from boamp.synthetic.compatibility import adapt_observed_notices_to_sources
from boamp.synthetic.conditional_observation import build_conditional_observation_model
from boamp.synthetic.pipeline import (
    generate_clean_world,
    generate_observed_world,
    generate_pilot,
    write_pilot_outputs,
)
from boamp.synthetic.relations import build_true_relations
from boamp.synthetic.scenarios import load_benchmark_defaults, load_scenario
from utils.text_clean import normalize_objet

VERSION = "v0_3_temporal_candidate_revision"
CENTRAL_SCENARIO = "central_provisional"
SANITY_SCENARIO = "clean_sanity"
SANITY_N_BUYERS = 300

MULTIPLIERS = [0.88, 1.3, 1.6, 2.0]
NEAR_WINDOW_SHARES = [1.00, 0.80, 0.90]
HARD_NEGATIVE_RATES = [0.34, 0.0, 0.05, 0.10]
SCOPED_BUYER_AFFINITY_SHARE = 0.102
SCOPED_NEED_PROBABILITY_HIGH = 0.70

GATES = {
    "source_count_ratio_min": 0.80,
    "source_count_ratio_max": 1.20,
    "zero_candidate_abs_pp_max": 5.0,
    "p75_abs_count_max": 3.0,
    "p90_abs_count_max": 5.0,
    "p95_abs_count_max": 8.0,
    "cap_rate_max": 0.01,
    "by_key_zero_abs_pp_max": 10.0,
    "broad_gap_tail_min": 0.45,
}


def _candidate_count_frame(sources: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    eligible = sources.loc[sources["buyer_key_type"] != "MISSING"].copy()
    counts = pairs.groupby("source_notice_id").size() if len(pairs) else pd.Series(dtype=int)
    out = eligible[["notice_id", "publication_date", "buyer_key_type", "cpv_division"]].copy()
    out["candidate_count"] = out["notice_id"].map(counts).fillna(0).astype(int)
    return out


def _candidate_summary(counts: pd.DataFrame, max_candidates: int) -> dict:
    return {
        "n_sources": int(len(counts)),
        "zero_candidate_rate": float((counts["candidate_count"] == 0).mean()),
        "mean_candidate_count": float(counts["candidate_count"].mean()),
        "median_candidate_count": float(counts["candidate_count"].median()),
        "p75_candidate_count": float(counts["candidate_count"].quantile(0.75)),
        "p90_candidate_count": float(counts["candidate_count"].quantile(0.90)),
        "p95_candidate_count": float(counts["candidate_count"].quantile(0.95)),
        "p99_candidate_count": float(counts["candidate_count"].quantile(0.99)),
        "max_candidate_count": int(counts["candidate_count"].max()),
        "cap_reached_rate": float((counts["candidate_count"] >= max_candidates).mean()),
    }


def _real_candidate_baseline(cfg) -> tuple[dict, pd.DataFrame, int]:
    real_prepared = pd.read_csv(ROOT / "data/interim/boamp_common_prepared.csv", usecols=["notice_id"], low_memory=False)
    real_sources = pd.read_csv(ROOT / "data/processed/boamp_only/boamp_only_sources.csv", parse_dates=["publication_date"])
    real_pairs = pd.read_csv(ROOT / "data/processed/boamp_only/boamp_only_candidate_pairs.csv")
    real_counts = _candidate_count_frame(real_sources, real_pairs)
    return _candidate_summary(real_counts, cfg.pipeline.candidates.max_candidates_per_source), real_counts, len(real_prepared)


def _synthetic_candidate_environment(observed: pd.DataFrame, cfg) -> tuple[dict, pd.DataFrame, pd.DataFrame, int]:
    sources = adapt_observed_notices_to_sources(observed)
    sources["objet_normalized"] = sources["objet_clean"].map(normalize_objet)
    sources["is_digital_scope"] = sources.apply(
        lambda row: tag_digital_scope(row["cpv_division"], row["objet_normalized"], cfg), axis=1
    )
    scoped = sources.loc[
        sources["notice_type_normalized"].eq("APPEL_OFFRE") & sources["is_digital_scope"]
    ].copy()
    pairs, window_months = generate_pairs_single_key(scoped, cfg, verbose=False)
    counts = _candidate_count_frame(scoped, pairs)
    return _candidate_summary(counts, cfg.pipeline.candidates.max_candidates_per_source), counts, pairs, window_months


def _by_key_zero_table(real_counts: pd.DataFrame, synthetic_counts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key in ["NAME_FALLBACK", "RAW_SIRET"]:
        real = real_counts.loc[real_counts["buyer_key_type"].eq(key), "candidate_count"]
        synthetic = synthetic_counts.loc[synthetic_counts["buyer_key_type"].eq(key), "candidate_count"]
        rows.append(
            {
                "buyer_key_type": key,
                "n_real": int(len(real)),
                "n_synthetic": int(len(synthetic)),
                "real_zero_candidate_rate": float((real == 0).mean()) if len(real) else np.nan,
                "synthetic_zero_candidate_rate": float((synthetic == 0).mean()) if len(synthetic) else np.nan,
                "abs_diff_pp": abs(float((synthetic == 0).mean()) - float((real == 0).mean())) * 100
                if len(real) and len(synthetic)
                else np.nan,
                "eligible_for_gate": bool(len(synthetic) >= 30),
            }
        )
    return pd.DataFrame(rows)


def _truth_tail_share(world: dict[str, pd.DataFrame]) -> float:
    relations = build_true_relations(world["cycles"], CENTRAL_SCENARIO)
    gaps = relations.loc[relations["relation_type"].eq("NEXT_CYCLE"), "true_gap_months"]
    return float((gaps > 6).mean()) if len(gaps) else 0.0


def _gate_result(
    real_summary: dict,
    real_counts: pd.DataFrame,
    real_prepared_n: int,
    synthetic_summary: dict,
    synthetic_counts: pd.DataFrame,
    observed_n: int,
    truth_tail_share: float,
) -> tuple[bool, dict, pd.DataFrame]:
    expected_scaled_sources = real_summary["n_sources"] * observed_n / real_prepared_n
    source_count_ratio = synthetic_summary["n_sources"] / expected_scaled_sources
    by_key = _by_key_zero_table(real_counts, synthetic_counts)
    by_key_pass = by_key.loc[by_key["eligible_for_gate"], "abs_diff_pp"].le(GATES["by_key_zero_abs_pp_max"]).all()
    metrics = {
        "expected_scaled_sources": expected_scaled_sources,
        "source_count_ratio": source_count_ratio,
        "zero_abs_diff_pp": abs(synthetic_summary["zero_candidate_rate"] - real_summary["zero_candidate_rate"]) * 100,
        "p75_abs_diff": abs(synthetic_summary["p75_candidate_count"] - real_summary["p75_candidate_count"]),
        "p90_abs_diff": abs(synthetic_summary["p90_candidate_count"] - real_summary["p90_candidate_count"]),
        "p95_abs_diff": abs(synthetic_summary["p95_candidate_count"] - real_summary["p95_candidate_count"]),
        "cap_reached_rate": synthetic_summary["cap_reached_rate"],
        "truth_gap_gt6_share": truth_tail_share,
        "by_key_zero_gate_pass": bool(by_key_pass),
    }
    passes = (
        GATES["source_count_ratio_min"] <= source_count_ratio <= GATES["source_count_ratio_max"]
        and metrics["zero_abs_diff_pp"] <= GATES["zero_candidate_abs_pp_max"]
        and metrics["p75_abs_diff"] <= GATES["p75_abs_count_max"]
        and metrics["p90_abs_diff"] <= GATES["p90_abs_count_max"]
        and metrics["p95_abs_diff"] <= GATES["p95_abs_count_max"]
        and metrics["cap_reached_rate"] <= GATES["cap_rate_max"]
        and truth_tail_share >= GATES["broad_gap_tail_min"]
        and by_key_pass
    )
    return passes, metrics, by_key


def _scenario_for_params(params: dict):
    scenario = copy.deepcopy(load_scenario(ROOT, CENTRAL_SCENARIO))
    scoped = scenario.recurrence.scoped_candidate_environment
    scoped.enabled = True
    scoped.recurrence_propensity_multiplier = params["recurrence_propensity_multiplier"]
    scoped.near_window_share = params["near_window_share"]
    scoped.hard_negative_alignment_rate = params["hard_negative_alignment_rate"]
    scoped.cluster_scoped_needs_by_buyer = True
    scoped.scoped_buyer_affinity_share = SCOPED_BUYER_AFFINITY_SHARE
    scoped.scoped_need_probability_high = SCOPED_NEED_PROBABILITY_HIGH
    scoped.stabilize_scoped_establishment = True
    scoped.stabilize_scoped_name_fallback = True
    scoped.stabilize_scoped_identity_by_need = True
    return scenario


def _run_one(params: dict, defaults, cfg, real_summary, real_counts, real_prepared_n) -> dict:
    scenario = _scenario_for_params(params)
    world = generate_clean_world(
        CENTRAL_SCENARIO,
        ROOT,
        n_buyers=defaults.target_n_buyers,
        world_seed=defaults.seed.latent_world_seed,
        scenario_override=scenario,
    )
    observed, corruption_log = generate_observed_world(
        world,
        CENTRAL_SCENARIO,
        ROOT,
        corruption_seed=defaults.seed.corruption_seed,
        scenario_override=scenario,
    )
    synthetic_summary, synthetic_counts, synthetic_pairs, window_months = _synthetic_candidate_environment(observed, cfg)
    truth_tail = _truth_tail_share(world)
    passes, gate_metrics, by_key = _gate_result(
        real_summary, real_counts, real_prepared_n, synthetic_summary, synthetic_counts, len(observed), truth_tail
    )
    row = params | synthetic_summary | gate_metrics | {"passes_candidate_readiness": passes, "window_months": window_months}
    return {
        "row": row,
        "world": world,
        "observed": observed,
        "corruption_log": corruption_log,
        "synthetic_counts": synthetic_counts,
        "synthetic_pairs": synthetic_pairs,
        "by_key": by_key,
        "scenario": scenario,
    }


def main() -> None:
    defaults = load_benchmark_defaults(ROOT)
    cfg = load_config(ROOT)
    reports_dir = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION
    reports_dir.mkdir(parents=True, exist_ok=True)

    observation_model = build_conditional_observation_model(ROOT)
    conditional_parameters = observation_model.to_parameter_frame()
    conditional_parameters.to_csv(reports_dir / "conditional_observation_parameters.csv", index=False)

    sanity_dir = generate_pilot(
        SANITY_SCENARIO,
        ROOT,
        n_buyers=SANITY_N_BUYERS,
        world_seed=defaults.seed.latent_world_seed,
        corruption_seed=defaults.seed.corruption_seed,
        benchmark_version=VERSION,
    )

    real_summary, real_counts, real_prepared_n = _real_candidate_baseline(cfg)
    attempts = []
    selected = None
    for hard_negative_alignment_rate in HARD_NEGATIVE_RATES:
        for recurrence_propensity_multiplier in MULTIPLIERS:
            for near_window_share in NEAR_WINDOW_SHARES:
                params = {
                    "recurrence_propensity_multiplier": recurrence_propensity_multiplier,
                    "near_window_share": near_window_share,
                    "hard_negative_alignment_rate": hard_negative_alignment_rate,
                }
                result = _run_one(params, defaults, cfg, real_summary, real_counts, real_prepared_n)
                attempts.append(result["row"])
                pd.DataFrame(attempts).to_csv(reports_dir / "candidate_revision_sweep.csv", index=False)
                if result["row"]["passes_candidate_readiness"]:
                    selected = result
                    break
            if selected is not None:
                break
        if selected is not None:
            break

    sweep = pd.DataFrame(attempts)
    sweep.to_csv(reports_dir / "candidate_revision_sweep.csv", index=False)
    if selected is None:
        best = sweep.sort_values(["zero_abs_diff_pp", "p90_abs_diff", "p95_abs_diff"]).head(1)
        best.to_csv(reports_dir / "candidate_revision_best_failed_attempt.csv", index=False)
        raise SystemExit(
            "No fixed v0.3 sweep candidate passed readiness gates. "
            f"Best attempt written to {reports_dir / 'candidate_revision_best_failed_attempt.csv'}"
        )

    selected_params = {
        "benchmark_version": VERSION,
        "selection_rule": "first fixed sweep candidate satisfying all candidate-readiness gates",
        "parameters": {
            "recurrence_propensity_multiplier": selected["row"]["recurrence_propensity_multiplier"],
            "near_window_share": selected["row"]["near_window_share"],
            "hard_negative_alignment_rate": selected["row"]["hard_negative_alignment_rate"],
            "cluster_scoped_needs_by_buyer": True,
            "scoped_buyer_affinity_share": SCOPED_BUYER_AFFINITY_SHARE,
            "scoped_need_probability_high": SCOPED_NEED_PROBABILITY_HIGH,
            "stabilize_scoped_establishment": True,
            "stabilize_scoped_name_fallback": True,
            "stabilize_scoped_identity_by_need": True,
            "cpv_divisions": ["32", "35", "48", "72"],
            "near_window_distribution": {
                "type": "normal",
                "mean_months": 2.0,
                "sd_months": 2.0,
                "min_months": 0.1,
                "max_months": 6.0,
            },
        },
        "gates": GATES,
        "selected_metrics": selected["row"],
    }
    provenance = pd.DataFrame(
        [
            {"parameter": key, "value": json.dumps(value) if isinstance(value, (dict, list)) else value}
            for key, value in selected_params["parameters"].items()
        ]
    )
    provenance.to_csv(reports_dir / "candidate_revision_selected_parameters.csv", index=False)

    central_dir = write_pilot_outputs(
        selected["world"],
        selected["observed"],
        selected["corruption_log"],
        CENTRAL_SCENARIO,
        ROOT,
        defaults.seed.latent_world_seed,
        defaults.seed.corruption_seed,
        benchmark_version=VERSION,
        resolved_scenario=selected["scenario"],
    )
    conditional_parameters.to_csv(central_dir / "conditional_observation_parameters.csv", index=False)
    provenance.to_csv(central_dir / "candidate_revision_selected_parameters.csv", index=False)
    selected["by_key"].to_csv(reports_dir / "candidate_revision_selected_by_key_gate.csv", index=False)

    metadata_path = central_dir / "generation_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["candidate_revision"] = selected_params
    metadata_path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")

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
        "selected_parameters": selected_params,
        "sweep_table": str((reports_dir / "candidate_revision_sweep.csv").relative_to(ROOT)),
        "conditional_observation_parameters": {
            "report_table": str((reports_dir / "conditional_observation_parameters.csv").relative_to(ROOT)),
            "central_output_copy": str((central_dir / "conditional_observation_parameters.csv").relative_to(ROOT)),
            "source_path": observation_model.source_path,
        },
        "scope": [
            "candidate environment revised through latent recurrence timing and optional same-buyer distinct-need clustering",
            "candidate counts used only as post-hoc fidelity gates",
            "linkage scores, thresholds, accepted links, precision, and recall not used",
            "conditional observation model preserved from v0.2",
        ],
    }
    (reports_dir / "generation_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(json.dumps(manifest, indent=2, default=str))


if __name__ == "__main__":
    main()
