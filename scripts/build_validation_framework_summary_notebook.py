"""Build a notebook that summarizes validation-framework output tables."""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "12_synthetic_validation_framework_summary.ipynb"


def md(src: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(src)


def code(src: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(src)


def build_notebook() -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    nb["cells"] = [
        md(
            """# 12 - Synthetic Benchmark Validation Framework Summary

This notebook is intentionally table-driven. It reads the artifacts produced by
`scripts/validate_synthetic_benchmark.py` and `scripts/build_benchmark_registries.py`
and presents release readiness, warnings, and discrepancy details without
reimplementing validation logic in notebook cells.

Read the statuses with the specification's decision rule in mind:

- **PASS** — the interval lies inside the predeclared tolerance, or the invariant
  holds exactly. For metrics carrying no bootstrap interval this means "not
  obviously discrepant", which is weaker than equivalence.
- **WARNING** — the estimate crosses a tolerance, the evidence is too thin to
  decide, or a non-critical discrepancy remains.
- **FAIL** — a critical invariant broke, truth leaked, a real record was copied,
  or a core benchmark property is materially outside tolerance.
- **INCONCLUSIVE** — the check could not be run on the available data. Never read
  it as a pass.

Do not average these into one score: a high average hides a fatal defect.
"""
        ),
        code(
            """import json
from pathlib import Path

import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 90)

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
VERSION = "v0_3_temporal_candidate_revision"
BASE = PROJECT_ROOT / "reports/tables/synthetic_benchmark" / VERSION
VALIDATION_DIR = BASE / "validation_framework"
REGISTRY_DIR = BASE / "registries"

metrics = pd.read_csv(VALIDATION_DIR / "validation_metrics_long.csv")
gates = pd.read_csv(VALIDATION_DIR / "validation_gate_summary.csv")
discrepancies = pd.read_csv(VALIDATION_DIR / "discrepancy_register.csv")
probes = pd.read_csv(VALIDATION_DIR / "probe_linker_results.csv")
manifest = json.loads((VALIDATION_DIR / "validation_manifest.json").read_text())

{k: v for k, v in manifest.items() if k not in {"input_checksums", "probe_linker_results"}}"""
        ),
        md(
            """## Release gate

Critical gates block release on their own. Non-critical gates can only downgrade
the run to `PASS_WITH_WARNINGS`, and their breaches belong in the fidelity budget:
the benchmark is allowed to simplify the real corpus as long as the simplification
is written down."""
        ),
        code(
            """gates.sort_values(["critical", "status", "gate"], ascending=[False, True, True])"""
        ),
        md("### What is currently blocking"),
        code(
            """blocking = gates[gates["critical"] & gates["status"].eq("FAIL")]
if blocking.empty:
    print("No critical gate is failing.")
else:
    display(blocking[["gate", "n_fail", "blocking_reason"]])
    display(
        metrics[metrics["scope"].isin(blocking["gate"]) & metrics["status"].eq("FAIL")][
            ["property", "metric", "synthetic_estimate", "ci_low", "ci_high", "tolerance", "notes"]
        ]
    )"""
        ),
        md("## Discrepancy register"),
        code(
            """discrepancies.sort_values(["status", "scope", "property", "metric"])"""
        ),
        md("## Metric inventory by gate"),
        code(
            """(
    metrics.groupby(["scope", "status"])
    .size()
    .rename("n")
    .reset_index()
    .pivot(index="scope", columns="status", values="n")
    .fillna(0)
    .astype(int)
)"""
        ),
        md(
            """## Benchmark difficulty

These need the sealed truth tables and cannot be computed on real BOAMP at all.
Blocking recall says whether a comparison model is even being given the chance to
work; score overlap says whether telling a match from a plausible non-match takes
real discrimination."""
        ),
        code(
            """metrics[metrics["scope"].eq("hidden_truth_difficulty")][
    ["subgroup", "property", "metric", "synthetic_estimate", "tolerance", "status"]
]"""
        ),
        md(
            """## Probe linkers

Three deliberately different linkers with frozen parameters. None of them is the
production acceptance threshold — a pipeline threshold is an output of that
pipeline, never a definition of truth. The benchmark is informative if the probes
separate, and unusable if any of them solves it."""
        ),
        code("""probes"""),
        md(
            """## Predeclared tolerances and parameter provenance

Tolerances are read from the gate code itself, so a retuned tolerance shows up here
instead of quietly diverging from the registry. Parameters marked
`SCENARIO_UNIDENTIFIED` encode assumptions real BOAMP cannot settle and must be
varied across scenarios rather than quoted as estimates."""
        ),
        code(
            """tolerances = pd.read_csv(REGISTRY_DIR / "tolerance_registry.csv")
parameters = pd.read_csv(REGISTRY_DIR / "parameter_registry.csv")

display(tolerances[tolerances["gate_is_critical"]][["module", "tolerance_key", "value", "gate"]].drop_duplicates())
parameters["provenance_class"].value_counts()"""
        ),
        md("### Parameters whose scenario-file value was overridden at run time"),
        code(
            """parameters[parameters["overridden_at_runtime"]][
    ["parameter", "scenario_file_value", "effective_value", "provenance_class"]
]"""
        ),
        md(
            """## Replicate inventory

Seed-to-seed stability cannot be estimated from a single world per scenario, so it
is reported `INCONCLUSIVE` rather than assumed."""
        ),
        code(
            """display(pd.read_csv(REGISTRY_DIR / "scenario_manifest.csv"))
metrics[metrics["scope"].eq("robustness")][["subgroup", "property", "metric", "synthetic_estimate", "status", "notes"]]"""
        ),
    ]
    return nb


def main() -> None:
    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(build_notebook(), NOTEBOOK)
    print(f"Wrote {NOTEBOOK}")


if __name__ == "__main__":
    main()
