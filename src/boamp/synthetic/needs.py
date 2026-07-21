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


def generate_latent_needs(buyers: pd.DataFrame, establishments: pd.DataFrame,
                           calib, rng: np.random.Generator,
                           base_recurrence_propensity: float) -> pd.DataFrame:
    divisions, division_probs = _division_distribution(calib)
    estab_by_buyer = {k: v["establishment_id_true"].tolist() for k, v in establishments.groupby("buyer_id_true")}

    rows = []
    need_seq = 0
    for _, b in buyers.iterrows():
        lam = _TIER_LAMBDA.get(b["activity_tier"], 1.2)
        n_needs = max(1, int(rng.poisson(lam)))
        estabs = estab_by_buyer.get(b["buyer_id_true"], [f"{b['buyer_id_true']}-EST01"])
        for _ in range(n_needs):
            division = rng.choice(divisions, p=division_probs)
            cpv_true = _synthetic_cpv_code(division, rng)
            base_concepts, base_vocabulary = sample_division_vocab(division, rng)
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
