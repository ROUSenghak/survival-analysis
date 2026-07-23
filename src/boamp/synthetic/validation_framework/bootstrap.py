"""Cluster bootstrap intervals and equivalence (TOST) decisions.

Section 4 of the validation specification is explicit that "fail to reject"
must never be read as "equivalent": with ~9.5k synthetic and ~200k real rows,
a classical equality test rejects on differences far too small to matter for
linkage. Decisions here are therefore driven by an interval on the
real-vs-synthetic difference plus a predeclared practical tolerance, following
the two-one-sided-tests logic (Lakens 2017): equivalence is claimed only when
the whole interval sits inside (-delta, +delta).

Resampling is clustered at the buyer level because notices from one buyer
share text, identifiers and missingness behaviour; an iid bootstrap would
report intervals several times too narrow.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from boamp.synthetic.validation_framework.models import Status


DEFAULT_REPS = 200
DEFAULT_SEED = 20260723


def _cluster_index(frame: pd.DataFrame, cluster_col: str | None) -> tuple[np.ndarray, list[np.ndarray]]:
    """Return (cluster labels, row-index arrays per cluster)."""
    if cluster_col is None or cluster_col not in frame.columns:
        # Degenerate clustering: every row is its own cluster (iid bootstrap).
        positions = np.arange(len(frame))
        return positions, [np.array([p]) for p in positions]
    codes = frame[cluster_col].fillna("__MISSING__").astype(str).to_numpy()
    positions = pd.Series(np.arange(len(frame)))
    groups = [np.asarray(v, dtype=int) for v in positions.groupby(codes, sort=False).indices.values()]
    return codes, groups


def _resample(frame: pd.DataFrame, groups: list[np.ndarray], rng: np.random.Generator) -> pd.DataFrame:
    if not groups:
        return frame.iloc[[]]
    picks = rng.integers(0, len(groups), size=len(groups))
    rows = np.concatenate([groups[p] for p in picks]) if len(picks) else np.array([], dtype=int)
    return frame.iloc[rows]


def cluster_bootstrap_difference(
    real: pd.DataFrame,
    synthetic: pd.DataFrame,
    statistic: Callable[[pd.DataFrame], float],
    real_cluster: str | None = "buyer_key",
    synthetic_cluster: str | None = "buyer_key",
    reps: int = DEFAULT_REPS,
    seed: int = DEFAULT_SEED,
    scale: float = 1.0,
) -> dict:
    """Bootstrap CI for ``scale * (statistic(synthetic) - statistic(real))``.

    ``scale`` exists so a rate difference can be reported in percentage points
    (scale=100) while the statistic itself stays a proportion.
    """
    point_real = float(statistic(real))
    point_syn = float(statistic(synthetic))
    observed = scale * (point_syn - point_real)
    if reps <= 0:
        return {
            "real": point_real,
            "synthetic": point_syn,
            "difference": observed,
            "ci_low": None,
            "ci_high": None,
            "reps": 0,
        }

    rng = np.random.default_rng(seed)
    _, real_groups = _cluster_index(real, real_cluster)
    _, syn_groups = _cluster_index(synthetic, synthetic_cluster)

    draws = np.empty(reps, dtype=float)
    for b in range(reps):
        try:
            r = statistic(_resample(real, real_groups, rng))
            s = statistic(_resample(synthetic, syn_groups, rng))
            draws[b] = scale * (float(s) - float(r))
        except (ValueError, ZeroDivisionError, IndexError):
            draws[b] = np.nan
    finite = draws[np.isfinite(draws)]
    if len(finite) < max(20, reps // 10):
        return {
            "real": point_real,
            "synthetic": point_syn,
            "difference": observed,
            "ci_low": None,
            "ci_high": None,
            "reps": int(len(finite)),
        }
    lo, hi = np.percentile(finite, [2.5, 97.5])
    return {
        "real": point_real,
        "synthetic": point_syn,
        "difference": observed,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "reps": int(len(finite)),
    }


def equivalence_status(
    difference: float | None,
    ci_low: float | None,
    ci_high: float | None,
    delta: float,
    warning_delta: float | None = None,
) -> Status:
    """TOST-style decision on a difference and its bootstrap interval.

    PASS   -- the whole interval lies inside (-delta, +delta): practical
              equivalence is supported, not merely un-rejected.
    WARNING-- the point estimate is inside the tolerance but the interval is
              not (under-powered), or the estimate sits in the wider warning
              band.
    FAIL   -- the interval lies wholly outside the warning band, i.e. a
              material difference is established rather than suspected.
    """
    if difference is None or not np.isfinite(float(difference)):
        return Status.INCONCLUSIVE
    difference = float(difference)
    warning_delta = delta * 2 if warning_delta is None else warning_delta

    if ci_low is None or ci_high is None:
        # No interval available: fall back to a point-estimate verdict, which
        # can never claim equivalence, only "not obviously discrepant".
        if abs(difference) <= delta:
            return Status.PASS
        return Status.WARNING if abs(difference) <= warning_delta else Status.FAIL

    ci_low, ci_high = float(ci_low), float(ci_high)
    if ci_low >= -delta and ci_high <= delta:
        return Status.PASS
    if ci_low > warning_delta or ci_high < -warning_delta:
        return Status.FAIL
    if abs(difference) > warning_delta:
        return Status.FAIL
    return Status.WARNING


def bootstrap_quantile_ci(
    values: pd.Series,
    q: float,
    cluster: pd.Series | None = None,
    reps: int = DEFAULT_REPS,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float | None, float | None]:
    """Point estimate and clustered bootstrap CI for a single quantile."""
    values = pd.to_numeric(values, errors="coerce")
    frame = pd.DataFrame({"value": values})
    if cluster is not None:
        frame["cluster"] = cluster.astype(str).to_numpy()
    frame = frame.dropna(subset=["value"])
    if frame.empty:
        return float("nan"), None, None
    point = float(frame["value"].quantile(q))
    if reps <= 0:
        return point, None, None
    rng = np.random.default_rng(seed)
    _, groups = _cluster_index(frame, "cluster" if "cluster" in frame.columns else None)
    draws = np.array(
        [float(_resample(frame, groups, rng)["value"].quantile(q)) for _ in range(reps)]
    )
    finite = draws[np.isfinite(draws)]
    if len(finite) < max(20, reps // 10):
        return point, None, None
    lo, hi = np.percentile(finite, [2.5, 97.5])
    return point, float(lo), float(hi)


def gini(values: np.ndarray | pd.Series) -> float:
    """Gini concentration coefficient of a non-negative activity vector."""
    x = np.sort(np.asarray(pd.to_numeric(pd.Series(values), errors="coerce").dropna(), dtype=float))
    if x.size == 0 or x.sum() <= 0:
        return float("nan")
    n = x.size
    index = np.arange(1, n + 1)
    return float((2 * (index * x).sum()) / (n * x.sum()) - (n + 1) / n)


def top_share(values: np.ndarray | pd.Series, fraction: float) -> float:
    """Share of total activity held by the most active ``fraction`` of units."""
    x = np.sort(np.asarray(pd.to_numeric(pd.Series(values), errors="coerce").dropna(), dtype=float))[::-1]
    if x.size == 0 or x.sum() <= 0:
        return float("nan")
    k = max(1, int(round(fraction * x.size)))
    return float(x[:k].sum() / x.sum())


def overlap_coefficient(a: pd.Series, b: pd.Series, bins: int = 50) -> float:
    """Overlapping area of two densities, estimated on a shared histogram grid.

    Used for match vs hard-negative score separation: a benchmark where the
    two classes are perfectly separated is trivially easy and therefore not
    BOAMP-like, so this is a difficulty diagnostic rather than a fidelity one.
    """
    a = pd.to_numeric(a, errors="coerce").dropna().to_numpy()
    b = pd.to_numeric(b, errors="coerce").dropna().to_numpy()
    if a.size == 0 or b.size == 0:
        return float("nan")
    lo = float(min(a.min(), b.min()))
    hi = float(max(a.max(), b.max()))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return 1.0
    edges = np.linspace(lo, hi, bins + 1)
    pa, _ = np.histogram(a, bins=edges, density=False)
    pb, _ = np.histogram(b, bins=edges, density=False)
    pa = pa / pa.sum()
    pb = pb / pb.sum()
    return float(np.minimum(pa, pb).sum())
