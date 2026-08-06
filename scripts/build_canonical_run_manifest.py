"""Build the canonical run manifest for the BOAMP linkage pipeline."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.config import ensure_output_dirs, load_config
from boamp.status import (  # noqa: E402
    BLOCKED_BY_EXTERNAL_CLASSIFICATION,
    BLOCKED_BY_MANUAL_AUDIT,
    PROVISIONAL_LINKAGE_OUTPUT,
    UNKNOWN_REAL_PRECISION_RECALL,
    classification_export_status,
    manual_audit_status,
)


RUN_ID = "canonical_boamp_linkage_freeze_v1"
BENCHMARK_VERSION = "v0_4_population_alias_revision"
CANONICAL_CANDIDATE_GENERATOR = "dur_w6_same_buyer_expected_end_window_top30"


def git_value(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def row_count(path: Path) -> int | None:
    if not path.exists() or not path.is_file():
        return None
    if path.suffix.lower() == ".csv":
        return int(len(pd.read_csv(path, usecols=[0], low_memory=False)))
    if path.suffix.lower() in {".parquet", ".pq"}:
        return int(len(pd.read_parquet(path, columns=[])))
    return None


def file_record(path: Path) -> dict:
    return {
        "path": str(path.relative_to(ROOT)),
        "exists": path.exists(),
        "rows": row_count(path),
        "bytes": path.stat().st_size if path.exists() and path.is_file() else None,
        "sha256": file_sha256(path),
        "git_tracked": bool(git_value("ls-files", "--error-unmatch", str(path.relative_to(ROOT)))),
    }


def main() -> None:
    cfg = load_config(ROOT)
    ensure_output_dirs(cfg)

    audit_path = cfg.paths.manual_audit_sample_30
    classification_path = cfg.paths.external_classification_export
    manual_status = manual_audit_status(audit_path)
    class_status = classification_export_status(classification_path)

    outputs = [
        cfg.paths.interim_common_prepared,
        cfg.paths.processed_boamp_only / "boamp_only_sources.csv",
        cfg.paths.processed_boamp_only / "boamp_only_candidate_pairs.csv",
        cfg.paths.processed_boamp_only / "boamp_only_links_balanced.csv",
        ROOT / "reports/tables/real_linkage_freeze/real_candidate_pairs_reproduced.csv",
        ROOT / "reports/tables/real_linkage_freeze/real_primary_gbm_links.csv",
        ROOT / "reports/tables/real_linkage_freeze/real_linkage_strategy_summary.csv",
        cfg.paths.manual_audit_sample_30,
        cfg.paths.manual_audit_entry_template,
        cfg.paths.reports_data_quality / "corpus_freeze_manifest.json",
    ]
    synthetic_outputs = [
        ROOT / "reports/tables/synthetic_benchmark" / BENCHMARK_VERSION / "generation_manifest.json",
        ROOT / "reports/tables/synthetic_benchmark" / BENCHMARK_VERSION / "readiness/readiness_decisions.json",
        ROOT / "reports/tables/synthetic_benchmark" / BENCHMARK_VERSION / "linkage_algorithm_benchmark/summary_metrics.csv",
        ROOT / "reports/tables/synthetic_benchmark" / BENCHMARK_VERSION / "validation_framework/replay_replicates.json",
    ]
    config_inputs = [
        ROOT / "config/pipeline.yaml",
        ROOT / "config/paths.yaml",
        ROOT / "config/synthetic/benchmark_defaults_v0_4.yaml",
        ROOT / "config/synthetic/scenarios/v0_4/central_provisional.yaml",
    ]
    canonical_index = [
        ROOT / "canonical/README.md",
        ROOT / "canonical/config/README.md",
        ROOT / "canonical/data/README.md",
        ROOT / "canonical/synthetic_benchmark/README.md",
        ROOT / "canonical/linkage/README.md",
        ROOT / "canonical/audit/README.md",
        ROOT / "canonical/classification/README.md",
        ROOT / "canonical/downstream/README.md",
        ROOT / "canonical/reports/README.md",
    ]

    manifest = {
        "run_id": RUN_ID,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project_status": {
            "canonical_real_layer": "boamp_only",
            "real_precision_recall_status": UNKNOWN_REAL_PRECISION_RECALL,
            "event_censoring_status": PROVISIONAL_LINKAGE_OUTPUT,
            "manual_audit_gate": manual_status.__dict__,
            "classification_gate": class_status.__dict__,
            "survival_analysis_gate": BLOCKED_BY_MANUAL_AUDIT,
            "technology_specific_gate": BLOCKED_BY_EXTERNAL_CLASSIFICATION,
        },
        "git": {
            "branch": git_value("branch", "--show-current"),
            "head": git_value("rev-parse", "HEAD"),
            "status_porcelain": git_value("status", "--short"),
        },
        "configuration": {
            "seed": cfg.pipeline.run.random_seed,
            "candidate_generator": CANONICAL_CANDIDATE_GENERATOR,
            "benchmark_version": BENCHMARK_VERSION,
            "thresholds": {
                "gbm_primary": _read_threshold("gradient_boosting"),
                "composite_balanced": cfg.pipeline.thresholds.balanced,
                "composite_strict": cfg.pipeline.thresholds.strict,
            },
        },
        "config_files": [file_record(path) for path in config_inputs],
        "canonical_index": [file_record(path) for path in canonical_index],
        "canonical_outputs": [file_record(path) for path in outputs],
        "synthetic_benchmark_outputs": [file_record(path) for path in synthetic_outputs],
        "reproduction_commands": [
            "PYTHONPATH=src .venv/bin/python scripts/check_boamp_corpus_quality.py",
            "PYTHONPATH=src .venv/bin/python scripts/freeze_real_linkage.py",
            "PYTHONPATH=src .venv/bin/python scripts/build_linkage_algorithm_diagnostic_curves.py",
            "PYTHONPATH=src .venv/bin/python scripts/test_synthetic_to_real_transfer.py",
            "PYTHONPATH=src .venv/bin/python scripts/build_real_audit_sample.py",
            "PYTHONPATH=src .venv/bin/python scripts/build_canonical_run_manifest.py",
        ],
    }
    cfg.paths.canonical_run_manifest.parent.mkdir(parents=True, exist_ok=True)
    cfg.paths.canonical_run_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"WROTE {cfg.paths.canonical_run_manifest.relative_to(ROOT)}")


def _read_threshold(algorithm: str) -> float | None:
    path = (
        ROOT
        / "reports/tables/synthetic_benchmark"
        / BENCHMARK_VERSION
        / "linkage_algorithm_benchmark/algorithm_thresholds.csv"
    )
    if not path.exists():
        return None
    df = pd.read_csv(path)
    hit = df.loc[df["algorithm"].eq(algorithm), "threshold"]
    return float(hit.iloc[0]) if len(hit) else None


if __name__ == "__main__":
    main()
