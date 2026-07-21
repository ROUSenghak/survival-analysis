"""Generate contract cycles (Phase 4.4).

Each need produces a chain of cycles: cycle_number=1 starts within its
buyer's active window; each subsequent cycle is realized only if a
scenario-controlled successor draw succeeds AND the resulting start date
still falls inside the observation window (otherwise the chain stops and
relations.py will derive NO_SUCCESSOR for the last realized cycle — see
config/synthetic/recurrence_ontology_v0_1.yaml's generation_rule).

True duration is generated separately from any later "declared" duration
(that distinction is introduced only in corruption.py, Phase 6.4); here
there is only one duration, `duration_true_months`.

Successor gaps are NOT constrained to the real pipeline's 6-month blocking
window (temporal_window_months is DO_NOT_USE for generator truth, per
generator_parameter_actions.csv) — the scenario's cycle_gap_distribution is
centered further out with wide spread specifically so some true gaps fall
outside it (spec Phase 4.4 requirement).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _draw_gap_months(dist, rng: np.random.Generator) -> float:
    if dist.type != "normal":
        raise ValueError(f"unsupported cycle_gap_distribution.type {dist.type!r}")
    gap = rng.normal(dist.mean_months, dist.sd_months)
    return float(max(dist.min_months, gap))


def generate_latent_cycles(needs: pd.DataFrame, buyers: pd.DataFrame, scenario,
                            observation_end: pd.Timestamp, rng: np.random.Generator) -> pd.DataFrame:
    buyer_window = buyers.set_index("buyer_id_true")[["active_start", "active_end"]]
    max_cycles = scenario.recurrence.max_cycles_per_need
    gap_dist = scenario.recurrence.cycle_gap_distribution

    rows = []
    cycle_seq = 0
    for _, need in needs.iterrows():
        win = buyer_window.loc[need["buyer_id_true"]]
        span_days = max(1, (win["active_end"] - win["active_start"]).days)
        start = win["active_start"] + pd.to_timedelta(int(rng.integers(0, span_days)), unit="D")

        cycle_number = 1
        need_cycle_ids = []
        while True:
            duration = float(np.clip(
                rng.normal(need["duration_profile_months"], 0.25 * need["duration_profile_months"]),
                1.0, 120.0,
            ))
            expected_end = start + pd.DateOffset(days=round(duration * 30.44))
            cycle_id = f"CYCLE-{cycle_seq:08d}"
            rows.append(dict(
                cycle_id_true=cycle_id,
                need_id_true=need["need_id_true"],
                buyer_id_true=need["buyer_id_true"],
                cycle_number=cycle_number,
                start_date_true=start,
                duration_true_months=duration,
                expected_end_true=expected_end,
                scenario=scenario.scenario_id,
            ))
            need_cycle_ids.append(cycle_id)
            cycle_seq += 1

            if cycle_number >= max_cycles:
                break
            has_successor = rng.random() < need["recurrence_propensity"]
            if not has_successor:
                break
            gap = _draw_gap_months(gap_dist, rng)
            next_start = expected_end + pd.DateOffset(days=round(gap * 30.44))
            if next_start > observation_end:
                break  # administratively censored at the window boundary -> NO_SUCCESSOR
            start = next_start
            cycle_number += 1

    return pd.DataFrame(rows)
