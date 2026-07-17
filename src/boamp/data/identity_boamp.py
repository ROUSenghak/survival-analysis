"""Layer 1 (boamp_only) buyer identity - BOAMP-native fields only.

Extracted verbatim from the buyer-key block of scripts/preprocess_boamp_m0.py.
Priority ladder: cleaned SIRET > cleaned/derived SIREN > normalized name.
No external enrichment of any kind is used here.
"""

from __future__ import annotations

import pandas as pd


def buyer_key_and_type(row) -> tuple[str | None, str]:
    if pd.notna(row["buyer_siret_clean"]):
        return f"SIRET:{row['buyer_siret_clean']}", "RAW_SIRET"
    if pd.notna(row["buyer_siren_clean"]):
        return f"SIREN:{row['buyer_siren_clean']}", "RAW_SIREN"
    if pd.notna(row["buyer_name_normalized"]):
        return f"NAME:{row['buyer_name_normalized']}", "NAME_FALLBACK"
    return None, "MISSING"


def build_boamp_buyer_key(df: pd.DataFrame) -> pd.DataFrame:
    """Attach buyer_key / buyer_key_type (Layer 1 identity) plus provenance.

    buyer_key is the Layer 1 blocking key; buyer_identity_layer records that
    this identity is BOAMP-native (never externally inferred).
    """
    df = df.copy()
    keys_types = df.apply(buyer_key_and_type, axis=1)
    df["buyer_key"] = keys_types.map(lambda t: t[0])
    df["buyer_key_type"] = keys_types.map(lambda t: t[1])
    df["buyer_identity_layer"] = "BOAMP_NATIVE"
    return df


def fragmentation_summary(sources: pd.DataFrame) -> pd.DataFrame:
    """Buyer-name fragmentation: how many distinct keys per normalized name.

    A normalized buyer name mapping to several keys (e.g. several SIRETs, or
    a SIRET-keyed and a NAME-keyed subset) fragments that buyer's notice
    history and depresses blocking recall - the failure mode enrichment is
    meant to fix.
    """
    g = sources.groupby("buyer_name_normalized")["buyer_key"].nunique()
    frag = g[g > 1]
    return pd.DataFrame({
        "n_normalized_names": [g.shape[0]],
        "n_fragmented_names": [frag.shape[0]],
        "fragmentation_rate": [frag.shape[0] / g.shape[0] if g.shape[0] else 0.0],
        "max_keys_per_name": [int(g.max()) if len(g) else 0],
    })
