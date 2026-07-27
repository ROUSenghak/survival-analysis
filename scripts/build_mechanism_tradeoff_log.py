"""Write a machine-readable log of rejected benchmark mechanism changes.

The benchmark objective requires failed recalibration attempts to leave an
auditable trail when they reveal a real trade-off. This script records such
decisions without treating transient local trial outputs as accepted benchmark
artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VERSION = "v0_3_temporal_candidate_revision"
DEFAULT_BASE = ROOT / "reports" / "tables" / "synthetic_benchmark" / DEFAULT_VERSION


FIELDS = [
    "version",
    "mechanism_id",
    "component",
    "status",
    "provenance_category",
    "retained_mechanism",
    "tested_change",
    "intended_improvement",
    "evidence_level",
    "baseline_validation_status",
    "baseline_metric_failures",
    "baseline_blocking_gates",
    "baseline_replay_status",
    "observed_effect_summary",
    "quantitative_effect",
    "exact_trial_artifact_preserved",
    "decision_rationale",
    "readiness_consequence",
    "source_reference",
    "limitations",
]


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_tradeoff_log(base_dir: Path, version: str = DEFAULT_VERSION) -> list[dict]:
    validation = _load_json(base_dir / "validation_framework" / "validation_manifest.json")
    replay = _load_json(base_dir / "validation_framework" / "replay_replicates.json")

    baseline_status = str(validation.get("overall_status", "UNKNOWN"))
    baseline_failures = str(validation.get("n_metric_failures", "UNKNOWN"))
    baseline_blocking_gates = json.dumps(validation.get("blocking_gates", []), sort_keys=True)
    baseline_replay = str(replay.get("overall_status", "UNKNOWN"))

    common = {
        "version": version,
        "component": "observed_buyer_identity_persistence",
        "provenance_category": "SCENARIO_UNIDENTIFIED",
        "retained_mechanism": (
            "Cache observed buyer SIRET/SIREN/name at latent cycle level, and "
            "at latent need level for scoped digital CPV divisions when "
            "stabilize_scoped_identity_by_need is enabled."
        ),
        "baseline_validation_status": baseline_status,
        "baseline_metric_failures": baseline_failures,
        "baseline_blocking_gates": baseline_blocking_gates,
        "baseline_replay_status": baseline_replay,
        "exact_trial_artifact_preserved": "False",
        "source_reference": (
            "src/boamp/synthetic/corruption.py; "
            "docs/methodology.md; "
            "reports/generated/synthetic_benchmark/v0_3_temporal_candidate_revision_report.md; "
            "reports/synthetic_benchmark_technical_report.tex"
        ),
        "limitations": (
            "Rejected trial outputs were transient local recalibration evidence, "
            "not released benchmark artifacts. The log therefore records the "
            "decision and observed failure mode, not a full persisted metric table."
        ),
    }

    return [
        {
            **common,
            "mechanism_id": "identity_persistence_retained_2026_07_27",
            "status": "RETAINED",
            "tested_change": "None; current supported benchmark mechanism.",
            "intended_improvement": (
                "Preserve production-blocking reachability and avoid treating "
                "same-family text reuse as cross-buyer generic boilerplate solely "
                "because sibling notice identity keys drift."
            ),
            "evidence_level": "CURRENT_GENERATED_ARTIFACTS",
            "observed_effect_summary": (
                "Current regenerated central benchmark has no metric failures, "
                "passes all-artifact replay, and remains PASS_WITH_WARNINGS."
            ),
            "quantitative_effect": (
                f"validation_status={baseline_status}; "
                f"n_metric_failures={baseline_failures}; "
                f"replay_replicates={baseline_replay}"
            ),
            "decision_rationale": (
                "Retained because the tested alternatives improved one local "
                "identifier symptom but damaged validation domains that materially "
                "affect linkage difficulty."
            ),
            "readiness_consequence": (
                "Supports controlled synthetic comparison only with limitations; "
                "does not resolve final-ranking or release blockers."
            ),
        },
        {
            **common,
            "mechanism_id": "identity_cache_split_by_schema_year_notice_type_rejected_2026_07_27",
            "status": "REJECTED_LOCAL_AUDIT",
            "tested_change": (
                "Split the observed-identity cache by schema family, publication "
                "year, and notice type."
            ),
            "intended_improvement": (
                "Reduce attribution-specific SIRET presence mismatch by preventing "
                "award notices from inheriting the call-notice identifier draw."
            ),
            "evidence_level": "LOCAL_RECALIBRATION_TRIAL",
            "observed_effect_summary": (
                "The trial introduced a critical conditional-fidelity failure and "
                "reduced widened production-blocking completeness."
            ),
            "quantitative_effect": (
                "36-month production-blocking completeness fell to approximately "
                "0.602 in the tested central run."
            ),
            "decision_rationale": (
                "Rejected because a narrower identity cache damaged reachability "
                "and conditional realism more than it repaired identifier fidelity."
            ),
            "readiness_consequence": (
                "Would have blocked controlled-comparison readiness under the "
                "current hard-gate interpretation."
            ),
        },
        {
            **common,
            "mechanism_id": "identity_cache_split_by_notice_type_rejected_2026_07_27",
            "status": "REJECTED_LOCAL_AUDIT",
            "tested_change": "Split the observed-identity cache by notice type only.",
            "intended_improvement": (
                "Seek a smaller fix for attribution-specific SIRET presence while "
                "preserving most family-level identity persistence."
            ),
            "evidence_level": "LOCAL_RECALIBRATION_TRIAL",
            "observed_effect_summary": (
                "The trial still introduced a critical conditional text failure "
                "and SIRET-presence failures."
            ),
            "quantitative_effect": "No accepted generated artifact retained.",
            "decision_rationale": (
                "Rejected because the reduced split still created material "
                "validation regressions."
            ),
            "readiness_consequence": (
                "Would not support final-ranking readiness and was not adopted."
            ),
        },
    ]


def write_tradeoff_log(base_dir: Path, version: str = DEFAULT_VERSION) -> dict:
    rows = build_tradeoff_log(base_dir, version)
    base_dir.mkdir(parents=True, exist_ok=True)
    csv_path = base_dir / "mechanism_tradeoff_log.csv"
    json_path = base_dir / "mechanism_tradeoff_log.json"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "row_count": len(rows),
        "rows": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {"csv": str(csv_path), "json": str(json_path), "row_count": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Benchmark table directory. Defaults to reports/tables/synthetic_benchmark/<version>.",
    )
    args = parser.parse_args()
    base_dir = args.base_dir or ROOT / "reports" / "tables" / "synthetic_benchmark" / args.version
    result = write_tradeoff_log(base_dir, args.version)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
