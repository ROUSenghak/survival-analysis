"""Regenerate a synthetic benchmark and compare canonical table content."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.reproducibility import compare_table_sets, regenerate_tables_from_metadata  # noqa: E402
from boamp.synthetic.validation_framework.loaders import load_benchmark_data  # noqa: E402


DATA_ATTRS = {
    "latent_buyers": "latent_buyers",
    "latent_establishments": "latent_establishments",
    "latent_needs": "latent_needs",
    "latent_cycles": "latent_cycles",
    "true_relations": "true_relations",
    "notice_family_membership": "notice_family_membership",
    "clean_notices": "clean",
    "observed_notices": "observed",
    "corruption_log": "corruption_log",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v0_3_temporal_candidate_revision")
    parser.add_argument("--scenario", default="central_provisional")
    parser.add_argument("--world", default="001")
    parser.add_argument("--corruption", default="001")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = load_benchmark_data(ROOT, args.version, args.scenario, args.world, args.corruption)
    expected = {table: getattr(data, attr) for table, attr in DATA_ATTRS.items()}
    actual = regenerate_tables_from_metadata(ROOT, data.metadata, args.scenario)
    comparisons = compare_table_sets(expected, actual)
    rows = [
        {
            "table": item.table,
            "status": "PASS" if item.passed else "FAIL",
            "expected_hash": item.expected_hash,
            "actual_hash": item.actual_hash,
            "expected_rows": item.expected_rows,
            "actual_rows": item.actual_rows,
            "expected_columns": list(item.expected_columns),
            "actual_columns": list(item.actual_columns),
        }
        for item in comparisons
    ]
    result = {
        "benchmark_version": args.version,
        "scenario": args.scenario,
        "world": args.world,
        "corruption": args.corruption,
        "overall_status": "PASS" if all(item.passed for item in comparisons) else "FAIL",
        "tables": rows,
    }
    text = json.dumps(result, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    if result["overall_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
