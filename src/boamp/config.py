"""Central configuration loader for the two-layer BOAMP pipeline.

Loads config/paths.yaml and config/pipeline.yaml, resolves all paths against
the repository root, and exposes them as attribute-accessible namespaces:

    from boamp.config import load_config
    cfg = load_config()
    cfg.paths.processed_boamp_only   # -> absolute Path
    cfg.pipeline.scoring.weights.text
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"

_PATH_KEYS_ARE_PATHS = True

REQUIRED_PIPELINE_SECTIONS = [
    "run", "scope", "duration", "temporal_window", "candidates", "text_model",
    "cpv_score", "buyer_score", "scoring", "thresholds", "confidence_tiers",
    "enrichment", "survival", "evaluation",
]


def _to_namespace(obj):
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _to_namespace(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_to_namespace(v) for v in obj]
    return obj


def load_config(project_root: Path | None = None) -> SimpleNamespace:
    root = Path(project_root) if project_root else PROJECT_ROOT
    with open(root / "config" / "paths.yaml", encoding="utf-8") as f:
        raw_paths = yaml.safe_load(f)
    with open(root / "config" / "pipeline.yaml", encoding="utf-8") as f:
        raw_pipeline = yaml.safe_load(f)

    missing = [s for s in REQUIRED_PIPELINE_SECTIONS if s not in raw_pipeline]
    if missing:
        raise KeyError(f"config/pipeline.yaml is missing required sections: {missing}")

    weights = raw_pipeline["scoring"]["weights"]
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"scoring.weights must sum to 1.0, got {total}")

    thr = raw_pipeline["thresholds"]
    if not (thr["broad"] <= thr["balanced"] <= thr["strict"]):
        raise ValueError("thresholds must satisfy broad <= balanced <= strict")

    paths = SimpleNamespace(**{k: root / v for k, v in raw_paths.items()})
    cfg = SimpleNamespace(
        project_root=root,
        paths=paths,
        pipeline=_to_namespace(raw_pipeline),
    )
    return cfg


def ensure_output_dirs(cfg: SimpleNamespace) -> None:
    """Create every output directory the pipeline writes to."""
    for key in [
        "processed_dir", "processed_boamp_only", "processed_enriched",
        "processed_comparison", "reports_figures", "reports_tables",
        "reports_generated", "reports_data_quality",
    ]:
        getattr(cfg.paths, key).mkdir(parents=True, exist_ok=True)
