"""Fixed real-BOAMP buyer-level fidelity holdout (v0.4).

Every observable generator parameter in v0.4 is estimated from the *calibration*
side of this split; the *holdout* side is read once, at fresh-seed evaluation, to
show that observable fidelity is not purely in-sample.

Splitting unit is the production buyer key (`buyer_key` in
``data/interim/boamp_common_prepared.csv``), so no notice of a given buyer can
appear on both sides. Real buyer activity is heavy-tailed (the top 1% of keys
hold 38% of notices), so a plain random split routinely puts the whole upper tail
on one side and makes the tail metrics -- the exact metrics this revision is
about -- incomparable. The split is therefore stratified on

* activity decile (notice count per buyer key),
* dominant ``schema_family``,
* publication-year span bucket,

and assignment inside each stratum is a deterministic interleave of the
activity-sorted keys rather than an independent Bernoulli draw, which keeps the
per-stratum holdout share at the target fraction even for strata with only a
handful of keys.

The result is frozen to ``config/synthetic/real_holdout_buyer_keys.csv`` and
loaded from there afterwards; nothing downstream re-derives it, so the split
cannot drift between calibration and evaluation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HOLDOUT_RELATIVE_PATH = Path("config") / "synthetic" / "real_holdout_buyer_keys.csv"
PREPARED_RELATIVE_PATH = Path("data") / "interim" / "boamp_common_prepared.csv"

CALIBRATION = "calibration"
HOLDOUT = "holdout"

DEFAULT_HOLDOUT_FRACTION = 0.30
DEFAULT_SPLIT_SEED = 20260803

_USECOLS = ["buyer_key", "buyer_key_type", "schema_family", "publication_year"]


@dataclass(frozen=True)
class RealHoldout:
    """The frozen split plus enough provenance to prove it was not re-drawn."""

    assignments: pd.DataFrame
    source_path: str
    content_sha256: str

    def keys(self, split: str) -> set[str]:
        return set(self.assignments.loc[self.assignments["split"].eq(split), "buyer_key"])

    @property
    def calibration_keys(self) -> set[str]:
        return self.keys(CALIBRATION)

    @property
    def holdout_keys(self) -> set[str]:
        return self.keys(HOLDOUT)

    def filter(self, frame: pd.DataFrame, split: str, key_col: str = "buyer_key") -> pd.DataFrame:
        """Rows of ``frame`` whose buyer key is on the requested side."""
        if key_col not in frame.columns:
            raise KeyError(f"{key_col!r} not in frame; cannot apply the real holdout split")
        return frame.loc[frame[key_col].isin(self.keys(split))].copy()


def _activity_decile(counts: pd.Series) -> pd.Series:
    """Decile of buyer activity, robust to the many ties at 1-2 notices.

    ``qcut`` cannot cut ten equal bins out of a distribution whose median is 2,
    so ranks are used and the resulting label is stored as a plain string.
    """
    ranks = counts.rank(method="first", pct=True)
    return pd.cut(
        ranks,
        bins=np.linspace(0.0, 1.0, 11),
        labels=[f"d{i:02d}" for i in range(1, 11)],
        include_lowest=True,
    ).astype(str)


def _year_span_bucket(spans: pd.Series) -> pd.Series:
    return pd.cut(
        spans,
        bins=[0, 1, 3, 6, np.inf],
        labels=["1y", "2-3y", "4-6y", "7y+"],
        right=True,
        include_lowest=True,
    ).astype(str)


def _buyer_strata(real: pd.DataFrame) -> pd.DataFrame:
    eligible = real.loc[real["buyer_key_type"].astype(str).ne("MISSING") & real["buyer_key"].notna()]
    grouped = eligible.groupby("buyer_key", dropna=False)
    table = pd.DataFrame(
        {
            "n_notices": grouped.size(),
            "n_years": grouped["publication_year"].nunique(),
            "dominant_schema": grouped["schema_family"].agg(
                lambda s: s.astype(str).value_counts().idxmax()
            ),
            "buyer_key_type": grouped["buyer_key_type"].agg(
                lambda s: s.astype(str).value_counts().idxmax()
            ),
        }
    ).reset_index()
    table["activity_decile"] = _activity_decile(table["n_notices"])
    table["year_span_bucket"] = _year_span_bucket(table["n_years"])
    table["stratum"] = (
        table["activity_decile"] + "|" + table["dominant_schema"] + "|" + table["year_span_bucket"]
    )
    return table


def _assign_within_stratum(
    group: pd.DataFrame, holdout_fraction: float, rng: np.random.Generator
) -> pd.Series:
    """Deterministic interleave: sort by activity, take every 1/fraction-th key.

    A Bernoulli draw at this stratum size (some strata hold 3-5 keys) has a real
    chance of sending every tail buyer to one side. Walking the activity-sorted
    list and assigning by cumulative quota keeps both the count and the activity
    profile of each stratum close to the target on both sides. The rng only
    breaks ties between equal-activity keys, so the split is reproducible but not
    an artefact of the buyer_key string order.
    """
    jitter = rng.random(len(group))
    order = np.lexsort((jitter, -group["n_notices"].to_numpy()))
    split = np.full(len(group), CALIBRATION, dtype=object)
    quota = 0.0
    for position in order:
        quota += holdout_fraction
        if quota >= 1.0:
            split[position] = HOLDOUT
            quota -= 1.0
    return pd.Series(split, index=group.index)


def build_real_buyer_holdout(
    project_root: Path,
    *,
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION,
    seed: int = DEFAULT_SPLIT_SEED,
) -> pd.DataFrame:
    """Derive the split table from the prepared real corpus (does not write)."""
    project_root = Path(project_root)
    real = pd.read_csv(project_root / PREPARED_RELATIVE_PATH, usecols=_USECOLS, low_memory=False)
    table = _buyer_strata(real)
    rng = np.random.default_rng(seed)
    table["split"] = (
        table.groupby("stratum", group_keys=False)
        .apply(lambda g: _assign_within_stratum(g, holdout_fraction, rng), include_groups=False)
        .reindex(table.index)
    )
    columns = [
        "buyer_key",
        "split",
        "stratum",
        "activity_decile",
        "dominant_schema",
        "year_span_bucket",
        "buyer_key_type",
        "n_notices",
        "n_years",
    ]
    return table.loc[:, columns].sort_values("buyer_key").reset_index(drop=True)


def write_real_buyer_holdout(project_root: Path, table: pd.DataFrame) -> Path:
    path = Path(project_root) / HOLDOUT_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)
    return path


def load_real_buyer_holdout(project_root: Path) -> RealHoldout:
    """Load the frozen split. Raises if it has not been built yet."""
    project_root = Path(project_root)
    path = project_root / HOLDOUT_RELATIVE_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; run scripts/build_real_buyer_holdout.py to freeze the split"
        )
    payload = path.read_bytes()
    return RealHoldout(
        assignments=pd.read_csv(path, dtype={"buyer_key": str}),
        source_path=str(HOLDOUT_RELATIVE_PATH),
        content_sha256=hashlib.sha256(payload).hexdigest(),
    )


def load_real_calibration_frame(
    project_root: Path, frame: pd.DataFrame, *, key_col: str = "buyer_key"
) -> pd.DataFrame:
    """Convenience wrapper used by the observable calibration builders."""
    return load_real_buyer_holdout(project_root).filter(frame, CALIBRATION, key_col=key_col)


def summarise_split(table: pd.DataFrame) -> pd.DataFrame:
    """Coverage check: both sides must keep the tail, both schemas and all years."""
    rows = []
    for dimension in ["activity_decile", "dominant_schema", "year_span_bucket", "buyer_key_type"]:
        counts = table.pivot_table(
            index=dimension, columns="split", values="buyer_key", aggfunc="count"
        ).fillna(0)
        notices = table.pivot_table(
            index=dimension, columns="split", values="n_notices", aggfunc="sum"
        ).fillna(0)
        for level in counts.index:
            rows.append(
                {
                    "dimension": dimension,
                    "level": str(level),
                    "n_keys_calibration": int(counts.loc[level].get(CALIBRATION, 0)),
                    "n_keys_holdout": int(counts.loc[level].get(HOLDOUT, 0)),
                    "n_notices_calibration": int(notices.loc[level].get(CALIBRATION, 0)),
                    "n_notices_holdout": int(notices.loc[level].get(HOLDOUT, 0)),
                }
            )
    out = pd.DataFrame(rows)
    total_keys = out["n_keys_calibration"] + out["n_keys_holdout"]
    out["holdout_key_share"] = out["n_keys_holdout"] / total_keys.replace(0, np.nan)
    return out
