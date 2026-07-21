"""Generate the clean latent buyer population (Phase 4.1).

Buyer activity is drawn from a heavy-tailed distribution (Pareto); the
resulting concentration (Gini coefficient) is an EMERGENT property checked
in validation/fidelity, never assigned directly — the shape parameter below
was chosen once so the emergent Gini lands near the real corpus's observed
0.832 (calib_buyer_concentration_lorenz.csv, USE_AS_FIDELITY_TARGET; see
reports/generated/synthetic_benchmark/v0_1_clean_world_validation.md for the
achieved value), not tuned to hit it exactly every run.

Buyer names are synthetic, syllable-generated organization names — never a
real commune/institution name — so no real identifier or text is copied
(spec requirement, and Lam et al.'s Step 3 "Privacy and Disclosure Risk"
principle).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from boamp.synthetic.establishments import generate_valid_siren

# Department shares: calibration_parameters_v0_1.yaml#departments (top-5,
# EMPIRICAL, USE_DIRECTLY); remainder pooled into a synthetic OTHER bucket.
DEPARTMENT_SHARES: dict[str, float] = {
    "44": 0.397, "49": 0.175, "85": 0.142, "72": 0.136, "53": 0.048,
}

BUYER_TYPE_PROBS: dict[str, float] = {
    "COMMUNE": 0.45, "EPCI": 0.15, "DEPARTEMENT": 0.05,
    "ETABLISSEMENT_PUBLIC": 0.20, "AUTRE": 0.15,
}

_SYLLABLES_A = ["ver", "bel", "mont", "sain", "château", "roche", "fon", "cler", "beau", "gran"]
_SYLLABLES_B = ["nay", "louze", "court", "ville", "eau", "bourg", "champ", "mont", "val", "sac"]

_BUYER_TYPE_TEMPLATES: dict[str, list[str]] = {
    "COMMUNE": ["Commune de {place}", "Mairie de {place}"],
    "EPCI": ["Communauté de communes {place}", "Communauté d'agglomération {place}"],
    "DEPARTEMENT": ["Conseil départemental de {place}", "Département de {place}"],
    "ETABLISSEMENT_PUBLIC": ["Centre hospitalier de {place}", "Université de {place}", "Lycée de {place}"],
    "AUTRE": ["Syndicat mixte {place}", "Office public de l'habitat {place}"],
}


def generate_synthetic_place_name(rng: np.random.Generator) -> str:
    a = rng.choice(_SYLLABLES_A)
    b = rng.choice(_SYLLABLES_B)
    return (a + b).capitalize()


def generate_synthetic_buyer_name(buyer_type: str, rng: np.random.Generator) -> str:
    place = generate_synthetic_place_name(rng)
    template = rng.choice(_BUYER_TYPE_TEMPLATES.get(buyer_type, _BUYER_TYPE_TEMPLATES["AUTRE"]))
    return template.format(place=place)


def _department_choices() -> tuple[list[str], list[float]]:
    depts = list(DEPARTMENT_SHARES) + ["OTHER"]
    probs = list(DEPARTMENT_SHARES.values())
    probs.append(max(0.0, 1.0 - sum(probs)))
    total = sum(probs)
    return depts, [p / total for p in probs]


def generate_latent_buyers(n_buyers: int, benchmark_defaults, rng: np.random.Generator,
                            pareto_shape: float = 1.0, pareto_offset: float = 0.15) -> pd.DataFrame:
    """`pareto_shape`/`pareto_offset` control emergent activity concentration
    (Phase 10 adaptive calibration): the textbook asymptotic formula
    Gini = 1/(2*shape-1) for a Pareto Type I variate assumes shape > 1 and
    n -> infinity; it is a poor guide at v0.1 pilot scale (~2,000 buyers)
    with the +1 location offset originally used to keep every draw positive.
    Empirically simulating Gini at n=2000 (the actual check this module is
    calibrated against, not the asymptotic formula) found shape=1.10,
    offset=1.0 -> Gini~0.64 (too low vs the real corpus's observed 0.832,
    calib_buyer_concentration_lorenz.csv); shape=1.0, offset=0.15 lands
    Gini~0.85-0.89 across seeds, close to the real corpus's target while
    keeping every buyer's activity_rate strictly positive. Gini is still an
    EMERGENT, checked property (benchmark_defaults_v0_1.yaml's tolerance
    band), never assigned directly.
    """
    if pareto_shape <= 0.5:
        raise ValueError("pareto_shape must exceed 0.5 for a finite Gini coefficient")

    raw = rng.pareto(pareto_shape, size=n_buyers) + pareto_offset
    activity_rate = raw / raw.sum()

    depts, probs = _department_choices()
    department = rng.choice(depts, size=n_buyers, p=probs)
    buyer_type = rng.choice(list(BUYER_TYPE_PROBS), size=n_buyers, p=list(BUYER_TYPE_PROBS.values()))

    p99, p80 = np.quantile(activity_rate, [0.99, 0.80])
    activity_tier = np.select(
        [activity_rate >= p99, activity_rate >= p80],
        ["21+", "6-20"],
        default="2-5",
    )

    start = pd.Timestamp(benchmark_defaults.observation_window.start_date)
    end = pd.Timestamp(benchmark_defaults.observation_window.end_date)
    total_days = max(1, (end - start).days)
    active_start = start + pd.to_timedelta(rng.integers(0, int(total_days * 0.6), size=n_buyers), unit="D")
    min_active_days = 180
    span_days = rng.integers(min_active_days, max(min_active_days + 1, total_days), size=n_buyers)
    active_end = pd.to_datetime(pd.Series(active_start) + pd.to_timedelta(span_days, unit="D")).clip(upper=end)

    buyer_id = [f"BUYER-{i:06d}" for i in range(n_buyers)]
    siren_true = [generate_valid_siren(rng) for _ in range(n_buyers)]
    buyer_name_true = [generate_synthetic_buyer_name(bt, rng) for bt in buyer_type]

    return pd.DataFrame({
        "buyer_id_true": buyer_id,
        "siren_true": siren_true,
        "department_true": department,
        "buyer_type_true": buyer_type,
        "buyer_name_true": buyer_name_true,
        "activity_rate": activity_rate,
        "activity_tier": activity_tier,
        "active_start": active_start,
        "active_end": active_end,
        "alias_propensity": rng.beta(2, 5, size=n_buyers),
        "identifier_quality_propensity": rng.beta(5, 2, size=n_buyers),
    })
