"""Generate latent establishments (Phase 4.2): valid synthetic SIREN/SIRET
hierarchy. Every SIRET is generated so its first 9 digits equal a buyer's
SIREN (`siren_from_siret` from src/utils/identifiers.py would recover it
exactly), and every generated identifier passes the same format+Luhn
validation the real pipeline applies to real BOAMP identifiers
(src/utils/identifiers.py::validate_siren / validate_siret) — reused
directly here, not re-implemented, so "valid" means the same thing on both
sides.

Never copies a real identifier: every SIREN/SIRET is drawn fresh from
`rng` and only accepted once it independently passes validation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from utils.identifiers import validate_siren, validate_siret


def generate_valid_siren(rng: np.random.Generator) -> str:
    """Draw random 8-digit bases until one has a working Luhn check digit
    (always succeeds on the first or second try; Luhn always has exactly one
    correct check digit for any base, so this never loops more than 10x)."""
    while True:
        base = "".join(str(int(d)) for d in rng.integers(0, 10, size=8))
        for c in range(10):
            candidate = base + str(c)
            fmt_ok, checksum_ok = validate_siren(candidate)
            if fmt_ok and checksum_ok:
                return candidate


def generate_valid_siret(siren: str, sequence: int) -> str:
    """Deterministic establishment SIRET for a given SIREN + 1-indexed
    establishment sequence number, so establishment_id_true order is stable
    and reproducible for a fixed siren+sequence (no extra randomness needed
    once the SIREN exists)."""
    nic_prefix = f"{sequence:04d}"
    base = siren + nic_prefix
    for c in range(10):
        candidate = base + str(c)
        fmt_ok, checksum_ok = validate_siret(candidate)
        if fmt_ok and checksum_ok:
            return candidate
    raise RuntimeError(f"no valid SIRET check digit found for base {base!r} (should be unreachable)")


def generate_latent_establishments(buyers: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """One or more establishments per buyer; more active buyers are more
    likely to operate several establishments under the same SIREN (a
    realistic source of same-SIREN/different-SIRET ambiguity for later
    corruption, Phase 6.1's `wrong_establishment_siret_rate`).

    Requires `buyers` to already carry a valid `siren_true` per row (see
    buyers.generate_latent_buyers).
    """
    rows = []
    tier_n_estab_probs = {
        "21+": ([1, 2, 3], [0.5, 0.35, 0.15]),
        "6-20": ([1, 2, 3], [0.65, 0.30, 0.05]),
    }
    for _, b in buyers.iterrows():
        choices, probs = tier_n_estab_probs.get(b["activity_tier"], ([1], [1.0]))
        n_estab = int(rng.choice(choices, p=probs))
        for seq in range(1, n_estab + 1):
            siret = generate_valid_siret(b["siren_true"], seq)
            rows.append(dict(
                establishment_id_true=f"{b['buyer_id_true']}-EST{seq:02d}",
                buyer_id_true=b["buyer_id_true"],
                siren_true=b["siren_true"],
                siret_true=siret,
                department_true=b["department_true"],
                active_start=b["active_start"],
                active_end=b["active_end"],
            ))
    return pd.DataFrame(rows)
