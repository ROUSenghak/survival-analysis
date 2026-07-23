"""Conditional observable-field targets for the v0.2 fidelity revision.

These targets are derived only from observable BOAMP fields. They tune how
clean truth is observed/corrupted; they do not alter latent buyers, needs,
cycles, recurrence truth, or any linkage algorithm output.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REAL_USECOLS = [
    "notice_id",
    "schema_family",
    "notice_type_normalized",
    "publication_year",
    "buyer_siret_clean",
    "duration_raw",
    "objet_normalized",
    "buyer_key",
]


def _activity_tier(counts: pd.Series) -> pd.Series:
    return pd.cut(
        counts,
        bins=[0, 1, 5, 20, np.inf],
        labels=["1 (single)", "2-5", "6-20", "21+"],
        right=True,
    ).astype(str)


def _add_buyer_activity_tier(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["buyer_activity_tier"] = _activity_tier(out.groupby("buyer_key", dropna=False)["notice_id"].transform("size"))
    return out


def _add_generic_text_flag(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    text_stats = (
        out.dropna(subset=["objet_normalized"])
        .groupby("objet_normalized")
        .agg(n_notices=("objet_normalized", "size"), n_buyers=("buyer_key", "nunique"))
    )
    generic_texts = set(text_stats.query("n_notices >= 2 and n_buyers >= 2").index)
    out["generic_text"] = out["objet_normalized"].isin(generic_texts)
    return out


def _smoothed_rate_table(
    frame: pd.DataFrame,
    outcome: str,
    group_cols: list[str],
    *,
    prior_strength: float,
) -> pd.DataFrame:
    global_rate = float(frame[outcome].mean())
    grouped = frame.groupby(group_cols, dropna=False)[outcome].agg(successes="sum", n="count").reset_index()
    grouped["observed_rate"] = grouped["successes"] / grouped["n"]
    grouped["smoothed_rate"] = (
        grouped["successes"] + prior_strength * global_rate
    ) / (grouped["n"] + prior_strength)
    grouped["global_prior_rate"] = global_rate
    grouped["prior_strength"] = prior_strength
    return grouped


def _mapping(table: pd.DataFrame, group_cols: list[str]) -> dict[tuple, float]:
    return {
        tuple(row[col] for col in group_cols): float(row["smoothed_rate"])
        for _, row in table.iterrows()
    }


@dataclass(frozen=True)
class ConditionalObservationModel:
    """Smoothed observable-field rates, with hierarchical fallbacks."""

    siret_table: pd.DataFrame
    duration_table: pd.DataFrame
    generic_text_table: pd.DataFrame
    siret_rates: dict[tuple, float]
    duration_rates: dict[tuple, float]
    generic_text_rates: dict[tuple, float]
    source_path: str

    @property
    def siret_global_rate(self) -> float:
        return float(self.siret_table["global_prior_rate"].iloc[0])

    @property
    def duration_global_rate(self) -> float:
        return float(self.duration_table["global_prior_rate"].iloc[0])

    @property
    def generic_text_global_rate(self) -> float:
        return float(self.generic_text_table["global_prior_rate"].iloc[0])

    def siret_present_rate(self, row) -> float:
        key = (row["schema_family_true"], int(row["publication_date_true"].year), row["notice_type_true"])
        return self.siret_rates.get(key, self.siret_global_rate)

    def duration_present_rate(self, row) -> float:
        key = (row["schema_family_true"], int(row["publication_date_true"].year), row["notice_type_true"])
        return self.duration_rates.get(key, self.duration_global_rate)

    def generic_text_rate(self, notice_type: str, buyer_activity_tier: str) -> float:
        return self.generic_text_rates.get((notice_type, buyer_activity_tier), self.generic_text_global_rate)

    def to_parameter_frame(self) -> pd.DataFrame:
        pieces = []
        for name, table in [
            ("siret_present", self.siret_table),
            ("duration_present", self.duration_table),
            ("generic_repeated_text", self.generic_text_table),
        ]:
            out = table.copy()
            out.insert(0, "parameter", name)
            out["source_path"] = self.source_path
            pieces.append(out)
        return pd.concat(pieces, ignore_index=True, sort=False)


def build_conditional_observation_model(
    project_root: Path,
    *,
    siret_prior_strength: float = 25.0,
    duration_prior_strength: float = 25.0,
    generic_text_prior_strength: float = 25.0,
) -> ConditionalObservationModel:
    """Build conditional observation targets from the prepared real corpus."""
    project_root = Path(project_root)
    real_path = project_root / "data" / "interim" / "boamp_common_prepared.csv"
    real = pd.read_csv(real_path, usecols=REAL_USECOLS, low_memory=False)
    real = _add_buyer_activity_tier(real)
    real = _add_generic_text_flag(real)
    real["siret_present"] = real["buyer_siret_clean"].notna()
    real["duration_present"] = real["duration_raw"].notna()

    siret_cols = ["schema_family", "publication_year", "notice_type_normalized"]
    duration_cols = ["schema_family", "publication_year", "notice_type_normalized"]
    generic_text_cols = ["notice_type_normalized", "buyer_activity_tier"]
    siret_table = _smoothed_rate_table(
        real, "siret_present", siret_cols, prior_strength=siret_prior_strength
    )
    duration_table = _smoothed_rate_table(
        real, "duration_present", duration_cols, prior_strength=duration_prior_strength
    )
    generic_text_table = _smoothed_rate_table(
        real, "generic_text", generic_text_cols, prior_strength=generic_text_prior_strength
    )
    return ConditionalObservationModel(
        siret_table=siret_table,
        duration_table=duration_table,
        generic_text_table=generic_text_table,
        siret_rates=_mapping(siret_table, siret_cols),
        duration_rates=_mapping(duration_table, duration_cols),
        generic_text_rates=_mapping(generic_text_table, generic_text_cols),
        source_path=str(real_path.relative_to(project_root)),
    )
