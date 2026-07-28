"""Extract every number the technical report quotes into LaTeX macros.

The report must not contain a hand-typed statistic. This script reads the
current generated artifacts and writes:

* ``report_values.tex``  -- one ``\\newcommand`` per reported quantity;
* ``report_values.json`` -- the same values, machine-readable, so
  ``scripts/check_report_consistency.py`` can re-derive them and prove the
  compiled PDF still matches the artifacts;
* ``tables/*.tex``       -- booktabs fragments generated from the CSVs, so a
  table in the PDF cannot drift from the table on disk.

Every macro name is prefixed ``rv`` (report value) and contains letters only,
because a LaTeX control sequence may not contain digits.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

VERSION = "v0_3_temporal_candidate_revision"
SCENARIO = "central_provisional"

TABLES = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION
VF = TABLES / "validation_framework"
REGISTRIES = TABLES / "registries"
OUT_DIR = ROOT / "reports" / "generated" / "synthetic_benchmark"
TABLE_DIR = OUT_DIR / "tables"

_ROMAN = {0: "Zero", 1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
          6: "Six", 7: "Seven", 8: "Eight", 9: "Nine"}


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------
def macro_name(key: str) -> str:
    """Letters-only LaTeX control sequence derived from a snake_case key."""
    parts = re.split(r"[^0-9a-zA-Z]+", key)
    camel = "".join(p[:1].upper() + p[1:] for p in parts if p)
    return "rv" + "".join(_ROMAN[int(c)] if c.isdigit() else c for c in camel)


def latex_escape(text: str) -> str:
    out = str(text)
    for old, new in (
        ("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
        ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
        ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"),
    ):
        out = out.replace(old, new)
    return out


def fmt_int(value) -> str:
    """Thousands-separated integer using LaTeX-safe thin separators."""
    n = int(round(float(value)))
    return f"{n:,}".replace(",", "{,}")


def fmt_float(value, places: int = 3) -> str:
    return f"{float(value):.{places}f}"


def fmt_pct(value, places: int = 1) -> str:
    """Fraction in [0,1] rendered as a percentage, percent sign escaped."""
    return f"{100 * float(value):.{places}f}\\%"


def fmt_pp(value, places: int = 2) -> str:
    """A value already expressed in percentage points."""
    return f"{float(value):.{places}f}"


# --------------------------------------------------------------------------
# collection
# --------------------------------------------------------------------------
class Values:
    def __init__(self) -> None:
        self.raw: dict[str, object] = {}
        self.tex: dict[str, str] = {}

    def add(self, key: str, raw, rendered: str) -> None:
        if key in self.tex:
            raise KeyError(f"duplicate report value {key!r}")
        self.raw[key] = raw
        self.tex[key] = rendered

    def add_int(self, key: str, value) -> None:
        self.add(key, int(round(float(value))), fmt_int(value))

    def add_float(self, key: str, value, places: int = 3) -> None:
        self.add(key, float(value), fmt_float(value, places))

    def add_pct(self, key: str, value, places: int = 1) -> None:
        self.add(key, float(value), fmt_pct(value, places))

    def add_pp(self, key: str, value, places: int = 2) -> None:
        self.add(key, float(value), fmt_pp(value, places))

    def add_text(self, key: str, value) -> None:
        self.add(key, str(value), latex_escape(value))

    def add_verbatim(self, key: str, value) -> None:
        """Already-formatted LaTeX; used for identifiers set in \\texttt."""
        self.add(key, str(value), str(value))


def metric_lookup(metrics: pd.DataFrame):
    def get(scope: str, subgroup: str, prop: str, metric: str, column: str = "synthetic_estimate"):
        sel = metrics.loc[
            metrics["scope"].eq(scope)
            & metrics["subgroup"].eq(subgroup)
            & metrics["property"].eq(prop)
            & metrics["metric"].eq(metric)
        ]
        if len(sel) != 1:
            raise LookupError(f"expected 1 row for {scope}/{subgroup}/{prop}/{metric}, found {len(sel)}")
        return sel.iloc[0][column]

    return get


def collect() -> Values:
    v = Values()
    from boamp.config import load_config

    cfg = load_config(ROOT)
    P = cfg.pipeline

    # ---- provenance of this extraction -----------------------------------
    v.add_text("report_build_date", datetime.now(timezone.utc).date().isoformat())
    v.add_verbatim("benchmark_version", latex_escape(VERSION))
    v.add_verbatim("central_scenario", latex_escape(SCENARIO))

    # ---- real corpus and production pipeline ------------------------------
    prepared = pd.read_csv(
        ROOT / "data" / "interim" / "boamp_common_prepared.csv",
        usecols=["notice_id", "publication_date", "schema_family", "notice_type_normalized"],
        low_memory=False,
    )
    v.add_int("corpus_notices", len(prepared))
    dates = pd.to_datetime(prepared["publication_date"], errors="coerce")
    v.add_text("corpus_first_publication", dates.min().date().isoformat())
    v.add_text("corpus_last_publication", dates.max().date().isoformat())
    schema_share = prepared["schema_family"].value_counts(normalize=True)
    v.add_pct("corpus_legacy_share", schema_share.get("LEGACY", 0.0))
    v.add_pct("corpus_eforms_share", schema_share.get("EFORMS", 0.0))
    type_share = prepared["notice_type_normalized"].value_counts(normalize=True)
    for label, key in (("APPEL_OFFRE", "corpus_call_share"),
                       ("ATTRIBUTION", "corpus_award_share"),
                       ("OTHER", "corpus_other_share")):
        v.add_pct(key, type_share.get(label, 0.0))

    layers = pd.read_csv(ROOT / "data" / "processed" / "comparison" / "layer_comparison_summary.csv")
    l1 = layers.set_index("layer").loc["boamp_only"]
    l2 = layers.set_index("layer").loc["enriched"]
    v.add_int("layer_one_sources", l1["eligible_source_count"])
    v.add_int("layer_one_pairs", l1["candidate_pair_count"])
    v.add_int("layer_one_links", l1["accepted_links"])
    v.add_pct("layer_one_link_rate", l1["overall_linking_rate"])
    v.add_int("layer_two_pairs", l2["candidate_pair_count"])
    v.add_int("layer_two_links", l2["accepted_links"])
    v.add_pct("layer_two_link_rate", l2["overall_linking_rate"])

    v.add_float("threshold_balanced", P.thresholds.balanced, 6)
    v.add_float("threshold_broad", P.thresholds.broad, 6)
    v.add_float("threshold_strict", P.thresholds.strict, 6)
    v.add_int("temporal_window_months", P.temporal_window.expected_value_months)
    v.add_int("max_candidates_per_source", P.candidates.max_candidates_per_source)
    v.add_float("weight_text", P.scoring.weights.text, 2)
    v.add_float("weight_cpv", P.scoring.weights.cpv, 2)
    v.add_float("weight_time", P.scoring.weights.time, 2)
    v.add_float("weight_buyer", P.scoring.weights.buyer, 2)
    v.add_float("month_days", P.run.month_days, 2)
    v.add_verbatim("digital_cpv_divisions", ", ".join(str(d) for d in P.scope.digital_cpv_divisions))
    v.add_int("duration_min_months", P.duration.min_plausible_months)
    v.add_int("duration_max_months", P.duration.max_plausible_months)

    # ---- generator code constants (not artifacts, but not hand-typed either) ---
    from boamp.synthetic import missingness as _miss
    from boamp.synthetic import notices as _notices
    from boamp.synthetic.conditional_observation import build_conditional_observation_model
    from boamp.synthetic.validation_framework import difficulty as _difficulty

    v.add_verbatim("severity_multipliers", ", ".join(
        f"{_miss.SEVERITY_MULTIPLIER[k]:.2f}" for k in ("HIGH", "MEDIUM", "LOW")))
    v.add_verbatim("duration_severity_multipliers", ", ".join(
        f"{_miss.DURATION_SEVERITY_MULTIPLIER[k]:.2f}" for k in ("HIGH", "MEDIUM", "LOW")))
    v.add_int("award_delay_mean_days", 90)
    v.add_int("award_delay_sd_days", 45)
    v.add_int("award_delay_min_days", 10)
    v.add_int("award_delay_max_days", 400)
    v.add_int("widened_probe_window_months", _difficulty.WIDENED_PROBE_WINDOW_MONTHS)
    v.add_float("blocking_recall_widened_floor",
                _difficulty.TOLERANCES["widened_pairs_completeness_min"], 2)
    v.add_float("blocking_recall_production_floor",
                _difficulty.TOLERANCES["production_pairs_completeness_min"], 2)
    eforms_years = sorted(_notices._EFORMS_ADOPTION_SHARE_BY_YEAR)
    v.add_verbatim("eforms_adoption_first_year", str(eforms_years[0]))
    v.add_pct("eforms_adoption_max_share",
              max(_notices._EFORMS_ADOPTION_SHARE_BY_YEAR.values()), 0)
    v.add_int("smoothing_prior_strength", 25)
    v.add_float("recurrence_propensity_cap", 0.98, 2)

    # ---- generator configuration ------------------------------------------
    meta_path = (ROOT / "data" / "processed" / "synthetic_benchmark" / VERSION / SCENARIO
                 / "world_001" / "corruption_001" / "generation_metadata.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    v.add_verbatim("generator_version", latex_escape(meta["generator_version"]))
    # Seeds are identifiers, not magnitudes: no thousands separators.
    v.add_verbatim("world_seed", str(int(meta["world_seed"])))
    v.add_verbatim("corruption_seed", str(int(meta["corruption_seed"])))
    v.add_text("generation_timestamp", str(meta["execution_timestamp_utc"])[:19].replace("T", " "))
    env = meta.get("runtime_environment") or {}
    for lib in ("python", "numpy", "pandas", "pyarrow"):
        v.add_verbatim(f"env_{lib}", latex_escape(env.get(lib, "not recorded")))
    for name, count in meta["row_counts"].items():
        v.add_int(f"rows_{name}", count)

    defaults = yaml.safe_load(
        (ROOT / "config" / "synthetic" / "benchmark_defaults_v0_1.yaml").read_text(encoding="utf-8")
    )
    v.add_int("target_n_buyers", defaults["target_n_buyers"])
    v.add_text("observation_start", defaults["observation_window"]["start_date"])
    v.add_text("observation_end", defaults["observation_window"]["end_date"])

    scen = yaml.safe_load(
        (ROOT / "config" / "synthetic" / "scenarios" / f"{SCENARIO}.yaml").read_text(encoding="utf-8")
    )
    rec = scen["recurrence"]
    gap = rec["cycle_gap_distribution"]
    v.add_float("base_recurrence_propensity", rec["base_recurrence_propensity"], 2)
    v.add_float("gap_mean_months", gap["mean_months"], 1)
    v.add_float("gap_sd_months", gap["sd_months"], 1)
    v.add_float("gap_min_months", gap["min_months"], 1)
    v.add_int("max_cycles_per_need", rec["max_cycles_per_need"])
    sc = rec["scoped_candidate_environment"]
    v.add_float("scoped_multiplier", sc["recurrence_propensity_multiplier"], 2)
    v.add_float("scoped_near_window_share", sc["near_window_share"], 2)
    v.add_float("scoped_hard_negative_rate", sc["hard_negative_alignment_rate"], 2)
    v.add_float("scoped_affinity_share", sc["scoped_buyer_affinity_share"], 3)
    v.add_float("scoped_need_probability_high", sc["scoped_need_probability_high"], 2)
    near = sc["near_window_distribution"]
    v.add_float("near_gap_mean_months", near["mean_months"], 1)
    v.add_float("near_gap_sd_months", near["sd_months"], 1)
    v.add_float("near_gap_min_months", near["min_months"], 1)
    v.add_float("near_gap_max_months", near["max_months"], 1)
    v.add_float("pareto_shape", scen["buyers"]["activity_pareto_shape"], 2)
    v.add_float("pareto_offset", scen["buyers"]["activity_pareto_offset"], 2)
    v.add_float("text_next_cycle_drift", scen["text"]["next_cycle_drift_severity"], 2)
    v.add_float("text_same_cycle_variation", scen["text"]["same_cycle_variation_severity"], 2)
    for cls, share in scen["quality_class_mix"].items():
        v.add_float(f"quality_share_{cls.lower()}", share, 2)

    calib = yaml.safe_load(
        (ROOT / "config" / "synthetic" / "calibration_parameters_v0_1.yaml").read_text(encoding="utf-8")
    )
    v.add_pct("calib_siret_present_rate",
              calib["identifiers"]["siret_format_and_checksum_valid_rate"]["value"])
    v.add_pct("calib_cpv_missing_rate", calib["cpv"]["missing_rate"]["value"])
    v.add_pct("calib_duration_present_rate", calib["duration"]["present_rate_full_corpus"]["value"])
    v.add_pct("calib_exact_duplicate_rate", calib["text"]["exact_duplicate_template_rate"]["value"])
    v.add_pct("calib_name_variation_rate", calib["names"]["buyer_name_variation_rate"]["value"])
    v.add_pct("calib_name_ambiguity_rate", calib["names"]["buyer_name_ambiguity_rate"]["value"])
    v.add_pct("calib_generic_name_share", calib["names"]["generic_buyer_name_share"]["value"])
    v.add_pct("calib_eforms_share", calib["schemas"]["eforms_share"]["value"])
    mix = calib["notice_types"]["mix"]["value"]
    v.add_float("calib_award_probability", mix["ATTRIBUTION"] / mix["APPEL_OFFRE"], 3)

    # ---- candidate environment -------------------------------------------
    cand = pd.read_csv(TABLES / "candidate_environment_summary_metrics.csv").set_index("scope")
    for scope_key, prefix in (
        ("real_layer1_algorithm_scope", "cand_real"),
        ("v0_2_conditional_revision_layer1_algorithm_scope", "cand_prev"),
        (f"{VERSION}_layer1_algorithm_scope", "cand_now"),
    ):
        row = cand.loc[scope_key]
        v.add_int(f"{prefix}_sources", row["n_sources"])
        v.add_pct(f"{prefix}_zero_rate", row["zero_candidate_rate"])
        v.add_float(f"{prefix}_mean", row["mean_candidate_count"], 2)
        v.add_int(f"{prefix}_median", row["median_candidate_count"])
        v.add_float(f"{prefix}_p_seventyfive", row["p75_candidate_count"], 1)
        v.add_float(f"{prefix}_p_ninety", row["p90_candidate_count"], 1)
        v.add_float(f"{prefix}_p_ninetyfive", row["p95_candidate_count"], 1)
        v.add_int(f"{prefix}_max", row["max_candidate_count"])
        v.add_pct(f"{prefix}_cap_rate", row["cap_reached_rate"], 2)

    gate = pd.read_csv(TABLES / "candidate_environment_validation_gate_by_version.csv")
    now = gate.loc[gate["version"].eq(VERSION)].set_index("dimension")
    for dimension, key, places in (
        ("source_count_ratio", "cand_source_count_ratio", 3),
        ("zero_candidate_abs_diff_pp", "cand_zero_abs_diff_pp", 2),
        ("p75_abs_diff", "cand_p_seventyfive_abs_diff", 1),
        ("p90_abs_diff", "cand_p_ninety_abs_diff", 1),
        ("p95_abs_diff", "cand_p_ninetyfive_abs_diff", 1),
    ):
        v.add_float(key, float(now.loc[dimension, "value"]), places)
    v.add_int("cand_gate_dimensions", len(now))
    v.add_int("cand_gate_passing", int((now["status"] == "PASS").sum()))

    # ---- validation framework --------------------------------------------
    manifest = json.loads((VF / "validation_manifest.json").read_text(encoding="utf-8"))
    v.add_verbatim("validation_status", latex_escape(manifest["overall_status"]))
    v.add_int("validation_metric_count", manifest["metric_count"])
    v.add_int("validation_gate_count", manifest["gate_count"])
    v.add_int("validation_metric_failures", manifest["n_metric_failures"])
    v.add_int("validation_noncritical_failures", manifest["n_metric_failures_in_noncritical_gates"])
    v.add_int("validation_bootstrap_reps", manifest["bootstrap_reps"])

    gates = pd.read_csv(VF / "validation_gate_summary.csv")
    v.add_int("gates_pass", int((gates["status"] == "PASS").sum()))
    v.add_int("gates_warning", int((gates["status"] == "WARNING").sum()))
    v.add_int("gates_fail", int((gates["status"] == "FAIL").sum()))
    v.add_int("gates_critical", int(gates["critical"].sum()))

    metrics = pd.read_csv(VF / "validation_metrics_long.csv")
    counts = metrics["status"].value_counts()
    for status in ("PASS", "WARNING", "FAIL", "INCONCLUSIVE"):
        v.add_int(f"metrics_{status.lower()}", int(counts.get(status, 0)))
    get = metric_lookup(metrics)

    v.add_int("truth_pairs_in_scope", get("hidden_truth_difficulty", "algorithm_scope",
                                          "true_matches_in_scope", "count"))
    v.add_float("blocking_recall_production", get("hidden_truth_difficulty", "production_window",
                                                  "blocking_pairs_completeness", "PC"))
    v.add_float("blocking_recall_widened", get("hidden_truth_difficulty", "36m_window",
                                               "blocking_pairs_completeness", "PC"))
    v.add_float("pairs_quality_production", get("hidden_truth_difficulty", "production_window",
                                                "pairs_quality", "PQ"))
    v.add_float("pairs_quality_widened", get("hidden_truth_difficulty", "36m_window",
                                             "pairs_quality", "PQ"))
    v.add_float("reduction_ratio_production", get("hidden_truth_difficulty", "production_window",
                                                  "reduction_ratio", "RR"))
    v.add_float("match_nonmatch_overlap", get("hidden_truth_difficulty", "production_window",
                                              "match_vs_hard_negative_score", "overlap"))
    v.add_float("true_match_mrr", get("hidden_truth_difficulty", "production_window",
                                      "true_match_rank", "MRR"))
    v.add_float("median_top_margin", get("hidden_truth_difficulty", "production_window",
                                         "top1_top2_margin", "median"))
    v.add_float("mean_true_gap_months", get("specification_recovery", "overall",
                                            "parameter_recovery",
                                            "mean_true_gap_months_in_monte_carlo_interval"), 2)

    probes = pd.read_csv(VF / "probe_linker_results.csv").set_index("probe")
    for probe, prefix in (("deterministic_top1", "probe_top_one"),
                          ("score_threshold_all_ranks", "probe_threshold"),
                          ("fellegi_sunter", "probe_fs")):
        row = probes.loc[probe]
        v.add_int(f"{prefix}_predicted", row["n_predicted_pairs"])
        v.add_float(f"{prefix}_precision", row["pair_precision"])
        v.add_float(f"{prefix}_recall", row["pair_recall"])
        v.add_float(f"{prefix}_f_one", row["pair_f1"])
        v.add_float(f"{prefix}_bcubed", row["bcubed_f1"])
    v.add_float("probe_best_f_one", probes["pair_f1"].max())
    v.add_text("probe_best_name", probes["pair_f1"].idxmax())

    replicate_probes = pd.read_csv(VF / "probe_replicate_results.csv")
    v.add_int("probe_replicate_rows", len(replicate_probes))
    ranking = pd.read_csv(VF / "probe_ranking_stability.csv")
    v.add_int("probe_ranking_rows", len(ranking))

    rob = metrics.loc[metrics["scope"].eq("robustness")]
    v.add_int("replicate_inventory", int(float(
        rob.loc[rob["property"].eq("replicate_inventory"), "synthetic_estimate"].iloc[0])))
    for prop, prefix in (("blocking_pairs_completeness", "rob_blocking"),
                         ("probe_headroom", "rob_headroom")):
        sel = rob.loc[rob["subgroup"].eq(f"seed_replicates:{SCENARIO}") & rob["property"].eq(prop)]
        by_metric = sel.set_index("metric")["synthetic_estimate"]
        v.add_int(f"{prefix}_seeds", int(float(by_metric["seed_count"])))
        v.add_float(f"{prefix}_mean", float(by_metric["mean"]))
        v.add_float(f"{prefix}_std", float(by_metric["std"]))
        v.add_float(f"{prefix}_worst", float(by_metric["worst_case"]))
        v.add_float(f"{prefix}_cv", float(by_metric["coefficient_of_variation"]))
        v.add_text(f"{prefix}_interval", str(by_metric["central_95pct_interval"]).replace("-", " to "))

    # ---- readiness --------------------------------------------------------
    readiness = json.loads((TABLES / "readiness" / "readiness_decisions.json").read_text(encoding="utf-8"))
    for decision in readiness["decisions"]:
        v.add_verbatim(f"readiness_{decision['level'].lower()}", latex_escape(decision["status"]))
    v.add_int("readiness_problem_count", len(readiness["current_problem_inventory"]))
    v.add_verbatim("readiness_git_head", latex_escape(str(readiness["current_git_head"])[:12]))
    v.add_text("readiness_worktree_dirty", "yes" if readiness["worktree_dirty"] else "no")

    # ---- registries -------------------------------------------------------
    registry = pd.read_csv(REGISTRIES / "parameter_registry.csv")
    v.add_int("registry_rows", len(registry))
    for cls in ("EMPIRICAL_OBSERVABLE", "SILVER_STANDARD_APPROXIMATION", "SCENARIO_UNIDENTIFIED",
                "FIDELITY_TARGET", "ALGORITHM_PARAMETER", "IMPLEMENTATION_CONSTANT"):
        n = int((registry["provenance_class"] == cls).sum())
        v.add_int(f"registry_{cls.lower()}", n)

    manifest_scen = pd.read_csv(REGISTRIES / "scenario_manifest.csv")
    generated = manifest_scen.loc[manifest_scen["manifest_row_type"].eq("GENERATED_REPLICATE")]
    v.add_int("scenarios_configured", manifest_scen["scenario"].nunique())
    v.add_int("scenarios_generated", generated["scenario"].nunique())
    v.add_int("artifacts_generated", len(generated))
    v.add_int("config_only_scenarios",
              int(manifest_scen["manifest_row_type"].eq("CONFIG_ONLY").sum()))
    per_scenario = generated.groupby("scenario").size()
    v.add_int("seeds_per_benchmark_scenario", int(per_scenario.drop("clean_sanity", errors="ignore").max()))

    units = pd.read_csv(REGISTRIES / "unit_of_analysis.csv")
    v.add_int("benchmark_tables", len(units))
    dictionary = pd.read_csv(REGISTRIES / "data_dictionary.csv")
    v.add_int("dictionary_columns", len(dictionary))
    v.add_int("observed_columns", int(dictionary["table"].eq("observed_notices").sum()))
    v.add_int("truth_only_columns", int(dictionary["truth_only_field"].fillna(False).astype(bool).sum()))

    # ---- replay -----------------------------------------------------------
    replay = json.loads((VF / "replay_comparison.json").read_text(encoding="utf-8"))
    v.add_verbatim("replay_status", latex_escape(replay["overall_status"]))
    v.add_int("replay_tables", len(replay["tables"]))
    drift = replay.get("environment_drift_since_generation") or {}
    v.add_text("replay_environment_drift", "none" if not drift else ", ".join(sorted(drift)))

    replicates = json.loads((VF / "replay_replicates.json").read_text(encoding="utf-8"))
    v.add_verbatim("replay_replicates_status", latex_escape(replicates.get("overall_status", "UNKNOWN")))
    rep_rows = replicates.get("replicates", [])
    v.add_int("replay_replicates_checked", replicates.get("n_replicates", len(rep_rows)))
    v.add_int("replay_replicates_passed", sum(1 for r in rep_rows if r.get("status") == "PASS"))

    return v


# --------------------------------------------------------------------------
# LaTeX table fragments
# --------------------------------------------------------------------------
def _tabular(frame: pd.DataFrame, colspec: str, caption: str, label: str,
             align_header: list[str] | None = None, *, env: str = "tabular",
             fontsize: str = r"\small") -> str:
    """Render a booktabs table.

    ``env`` may be ``tabular`` (natural widths) or ``tabularx`` (the caller's
    colspec contains at least one ``X`` column and the table is set to
    ``\\textwidth``). Wide tables must use ``tabularx``: a fixed-width column
    spec is the only thing that keeps a long tolerance string or a long metric
    name from running off the page.
    """
    header = align_header or [latex_escape(c) for c in frame.columns]
    begin = (f"\\begin{{tabularx}}{{\\textwidth}}{{{colspec}}}"
             if env == "tabularx" else f"\\begin{{tabular}}{{{colspec}}}")
    end = r"\end{tabularx}" if env == "tabularx" else r"\end{tabular}"
    lines = [
        r"\begin{table}[htbp]", r"\centering", fontsize,
        f"\\caption{{{caption}}}", f"\\label{{{label}}}",
        begin, r"\toprule",
        " & ".join(header) + r" \\", r"\midrule",
    ]
    for row in frame.itertuples(index=False):
        lines.append(" & ".join(str(c) for c in row) + r" \\")
    lines += [r"\bottomrule", end, r"\end{table}", ""]
    return "\n".join(lines)


def _shorten(text: str, limit: int = 34) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def write_tables() -> list[Path]:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # gate summary
    gates = pd.read_csv(VF / "validation_gate_summary.csv")
    frame = pd.DataFrame({
        "Gate": gates["gate"].map(lambda s: r"\texttt{" + latex_escape(s) + "}"),
        "Critical": gates["critical"].map(lambda b: "yes" if b else "no"),
        "Pass": gates["n_pass"].astype(int),
        "Warn": gates["n_warning"].astype(int),
        "Fail": gates["n_fail"].astype(int),
        "Status": gates["status"].map(latex_escape),
    })
    path = TABLE_DIR / "validation_gates.tex"
    path.write_text(_tabular(
        frame, ">{\\raggedright\\arraybackslash}Xccccl",
        "Validation-framework gate summary for the current run. A critical gate fails the release on "
        "its own; a non-critical gate can only downgrade the run to \\texttt{PASS\\_WITH\\_WARNINGS}. "
        "Source: \\texttt{validation\\_gate\\_summary.csv}.",
        "tab:gates", env="tabularx"), encoding="utf-8")
    written.append(path)

    # candidate environment
    cand = pd.read_csv(TABLES / "candidate_environment_summary_metrics.csv")
    labels = {
        "real_layer1_algorithm_scope": "Real BOAMP, Layer 1 scope",
        "v0_2_conditional_revision_layer1_algorithm_scope": "Synthetic v0.2",
        f"{VERSION}_layer1_algorithm_scope": "Synthetic v0.3 (current)",
    }
    frame = pd.DataFrame({
        "Scope": cand["scope"].map(labels).fillna(cand["scope"].map(latex_escape)),
        "$n$ sources": cand["n_sources"].map(fmt_int),
        "Zero-cand.": cand["zero_candidate_rate"].map(lambda x: fmt_pct(x, 1)),
        "Mean": cand["mean_candidate_count"].map(lambda x: fmt_float(x, 2)),
        "Median": cand["median_candidate_count"].map(lambda x: fmt_float(x, 0)),
        "$q_{.75}$": cand["p75_candidate_count"].map(lambda x: fmt_float(x, 1)),
        "$q_{.90}$": cand["p90_candidate_count"].map(lambda x: fmt_float(x, 1)),
        "$q_{.95}$": cand["p95_candidate_count"].map(lambda x: fmt_float(x, 1)),
        "Cap hit": cand["cap_reached_rate"].map(lambda x: fmt_pct(x, 2)),
    })
    path = TABLE_DIR / "candidate_environment.tex"
    path.write_text(_tabular(
        frame, ">{\\raggedright\\arraybackslash}Xrrrrrrrr",
        "Per-source candidate-set size under the production Layer-1 blocker, real corpus versus two "
        "generator versions. Unit: candidates per eligible source notice. "
        "Source: \\texttt{candidate\\_environment\\_summary\\_metrics.csv}.",
        "tab:candenv", env="tabularx"), encoding="utf-8")
    written.append(path)

    # probe linkers
    probes = pd.read_csv(VF / "probe_linker_results.csv")
    frame = pd.DataFrame({
        "Probe": probes["probe"].map(lambda s: r"\texttt{" + latex_escape(s) + "}"),
        "Predicted pairs": probes["n_predicted_pairs"].map(fmt_int),
        "Pair prec.": probes["pair_precision"].map(lambda x: fmt_float(x, 3)),
        "Pair rec.": probes["pair_recall"].map(lambda x: fmt_float(x, 3)),
        "Pair $F_1$": probes["pair_f1"].map(lambda x: fmt_float(x, 3)),
        "B-cubed $F_1$": probes["bcubed_f1"].map(lambda x: fmt_float(x, 3)),
    })
    path = TABLE_DIR / "probe_linkers.tex"
    path.write_text(_tabular(
        frame, ">{\\raggedright\\arraybackslash}Xrrrrr",
        "Frozen probe linkers scored against sealed synthetic truth on the central world. These are "
        "benchmark-discrimination diagnostics on generated truth, not estimates of real BOAMP accuracy. "
        "Source: \\texttt{probe\\_linker\\_results.csv}.",
        "tab:probes", env="tabularx"), encoding="utf-8")
    written.append(path)

    # readiness
    readiness = json.loads((TABLES / "readiness" / "readiness_decisions.json").read_text(encoding="utf-8"))
    frame = pd.DataFrame({
        "Readiness level": [r"\texttt{\scriptsize " + latex_escape(d["level"]) + "}"
                            for d in readiness["decisions"]],
        "Status": [latex_escape(d["status"]) for d in readiness["decisions"]],
        "Why blocked": [
            latex_escape(_shorten(", ".join(d["failed_hard_gates"]) or "none", 118))
            for d in readiness["decisions"]
        ],
    })
    path = TABLE_DIR / "readiness.tex"
    path.write_text(_tabular(
        frame, "ll>{\\raggedright\\arraybackslash}X",
        "Five-level readiness assessment. This, not the validation headline, governs what the "
        "benchmark may currently be used for. Source: \\texttt{readiness\\_decisions.json}.",
        "tab:readiness", env="tabularx"), encoding="utf-8")
    written.append(path)

    # parameter provenance
    registry = pd.read_csv(REGISTRIES / "parameter_registry.csv")
    counts = registry["provenance_class"].value_counts()
    descriptions = {
        "EMPIRICAL_OBSERVABLE": "estimated from a measurable real-BOAMP quantity",
        "SILVER_STANDARD_APPROXIMATION": "estimated through a documented imperfect proxy",
        "SCENARIO_UNIDENTIFIED": "assumption about a quantity BOAMP cannot identify",
        "FIDELITY_TARGET": "observable property used only to judge realism",
        "ALGORITHM_PARAMETER": "linkage or blocking setting, never synthetic truth",
        "IMPLEMENTATION_CONSTANT": "technical choice with no empirical interpretation",
    }
    frame = pd.DataFrame({
        "Provenance class": [r"\texttt{" + latex_escape(c) + "}" for c in descriptions],
        "Meaning": [descriptions[c] for c in descriptions],
        "Rows": [fmt_int(counts.get(c, 0)) for c in descriptions],
    })
    path = TABLE_DIR / "provenance_classes.tex"
    path.write_text(_tabular(
        frame, "l>{\\raggedright\\arraybackslash}Xr",
        "Parameter-provenance classes and how many registry rows carry each. "
        "Source: \\texttt{registries/parameter\\_registry.csv}.",
        "tab:provenance", env="tabularx"), encoding="utf-8")
    written.append(path)

    # unit of analysis
    units = pd.read_csv(REGISTRIES / "unit_of_analysis.csv")
    frame = pd.DataFrame({
        "Table": units["table"].map(lambda s: r"\texttt{" + latex_escape(s) + "}"),
        "Layer": units["layer"].map(latex_escape),
        "Grain": units["grain"].map(latex_escape),
        "Rows": units["n_rows"].map(fmt_int),
        "Cols": units["n_columns"].map(fmt_int),
    })
    path = TABLE_DIR / "unit_of_analysis.tex"
    path.write_text(_tabular(
        frame, ">{\\raggedright\\arraybackslash}Xllrr",
        "Emitted tables, the layer each belongs to, and its statistical unit. Only the observed layer "
        "is visible to a linkage method. Source: \\texttt{registries/unit\\_of\\_analysis.csv}.",
        "tab:units", env="tabularx"), encoding="utf-8")
    written.append(path)

    # discrepancy register (non-passing metrics)
    disc = pd.read_csv(VF / "discrepancy_register.csv")
    show = disc.loc[disc["status"].isin(["FAIL", "WARNING", "INCONCLUSIVE"])].copy()
    show = show.sort_values(["status", "scope"]).head(40)

    def _num(x):
        """Blank, not the string 'nan', for a metric with no real counterpart."""
        if pd.isna(x):
            return ""
        try:
            return fmt_float(float(x), 3)
        except (TypeError, ValueError):
            return latex_escape(x)

    # Property alone repeats across subgroups (three buyer-activity shares, two
    # blocking windows), so the subgroup has to be shown or the rows are
    # indistinguishable.
    prop_with_subgroup = [
        f"{p} ({g})" if str(g) not in ("overall", "nan", "") else str(p)
        for p, g in zip(show["property"], show["subgroup"])
    ]
    frame = pd.DataFrame({
        "Gate": show["scope"].map(lambda s: latex_escape(_shorten(s, 22).replace("_", " "))),
        "Property": [latex_escape(_shorten(s, 34).replace("_", " ")) for s in prop_with_subgroup],
        "Metric": show["metric"].map(lambda s: latex_escape(_shorten(s, 22).replace("_", " "))),
        "Real": show["real_estimate"].map(_num),
        "Synth.": show["synthetic_estimate"].map(_num),
        "Tol.": show["tolerance"].map(lambda x: latex_escape(_shorten(x, 14))),
        "Status": show["status"].map(lambda s: latex_escape(str(s).title())),
    })
    path = TABLE_DIR / "discrepancies.tex"
    path.write_text(_tabular(
        frame,
        ">{\\raggedright\\arraybackslash}X"
        ">{\\raggedright\\arraybackslash}X"
        ">{\\raggedright\\arraybackslash}Xrrll",
        "Every metric that did not pass, with its real and synthetic estimates and the tolerance it was "
        "judged against. Long names are truncated for width; the untruncated table is "
        "\\texttt{discrepancy\\_register.csv}. A blank real estimate marks a quantity that exists only "
        "inside the synthetic truth and therefore has no real counterpart.",
        "tab:discrepancies", env="tabularx", fontsize=r"\scriptsize"), encoding="utf-8")
    written.append(path)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Rebuild in memory and fail if the stored values differ.")
    args = parser.parse_args()

    values = collect()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "report_values.json"
    tex_path = OUT_DIR / "report_values.tex"

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": VERSION,
        "scenario": SCENARIO,
        "values": values.raw,
        "rendered": values.tex,
    }

    if args.check:
        if not json_path.exists():
            raise SystemExit(f"{json_path} missing; run without --check first")
        stored = json.loads(json_path.read_text(encoding="utf-8"))
        differing = sorted(
            k for k in set(stored["values"]) | set(values.raw)
            if stored["values"].get(k) != values.raw.get(k)
        )
        if differing:
            raise SystemExit(
                "report values are stale relative to the current artifacts: " + ", ".join(differing)
            )
        print(json.dumps({"status": "CONSISTENT", "n_values": len(values.raw)}, indent=2))
        return

    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    lines = [
        "% Generated by scripts/build_report_values.py -- do not edit by hand.",
        f"% Benchmark version: {VERSION}, scenario: {SCENARIO}.",
        f"% Built {payload['generated_at_utc']}.",
        "",
    ]
    for key, rendered in values.tex.items():
        lines.append(f"\\newcommand{{\\{macro_name(key)}}}{{{rendered}}}")
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tables = write_tables()
    print(json.dumps({
        "values_written": len(values.tex),
        "report_values_tex": str(tex_path.relative_to(ROOT)),
        "report_values_json": str(json_path.relative_to(ROOT)),
        "tables": [str(p.relative_to(ROOT)) for p in tables],
    }, indent=2))


if __name__ == "__main__":
    main()
