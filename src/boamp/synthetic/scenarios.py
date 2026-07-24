"""Loader for config/synthetic/scenarios/*.yaml and benchmark_defaults_v0_1.yaml.

Scenario values are SCENARIO_PARAMETER by construction (they set the
unidentified quantities: recurrence prevalence, cycle-gap distribution, text
drift severity, etc. — see generator_parameter_actions.csv). They must never
be read back as if they were measurements of true BOAMP behaviour.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

VALID_SCENARIOS: tuple[str, ...] = ("clean_sanity", "central_provisional", "adverse_identity")


def _to_namespace(obj):
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _to_namespace(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_to_namespace(v) for v in obj]
    return obj


def to_plain_dict(obj):
    """Convert nested scenario/default namespaces into JSON/YAML-safe data."""
    if isinstance(obj, SimpleNamespace):
        return {k: to_plain_dict(v) for k, v in vars(obj).items()}
    if isinstance(obj, dict):
        return {k: to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_plain_dict(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_plain_dict(v) for v in obj]
    return obj


def load_scenario(project_root: Path, scenario_id: str) -> SimpleNamespace:
    if scenario_id not in VALID_SCENARIOS:
        raise ValueError(f"unknown scenario_id {scenario_id!r}; expected one of {VALID_SCENARIOS}")
    path = Path(project_root) / "config" / "synthetic" / "scenarios" / f"{scenario_id}.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    ns = _to_namespace(raw)
    ns.scenario_id = scenario_id
    return ns


def load_benchmark_defaults(project_root: Path) -> SimpleNamespace:
    path = Path(project_root) / "config" / "synthetic" / "benchmark_defaults_v0_1.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _to_namespace(raw)
