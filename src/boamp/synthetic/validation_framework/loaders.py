"""Deterministic data loaders for synthetic benchmark validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class BenchmarkData:
    project_root: Path
    benchmark_version: str
    scenario: str
    world: str
    corruption: str
    synthetic_dir: Path
    observed: pd.DataFrame
    clean: pd.DataFrame
    true_relations: pd.DataFrame
    notice_family_membership: pd.DataFrame
    corruption_log: pd.DataFrame
    latent_cycles: pd.DataFrame
    latent_needs: pd.DataFrame
    latent_buyers: pd.DataFrame
    latent_establishments: pd.DataFrame
    metadata: dict
    real: pd.DataFrame
    real_sources: pd.DataFrame
    real_pairs: pd.DataFrame

    @property
    def seed_label(self) -> str:
        world_seed = self.metadata.get("world_seed", "")
        corruption_seed = self.metadata.get("corruption_seed", "")
        return f"world={world_seed};corruption={corruption_seed}"


def benchmark_output_dir(project_root: Path, version: str, scenario: str, world: str, corruption: str) -> Path:
    return (
        Path(project_root)
        / "data"
        / "processed"
        / "synthetic_benchmark"
        / version
        / scenario
        / f"world_{world}"
        / f"corruption_{corruption}"
    )


def _read_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_parquet(path)


def available_replicates(project_root: Path, version: str) -> list[tuple[str, str, str]]:
    """(scenario, world, corruption) triples generated for a benchmark version.

    Used by the robustness gate, which must know how many independent worlds
    and corruption draws actually exist before claiming anything about seed
    stability.
    """
    root = Path(project_root) / "data" / "processed" / "synthetic_benchmark" / version
    if not root.exists():
        return []
    out = []
    for metadata in sorted(root.glob("*/world_*/corruption_*/generation_metadata.json")):
        corruption_dir = metadata.parent
        world_dir = corruption_dir.parent
        out.append(
            (
                world_dir.parent.name,
                world_dir.name.removeprefix("world_"),
                corruption_dir.name.removeprefix("corruption_"),
            )
        )
    return out


@lru_cache(maxsize=4)
def _load_real_frames(project_root_str: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Real BOAMP reference frames, cached because they are large and reused.

    The validation run compares many synthetic replicates against the same real
    corpus; re-reading an 87k-row CSV per replicate dominates the runtime and
    changes nothing.
    """
    project_root = Path(project_root_str)
    real_usecols = [
        "notice_id", "publication_date", "publication_year", "schema_family",
        "notice_type_normalized", "buyer_siret_raw", "buyer_siren_raw",
        "buyer_siret_clean", "buyer_siren_clean", "buyer_siret_format_valid",
        "buyer_siret_checksum_valid", "buyer_siren_format_valid",
        "buyer_siren_checksum_valid", "buyer_identifier_source", "buyer_name_raw",
        "buyer_name_normalized", "buyer_key", "buyer_key_type", "code_departement",
        "cpv_clean", "cpv_division", "duration_raw", "declared_duration_months",
        "objet_clean", "objet_normalized", "text_length", "token_count",
    ]
    real_path = project_root / "data" / "interim" / "boamp_common_prepared.csv"
    available_real_cols = pd.read_csv(real_path, nrows=0).columns
    real_usecols = [c for c in real_usecols if c in available_real_cols]
    real = pd.read_csv(
        real_path, usecols=real_usecols, parse_dates=["publication_date"], low_memory=False
    )
    real_sources = pd.read_csv(
        project_root / "data" / "processed" / "boamp_only" / "boamp_only_sources.csv",
        parse_dates=["publication_date", "estimated_end_date"],
    )
    real_pairs = pd.read_csv(
        project_root / "data" / "processed" / "boamp_only" / "boamp_only_candidate_pairs.csv",
        parse_dates=["source_date", "candidate_date", "expected_end_date"],
    )
    return real, real_sources, real_pairs


def load_benchmark_data(
    project_root: Path,
    version: str,
    scenario: str,
    world: str = "001",
    corruption: str = "001",
) -> BenchmarkData:
    project_root = Path(project_root)
    synthetic_dir = benchmark_output_dir(project_root, version, scenario, world, corruption)
    metadata_path = synthetic_dir / "generation_metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(metadata_path)

    real, real_sources, real_pairs = _load_real_frames(str(project_root))

    return BenchmarkData(
        project_root=project_root,
        benchmark_version=version,
        scenario=scenario,
        world=world,
        corruption=corruption,
        synthetic_dir=synthetic_dir,
        observed=_read_parquet(synthetic_dir / "observed_notices.parquet"),
        clean=_read_parquet(synthetic_dir / "clean_notices.parquet"),
        true_relations=_read_parquet(synthetic_dir / "true_relations.parquet"),
        notice_family_membership=_read_parquet(synthetic_dir / "notice_family_membership.parquet"),
        corruption_log=_read_parquet(synthetic_dir / "corruption_log.parquet"),
        latent_cycles=_read_parquet(synthetic_dir / "latent_cycles.parquet"),
        latent_needs=_read_parquet(synthetic_dir / "latent_needs.parquet"),
        latent_buyers=_read_parquet(synthetic_dir / "latent_buyers.parquet"),
        latent_establishments=_read_parquet(synthetic_dir / "latent_establishments.parquet"),
        metadata=json.loads(metadata_path.read_text(encoding="utf-8")),
        real=real,
        real_sources=real_sources,
        real_pairs=real_pairs,
    )
