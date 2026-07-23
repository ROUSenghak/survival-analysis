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

from types import SimpleNamespace

import numpy as np
import pandas as pd


def _draw_normal_gap_months(dist, rng: np.random.Generator) -> float:
    if dist.type != "normal":
        raise ValueError(f"unsupported cycle_gap_distribution.type {dist.type!r}")
    gap = rng.normal(dist.mean_months, dist.sd_months)
    gap = max(dist.min_months, gap)
    max_months = getattr(dist, "max_months", None)
    if max_months is not None:
        gap = min(max_months, gap)
    return float(gap)


def _draw_gap_months(dist, rng: np.random.Generator) -> float:
    return _draw_normal_gap_months(dist, rng)


def _scoped_candidate_cfg(scenario) -> SimpleNamespace:
    recurrence = getattr(scenario, "recurrence", None)
    cfg = getattr(recurrence, "scoped_candidate_environment", None)
    return cfg or SimpleNamespace(enabled=False)


def _is_scoped_candidate_need(need: pd.Series, cfg: SimpleNamespace) -> bool:
    if not getattr(cfg, "enabled", False):
        return False
    divisions = {str(v) for v in getattr(cfg, "cpv_divisions", [])}
    cpv = str(need.get("cpv_true", ""))
    return cpv[:2] in divisions


def _recurrence_propensity_for_need(need: pd.Series, scenario) -> float:
    cfg = _scoped_candidate_cfg(scenario)
    propensity = float(need["recurrence_propensity"])
    if _is_scoped_candidate_need(need, cfg):
        propensity *= float(getattr(cfg, "recurrence_propensity_multiplier", 1.0))
    return float(np.clip(propensity, 0.0, 0.98))


def _draw_successor_gap_months(need: pd.Series, scenario, rng: np.random.Generator) -> float:
    cfg = _scoped_candidate_cfg(scenario)
    if _is_scoped_candidate_need(need, cfg) and rng.random() < float(getattr(cfg, "near_window_share", 0.0)):
        return _draw_normal_gap_months(cfg.near_window_distribution, rng)
    return _draw_gap_months(scenario.recurrence.cycle_gap_distribution, rng)


def _align_same_buyer_hard_negative_chains(
    cycles: pd.DataFrame,
    needs: pd.DataFrame,
    scenario,
    observation_end: pd.Timestamp,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Optionally move whole distinct-need chains near a source expected end.

    This creates realistic same-buyer future candidates without changing
    labels or assigning candidate counts directly. Shifting whole chains keeps
    within-need cycle order and NEXT_CYCLE truth derivable from cycles.
    """
    cfg = _scoped_candidate_cfg(scenario)
    rate = float(getattr(cfg, "hard_negative_alignment_rate", 0.0))
    if not getattr(cfg, "enabled", False) or rate <= 0 or cycles.empty:
        return cycles

    needs_idx = needs.set_index("need_id_true")
    scoped_needs = needs[needs.apply(lambda row: _is_scoped_candidate_need(row, cfg), axis=1)]
    candidate_need_ids_by_buyer = {
        buyer_id: set(group["need_id_true"])
        for buyer_id, group in scoped_needs.groupby("buyer_id_true")
        if len(group) >= 2
    }
    if not candidate_need_ids_by_buyer:
        return cycles

    out = cycles.copy()
    scoped_cycle_mask = out["need_id_true"].isin(scoped_needs["need_id_true"])
    source_cycles = out.loc[scoped_cycle_mask].sample(frac=1.0, random_state=int(rng.integers(0, 2**32 - 1)))
    n_to_try = int(round(rate * len(source_cycles)))
    if n_to_try <= 0:
        return out

    used_target_needs: set[str] = set()
    n_aligned = 0
    for _, source in source_cycles.iterrows():
        if n_aligned >= n_to_try:
            break
        buyer_id = source["buyer_id_true"]
        source_need_id = source["need_id_true"]
        possible_targets = sorted(candidate_need_ids_by_buyer.get(buyer_id, set()) - {source_need_id} - used_target_needs)
        if not possible_targets:
            continue
        target_need_id = str(rng.choice(possible_targets))
        target_chain = out.loc[out["need_id_true"] == target_need_id].sort_values("cycle_number")
        if target_chain.empty:
            continue

        target_first = target_chain.iloc[0]
        near_gap = _draw_normal_gap_months(cfg.near_window_distribution, rng)
        desired_first_start = source["expected_end_true"] + pd.DateOffset(days=round(near_gap * 30.44))
        if desired_first_start <= source["start_date_true"]:
            continue

        delta = desired_first_start - target_first["start_date_true"]
        shifted_starts = target_chain["start_date_true"] + delta
        shifted_ends = target_chain["expected_end_true"] + delta
        if shifted_starts.min() <= pd.Timestamp("2015-01-01") or shifted_starts.max() > observation_end:
            continue
        if not (shifted_starts.sort_values().diff().dropna() > pd.Timedelta(0)).all():
            continue

        idx = target_chain.index
        out.loc[idx, "start_date_true"] = shifted_starts.values
        out.loc[idx, "expected_end_true"] = shifted_ends.values
        used_target_needs.add(target_need_id)
        n_aligned += 1
    return out.sort_values(["start_date_true", "cycle_id_true"]).reset_index(drop=True)


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
            has_successor = rng.random() < _recurrence_propensity_for_need(need, scenario)
            if not has_successor:
                break
            gap = _draw_successor_gap_months(need, scenario, rng)
            next_start = expected_end + pd.DateOffset(days=round(gap * 30.44))
            if next_start > observation_end:
                break  # administratively censored at the window boundary -> NO_SUCCESSOR
            start = next_start
            cycle_number += 1

    cycles = pd.DataFrame(rows)
    return _align_same_buyer_hard_negative_chains(cycles, needs, scenario, observation_end, rng)
