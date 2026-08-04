"""Buyer activity intensity and active-window mechanisms (v0.4).

v0.1-v0.3 drew one Pareto variate per buyer and used it for everything: how much
the buyer publishes, which activity tier it lands in, and (indirectly, through
the cycle chain) when it publishes. Three separate observable failures traced
back to that single draw.

* A one-parameter Pareto cannot match both the body and the upper-middle tail of
  the real notices-per-buyer-key distribution. The real calibration corpus is a
  clean two-regime object: 92% of keys carry 1-35 notices and only 25% of the
  notice mass, while a discrete power law with alpha ~= 2.04 above x_min = 36
  fits the remaining 8% of keys carrying 75% of the mass (Clauset-Shalizi-Newman
  MLE with the KS-minimising x_min). The body is therefore sampled from a
  smoothed empirical quantile grid and only the tail is parametric.
* Publication *timing* was tied to the same draw through a buyer active window
  that started uniformly inside the first 60% of the observation period, which
  piled notice mass into the middle years. Entry time is now its own mechanism,
  driven by a calibrated by-year entry weight vector.
* Active-window *length* was uniform and independent of activity, but in the real
  corpus span rises monotonically with activity (rank correlation of log activity
  with span fraction: 0.77; decile mean span fraction runs 0.00 -> 0.59). Span is
  now a function of the buyer's activity rank.

Everything here is calibrated from observable BOAMP quantities only -- notices
per observed buyer key, publication year, and observed first/last publication
date per key -- computed on the calibration side of the frozen buyer holdout. No
accepted link, linkage score, threshold or algorithm result enters any of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

# Guards. `alpha > 1` is required for the inverse-CDF form below to be a proper
# distribution; `tempering` outside (0, 2] would stop being a mild reshaping of a
# calibrated distribution and become a different distribution altogether.
MIN_TAIL_ALPHA = 1.01
MIN_TEMPERING = 0.10
MAX_TEMPERING = 2.00


@dataclass(frozen=True)
class ActivityModel:
    """Two-component relative-activity distribution plus its active-window rules.

    All sizes are expressed *relative to the mean* of the real observed-key
    activity distribution, so the model is scale-free: it does not encode how
    many buyers or notices the benchmark generates.
    """

    tail_key_share: float
    tail_xmin_relative: float
    tail_xmax_relative: float
    tail_alpha: float
    body_quantile_grid: tuple[float, ...]
    body_quantile_values: tuple[float, ...]
    dispersion_tempering: float
    span_fraction_by_activity_rank: tuple[float, ...]
    span_knot_positions: tuple[float, ...]
    span_extension_factor: float
    span_jitter_concentration: float
    min_active_days: int
    entry_year_weights: tuple[tuple[int, float], ...]
    provenance: str

    @property
    def entry_years(self) -> np.ndarray:
        return np.array([year for year, _ in self.entry_year_weights], dtype=int)

    @property
    def entry_probabilities(self) -> np.ndarray:
        weights = np.array([w for _, w in self.entry_year_weights], dtype=float)
        total = weights.sum()
        return weights / total if total > 0 else np.full(len(weights), 1.0 / len(weights))


def build_activity_model(cfg) -> ActivityModel | None:
    """Read the scenario's ``buyers.activity_model`` block, or None for legacy.

    Returning None keeps the v0.1-v0.3 single-Pareto path alive so already
    released benchmark versions replay unchanged from their own configuration.
    """
    if cfg is None or not getattr(cfg, "enabled", False):
        return None

    grid = tuple(float(v) for v in getattr(cfg, "body_quantile_grid", ()))
    values = tuple(float(v) for v in getattr(cfg, "body_quantile_values", ()))
    if len(grid) < 2 or len(grid) != len(values):
        raise ValueError("activity_model needs matching body_quantile_grid/body_quantile_values of length >= 2")
    if any(b < a for a, b in zip(grid, grid[1:], strict=False)):
        raise ValueError("activity_model.body_quantile_grid must be non-decreasing")

    alpha = float(getattr(cfg, "tail_alpha", 2.0))
    if alpha <= MIN_TAIL_ALPHA:
        raise ValueError(f"activity_model.tail_alpha must exceed {MIN_TAIL_ALPHA}")
    tempering = float(getattr(cfg, "dispersion_tempering", 1.0))
    if not MIN_TEMPERING <= tempering <= MAX_TEMPERING:
        raise ValueError(f"activity_model.dispersion_tempering must lie in [{MIN_TEMPERING}, {MAX_TEMPERING}]")

    entry = getattr(cfg, "entry_year_weights", None)
    entry_pairs: tuple[tuple[int, float], ...] = ()
    if entry is not None:
        raw = vars(entry) if isinstance(entry, SimpleNamespace) else dict(entry)
        entry_pairs = tuple(sorted((int(k), float(v)) for k, v in raw.items()))
        if not entry_pairs:
            raise ValueError("activity_model.entry_year_weights was present but empty")

    span_curve = tuple(float(v) for v in getattr(cfg, "span_fraction_by_activity_rank", ()))
    if len(span_curve) < 2:
        raise ValueError("activity_model needs span_fraction_by_activity_rank with >= 2 knots")
    knot_positions = tuple(float(v) for v in getattr(cfg, "span_knot_positions", ()))
    if not knot_positions:
        knot_positions = tuple(np.linspace(0.0, 1.0, len(span_curve)))
    if len(knot_positions) != len(span_curve):
        raise ValueError("activity_model.span_knot_positions must match span_fraction_by_activity_rank")

    return ActivityModel(
        tail_key_share=float(getattr(cfg, "tail_key_share", 0.08)),
        tail_xmin_relative=float(getattr(cfg, "tail_xmin_relative", 2.0)),
        tail_xmax_relative=float(getattr(cfg, "tail_xmax_relative", 200.0)),
        tail_alpha=alpha,
        body_quantile_grid=grid,
        body_quantile_values=values,
        dispersion_tempering=tempering,
        span_fraction_by_activity_rank=span_curve,
        span_knot_positions=knot_positions,
        span_extension_factor=float(getattr(cfg, "span_extension_factor", 1.0)),
        span_jitter_concentration=float(getattr(cfg, "span_jitter_concentration", 4.0)),
        min_active_days=int(getattr(cfg, "min_active_days", 30)),
        entry_year_weights=entry_pairs,
        provenance=str(getattr(cfg, "provenance", "EMPIRICAL_OBSERVABLE")),
    )


def _sample_body(u: np.ndarray, model: ActivityModel) -> np.ndarray:
    """Smoothed empirical body: linear interpolation of the quantile grid.

    Interpolating on the log scale would over-smooth the 1-notice spike that
    carries 41% of the body; linear interpolation of the quantile function keeps
    that mass where the real corpus puts it.
    """
    return np.interp(u, model.body_quantile_grid, model.body_quantile_values)


def _sample_tail(u: np.ndarray, model: ActivityModel) -> np.ndarray:
    """Inverse CDF of a power law *truncated* at the observable maximum.

    An untruncated Pareto with the fitted alpha ~= 2.04 has infinite variance and
    a maximum that grows almost linearly in the sample size, so at benchmark
    scale it reliably produces one buyer that dwarfs the corpus: an early v0.4
    pilot put 17,192 of 78,651 notices (22%) under a single buyer key, against a
    real maximum of 3,185 of 84,623 (3.8%). Real BOAMP's tail is finite -- there
    is a largest French public buyer -- so the generator samples the truncated
    form, whose upper limit is the observable maximum relative activity. This is
    the standard treatment of a bounded heavy tail (Aban, Meerschaert and
    Panorska 2006); leaving it untruncated is what makes a power-law fit look
    right on a log-log plot and behave absurdly when sampled from.
    """
    alpha = model.tail_alpha - 1.0
    xmin = model.tail_xmin_relative
    xmax = max(model.tail_xmax_relative, xmin * 1.000001)
    safe = np.clip(u, 0.0, 1.0 - 1e-12)
    ratio = (xmin / xmax) ** alpha
    return xmin * np.power(1.0 - safe * (1.0 - ratio), -1.0 / alpha)


def draw_relative_activity(n_buyers: int, model: ActivityModel, rng: np.random.Generator) -> np.ndarray:
    """Relative activity weights (mean ~1) from the two-component model.

    `dispersion_tempering` reshapes the draw on the log scale before
    normalisation. It exists because the notice count a buyer ends up with is not
    its weight: the weight passes through a Poisson need count, a geometric-ish
    cycle chain and an award coin flip, each of which adds dispersion of its own.
    Tempering is the single knob the bounded sweep uses to absorb that compounding
    without touching the calibrated shape parameters. It is a mechanism
    parameter, never an estimate of anything real.
    """
    if n_buyers <= 0:
        return np.zeros(0, dtype=float)

    is_tail = rng.random(n_buyers) < model.tail_key_share
    u = rng.random(n_buyers)
    raw = np.where(is_tail, _sample_tail(u, model), _sample_body(u, model))
    raw = np.clip(raw, 1e-9, None)

    if not np.isclose(model.dispersion_tempering, 1.0):
        raw = np.exp(model.dispersion_tempering * np.log(raw))

    total = raw.sum()
    return raw / total if total > 0 else np.full(n_buyers, 1.0 / n_buyers)


def _entry_cdf_knots(model: ActivityModel, window_start, window_end) -> tuple[np.ndarray, np.ndarray]:
    """Day-offset breakpoints and the cumulative entry weight at each of them.

    The entry density is piecewise uniform within each calendar year, with the
    first and last year clipped to the observation window (BOAMP's window opens
    on 2 March 2015 and closes on 13 July 2026).
    """
    import pandas as pd

    start = pd.Timestamp(window_start)
    end = pd.Timestamp(window_end)
    total_days = float(max(1, (end - start).days))

    edges = [0.0]
    masses = []
    for year, weight in model.entry_year_weights:
        year_lo = max(start, pd.Timestamp(year=int(year), month=1, day=1))
        year_hi = min(end, pd.Timestamp(year=int(year), month=12, day=31))
        lo = float((year_lo - start).days)
        hi = float((year_hi - start).days)
        if hi <= lo:
            continue
        if lo > edges[-1]:
            edges.append(lo)
            masses.append(0.0)
        edges.append(hi)
        masses.append(float(weight))
    if edges[-1] < total_days:
        edges.append(total_days)
        masses.append(0.0)

    knots = np.asarray(edges, dtype=float)
    weights = np.asarray(masses, dtype=float)
    total = weights.sum()
    weights = weights / total if total > 0 else np.full(len(weights), 1.0 / max(1, len(weights)))
    return knots, np.concatenate([[0.0], np.cumsum(weights)])


def draw_active_window_offsets(
    spans: np.ndarray,
    model: ActivityModel,
    window_start,
    window_end,
    rng: np.random.Generator,
) -> np.ndarray:
    """Start-day offsets of buyer active windows; may be negative.

    Each buyer draws a *reference day* from the calibrated year weights and then
    places its window uniformly around that day, so the buyer is certainly active
    on it. Windows are allowed to start before the corpus opens and end after it
    closes: real BOAMP buyers existed before 2 March 2015 and keep publishing
    after 13 July 2026, and the corpus records only the intersection.

    Two earlier designs failed here and both failures are instructive.
    Uniform-entry-plus-forward-span put a high-activity buyer's whole output in
    the last eighteen months whenever it happened to be born late (23% of notices
    in 2025 against a real 9%). Forcing the window to fit inside the observation
    period fixed that but created the mirror problem: long-lived buyers were
    pushed to the start, so no buyer window could cover 2025-2026 and the
    entry-weight fixed point diverged trying to compensate. Allowing truncation
    at both ends makes coverage flat by construction and leaves the year weights
    a near-diagonal, well-conditioned problem to solve.
    """
    import pandas as pd

    n_buyers = len(spans)
    start = pd.Timestamp(window_start)
    end = pd.Timestamp(window_end)
    total_days = float(max(1, (end - start).days))
    span_days = np.asarray(spans, dtype=float)

    if model.entry_year_weights:
        knots, cumulative = _entry_cdf_knots(model, window_start, window_end)
        reference = np.interp(rng.random(n_buyers), cumulative, knots)
    else:
        reference = rng.uniform(0.0, total_days, size=n_buyers)

    position = rng.random(n_buyers)
    return reference - position * span_days


def draw_span_fractions(
    activity: np.ndarray, model: ActivityModel, rng: np.random.Generator
) -> np.ndarray:
    """Active-window length as a fraction of the observation window.

    The mean span of a buyer is read off the calibrated activity-rank curve and a
    Beta draw with that mean supplies the spread, so the observable
    activity-versus-span relationship is reproduced without making span a
    deterministic function of activity.
    """
    n = len(activity)
    if n == 0:
        return np.zeros(0, dtype=float)

    ranks = np.empty(n, dtype=float)
    ranks[np.argsort(activity, kind="stable")] = np.arange(n, dtype=float)
    percentile = ranks / max(1.0, n - 1.0)

    knots = np.asarray(model.span_fraction_by_activity_rank, dtype=float)
    knot_positions = np.asarray(model.span_knot_positions, dtype=float)
    # `span_extension_factor` converts the *observed* span the calibration
    # measured into the buyer's underlying active span. They are not the same
    # quantity: the real corpus only ever sees a buyer's window intersected with
    # 2015-03-02..2026-07-13, so the observable curve is systematically shorter
    # than the truth it is a censored view of. The factor is a MECHANISM_PARAMETER
    # chosen by the sweep so the *resimulated observed* span matches the target,
    # rather than pretending the censored measurement is the truth.
    mean_span = np.clip(
        np.interp(percentile, knot_positions, knots) * model.span_extension_factor,
        1e-4,
        1.0 - 1e-4,
    )

    concentration = max(0.5, model.span_jitter_concentration)
    return np.clip(
        rng.beta(concentration * mean_span, concentration * (1.0 - mean_span)), 0.0, 1.0
    )
