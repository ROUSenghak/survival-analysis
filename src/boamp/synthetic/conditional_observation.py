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

MIN_VALID_DECLARED_DURATION_MONTHS = 1.0
MAX_VALID_DECLARED_DURATION_MONTHS = 120.0
LOW_DISCREPANCY_DURATION_OFFSET = 0.0
_GOLDEN_RATIO_CONJUGATE = (5**0.5 - 1) / 2


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
    declared_duration_values: tuple[float, ...]
    siret_rates: dict[tuple, float]
    duration_rates: dict[tuple, float]
    generic_text_rates: dict[tuple, float]
    source_path: str
    calibration_split: str = "full_corpus"
    n_calibration_notices: int = 0

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

    def declared_duration_value(
        self,
        notice_id_synthetic: object,
        *,
        offset: float = LOW_DISCREPANCY_DURATION_OFFSET,
    ) -> float:
        """Empirical observed-duration value via deterministic inverted CDF.

        Presence is still sampled separately from conditional BOAMP rates.
        When a duration is present, the visible value is drawn from valid raw
        BOAMP durations rather than transformed from hidden cycle length.
        """
        if not self.declared_duration_values:
            raise ValueError("conditional observation model has no valid real duration values")
        digits = "".join(ch for ch in str(notice_id_synthetic) if ch.isdigit())
        integer_id = int(digits or 0)
        u = (float(offset) + (integer_id + 1) * _GOLDEN_RATIO_CONJUGATE) % 1.0
        pos = min(
            len(self.declared_duration_values) - 1,
            max(0, int(np.ceil(u * len(self.declared_duration_values)) - 1)),
        )
        return float(self.declared_duration_values[pos])

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
            out["calibration_split"] = self.calibration_split
            pieces.append(out)
        return pd.concat(pieces, ignore_index=True, sort=False)


def build_conditional_observation_model(
    project_root: Path,
    *,
    siret_prior_strength: float = 25.0,
    duration_prior_strength: float = 25.0,
    generic_text_prior_strength: float = 25.0,
    calibration_split: str | None = None,
) -> ConditionalObservationModel:
    """Build conditional observation targets from the prepared real corpus.

    `calibration_split` selects a side of the frozen real buyer-key holdout
    (v0.4). Passing None reads the whole corpus, which is what v0.1-v0.3 did and
    what their replay still needs; passing "calibration" restricts estimation to
    the 70% calibration buyers so the held-out 30% can provide out-of-sample
    fidelity evidence.
    """
    project_root = Path(project_root)
    real_path = project_root / "data" / "interim" / "boamp_common_prepared.csv"
    real = pd.read_csv(real_path, usecols=REAL_USECOLS, low_memory=False)
    if calibration_split is not None:
        from boamp.synthetic.holdout import load_real_buyer_holdout

        real = load_real_buyer_holdout(project_root).filter(real, calibration_split)
        if real.empty:
            raise ValueError(f"real holdout split {calibration_split!r} selected zero notices")
    real = _add_buyer_activity_tier(real)
    real = _add_generic_text_flag(real)
    real["siret_present"] = real["buyer_siret_clean"].notna()
    real["duration_present"] = real["duration_raw"].notna()
    duration_values = (
        pd.to_numeric(real["duration_raw"], errors="coerce")
        .dropna()
        .loc[lambda s: s.between(MIN_VALID_DECLARED_DURATION_MONTHS, MAX_VALID_DECLARED_DURATION_MONTHS)]
        .sort_values()
        .astype(float)
        .tolist()
    )

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
        declared_duration_values=tuple(duration_values),
        siret_rates=_mapping(siret_table, siret_cols),
        duration_rates=_mapping(duration_table, duration_cols),
        generic_text_rates=_mapping(generic_text_table, generic_text_cols),
        source_path=str(real_path.relative_to(project_root)),
        calibration_split=calibration_split or "full_corpus",
        n_calibration_notices=int(len(real)),
    )
