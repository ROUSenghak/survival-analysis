"""Replay generated synthetic benchmark artifacts and compare table hashes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.reproducibility import compare_table_sets, regenerate_tables_from_metadata  # noqa: E402
from boamp.synthetic.validation_framework.loaders import available_replicates, load_benchmark_data  # noqa: E402


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
    parser.add_argument(
        "--scenarios",
        nargs="*",
        default=None,
        help="Optional scenario ids to replay. Defaults to every generated replicate.",
    )
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def _replay_one(version: str, scenario: str, world: str, corruption: str) -> dict:
    data = load_benchmark_data(ROOT, version, scenario, world, corruption)
    expected = {table: getattr(data, attr) for table, attr in DATA_ATTRS.items()}
    actual = regenerate_tables_from_metadata(ROOT, data.metadata, scenario)
    comparisons = compare_table_sets(expected, actual)
    failed_tables = [item.table for item in comparisons if not item.passed]
    return {
        "scenario": scenario,
        "world": world,
        "corruption": corruption,
        "status": "PASS" if not failed_tables else "FAIL",
        "failed_tables": failed_tables,
        "table_count": len(comparisons),
    }


def main() -> None:
    args = parse_args()
    wanted = set(args.scenarios or [])
    triples = [
        triple
        for triple in available_replicates(ROOT, args.version)
        if not wanted or triple[0] in wanted
    ]
    rows = [_replay_one(args.version, scenario, world, corruption) for scenario, world, corruption in triples]
    result = {
        "benchmark_version": args.version,
        "n_replicates": len(rows),
        "overall_status": "PASS" if rows and all(row["status"] == "PASS" for row in rows) else "FAIL",
        "replicates": rows,
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
