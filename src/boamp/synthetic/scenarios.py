"""Loader for config/synthetic/scenarios/*.yaml and benchmark_defaults_*.yaml.

Scenario values are SCENARIO_PARAMETER by construction (they set the
unidentified quantities: recurrence prevalence, cycle-gap distribution, text
drift severity, etc. — see generator_parameter_actions.csv). They must never
be read back as if they were measurements of true BOAMP behaviour.

Configuration is *family*-versioned (v0.4). A benchmark version replays by
re-reading its live scenario file, so editing the shared scenario files in place
would silently break replay of every already-released version. Each generator
revision therefore gets its own configuration family — a subdirectory of
`config/synthetic/scenarios/` plus a matching `benchmark_defaults_*.yaml` — and
`family=None` keeps reading the flat v0.1-v0.3 files unchanged.
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

# Configuration family -> (scenario subdirectory, benchmark-defaults filename).
# `None` is the original flat layout that v0.1-v0.3 artifacts replay from.
SCENARIO_FAMILIES: dict[str, tuple[str, str]] = {
    "v0_4": ("v0_4", "benchmark_defaults_v0_4.yaml"),
}
DEFAULT_BENCHMARK_DEFAULTS_FILENAME = "benchmark_defaults_v0_1.yaml"


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


def scenario_config_path(project_root: Path, scenario_id: str, family: str | None = None) -> Path:
    """Resolve one scenario file inside its configuration family.

    A family file wins over the flat file of the same name; a family that does
    not define a scenario falls back to the flat one, so a new family only has to
    ship the scenarios it actually changes.
    """
    base = Path(project_root) / "config" / "synthetic" / "scenarios"
    if family is not None:
        if family not in SCENARIO_FAMILIES:
            raise ValueError(f"unknown scenario family {family!r}; expected one of {sorted(SCENARIO_FAMILIES)}")
        candidate = base / SCENARIO_FAMILIES[family][0] / f"{scenario_id}.yaml"
        if candidate.exists():
            return candidate
    return base / f"{scenario_id}.yaml"


def _load_raw_scenario(
    project_root: Path, scenario_id: str, stack: tuple[str, ...] = (), family: str | None = None
) -> dict:
    if scenario_id in stack:
        chain = " -> ".join((*stack, scenario_id))
        raise ValueError(f"cyclic scenario inheritance: {chain}")
    path = scenario_config_path(project_root, scenario_id, family)
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    parent = raw.get("extends")
    if not parent:
        return raw
    base = _load_raw_scenario(project_root, str(parent), (*stack, scenario_id), family=family)
    child = {k: v for k, v in raw.items() if k != "extends"}
    return _deep_merge(base, child)


def _to_namespace(obj):
    if isinstance(obj, dict):
        # Attribute access needs string keys. Lookup tables keyed by a value --
        # v0.4's entry-year weights and alias-set-size weights -- stay plain
        # dicts rather than being stringified into attribute names.
        if not all(isinstance(k, str) for k in obj):
            return {k: _to_namespace(v) for k, v in obj.items()}
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


def load_scenario(project_root: Path, scenario_id: str, family: str | None = None) -> SimpleNamespace:
    if scenario_id not in VALID_SCENARIOS:
        raise ValueError(f"unknown scenario_id {scenario_id!r}; expected one of {VALID_SCENARIOS}")
    raw = _load_raw_scenario(project_root, scenario_id, family=family)
    ns = _to_namespace(raw)
    ns.scenario_id = scenario_id
    ns.config_family = family
    return ns


def benchmark_defaults_path(project_root: Path, family: str | None = None) -> Path:
    filename = (
        SCENARIO_FAMILIES[family][1] if family in SCENARIO_FAMILIES else DEFAULT_BENCHMARK_DEFAULTS_FILENAME
    )
    return Path(project_root) / "config" / "synthetic" / filename


def load_benchmark_defaults(project_root: Path, family: str | None = None) -> SimpleNamespace:
    path = benchmark_defaults_path(project_root, family)
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _to_namespace(raw)
