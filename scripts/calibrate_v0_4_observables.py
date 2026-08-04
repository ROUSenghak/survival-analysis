"""Estimate v0.4 observable generator parameters from calibration-side real BOAMP.

Every quantity fitted here is observable in the prepared real corpus:
notices per observed buyer key, publication year, observed first/last publication
date per key, checksum-valid SIRET presence, and distinct normalised buyer names
per checksum-valid SIREN. No accepted link, linkage score, acceptance threshold,
algorithm ranking or survival result is read.

Estimation uses only the *calibration* side of the frozen buyer-key holdout
(`config/synthetic/real_holdout_buyer_keys.csv`); the held-out 30% is never
touched here.

Outputs
-------
reports/tables/synthetic_benchmark/v0_4_population_alias_revision/calibration/
    activity_tail_fit.csv          candidate heavy-tail families and their fits
    activity_body_quantiles.csv    the smoothed empirical body grid
    span_by_activity_rank.csv      active-window length vs activity
    siret_buyer_effect_fit.csv     logit-scale between-buyer dispersion profile
    alias_set_size_weights.csv     distinct names per SIREN
    name_similarity_target.csv     the real within-SIREN similarity distribution
    observable_targets.json        everything above in one machine-readable file
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.holdout import CALIBRATION, load_real_buyer_holdout  # noqa: E402
from utils.identifiers import normalize_buyer_name  # noqa: E402

VERSION = "v0_4_population_alias_revision"
OUT = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION / "calibration"
PREPARED = ROOT / "data" / "interim" / "boamp_common_prepared.csv"

BODY_QUANTILE_GRID = tuple(
    [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
     0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.94, 0.97, 0.99, 1.0]
)
MIN_TAIL_KEYS = 50
MAX_XMIN_SEARCH = 200

# Activity-rank bins for the span curve. Deliberately finer above the 80th
# percentile: the top 1% of buyers carry 38% of all notices, and equal deciles
# average their span (0.78) together with the rest of the top decile down to
# 0.59, which is enough to make the whole publication-time mechanism unsolvable.
SPAN_RANK_BINS = (
    0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80,
    0.85, 0.90, 0.94, 0.97, 0.99, 0.995, 1.0,
)


# ---------------------------------------------------------------------------
# heavy-tail candidates
# ---------------------------------------------------------------------------


def _discrete_power_law_alpha(values: np.ndarray, xmin: float) -> float:
    """Clauset-Shalizi-Newman MLE for a discrete power law (their eq. 3.7)."""
    tail = values[values >= xmin]
    return 1.0 + len(tail) / float(np.sum(np.log(tail / (xmin - 0.5))))


def _discrete_power_law_ks(values: np.ndarray, xmin: float, alpha: float) -> float:
    from scipy.special import zeta

    tail = np.sort(values[values >= xmin])
    n = len(tail)
    empirical = np.arange(1, n + 1) / n
    theoretical = 1.0 - zeta(alpha, tail + 1) / zeta(alpha, xmin)
    return float(np.max(np.abs(empirical - theoretical)))


def _lomax_fit(values: np.ndarray, xmin: float) -> tuple[float, float, float]:
    """Lomax (Pareto type II) fitted to the tail by maximum likelihood."""
    from scipy.stats import lomax

    tail = values[values >= xmin].astype(float)
    shape, _loc, scale = lomax.fit(tail - xmin + 1e-9, floc=0)
    empirical = np.arange(1, len(tail) + 1) / len(tail)
    theoretical = lomax.cdf(np.sort(tail) - xmin + 1e-9, shape, loc=0, scale=scale)
    return float(shape), float(scale), float(np.max(np.abs(empirical - theoretical)))


def _zipf_mandelbrot_ks(values: np.ndarray, xmin: float) -> tuple[float, float, float]:
    """Zipf-Mandelbrot: a shifted discrete power law, P(x) ~ (x + q)^-alpha."""
    from scipy.optimize import minimize
    from scipy.special import zeta

    tail = np.sort(values[values >= xmin].astype(float))

    def negative_log_likelihood(params):
        alpha, q = params
        if alpha <= 1.01 or q <= -xmin + 0.51:
            return 1e12
        norm = zeta(alpha, xmin + q)
        return float(alpha * np.sum(np.log(tail + q)) + len(tail) * np.log(norm))

    result = minimize(
        negative_log_likelihood, x0=[2.0, 1.0], method="Nelder-Mead",
        options={"maxiter": 2000, "xatol": 1e-4, "fatol": 1e-4},
    )
    alpha, q = float(result.x[0]), float(result.x[1])
    empirical = np.arange(1, len(tail) + 1) / len(tail)
    theoretical = 1.0 - zeta(alpha, tail + q + 1) / zeta(alpha, xmin + q)
    return alpha, q, float(np.max(np.abs(empirical - theoretical)))


def fit_activity_tail(values: np.ndarray) -> tuple[pd.DataFrame, dict]:
    """Search x_min by KS, then compare three heavy-tail families at that x_min.

    The family is chosen on fit evidence (KS distance at the common x_min, plus
    parameter parsimony), not on visual resemblance to a straight line on a
    log-log plot -- the failure mode Clauset, Shalizi and Newman (2009) were
    writing about.
    """
    rows = []
    best = None
    for xmin in range(2, MAX_XMIN_SEARCH):
        if (values >= xmin).sum() < MIN_TAIL_KEYS:
            break
        alpha = _discrete_power_law_alpha(values, xmin)
        try:
            ks = _discrete_power_law_ks(values, xmin, alpha)
        except Exception:  # pragma: no cover - zeta domain guard
            continue
        rows.append({"xmin": xmin, "alpha": alpha, "ks": ks, "n_tail": int((values >= xmin).sum())})
        if best is None or ks < best["ks"]:
            best = rows[-1]

    search = pd.DataFrame(rows)
    xmin = float(best["xmin"])
    candidates = [
        {
            "family": "discrete_power_law",
            "n_parameters": 1,
            "alpha": float(best["alpha"]),
            "secondary_parameter": np.nan,
            "ks": float(best["ks"]),
        }
    ]
    lomax_shape, lomax_scale, lomax_ks = _lomax_fit(values, xmin)
    candidates.append(
        {
            "family": "lomax",
            "n_parameters": 2,
            "alpha": lomax_shape,
            "secondary_parameter": lomax_scale,
            "ks": lomax_ks,
        }
    )
    zm_alpha, zm_q, zm_ks = _zipf_mandelbrot_ks(values, xmin)
    candidates.append(
        {
            "family": "zipf_mandelbrot",
            "n_parameters": 2,
            "alpha": zm_alpha,
            "secondary_parameter": zm_q,
            "ks": zm_ks,
        }
    )
    table = pd.DataFrame(candidates)
    table["xmin"] = xmin
    table["n_tail"] = int((values >= xmin).sum())
    table["tail_key_share"] = float((values >= xmin).mean())
    table["tail_notice_share"] = float(values[values >= xmin].sum() / values.sum())
    table = table.sort_values("ks").reset_index(drop=True)

    chosen = table.iloc[0].to_dict()
    # Prefer the one-parameter family when a two-parameter family does not beat
    # it by a practically meaningful margin (10% of its KS distance).
    simplest = table.loc[table["n_parameters"].idxmin()]
    if chosen["family"] != simplest["family"] and chosen["ks"] > 0.9 * simplest["ks"]:
        chosen = simplest.to_dict()
    chosen["selection_rule"] = (
        "lowest KS at the shared x_min; the 1-parameter family wins ties within 10% KS"
    )
    return pd.concat([table.assign(selected=table["family"].eq(chosen["family"])), search.assign(
        family="xmin_search", n_parameters=np.nan, secondary_parameter=np.nan,
        tail_key_share=np.nan, tail_notice_share=np.nan, selected=False,
    )], ignore_index=True, sort=False), chosen


# ---------------------------------------------------------------------------
# between-buyer SIRET dispersion
# ---------------------------------------------------------------------------


def fit_siret_buyer_effect(real: pd.DataFrame, min_notices: int = 5) -> tuple[pd.DataFrame, float]:
    """Logit-scale between-buyer SD of checksum-valid SIRET presence.

    Marginal likelihood of a logit-normal-binomial random effect, integrated by
    Gauss-Hermite quadrature over a grid of sigma. Each buyer's baseline is its
    own notice-weighted mean of the schema x year x notice-type cell rates the
    generator is calibrated on, so the fitted sigma is dispersion *beyond* what
    the conditional model already explains -- which is exactly what the generator
    needs to add.
    """
    from scipy.special import expit, logit

    cell_cols = ["schema_family", "publication_year", "notice_type_normalized"]
    cell_rate = real.groupby(cell_cols)["siret_present"].transform("mean")
    real = real.assign(cell_rate=np.clip(cell_rate, 1e-4, 1 - 1e-4))

    grouped = real.groupby("buyer_name_normalized").agg(
        k=("siret_present", "sum"),
        n=("siret_present", "size"),
        baseline_logit=("cell_rate", lambda s: float(np.mean(logit(s)))),
    )
    grouped = grouped.loc[grouped["n"] >= min_notices]

    nodes, weights = np.polynomial.hermite_e.hermegauss(41)
    weights = weights / weights.sum()
    k = grouped["k"].to_numpy(dtype=float)
    n = grouped["n"].to_numpy(dtype=float)
    base = grouped["baseline_logit"].to_numpy(dtype=float)

    rows = []
    for sigma in np.round(np.arange(0.0, 4.01, 0.05), 2):
        p = expit(base[:, None] + sigma * nodes[None, :])
        p = np.clip(p, 1e-9, 1 - 1e-9)
        log_lik_component = k[:, None] * np.log(p) + (n - k)[:, None] * np.log1p(-p)
        # log-sum-exp over the quadrature nodes, weighted
        shift = log_lik_component.max(axis=1, keepdims=True)
        marginal = np.log((np.exp(log_lik_component - shift) * weights[None, :]).sum(axis=1)) + shift[:, 0]
        rows.append({"sigma": float(sigma), "log_likelihood": float(marginal.sum())})

    profile = pd.DataFrame(rows)
    best_sigma = float(profile.loc[profile["log_likelihood"].idxmax(), "sigma"])
    profile["selected"] = profile["sigma"].eq(best_sigma)
    profile["n_buyer_groups"] = int(len(grouped))
    profile["min_notices_per_group"] = min_notices
    return profile, best_sigma


# ---------------------------------------------------------------------------
# name variation
# ---------------------------------------------------------------------------


def within_siren_similarity(
    frame: pd.DataFrame, group_col: str, name_col: str, seed: int = 20260723, max_pairs: int = 20
) -> pd.DataFrame:
    """Same estimator the validation framework uses, so targets are comparable."""
    from rapidfuzz.distance import JaroWinkler

    sub = frame.loc[frame[group_col].notna() & frame[name_col].notna(), [group_col, name_col]]
    rng = np.random.default_rng(seed)
    rows = []
    for group, names in sub.groupby(group_col)[name_col]:
        distinct = sorted(set(names.astype(str)))
        if len(distinct) < 2:
            continue
        pairs = [(i, j) for i in range(len(distinct)) for j in range(i + 1, len(distinct))]
        if len(pairs) > max_pairs:
            pairs = [pairs[p] for p in rng.choice(len(pairs), size=max_pairs, replace=False)]
        for i, j in pairs:
            a, b = distinct[i], distinct[j]
            ta, tb = set(a.split()), set(b.split())
            union = ta | tb
            rows.append(
                {
                    "group": str(group),
                    "jaro_winkler": float(JaroWinkler.similarity(a, b)),
                    "token_jaccard": float(len(ta & tb) / len(union)) if union else np.nan,
                    "token_count_difference": abs(len(a.split()) - len(b.split())),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    holdout = load_real_buyer_holdout(ROOT)
    real = pd.read_csv(
        PREPARED,
        usecols=[
            "buyer_key", "buyer_key_type", "publication_date", "publication_year",
            "schema_family", "notice_type_normalized", "buyer_siret_clean",
            "buyer_siren_clean", "buyer_name_normalized",
        ],
        parse_dates=["publication_date"],
        low_memory=False,
    )
    real = holdout.filter(real, CALIBRATION)
    real = real.loc[real["buyer_key_type"].astype(str).ne("MISSING")]
    real["siret_present"] = real["buyer_siret_clean"].notna()

    # -- activity ---------------------------------------------------------
    activity = real.groupby("buyer_key").size()
    values = activity.to_numpy(dtype=float)
    mean_activity = float(values.mean())
    tail_table, tail_choice = fit_activity_tail(values)
    tail_table.to_csv(OUT / "activity_tail_fit.csv", index=False)

    xmin = float(tail_choice["xmin"])
    body = values[values < xmin]
    body_relative = np.quantile(body / mean_activity, BODY_QUANTILE_GRID)
    pd.DataFrame(
        {"quantile": BODY_QUANTILE_GRID, "relative_activity": body_relative}
    ).to_csv(OUT / "activity_body_quantiles.csv", index=False)

    # -- active window ----------------------------------------------------
    window_days = (pd.Timestamp("2026-07-13") - pd.Timestamp("2015-03-02")).days
    spans = real.groupby("buyer_key")["publication_date"].agg(["min", "max", "size"])
    spans["span_fraction"] = (spans["max"] - spans["min"]).dt.days / window_days
    spans["activity_percentile"] = spans["size"].rank(method="first", pct=True)
    spans["activity_rank_bin"] = pd.cut(
        spans["activity_percentile"], list(SPAN_RANK_BINS), include_lowest=True
    )
    span_curve = spans.groupby("activity_rank_bin", observed=True)["span_fraction"].agg(
        ["mean", "median", "count"]
    )
    span_curve["n_notices"] = spans.groupby("activity_rank_bin", observed=True)["size"].sum()
    # Knot positions are bin midpoints, so interpolation between them is a
    # faithful reading of the curve rather than an artefact of equal spacing.
    knot_positions = [
        (SPAN_RANK_BINS[i] + SPAN_RANK_BINS[i + 1]) / 2 for i in range(len(SPAN_RANK_BINS) - 1)
    ]
    span_curve["knot_position"] = knot_positions[: len(span_curve)]
    span_curve.to_csv(OUT / "span_by_activity_rank.csv")
    notice_weighted_span = float(
        (spans["span_fraction"] * spans["size"]).sum() / spans["size"].sum()
    )

    # -- publication-year shares (initial entry-weight seed) ---------------
    year_share = real["publication_year"].value_counts(normalize=True).sort_index()
    year_share.rename("real_share").to_csv(OUT / "publication_year_share.csv")

    # -- SIRET between-buyer dispersion -----------------------------------
    profile, buyer_sigma = fit_siret_buyer_effect(real)
    profile.to_csv(OUT / "siret_buyer_effect_fit.csv", index=False)

    # -- alias sets --------------------------------------------------------
    named = real.dropna(subset=["buyer_siren_clean", "buyer_name_normalized"])
    variants = named.groupby("buyer_siren_clean")["buyer_name_normalized"].nunique()
    alias_weights = variants.value_counts(normalize=True).sort_index()
    alias_weights.rename("share").to_csv(OUT / "alias_set_size_weights.csv")

    similarity = within_siren_similarity(real, "buyer_siren_clean", "buyer_name_normalized")
    similarity.to_csv(OUT / "name_similarity_pairs.csv", index=False)
    quantile_grid = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
    target = pd.DataFrame(
        {
            "quantile": quantile_grid,
            "token_jaccard": similarity["token_jaccard"].quantile(quantile_grid).to_numpy(),
            "jaro_winkler": similarity["jaro_winkler"].quantile(quantile_grid).to_numpy(),
        }
    )
    target.to_csv(OUT / "name_similarity_target.csv", index=False)

    zero_overlap_share = float((similarity["token_jaccard"] == 0).mean())
    full_overlap_share = float((similarity["token_jaccard"] == 1).mean())

    targets = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": VERSION,
        "calibration_split": CALIBRATION,
        "holdout_sha256": holdout.content_sha256,
        "source": "data/interim/boamp_common_prepared.csv",
        "provenance": "EMPIRICAL_OBSERVABLE",
        "n_calibration_notices": int(len(real)),
        "n_calibration_buyer_keys": int(len(activity)),
        "activity": {
            "mean_notices_per_key": mean_activity,
            "median_notices_per_key": float(np.median(values)),
            "gini": float(
                (2 * np.arange(1, len(values) + 1) - len(values) - 1).dot(np.sort(values))
                / (len(values) * values.sum())
            ),
            "top1pct_share": float(
                np.sort(values)[::-1][: max(1, round(0.01 * len(values)))].sum() / values.sum()
            ),
            "keys_per_notice": float(len(activity) / len(real)),
            "selected_tail_family": tail_choice["family"],
            "selection_rule": tail_choice["selection_rule"],
            "tail_alpha": float(tail_choice["alpha"]),
            "tail_xmin_absolute": xmin,
            "tail_xmin_relative": xmin / mean_activity,
            "tail_xmax_relative": float(values.max() / mean_activity),
            "max_notices_per_key": float(values.max()),
            "tail_key_share": float((values >= xmin).mean()),
            "tail_notice_share": float(values[values >= xmin].sum() / values.sum()),
            "body_quantile_grid": list(BODY_QUANTILE_GRID),
            "body_quantile_values": [float(v) for v in body_relative],
            "span_fraction_by_activity_rank": [float(v) for v in span_curve["mean"]],
            "span_knot_positions": [float(v) for v in span_curve["knot_position"]],
            "notice_weighted_observed_span_fraction": notice_weighted_span,
        },
        "publication_year_share": {int(k): float(v) for k, v in year_share.items()},
        "siret": {
            "aggregate_present_rate": float(real["siret_present"].mean()),
            "buyer_effect_logit_sd": buyer_sigma,
            "n_buyer_groups_used": int(profile["n_buyer_groups"].iloc[0]),
        },
        "buyer_names": {
            "alias_set_size_weights": {int(k): float(v) for k, v in alias_weights.items()},
            "mean_names_per_siren": float(variants.mean()),
            "n_pairs": int(len(similarity)),
            "zero_token_overlap_share": zero_overlap_share,
            "full_token_overlap_share": full_overlap_share,
            "token_jaccard_quantiles": dict(
                zip([str(q) for q in quantile_grid], target["token_jaccard"].round(6).tolist(), strict=False)
            ),
            "jaro_winkler_quantiles": dict(
                zip([str(q) for q in quantile_grid], target["jaro_winkler"].round(6).tolist(), strict=False)
            ),
            "mean_token_count_difference": float(similarity["token_count_difference"].mean()),
        },
    }
    (OUT / "observable_targets.json").write_text(json.dumps(targets, indent=2) + "\n", encoding="utf-8")

    print(f"calibration notices: {len(real)}  buyer keys: {len(activity)}")
    print(f"activity: mean={mean_activity:.3f} gini={targets['activity']['gini']:.4f} "
          f"top1%={targets['activity']['top1pct_share']:.4f} keys/notice={targets['activity']['keys_per_notice']:.5f}")
    print(f"tail: family={tail_choice['family']} alpha={tail_choice['alpha']:.4f} "
          f"xmin={xmin:.0f} (rel {xmin / mean_activity:.3f}) key_share={targets['activity']['tail_key_share']:.4f}")
    print(f"SIRET buyer random effect: logit sd = {buyer_sigma:.2f} over "
          f"{targets['siret']['n_buyer_groups_used']} buyer groups")
    print(f"aliases: mean names/SIREN={variants.mean():.3f} zero-overlap pair share={zero_overlap_share:.3f} "
          f"full-overlap={full_overlap_share:.4f}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
