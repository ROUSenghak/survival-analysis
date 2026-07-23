"""Generate latent procurement needs (Phase 4.3).

A buyer may hold several simultaneous needs, including same-buyer/same-CPV
but genuinely distinct needs (spec requirement), so realistic hard-negative
candidates can emerge later without any extra bookkeeping: two needs of the
same buyer that happen to share `segment_true`/`cpv_true` are exactly that
case (see notices.py, which does not special-case it — the ambiguity is
structural, not scripted).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from boamp.synthetic.text_generation import DIVISION_VOCAB, sample_division_vocab

# CPV division sampling distribution: calib_cpv_division_coverage.csv minus
# its missing-CPV row (empty division), renormalized. Loaded once from the
# calibration table rather than hardcoded (spec: "prefer references to
# machine-readable calibration tables").
_TIER_LAMBDA = {"21+": 8.0, "6-20": 4.0, "2-5": 1.8, "1": 1.2}


def _division_distribution(calib) -> tuple[list[str], list[float]]:
    table = calib.table("cpv", "division_distribution_table")
    table = table[table["cpv_division"].notna()].copy()
    table["cpv_division"] = table["cpv_division"].astype(str).str.replace(r"\.0$", "", regex=True)
    total = table["share"].sum()
    return table["cpv_division"].tolist(), (table["share"] / total).tolist()


def _synthetic_cpv_code(division: str, rng: np.random.Generator) -> str:
    """8-digit CPV-looking code: division (2 digits) + a small fixed set of
    sub-code suffixes standing in for the missing manually-validated
    technological taxonomy (spec §4.3)."""
    suffix = "".join(str(int(d)) for d in rng.integers(0, 10, size=6))
    return division + suffix


def _scoped_candidate_cfg(scenario):
    recurrence = getattr(scenario, "recurrence", None)
    cfg = getattr(recurrence, "scoped_candidate_environment", None)
    return cfg


def _division_sampler(calib, scenario):
    divisions, division_probs = _division_distribution(calib)
    cfg = _scoped_candidate_cfg(scenario)
    if cfg is None or not getattr(cfg, "enabled", False) or not getattr(cfg, "cluster_scoped_needs_by_buyer", False):
        return divisions, division_probs, None

    scoped_divisions = {str(v) for v in getattr(cfg, "cpv_divisions", [])}
    division_prob = dict(zip(divisions, division_probs, strict=False))
    scoped = [d for d in divisions if d in scoped_divisions]
    non_scoped = [d for d in divisions if d not in scoped_divisions]
    scoped_mass = sum(division_prob[d] for d in scoped)
    if not scoped or not non_scoped or scoped_mass <= 0:
        return divisions, division_probs, None

    scoped_probs = np.array([division_prob[d] for d in scoped], dtype=float)
    scoped_probs = scoped_probs / scoped_probs.sum()
    non_scoped_probs = np.array([division_prob[d] for d in non_scoped], dtype=float)
    non_scoped_probs = non_scoped_probs / non_scoped_probs.sum()

    affinity_share = float(getattr(cfg, "scoped_buyer_affinity_share", 0.25))
    high_prob = float(getattr(cfg, "scoped_need_probability_high", 0.28))
    low_prob = max(0.0, min(1.0, (scoped_mass - affinity_share * high_prob) / max(1e-9, 1.0 - affinity_share)))
    sampler = {
        "scoped": scoped,
        "scoped_probs": scoped_probs,
        "non_scoped": non_scoped,
        "non_scoped_probs": non_scoped_probs,
        "affinity_share": affinity_share,
        "high_prob": high_prob,
        "low_prob": low_prob,
    }
    return divisions, division_probs, sampler


def _draw_division(divisions, division_probs, sampler, buyer_has_scoped_affinity: bool,
                   rng: np.random.Generator) -> str:
    if sampler is None:
        return rng.choice(divisions, p=division_probs)
    scoped_prob = sampler["high_prob"] if buyer_has_scoped_affinity else sampler["low_prob"]
    if rng.random() < scoped_prob:
        return rng.choice(sampler["scoped"], p=sampler["scoped_probs"])
    return rng.choice(sampler["non_scoped"], p=sampler["non_scoped_probs"])


def generate_latent_needs(buyers: pd.DataFrame, establishments: pd.DataFrame,
                           calib, rng: np.random.Generator,
                           base_recurrence_propensity: float,
                           scenario=None) -> pd.DataFrame:
    divisions, division_probs, sampler = _division_sampler(calib, scenario)
    estab_by_buyer = {k: v["establishment_id_true"].tolist() for k, v in establishments.groupby("buyer_id_true")}

    rows = []
    need_seq = 0
    for _, b in buyers.iterrows():
        lam = _TIER_LAMBDA.get(b["activity_tier"], 1.2)
        n_needs = max(1, int(rng.poisson(lam)))
        estabs = estab_by_buyer.get(b["buyer_id_true"], [f"{b['buyer_id_true']}-EST01"])
        buyer_has_scoped_affinity = bool(
            sampler is not None and rng.random() < sampler["affinity_share"]
        )
        scoped_establishment_id = rng.choice(estabs)
        for _ in range(n_needs):
            division = _draw_division(divisions, division_probs, sampler, buyer_has_scoped_affinity, rng)
            cpv_true = _synthetic_cpv_code(division, rng)
            base_concepts, base_vocabulary = sample_division_vocab(division, rng)
            if (
                sampler is not None
                and buyer_has_scoped_affinity
                and division in set(sampler["scoped"])
                and getattr(_scoped_candidate_cfg(scenario), "stabilize_scoped_establishment", False)
            ):
                establishment_id = scoped_establishment_id
            else:
                establishment_id = rng.choice(estabs)
            duration_profile = float(np.clip(rng.lognormal(mean=np.log(12.0), sigma=0.7), 1.0, 120.0))
            # Per-need multiplicative jitter around the scenario's central
            # recurrence propensity (never set to a single point value for
            # every need — spec Phase 4.3/4.4 intent).
            jitter = rng.beta(4, 4) * 0.6 + 0.7  # ~[0.7, 1.3]
            recurrence_propensity = float(np.clip(base_recurrence_propensity * jitter, 0.0, 0.98))
            rows.append(dict(
                need_id_true=f"NEED-{need_seq:07d}",
                buyer_id_true=b["buyer_id_true"],
                establishment_id_true=establishment_id,
                segment_true=f"DIVISION_{division}",
                cpv_true=cpv_true,
                base_concepts=base_concepts,
                base_vocabulary=base_vocabulary,
                duration_profile_months=duration_profile,
                recurrence_propensity=recurrence_propensity,
            ))
            need_seq += 1
    return pd.DataFrame(rows)
