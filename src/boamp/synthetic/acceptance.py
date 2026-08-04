"""Joint observable acceptance vector for the v0.4 development sweep.

The v0.4 revision touches three mechanisms at once, and each of them can fix one
observable metric while breaking another: concentrating the buyer population
raises candidate density, adding buyer-persistent SIRET visibility moves the
marginal identifier rate, and richer buyer-name aliases fragment the
NAME_FALLBACK key space. A sweep that optimised any single metric would
therefore be worse than no sweep at all.

This module computes every affected observable in one pass so a candidate
parameter set is accepted or rejected on the whole vector. It is a *development*
instrument: the released numbers still come from
`boamp.synthetic.validation_framework`, which is the gate of record. Metric
definitions here mirror that framework exactly (same populations, denominators
and estimators) so a sweep decision cannot be an artefact of a second,
subtly-different implementation.

Nothing in here reads accepted links, linkage scores, acceptance thresholds,
algorithm rankings, precision/recall/F1 or survival results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from boamp.config import load_config
from boamp.data.prepare import tag_digital_scope
from boamp.linkage.candidates import generate_pairs_single_key
from boamp.synthetic.compatibility import adapt_observed_notices_to_sources
from boamp.synthetic.holdout import CALIBRATION, load_real_buyer_holdout
from utils.text_clean import normalize_objet

SIMILARITY_QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
ACTIVITY_QUANTILES = (0.50, 0.90, 0.99)
MAX_PAIRS_PER_GROUP = 20
SIMILARITY_SEED = 20260723


@dataclass(frozen=True)
class AcceptanceTolerance:
    """One entry of the acceptance vector.

    `critical=True` marks the metrics that the v0.4 revision exists to fix or
    must not break; a candidate parameter set failing any of them is rejected
    outright rather than traded off.
    """

    metric: str
    tolerance: float
    critical: bool = False
    higher_is_worse: bool = True


ACCEPTANCE_TOLERANCES: tuple[AcceptanceTolerance, ...] = (
    # --- the five v0.3 hard failures -----------------------------------
    AcceptanceTolerance("siret_present_abs_diff_pp", 2.0, critical=True),
    AcceptanceTolerance("activity_relative_q99_abs_diff", 1.0, critical=True),
    AcceptanceTolerance("name_token_jaccard_q10_abs_diff", 0.15, critical=True),
    AcceptanceTolerance("name_token_jaccard_q50_abs_diff", 0.15, critical=True),
    # --- v0.3 warnings the same mechanisms should also move -------------
    AcceptanceTolerance("siren_present_abs_diff_pp", 2.0),
    AcceptanceTolerance("cpv_missing_abs_diff_pp", 2.0),
    AcceptanceTolerance("runway_60m_abs_diff_pp", 5.0),
    AcceptanceTolerance("name_jaro_winkler_q50_abs_diff", 0.15),
    AcceptanceTolerance("activity_top1pct_share_abs_diff_pp", 10.0),
    # --- must not regress ----------------------------------------------
    AcceptanceTolerance("publication_year_wmae_pp", 1.0, critical=True),
    AcceptanceTolerance("publication_year_tvd", 0.20),
    AcceptanceTolerance("activity_gini_abs_diff", 0.10),
    AcceptanceTolerance("activity_relative_q50_abs_diff", 1.0),
    AcceptanceTolerance("activity_relative_q90_abs_diff", 1.0),
    AcceptanceTolerance("keys_per_notice_relative_error", 0.20),
    AcceptanceTolerance("buyer_key_type_mix_tv", 0.10),
    AcceptanceTolerance("name_variants_per_buyer_abs_diff", 0.50),
    AcceptanceTolerance("candidate_source_count_ratio_deviation", 0.20, critical=True),
    AcceptanceTolerance("candidate_zero_rate_abs_diff_pp", 5.0, critical=True),
    AcceptanceTolerance("candidate_p75_abs_diff", 3.0, critical=True),
    AcceptanceTolerance("candidate_p90_abs_diff", 5.0, critical=True),
    AcceptanceTolerance("candidate_p95_abs_diff", 8.0, critical=True),
    AcceptanceTolerance("candidate_cap_reached_rate", 0.01, critical=True),
    AcceptanceTolerance("candidate_zero_rate_name_fallback_abs_diff_pp", 10.0),
    AcceptanceTolerance("candidate_zero_rate_raw_siret_abs_diff_pp", 10.0),
    AcceptanceTolerance("schema_family_tv", 0.05),
    AcceptanceTolerance("notice_type_tv", 0.05),
    AcceptanceTolerance("cpv_division_tv", 0.05),
    AcceptanceTolerance("duration_present_abs_diff_pp", 5.0),
    # --- text realism -----------------------------------------------------
    # Added after v0.4: the buyer-population correction moved notices into the
    # activity tiers that trigger the same-buyer administrative template, which
    # shortened the corpus and turned `text_length W1_scaled` into the release's
    # only metric failure. The sweep could not see that happening, because the
    # acceptance vector carried no text metric at all. Tolerances mirror
    # validation_framework.text and .fidelity exactly.
    AcceptanceTolerance("text_length_w1_scaled", 0.10, critical=True),
    AcceptanceTolerance("text_length_q50_relative_error", 0.10),
    AcceptanceTolerance("text_length_q75_relative_error", 0.10),
    AcceptanceTolerance("token_count_q50_relative_error", 0.20),
    AcceptanceTolerance("unigram_js", 0.30),
    AcceptanceTolerance("bigram_js", 0.40),
    AcceptanceTolerance("internal_duplicate_share_abs_diff_pp", 10.0),
    AcceptanceTolerance("type_token_ratio_abs_diff", 0.15),
    # --- linkage difficulty (synthetic truth; opt-in, see evaluate_observed) --
    # These are the gates a text change can silently break: less repeated text
    # means more discriminating text, which makes the benchmark easier. They are
    # scored against the *benchmark's own* declared floors, not against real
    # BOAMP, because no real linkage truth exists.
    AcceptanceTolerance("production_pairs_completeness_shortfall", 0.0, critical=True),
    AcceptanceTolerance("widened_pairs_completeness_shortfall", 0.0, critical=True),
    AcceptanceTolerance("pairs_quality_shortfall", 0.0, critical=True),
    AcceptanceTolerance("probe_best_f1_excess", 0.0, critical=True),
    AcceptanceTolerance("probe_f1_spread_shortfall", 0.0, critical=True),
)

TOLERANCE_BY_METRIC = {t.metric: t for t in ACCEPTANCE_TOLERANCES}


@dataclass
class AcceptanceResult:
    values: dict[str, float]
    real: dict[str, float] = field(default_factory=dict)
    synthetic: dict[str, float] = field(default_factory=dict)
    context: dict[str, float] = field(default_factory=dict)

    def status(self, metric: str) -> str:
        tolerance = TOLERANCE_BY_METRIC.get(metric)
        value = self.values.get(metric)
        if tolerance is None or value is None or not np.isfinite(value):
            return "CONTEXT"
        return "PASS" if abs(value) <= tolerance.tolerance else "FAIL"

    @property
    def critical_failures(self) -> list[str]:
        return [
            t.metric
            for t in ACCEPTANCE_TOLERANCES
            if t.critical and self.status(t.metric) == "FAIL"
        ]

    @property
    def failures(self) -> list[str]:
        return [t.metric for t in ACCEPTANCE_TOLERANCES if self.status(t.metric) == "FAIL"]

    @property
    def accepted(self) -> bool:
        return not self.critical_failures

    def to_frame(self) -> pd.DataFrame:
        rows = []
        for tolerance in ACCEPTANCE_TOLERANCES:
            rows.append(
                {
                    "metric": tolerance.metric,
                    "real": self.real.get(tolerance.metric, np.nan),
                    "synthetic": self.synthetic.get(tolerance.metric, np.nan),
                    "value": self.values.get(tolerance.metric, np.nan),
                    "tolerance": tolerance.tolerance,
                    "critical": tolerance.critical,
                    "status": self.status(tolerance.metric),
                }
            )
        for key, value in sorted(self.context.items()):
            rows.append(
                {
                    "metric": key,
                    "real": np.nan,
                    "synthetic": value,
                    "value": np.nan,
                    "tolerance": np.nan,
                    "critical": False,
                    "status": "CONTEXT",
                }
            )
        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# real reference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RealReference:
    """Real-side statistics, computed once per (split, project root)."""

    split: str
    n_notices: int
    activity: pd.Series
    year_share: pd.Series
    schema_share: pd.Series
    notice_type_share: pd.Series
    cpv_division_share: pd.Series
    key_type_share: pd.Series
    siret_present_rate: float
    siren_present_rate: float
    cpv_missing_rate: float
    duration_present_rate: float
    runway_rate_60m: float
    similarity: pd.DataFrame
    name_variants_mean: float
    candidate_counts: pd.DataFrame
    n_prepared_notices: int


def _normalize_division(series: pd.Series) -> pd.Series:
    """CPV division as a bare two-digit string on both sides of the comparison."""
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.astype("Int64").astype("string")


def _shares(series: pd.Series) -> pd.Series:
    counts = series.fillna("__MISSING__").astype(str).value_counts()
    return counts / counts.sum() if counts.sum() else counts


def _tv(a: pd.Series, b: pd.Series) -> float:
    index = a.index.union(b.index)
    return float(0.5 * (a.reindex(index, fill_value=0) - b.reindex(index, fill_value=0)).abs().sum())


def _wmae_pp(real: pd.Series, synthetic: pd.Series) -> float:
    """Real-share-weighted mean absolute share error, in percentage points.

    TVD over twelve publication years tolerates a 15 pp shift in the year mix, as
    v0.3 demonstrated. Weighting each year's absolute share error by that year's
    real share makes the same error visible at a scale that matches the other
    conditional gates in the framework.
    """
    index = real.index.union(synthetic.index)
    r = real.reindex(index, fill_value=0.0)
    s = synthetic.reindex(index, fill_value=0.0)
    weights = r / r.sum() if r.sum() else r
    return float((weights * (s - r).abs() * 100).sum())


def _gini(values: np.ndarray) -> float:
    values = np.sort(np.asarray(values, dtype=float))
    n = len(values)
    total = values.sum()
    if n == 0 or total <= 0:
        return float("nan")
    return float((2 * np.arange(1, n + 1) - n - 1).dot(values) / (n * total))


def _top_share(values: np.ndarray, fraction: float) -> float:
    ordered = np.sort(np.asarray(values, dtype=float))[::-1]
    k = max(1, int(round(fraction * len(ordered))))
    total = ordered.sum()
    return float(ordered[:k].sum() / total) if total > 0 else float("nan")


def within_group_similarity(
    frame: pd.DataFrame, group_col: str, name_col: str
) -> pd.DataFrame:
    """Identical estimator to validation_framework.structure._within_group_similarities."""
    from rapidfuzz.distance import JaroWinkler

    sub = frame.loc[frame[group_col].notna() & frame[name_col].notna(), [group_col, name_col]]
    if sub.empty:
        return pd.DataFrame(columns=["jaro_winkler", "token_jaccard", "token_count_difference"])
    rng = np.random.default_rng(SIMILARITY_SEED)
    rows = []
    for _group, names in sub.groupby(group_col)[name_col]:
        distinct = sorted(set(names.astype(str)))
        if len(distinct) < 2:
            continue
        pairs = [(i, j) for i in range(len(distinct)) for j in range(i + 1, len(distinct))]
        if len(pairs) > MAX_PAIRS_PER_GROUP:
            picks = rng.choice(len(pairs), size=MAX_PAIRS_PER_GROUP, replace=False)
            pairs = [pairs[p] for p in picks]
        for i, j in pairs:
            a, b = distinct[i], distinct[j]
            ta, tb = set(a.split()), set(b.split())
            union = ta | tb
            rows.append(
                {
                    "jaro_winkler": float(JaroWinkler.similarity(a, b)),
                    "token_jaccard": float(len(ta & tb) / len(union)) if union else np.nan,
                    "token_count_difference": abs(len(a.split()) - len(b.split())),
                }
            )
    return pd.DataFrame(rows, columns=["jaro_winkler", "token_jaccard", "token_count_difference"])


def _candidate_count_frame(sources: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    eligible = sources.loc[sources["buyer_key_type"] != "MISSING"].copy()
    counts = pairs.groupby("source_notice_id").size() if len(pairs) else pd.Series(dtype=int)
    keep = [c for c in ["notice_id", "buyer_key_type"] if c in eligible.columns]
    out = eligible[keep].copy()
    out["candidate_count"] = out["notice_id"].map(counts).fillna(0).astype(int)
    return out


@lru_cache(maxsize=4)
def load_real_reference(project_root_str: str, split: str | None = CALIBRATION) -> RealReference:
    project_root = Path(project_root_str)
    real = pd.read_csv(
        project_root / "data" / "interim" / "boamp_common_prepared.csv",
        usecols=[
            "notice_id", "publication_date", "publication_year", "schema_family",
            "notice_type_normalized", "buyer_siret_clean", "buyer_siren_clean",
            "buyer_name_normalized", "buyer_key", "buyer_key_type", "cpv_clean",
            "cpv_division", "duration_raw",
        ],
        parse_dates=["publication_date"],
        low_memory=False,
    )
    n_prepared = len(real)
    sources = pd.read_csv(
        project_root / "data" / "processed" / "boamp_only" / "boamp_only_sources.csv",
        parse_dates=["publication_date"],
    )
    pairs = pd.read_csv(
        project_root / "data" / "processed" / "boamp_only" / "boamp_only_candidate_pairs.csv"
    )

    if split is not None:
        holdout = load_real_buyer_holdout(project_root)
        real = holdout.filter(real, split)
        sources = holdout.filter(sources, split)
        pairs = pairs.loc[pairs["source_notice_id"].isin(sources["notice_id"])]
        # The scoped-source-count ratio scales the real source count by the
        # synthetic-to-real notice ratio. Both terms must come from the *same*
        # population: pairing a split-filtered source count with the full-corpus
        # notice count understates the expected count by the split fraction and
        # makes every candidate look ~36% too dense.
        n_prepared = len(real)

    eligible = real.loc[real["buyer_key_type"].astype(str).ne("MISSING")]
    study_end = pd.Timestamp("2026-07-13")
    cfg = load_config(project_root)
    days_60m = int(round(60 * cfg.pipeline.run.month_days))

    return RealReference(
        split=split or "full_corpus",
        n_notices=int(len(real)),
        activity=eligible.groupby("buyer_key").size(),
        year_share=_shares(real["publication_year"]),
        schema_share=_shares(real["schema_family"]),
        notice_type_share=_shares(real["notice_type_normalized"]),
        cpv_division_share=_shares(_normalize_division(real["cpv_division"])),
        key_type_share=_shares(real["buyer_key_type"]),
        siret_present_rate=float(real["buyer_siret_clean"].notna().mean()),
        siren_present_rate=float(real["buyer_siren_clean"].notna().mean()),
        cpv_missing_rate=float(real["cpv_clean"].isna().mean()),
        duration_present_rate=float(real["duration_raw"].notna().mean()),
        runway_rate_60m=float(((study_end - real["publication_date"]).dt.days >= days_60m).mean()),
        similarity=within_group_similarity(real, "buyer_siren_clean", "buyer_name_normalized"),
        name_variants_mean=float(
            real.dropna(subset=["buyer_siren_clean", "buyer_name_normalized"])
            .groupby("buyer_siren_clean")["buyer_name_normalized"]
            .nunique()
            .mean()
        ),
        candidate_counts=_candidate_count_frame(sources, pairs),
        n_prepared_notices=n_prepared,
    )


# ---------------------------------------------------------------------------
# synthetic side and the vector itself
# ---------------------------------------------------------------------------


def _benchmark_data_from_world(
    observed: pd.DataFrame, world: dict, project_root: Path
) -> "object":
    """Wrap an in-memory generated world in the shape the gates expect.

    The text and difficulty gates are functions of `BenchmarkData`. Building one
    here lets the sweep call the *same* functions the release validation calls,
    instead of a second implementation that could drift from them. Fields the
    two gates never touch are filled with empty frames.
    """
    from boamp.synthetic.validation_framework.loaders import BenchmarkData, _load_real_frames

    real, real_sources, real_pairs = _load_real_frames(str(project_root))
    empty = pd.DataFrame()
    return BenchmarkData(
        project_root=project_root,
        benchmark_version="sweep",
        scenario="sweep",
        world="000",
        corruption="000",
        synthetic_dir=project_root,
        observed=observed,
        clean=world.get("clean_notices", empty),
        true_relations=world.get("true_relations", empty),
        notice_family_membership=world.get("notice_family_membership", empty),
        corruption_log=empty,
        latent_cycles=world.get("cycles", empty),
        latent_needs=world.get("needs", empty),
        latent_buyers=world.get("buyers", empty),
        latent_establishments=world.get("establishments", empty),
        metadata={"world_seed": "sweep", "corruption_seed": "sweep"},
        real=real,
        real_sources=real_sources,
        real_pairs=real_pairs,
    )


def _text_and_difficulty(
    observed: pd.DataFrame,
    project_root: Path,
    world: dict | None,
    include_difficulty: bool,
) -> tuple[dict, dict, dict, dict]:
    """Text-realism and (optionally) linkage-difficulty entries for the vector.

    Both are computed by calling the release gates and reading their results,
    so a sweep decision cannot disagree with the gate that will later judge it.
    Difficulty is opt-in because it regenerates candidates at two windows and
    scores every pair, which roughly triples the cost of evaluating a candidate
    parameter set.
    """
    from boamp.synthetic.validation_framework.difficulty import (
        TOLERANCES as DIFFICULTY_FLOORS,
        run_difficulty_metrics,
    )
    from boamp.synthetic.validation_framework.fidelity import run_marginal_metrics
    from boamp.synthetic.validation_framework.text import run_text_profile_metrics

    data = _benchmark_data_from_world(observed, world or {}, project_root)
    values: dict[str, float] = {}
    real: dict[str, float] = {}
    synthetic: dict[str, float] = {}

    def take(results, wanted: dict[str, str]) -> None:
        for result in results:
            key = f"{result.property}:{result.metric}"
            name = wanted.get(key)
            if name is None:
                continue
            values[name] = float(result.effect_size) if result.effect_size is not None else float("nan")
            real[name] = float(result.real_estimate) if result.real_estimate is not None else float("nan")
            synthetic[name] = (
                float(result.synthetic_estimate) if result.synthetic_estimate is not None else float("nan")
            )

    # `text_length` W1 and its quantiles live in the marginals gate; the ngram,
    # duplication and diversity statistics live in the text gate.
    take(
        run_marginal_metrics(data),
        {
            "text_length:W1_scaled": "text_length_w1_scaled",
            "text_length:q50_relative_error": "text_length_q50_relative_error",
            "text_length:q75_relative_error": "text_length_q75_relative_error",
        },
    )
    take(
        run_text_profile_metrics(data),
        {
            "token_count:q50_relative_error": "token_count_q50_relative_error",
            "unigram_distribution:JS": "unigram_js",
            "bigram_distribution:JS": "bigram_js",
            "internal_duplicate_share:abs_diff_pp": "internal_duplicate_share_abs_diff_pp",
            "type_token_ratio:abs_diff": "type_token_ratio_abs_diff",
        },
    )

    context: dict[str, float] = {}
    if not include_difficulty or world is None:
        return values, real, synthetic, context

    difficulty, _probe_frame = run_difficulty_metrics(data)
    # These gates are one-sided floors and ceilings rather than two-sided
    # tolerances, so each is converted to a non-negative shortfall/excess whose
    # tolerance is 0: any positive value is a violation.
    floors = {
        "pairs_completeness:PRODUCTION_BLOCKING": (
            "production_pairs_completeness_shortfall",
            DIFFICULTY_FLOORS["production_pairs_completeness_min"],
            "floor",
        ),
        f"pairs_completeness:{'36M_BLOCKING'}": (
            "widened_pairs_completeness_shortfall",
            DIFFICULTY_FLOORS["widened_pairs_completeness_min"],
            "floor",
        ),
        "pairs_quality:PQ": ("pairs_quality_shortfall", DIFFICULTY_FLOORS["pairs_quality_min"], "floor"),
        "probe_headroom:best_pair_f1": (
            "probe_best_f1_excess",
            DIFFICULTY_FLOORS["probe_best_f1_max"],
            "ceiling",
        ),
        "probe_headroom:pair_f1_spread": (
            "probe_f1_spread_shortfall",
            DIFFICULTY_FLOORS["probe_f1_spread_min"],
            "floor",
        ),
    }
    for result in difficulty:
        for key, (name, bound, kind) in floors.items():
            prop, metric = key.split(":", 1)
            if result.property != prop or result.metric != metric:
                continue
            observed_value = result.synthetic_estimate
            if observed_value is None:
                continue
            observed_value = float(observed_value)
            values[name] = (
                max(0.0, bound - observed_value) if kind == "floor"
                else max(0.0, observed_value - bound)
            )
            real[name] = bound
            synthetic[name] = observed_value
            context[f"raw_{name}"] = observed_value
    return values, real, synthetic, context


def evaluate_observed(
    observed: pd.DataFrame,
    project_root: Path,
    *,
    split: str | None = CALIBRATION,
    world: dict | None = None,
    include_difficulty: bool = False,
) -> AcceptanceResult:
    """Score one observed-notices frame against the real reference.

    Passing `world` (the dict `generate_clean_world` returns) adds the text
    metrics; additionally setting `include_difficulty` adds the truth-dependent
    linkage-difficulty floors, at roughly triple the evaluation cost.
    """
    project_root = Path(project_root)
    reference = load_real_reference(str(project_root), split)
    cfg = load_config(project_root)

    sources = adapt_observed_notices_to_sources(observed)
    sources["publication_year"] = pd.to_datetime(sources["publication_date"]).dt.year
    # `adapt_observed_notices_to_sources` already derives cpv_division as the
    # first two characters of the code. The real corpus stores it as a float, so
    # both sides are normalised to a plain integer-like string before comparison
    # -- otherwise "45" and "45.0" look like two different divisions and the
    # comparison reports a total-variation distance of 0.85 for identical data.
    sources["cpv_division"] = _normalize_division(sources["cpv_division"])

    values: dict[str, float] = {}
    real: dict[str, float] = {}
    synthetic: dict[str, float] = {}
    context: dict[str, float] = {}

    def record(metric: str, real_value, syn_value, difference) -> None:
        real[metric] = float(real_value) if real_value is not None else np.nan
        synthetic[metric] = float(syn_value) if syn_value is not None else np.nan
        values[metric] = float(difference)

    # -- composition -------------------------------------------------------
    year_share = _shares(sources["publication_year"])
    record("publication_year_wmae_pp", None, None, _wmae_pp(reference.year_share, year_share))
    record("publication_year_tvd", None, None, _tv(reference.year_share, year_share))
    record("schema_family_tv", None, None, _tv(reference.schema_share, _shares(sources["schema_family"])))
    record(
        "notice_type_tv", None, None,
        _tv(reference.notice_type_share, _shares(sources["notice_type_normalized"])),
    )
    record(
        "cpv_division_tv", None, None,
        _tv(reference.cpv_division_share, _shares(sources["cpv_division"])),
    )

    study_end = pd.Timestamp("2026-07-13")
    days_60m = int(round(60 * cfg.pipeline.run.month_days))
    runway = float(
        ((study_end - pd.to_datetime(sources["publication_date"])).dt.days >= days_60m).mean()
    )
    record(
        "runway_60m_abs_diff_pp", reference.runway_rate_60m, runway,
        (runway - reference.runway_rate_60m) * 100,
    )

    # -- identifier and field availability ---------------------------------
    siret_present = float(observed["buyer_siret_raw"].notna().mean())
    siren_present = float(observed["buyer_siren_raw"].notna().mean())
    cpv_missing = float(observed["cpv_clean"].isna().mean())
    duration_present = float(observed["declared_duration_months"].notna().mean())
    record(
        "siret_present_abs_diff_pp", reference.siret_present_rate, siret_present,
        (siret_present - reference.siret_present_rate) * 100,
    )
    record(
        "siren_present_abs_diff_pp", reference.siren_present_rate, siren_present,
        (siren_present - reference.siren_present_rate) * 100,
    )
    record(
        "cpv_missing_abs_diff_pp", reference.cpv_missing_rate, cpv_missing,
        (cpv_missing - reference.cpv_missing_rate) * 100,
    )
    record(
        "duration_present_abs_diff_pp", reference.duration_present_rate, duration_present,
        (duration_present - reference.duration_present_rate) * 100,
    )

    # -- buyer activity ----------------------------------------------------
    eligible = sources.loc[sources["buyer_key_type"].astype(str).ne("MISSING")]
    activity = eligible.groupby("buyer_key").size()
    real_activity = reference.activity
    record(
        "activity_gini_abs_diff", _gini(real_activity.to_numpy()), _gini(activity.to_numpy()),
        _gini(activity.to_numpy()) - _gini(real_activity.to_numpy()),
    )
    record(
        "activity_top1pct_share_abs_diff_pp",
        _top_share(real_activity.to_numpy(), 0.01), _top_share(activity.to_numpy(), 0.01),
        (_top_share(activity.to_numpy(), 0.01) - _top_share(real_activity.to_numpy(), 0.01)) * 100,
    )
    real_relative = real_activity / real_activity.mean()
    syn_relative = activity / activity.mean() if len(activity) else activity
    for q in ACTIVITY_QUANTILES:
        rq = float(real_relative.quantile(q))
        sq = float(syn_relative.quantile(q)) if len(syn_relative) else np.nan
        record(f"activity_relative_q{int(q * 100)}_abs_diff", rq, sq, sq - rq)

    real_keys_per_notice = len(real_activity) / reference.n_notices
    syn_keys_per_notice = len(activity) / len(sources)
    record(
        "keys_per_notice_relative_error", real_keys_per_notice, syn_keys_per_notice,
        (syn_keys_per_notice - real_keys_per_notice) / real_keys_per_notice,
    )
    record(
        "buyer_key_type_mix_tv", None, None,
        _tv(reference.key_type_share, _shares(sources["buyer_key_type"])),
    )
    context["n_synthetic_buyer_keys"] = float(len(activity))
    context["n_synthetic_notices"] = float(len(sources))
    context["synthetic_mean_notices_per_key"] = float(activity.mean()) if len(activity) else np.nan
    context["synthetic_max_notices_per_key"] = float(activity.max()) if len(activity) else np.nan

    # -- buyer names -------------------------------------------------------
    similarity = within_group_similarity(sources, "buyer_siren_clean", "buyer_name_normalized")
    for column, label in [("token_jaccard", "name_token_jaccard"), ("jaro_winkler", "name_jaro_winkler")]:
        for q in SIMILARITY_QUANTILES:
            metric = f"{label}_q{int(q * 100)}_abs_diff"
            rq = float(reference.similarity[column].quantile(q)) if len(reference.similarity) else np.nan
            sq = float(similarity[column].quantile(q)) if len(similarity) else np.nan
            real[metric] = rq
            synthetic[metric] = sq
            values[metric] = sq - rq
    context["n_synthetic_name_pairs"] = float(len(similarity))
    context["n_real_name_pairs"] = float(len(reference.similarity))
    context["synthetic_zero_token_overlap_share"] = (
        float((similarity["token_jaccard"] == 0).mean()) if len(similarity) else np.nan
    )
    context["real_zero_token_overlap_share"] = (
        float((reference.similarity["token_jaccard"] == 0).mean())
        if len(reference.similarity) else np.nan
    )
    context["synthetic_full_token_overlap_share"] = (
        float((similarity["token_jaccard"] == 1).mean()) if len(similarity) else np.nan
    )
    syn_variants = (
        sources.dropna(subset=["buyer_siren_clean", "buyer_name_normalized"])
        .groupby("buyer_siren_clean")["buyer_name_normalized"]
        .nunique()
    )
    record(
        "name_variants_per_buyer_abs_diff", reference.name_variants_mean,
        float(syn_variants.mean()) if len(syn_variants) else np.nan,
        (float(syn_variants.mean()) if len(syn_variants) else np.nan) - reference.name_variants_mean,
    )

    # -- candidate environment --------------------------------------------
    sources["objet_normalized"] = sources["objet_clean"].map(normalize_objet)
    sources["is_digital_scope"] = sources.apply(
        lambda row: tag_digital_scope(row["cpv_division"], row["objet_normalized"], cfg), axis=1
    )
    scoped = sources.loc[
        sources["notice_type_normalized"].eq("APPEL_OFFRE") & sources["is_digital_scope"]
    ].copy()
    syn_pairs, _window = generate_pairs_single_key(scoped, cfg, verbose=False)
    syn_counts = _candidate_count_frame(scoped, syn_pairs)
    real_counts = reference.candidate_counts
    max_candidates = cfg.pipeline.candidates.max_candidates_per_source

    expected_sources = len(real_counts) * len(sources) / reference.n_prepared_notices
    ratio = len(syn_counts) / expected_sources if expected_sources else np.nan
    record("candidate_source_count_ratio_deviation", 1.0, ratio, ratio - 1.0)

    real_zero = float((real_counts["candidate_count"] == 0).mean())
    syn_zero = float((syn_counts["candidate_count"] == 0).mean()) if len(syn_counts) else np.nan
    record("candidate_zero_rate_abs_diff_pp", real_zero, syn_zero, (syn_zero - real_zero) * 100)
    for q, label in [(0.75, "p75"), (0.90, "p90"), (0.95, "p95")]:
        rq = float(real_counts["candidate_count"].quantile(q))
        sq = float(syn_counts["candidate_count"].quantile(q)) if len(syn_counts) else np.nan
        record(f"candidate_{label}_abs_diff", rq, sq, sq - rq)
    cap_rate = (
        float((syn_counts["candidate_count"] >= max_candidates).mean()) if len(syn_counts) else np.nan
    )
    record("candidate_cap_reached_rate", 0.0, cap_rate, cap_rate)
    for key, label in [("NAME_FALLBACK", "name_fallback"), ("RAW_SIRET", "raw_siret")]:
        rk = real_counts.loc[real_counts["buyer_key_type"].eq(key), "candidate_count"]
        sk = syn_counts.loc[syn_counts["buyer_key_type"].eq(key), "candidate_count"]
        rr = float((rk == 0).mean()) if len(rk) >= 30 else np.nan
        sr = float((sk == 0).mean()) if len(sk) >= 30 else np.nan
        record(f"candidate_zero_rate_{label}_abs_diff_pp", rr, sr, (sr - rr) * 100)
    context["n_synthetic_scoped_sources"] = float(len(syn_counts))
    context["n_real_scoped_sources"] = float(len(real_counts))

    # -- text realism and linkage difficulty -------------------------------
    # Computed by calling the release gates so the sweep and the gate that will
    # later judge the release cannot disagree.
    text_values, text_real, text_syn, text_context = _text_and_difficulty(
        observed, project_root, world, include_difficulty
    )
    values.update(text_values)
    real.update(text_real)
    synthetic.update(text_syn)
    context.update(text_context)

    return AcceptanceResult(values=values, real=real, synthetic=synthetic, context=context)
