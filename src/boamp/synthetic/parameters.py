"""Loader for config/synthetic/calibration_parameters_v0_1.yaml.

Every value this module exposes is `action == USE_DIRECTLY` in
reports/tables/synthetic_calibration/generator_parameter_actions.csv: an
OBSERVABLE/EMPIRICAL or structural (LITERATURE_BASED) value the generator
may consume as a direct input. Fidelity-target and scenario values are
deliberately not exposed here — see scenarios.py and the fidelity
notebooks/tables instead.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import yaml


def _to_namespace(obj):
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _to_namespace(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_to_namespace(v) for v in obj]
    return obj


class CalibratedParameters:
    """Thin wrapper over the parsed calibration_parameters_v0_1.yaml tree."""

    def __init__(self, raw: dict, project_root: Path):
        self.raw = raw
        self.project_root = Path(project_root)
        self.ns = _to_namespace(raw)

    def value(self, *path: str):
        """Walk a dotted section path and return its `.value` leaf.

        Example: value("cpv", "missing_rate") -> 0.1706
        """
        node = self.ns
        for p in path:
            node = getattr(node, p)
        return node.value if hasattr(node, "value") else node

    def table(self, *path: str) -> pd.DataFrame:
        """Walk a dotted section path to a table-reference leaf (a bare
        string path, or a `.value` string path) and load it as a DataFrame.
        """
        node = self.ns
        for p in path:
            node = getattr(node, p)
        rel = node.value if hasattr(node, "value") else node
        return pd.read_csv(self.project_root / rel)


def load_calibration_parameters(project_root: Path) -> CalibratedParameters:
    path = Path(project_root) / "config" / "synthetic" / "calibration_parameters_v0_1.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return CalibratedParameters(raw, project_root)
