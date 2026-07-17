import pandas as pd

from boamp.linkage.scoring import estimate_window_months


def _sources(durations, imputed=None):
    n = len(durations)
    return pd.DataFrame({
        "declared_duration_months": durations,
        "dur_was_imputed": imputed if imputed is not None else [False] * n,
    })


def test_window_collapses_to_floor(cfg):
    # median 6 -> 0.5*6 = 3 -> clipped up to floor 6 (the real corpus's case)
    w, med = estimate_window_months(_sources([6, 6, 6, 6, 8]), cfg)
    assert med == 6
    assert w == cfg.pipeline.temporal_window.floor_months


def test_window_uses_half_median_between_bounds(cfg):
    w, med = estimate_window_months(_sources([24, 24, 24]), cfg)
    assert med == 24
    assert w == 12


def test_window_capped(cfg):
    w, _ = estimate_window_months(_sources([120, 120, 120]), cfg)
    assert w == cfg.pipeline.temporal_window.cap_months


def test_window_ignores_imputed_durations(cfg):
    # observed rows say 24 (window 12); imputed 6s must not drag the median down
    w, med = estimate_window_months(
        _sources([24, 24, 24, 6, 6, 6, 6], imputed=[False, False, False, True, True, True, True]), cfg)
    assert med == 24
    assert w == 12
