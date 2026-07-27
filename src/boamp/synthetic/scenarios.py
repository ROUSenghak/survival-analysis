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

VALID_SCENARIOS: tuple[str, ...] = (
    "clean_sanity",
    "central_provisional",
    "adverse_identity",
    "easier",
    "moderate",
    "difficult",
    "stress",
)


def _deep_merge(base: dict, overlay: dict) -> dict:
    merged = dict(base)
    for key, value in overlay.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_raw_scenario(project_root: Path, scenario_id: str, stack: tuple[str, ...] = ()) -> dict:
    if scenario_id in stack:
        chain = " -> ".join((*stack, scenario_id))
        raise ValueError(f"cyclic scenario inheritance: {chain}")
    path = Path(project_root) / "config" / "synthetic" / "scenarios" / f"{scenario_id}.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    parent = raw.get("extends")
    if not parent:
        return raw
    base = _load_raw_scenario(project_root, str(parent), (*stack, scenario_id))
    child = {k: v for k, v in raw.items() if k != "extends"}
    return _deep_merge(base, child)


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
    raw = _load_raw_scenario(project_root, scenario_id)
    ns = _to_namespace(raw)
    ns.scenario_id = scenario_id
    return ns


def load_benchmark_defaults(project_root: Path) -> SimpleNamespace:
    path = Path(project_root) / "config" / "synthetic" / "benchmark_defaults_v0_1.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _to_namespace(raw)
