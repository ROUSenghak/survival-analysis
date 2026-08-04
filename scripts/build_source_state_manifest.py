"""Record the exact dirty source/artifact state for release packaging.

The manifest gives reviewers a machine-readable inventory of the
uncommitted/untracked files that define the current benchmark state. When paired
with a verified overlay archive, it can support a reproducible release-state
package without pretending that scientific ranking gates have passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GIT = [
    "git",
    "-c", "filter.lfs.process=",
    "-c", "filter.lfs.required=false",
    "-c", "filter.lfs.clean=cat",
    "-c", "filter.lfs.smudge=cat",
]
DEFAULT_OUTPUT = (
    ROOT
    / "reports"
    / "tables"
    / "synthetic_benchmark"
    / "v0_3_temporal_candidate_revision"
    / "source_state_manifest.json"
)
DEFAULT_EXCLUDED_PATHS = {
    "reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/dirty_state_overlay.tar.gz",
    "reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/dirty_state_overlay_manifest.json",
    "reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/dirty_state_overlay_verification.json",
    "reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/readiness/readiness_assessment.md",
    "reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/readiness/readiness_decisions.json",
}
PACKAGE_FILENAMES = {
    "source_state_manifest.json",
    "dirty_state_overlay.tar.gz",
    "dirty_state_overlay_manifest.json",
    "dirty_state_overlay_verification.json",
}
READINESS_FILENAMES = {
    "readiness_assessment.md",
    "readiness_decisions.json",
}


def _git(args: list[str]) -> str:
    return subprocess.run(
        [*GIT, *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _git_z(args: list[str]) -> list[str]:
    out = subprocess.run(
        [*GIT, *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return [part.decode("utf-8") for part in out.split(b"\0") if part]


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_local_excluded_paths(output: Path) -> set[str]:
    """Exclude version-local package/readiness files that record this package."""
    excluded: set[str] = set()
    base = output.parent
    if base.name in {"readiness", "validation_framework"}:
        base = base.parent
    if base.parent.name == "synthetic_benchmark":
        for name in PACKAGE_FILENAMES:
            excluded.add((base / name).relative_to(ROOT).as_posix())
        readiness_dir = base / "readiness"
        for name in READINESS_FILENAMES:
            excluded.add((readiness_dir / name).relative_to(ROOT).as_posix())
    return excluded


def _status_entries() -> list[dict]:
    rows = []
    for raw in _git_z(["status", "--porcelain=v1", "-z", "--untracked-files=all"]):
        status = raw[:2]
        path = raw[3:]
        rows.append({"status": status, "path": path})
    return rows


def build_manifest(output: Path, extra_excluded_paths: set[str] | None = None) -> dict:
    output = output.resolve()
    output_rel = output.relative_to(ROOT).as_posix()
    excluded_paths = {output_rel, *DEFAULT_EXCLUDED_PATHS, *_version_local_excluded_paths(output)}
    if extra_excluded_paths:
        excluded_paths.update(extra_excluded_paths)
    status_entries = _status_entries()
    paths = sorted({row["path"] for row in status_entries if row["path"] not in excluded_paths})
    file_rows = []
    for rel_path in paths:
        path = ROOT / rel_path
        file_rows.append(
            {
                "path": rel_path,
                "exists": path.exists(),
                "is_file": path.is_file(),
                "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
                "sha256": _sha256(path),
            }
        )
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": _git(["rev-parse", "HEAD"]).strip(),
        "git_status_porcelain": status_entries,
        "excluded_self": output_rel,
        "excluded_paths": sorted(excluded_paths),
        "tracked_diff_sha256": hashlib.sha256(_git(["diff", "--binary"]).encode("utf-8")).hexdigest(),
        "staged_diff_sha256": hashlib.sha256(_git(["diff", "--cached", "--binary"]).encode("utf-8")).hexdigest(),
        "n_status_entries": len(status_entries),
        "n_hashed_paths": len(file_rows),
        "files": file_rows,
        "limitations": [
            "The manifest hashes the dirty worktree for auditability and release-state packaging.",
            "Dirty-state overlay archive paths are excluded to avoid self-referential hashes.",
            "The manifest cannot include its own final hash without becoming self-referential; excluded_self records that path.",
            "This state-capture manifest does not change scientific ranking or robustness readiness.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build_manifest(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ["git_head", "n_status_entries", "n_hashed_paths", "excluded_self"]}, indent=2))


if __name__ == "__main__":
    main()
