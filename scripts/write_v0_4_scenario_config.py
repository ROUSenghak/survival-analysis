"""Emit the v0.4 configuration family from the fitted observable targets.

The v0.4 scenario files are generated rather than hand-edited so that every
calibrated array in them is traceable to
`reports/tables/synthetic_benchmark/v0_4_population_alias_revision/calibration/observable_targets.json`,
which in turn is derived only from the calibration side of the frozen real
buyer-key holdout.

Two kinds of number live in the emitted files and they are labelled differently:

* EMPIRICAL_OBSERVABLE -- copied from the fitted observable targets (activity
  body/tail, span-versus-activity curve, alias-set sizes, similarity bands,
  SIRET between-buyer dispersion, publication-year shares).
* MECHANISM_PARAMETER -- knobs with no observable counterpart that the bounded
  sweep selects against the joint acceptance vector (buyer population size,
  needs per buyer, dispersion tempering, dominant-alias share, and the carried
  scoped-candidate-environment block). These are read from
  `mechanism_parameters.json`, which the sweep rewrites.

Nothing here reads accepted links, linkage scores, thresholds, algorithm
rankings or survival results.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

VERSION = "v0_4_population_alias_revision"
CALIB_DIR = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION / "calibration"
TARGETS_PATH = CALIB_DIR / "observable_targets.json"
MECHANISM_PATH = CALIB_DIR / "mechanism_parameters.json"
SCENARIO_DIR = ROOT / "config" / "synthetic" / "scenarios" / "v0_4"
FLAT_SCENARIO_DIR = ROOT / "config" / "synthetic" / "scenarios"
DEFAULTS_PATH = ROOT / "config" / "synthetic" / "benchmark_defaults_v0_4.yaml"

OVERLAY_SCENARIOS = ("easier", "moderate", "difficult", "stress")

# Per-scenario alias aggression. v0.4 replaces `false_split_rate` with a
# persistent alias set, so the difficulty gradient the required scenarios encode
# has to be expressed as how often a buyer publishes under a non-primary form.
# Ratios are the scenarios' own v0.3 false_split_rate divided by central's 0.279,
# so the gradient is carried across unchanged rather than reinvented.
_FALSE_SPLIT_RATE_V0_3 = {
    "central_provisional": 0.279,
    "easier": 0.16,
    "moderate": 0.279,
    "difficult": 0.38,
    "stress": 0.50,
}

DEFAULT_MECHANISM_PARAMETERS = {
    "target_n_buyers": 6000,
    "needs_per_buyer_mean": 7.3,
    "dispersion_tempering": 1.0,
    "span_jitter_concentration": 4.0,
    "span_extension_factor": 1.0,
    "min_active_days": 30,
    "dominant_alias_share": 0.70,
    "presence_scale": 1.00,
    # v0.4 changed the buyer population and moved more notices into the 6-20/21+
    # activity tiers that can receive the same-buyer administrative template.
    # Preserve the v0.3 realised central share as the observable repeated-admin
    # text target, and let corruption.py solve the per-world scalar from the
    # generated tier composition.
    "same_buyer_admin_template_target_share": 0.2586715280926711,
    "same_buyer_admin_template_target_source": (
        "v0.3 central_provisional 10-world realised share of SAME_BUYER_ADMIN_TEMPLATE "
        "corruptions per observed notice"
    ),
    "scoped_candidate_environment": {
        "recurrence_propensity_multiplier": 1.60,
        "near_window_share": 0.90,
        "hard_negative_alignment_rate": 0.00,
        "scoped_buyer_affinity_share": 0.102,
        "scoped_need_probability_high": 0.54,
    },
    "entry_year_weights": None,
    "selection_note": "initial values; replaced by the bounded development sweep",
}


def load_mechanism_parameters() -> dict:
    if MECHANISM_PATH.exists():
        stored = json.loads(MECHANISM_PATH.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_MECHANISM_PARAMETERS) | stored
        merged["scoped_candidate_environment"] = (
            dict(DEFAULT_MECHANISM_PARAMETERS["scoped_candidate_environment"])
            | stored.get("scoped_candidate_environment", {})
        )
        return merged
    return json.loads(json.dumps(DEFAULT_MECHANISM_PARAMETERS))


def save_mechanism_parameters(params: dict) -> None:
    MECHANISM_PATH.parent.mkdir(parents=True, exist_ok=True)
    MECHANISM_PATH.write_text(json.dumps(params, indent=2) + "\n", encoding="utf-8")


def _base_scenario_dict() -> dict:
    """The flat central_provisional scenario, resolved, as the v0.4 starting point."""
    with open(FLAT_SCENARIO_DIR / "central_provisional.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_central_scenario(targets: dict, mechanism: dict) -> dict:
    scenario = _base_scenario_dict()
    activity = targets["activity"]
    names = targets["buyer_names"]

    entry_weights = mechanism.get("entry_year_weights") or {
        int(year): float(share) for year, share in targets["publication_year_share"].items()
    }

    scenario["scenario_id"] = "central_provisional"
    scenario["display_name"] = "Central provisional (v0.4)"
    scenario["version"] = "0.4"
    scenario["config_family"] = "v0_4"
    scenario["generated_by"] = "scripts/write_v0_4_scenario_config.py"
    scenario["generated_from"] = str(TARGETS_PATH.relative_to(ROOT))
    scenario["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    scenario["purpose"] = (
        "Principal v0.4 benchmark scenario. Identical to the v0.3 central scenario except "
        "for three observable mechanisms that v0.3 got wrong: buyer publication timing, "
        "buyer population scale with buyer-persistent identifier visibility, and buyer-name "
        "alias structure. Recurrence prevalence, cycle-gap distribution and text drift remain "
        "explicit scenario assumptions and are unchanged from v0.3."
    )
    scenario["provenance"] = "EMPIRICAL_OBSERVABLE, MECHANISM_PARAMETER, SCENARIO_ASSUMPTION"
    scenario["baseline_reference"] = "config/synthetic/scenarios/central_provisional.yaml"

    scenario["buyers"] = {
        "activity_pareto_shape": scenario.get("buyers", {}).get("activity_pareto_shape", 1.22),
        "activity_pareto_offset": scenario.get("buyers", {}).get("activity_pareto_offset", 0.15),
        "activity_model": {
            "enabled": True,
            "provenance": "EMPIRICAL_OBSERVABLE",
            "source": targets["source"],
            "calibration_split": targets["calibration_split"],
            "family": activity["selected_tail_family"],
            "selection_rule": activity["selection_rule"],
            "tail_alpha": round(float(activity["tail_alpha"]), 6),
            "tail_xmin_relative": round(float(activity["tail_xmin_relative"]), 6),
            "tail_xmax_relative": round(float(activity["tail_xmax_relative"]), 6),
            "tail_key_share": round(float(activity["tail_key_share"]), 6),
            "body_quantile_grid": [round(float(v), 4) for v in activity["body_quantile_grid"]],
            "body_quantile_values": [round(float(v), 6) for v in activity["body_quantile_values"]],
            "span_fraction_by_activity_rank": [
                round(float(v), 6) for v in activity["span_fraction_by_activity_rank"]
            ],
            "span_knot_positions": [round(float(v), 6) for v in activity["span_knot_positions"]],
            "span_extension_factor": float(mechanism["span_extension_factor"]),
            "span_jitter_concentration": float(mechanism["span_jitter_concentration"]),
            "min_active_days": int(mechanism["min_active_days"]),
            "dispersion_tempering": float(mechanism["dispersion_tempering"]),
            "entry_year_weights": {int(k): round(float(v), 8) for k, v in sorted(entry_weights.items())},
            "note": (
                "Two-component relative-activity distribution: a smoothed empirical body below "
                "the fitted x_min plus a discrete power law above it, with entry time and "
                "active-window length as separate mechanisms. tail_alpha, tail_xmin_relative, "
                "tail_key_share, the body grid, the span curve and the initial entry weights are "
                "EMPIRICAL_OBSERVABLE. dispersion_tempering and span_jitter_concentration are "
                "MECHANISM_PARAMETERs selected by the bounded sweep; entry_year_weights are "
                "refined by fixed-point deconvolution against the observable by-year notice "
                "shares, because the emergent year distribution is the convolution of entry "
                "time with the successor cascade, not the entry distribution itself."
            ),
        },
    }

    scenario["needs"] = {
        "needs_per_buyer_mean": float(mechanism["needs_per_buyer_mean"]),
        "note": (
            "MECHANISM_PARAMETER. Benchmark size used to be a side effect of the buyer count "
            "through needs.py's activity-tier means; making it explicit lets the buyer "
            "population be recalibrated without rescaling the corpus."
        ),
    }

    identifiers = dict(scenario.get("identifiers", {}))
    conditional = dict(identifiers.get("conditional_siret_presence", {}))
    conditional["presence_scale"] = float(mechanism["presence_scale"])
    conditional["buyer_effect_logit_sd"] = round(float(targets["siret"]["buyer_effect_logit_sd"]), 4)
    conditional["buyer_effect_provenance"] = "EMPIRICAL_OBSERVABLE"
    conditional["buyer_effect_note"] = (
        "Logit-scale between-buyer standard deviation of checksum-valid SIRET presence, fitted "
        "by logit-normal-binomial marginal likelihood on calibration buyers with at least five "
        "notices, over and above the schema x year x notice-type rates already in this block. "
        "v0.2 made SIRET visibility independent across a buyer's notices; the real corpus is "
        "strongly buyer-persistent, and that independence was fragmenting the synthetic "
        "SIRET-keyed buyer population into roughly four times as many keys as the real corpus has."
    )
    identifiers["conditional_siret_presence"] = conditional
    scenario["identifiers"] = identifiers

    buyer_names = dict(scenario.get("buyer_names", {}))
    buyer_names["persistent_aliases"] = {
        "enabled": True,
        "provenance": "EMPIRICAL_OBSERVABLE, MECHANISM_PARAMETER",
        "source": targets["source"],
        "calibration_split": targets["calibration_split"],
        "alias_set_size_weights": {
            int(k): round(float(v), 8) for k, v in sorted(names["alias_set_size_weights"].items())
        },
        "zero_overlap_family_share": round(float(names["zero_token_overlap_share"]), 6),
        "full_overlap_family_share": round(float(names["full_token_overlap_share"]), 6),
        "dominant_alias_share": float(mechanism["dominant_alias_share"]),
        "max_alias_attempts": 6,
        "note": (
            "Persistent per-buyer alias set, drawn once per world. alias_set_size_weights is the "
            "observable distinct-normalised-names-per-SIREN distribution; "
            "zero_overlap_family_share and full_overlap_family_share are the observable shares of "
            "same-SIREN name pairs with no shared token and with an identical token set. "
            "dominant_alias_share is a MECHANISM_PARAMETER carrying the per-scenario difficulty "
            "gradient that v0.3 expressed through false_split_rate."
        ),
    }
    scenario["buyer_names"] = buyer_names

    conditional_observation = dict(scenario.get("conditional_observation", {}))
    conditional_observation["version"] = VERSION
    # Per-parameter holdout policy. The conditional SIRET/duration/repeated-text
    # rate tables are direct empirical rate tables whose own marginal is the
    # fidelity gate's target, and they are estimated on the FULL corpus. A
    # buyer-level split cannot be used for them: checksum-valid SIRET presence is
    # a buyer-level property, so splitting on buyer key splits it too, and the
    # two real sides differ by 10.2 pp (0.2993 calibration vs 0.1976 holdout).
    # Decomposed against the full corpus, only 0.76 pp of the calibration-side
    # shift is cell composition; 1.94 pp is buyer selection within the same
    # cells, and is irreducible. Calibrating these tables on 70% of buyers would
    # therefore build a known ~2.7 pp bias into the released marginal to buy an
    # out-of-sample claim the split cannot actually support for this quantity.
    #
    # Everything the holdout *can* test out of sample -- the activity body and
    # tail, the span curve, the entry weights, the alias-set sizes and overlap
    # bands, and every swept mechanism parameter -- remains calibration-only.
    # Those are distributional-shape parameters, and the holdout evaluation
    # confirms they transfer (name-similarity quantiles pass on every world
    # against both real sides).
    conditional_observation["calibration_split"] = None
    conditional_observation["shape_parameter_calibration_split"] = targets["calibration_split"]
    conditional_observation["holdout"] = "config/synthetic/real_holdout_buyer_keys.csv"
    conditional_observation["holdout_sha256"] = targets["holdout_sha256"]
    conditional_observation["note"] = (
        "Conditional rate tables: full corpus (their marginal is the gate target and a "
        "buyer-level split shifts it by 1.94 pp through buyer selection alone). Shape "
        "parameters: calibration buyers only, evaluated out of sample on the held-out 30%. "
        "See holdout/holdout_marginal_rate_limitation.json."
    )
    scenario["conditional_observation"] = conditional_observation

    text = dict(scenario.get("text", {}))
    conditional_reuse = dict(text.get("conditional_reuse", {}))
    conditional_reuse["same_buyer_admin_template_target_share"] = round(
        float(mechanism["same_buyer_admin_template_target_share"]), 8
    )
    conditional_reuse["same_buyer_admin_template_target_source"] = mechanism[
        "same_buyer_admin_template_target_source"
    ]
    conditional_reuse["same_buyer_admin_template_rate_note"] = (
        "The scalar same_buyer_admin_template_rate is retained as a legacy fallback. "
        "When same_buyer_admin_template_target_share is present, the corruption layer "
        "solves the effective per-exposed-notice rate from the generated world's actual "
        "6-20/21+ buyer-tier composition and the earlier exact/near/weak generic-text "
        "replacement probabilities. This prevents the v0.4 buyer-population correction "
        "from mechanically shortening the text corpus by over-firing the 49-character "
        "same-buyer administrative template."
    )
    text["conditional_reuse"] = conditional_reuse
    scenario["text"] = text

    scoped = dict(scenario["recurrence"]["scoped_candidate_environment"])
    scoped.update(mechanism["scoped_candidate_environment"])
    scoped["note"] = (
        "Carried from v0.3 and re-swept at the v0.4 buyer population, because changing the buyer "
        "scale changes candidate density. MECHANISM_PARAMETERs selected against the "
        "candidate-environment gates; they never set per-source candidate counts, linkage scores, "
        "accepted links or thresholds."
    )
    scenario["recurrence"] = dict(scenario["recurrence"]) | {"scoped_candidate_environment": scoped}
    return scenario


def build_overlay_scenario(scenario_id: str, mechanism: dict) -> dict:
    with open(FLAT_SCENARIO_DIR / f"{scenario_id}.yaml", encoding="utf-8") as f:
        overlay = yaml.safe_load(f) or {}
    overlay["version"] = "0.4"
    overlay["config_family"] = "v0_4"
    overlay["generated_by"] = "scripts/write_v0_4_scenario_config.py"

    ratio = _FALSE_SPLIT_RATE_V0_3[scenario_id] / _FALSE_SPLIT_RATE_V0_3["central_provisional"]
    central_alias_use = 1.0 - float(mechanism["dominant_alias_share"])
    dominant = max(0.05, min(0.98, 1.0 - ratio * central_alias_use))
    buyer_names = dict(overlay.get("buyer_names", {}))
    buyer_names["persistent_aliases"] = {
        "dominant_alias_share": round(dominant, 4),
        "note": (
            f"SCENARIO_UNIDENTIFIED. Carries this scenario's v0.3 false_split_rate ratio "
            f"({_FALSE_SPLIT_RATE_V0_3[scenario_id]} / "
            f"{_FALSE_SPLIT_RATE_V0_3['central_provisional']} = {ratio:.3f}) onto the v0.4 "
            "persistent-alias mechanism, so the required-scenario difficulty gradient is "
            "unchanged. Only central_provisional/moderate claim observable calibration."
        ),
    }
    overlay["buyer_names"] = buyer_names
    return overlay


def build_defaults(mechanism: dict, targets: dict) -> dict:
    with open(ROOT / "config" / "synthetic" / "benchmark_defaults_v0_1.yaml", encoding="utf-8") as f:
        defaults = yaml.safe_load(f) or {}
    defaults["version"] = "0.4"
    defaults["benchmark_id"] = f"synthetic_benchmark_{VERSION}"
    defaults["config_family"] = "v0_4"
    defaults["generated_by"] = "scripts/write_v0_4_scenario_config.py"
    defaults["target_n_buyers"] = int(mechanism["target_n_buyers"])
    defaults["target_n_buyers_note"] = (
        "MECHANISM_PARAMETER selected by the bounded sweep against the observable "
        f"distinct-observed-buyer-keys-per-notice target of "
        f"{targets['activity']['keys_per_notice']:.5f}. The v0.1-v0.3 value of 19,200 was "
        "documented as the real prepared corpus's buyer count, but that corpus has 5,148 "
        "distinct raw buyer names, 4,492 normalised names, 1,506 checksum-valid SIRENs and "
        "5,268 production buyer keys; 19,200 is not traceable to any observable quantity in "
        "this repository."
    )
    defaults["real_holdout"] = {
        "path": "config/synthetic/real_holdout_buyer_keys.csv",
        "sha256": targets["holdout_sha256"],
        "calibration_split": targets["calibration_split"],
    }
    return defaults


def _dump(path: Path, payload: dict, header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100)
    path.write_text(header.rstrip() + "\n\n" + body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset-mechanism-parameters", action="store_true")
    args = parser.parse_args()

    if args.reset_mechanism_parameters and MECHANISM_PATH.exists():
        MECHANISM_PATH.unlink()

    targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    mechanism = load_mechanism_parameters()
    save_mechanism_parameters(mechanism)

    header = (
        "# GENERATED FILE -- do not hand-edit.\n"
        "# Written by scripts/write_v0_4_scenario_config.py from\n"
        f"# {TARGETS_PATH.relative_to(ROOT)} (EMPIRICAL_OBSERVABLE, calibration buyers only)\n"
        f"# and {MECHANISM_PATH.relative_to(ROOT)} (MECHANISM_PARAMETER, sweep-selected).\n"
        "# The flat config/synthetic/scenarios/*.yaml files are the v0.1-v0.3 family and are\n"
        "# left untouched so already-released benchmark versions keep replaying from them."
    )

    _dump(SCENARIO_DIR / "central_provisional.yaml", build_central_scenario(targets, mechanism), header)
    for scenario_id in OVERLAY_SCENARIOS:
        _dump(SCENARIO_DIR / f"{scenario_id}.yaml", build_overlay_scenario(scenario_id, mechanism), header)
    # clean_sanity is a structural smoke test with no observable calibration; it
    # is copied verbatim so the v0.4 family is self-contained and its hash is
    # recorded in generation metadata like every other scenario.
    shutil.copyfile(FLAT_SCENARIO_DIR / "clean_sanity.yaml", SCENARIO_DIR / "clean_sanity.yaml")
    _dump(DEFAULTS_PATH, build_defaults(mechanism, targets), header)

    print(f"wrote {SCENARIO_DIR} and {DEFAULTS_PATH.relative_to(ROOT)}")
    print(f"target_n_buyers={mechanism['target_n_buyers']} "
          f"needs_per_buyer_mean={mechanism['needs_per_buyer_mean']} "
          f"tempering={mechanism['dispersion_tempering']} "
          f"dominant_alias_share={mechanism['dominant_alias_share']}")


if __name__ == "__main__":
    main()
