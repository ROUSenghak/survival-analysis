"""Build an immutable release-state overlay archive.

The archive packages the files listed in source_state_manifest.json plus that
manifest, so the current benchmark state can be reconstructed as an overlay on
the recorded Git HEAD. This solves reproducible state capture for packaging; it
does not approve scientific algorithm-ranking claims.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from build_source_state_manifest import ROOT, build_manifest


DEFAULT_VERSION = "v0_3_temporal_candidate_revision"
DEFAULT_BASE = ROOT / "reports" / "tables" / "synthetic_benchmark" / DEFAULT_VERSION
DEFAULT_SOURCE_MANIFEST = DEFAULT_BASE / "source_state_manifest.json"
DEFAULT_ARCHIVE = DEFAULT_BASE / "dirty_state_overlay.tar.gz"
DEFAULT_MANIFEST = DEFAULT_BASE / "dirty_state_overlay_manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _add_file(tar: tarfile.TarFile, source: Path, arcname: str) -> None:
    data = source.read_bytes()
    info = tarfile.TarInfo(arcname)
    info.size = len(data)
    info.mode = 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    tar.addfile(info, fileobj=io.BytesIO(data))


def build_overlay_archive(source_manifest: Path, archive: Path, manifest_path: Path) -> dict:
    archive_rel = archive.resolve().relative_to(ROOT).as_posix()
    manifest_rel = manifest_path.resolve().relative_to(ROOT).as_posix()
    state = build_manifest(source_manifest, extra_excluded_paths={archive_rel, manifest_rel})
    source_manifest.parent.mkdir(parents=True, exist_ok=True)
    source_manifest.write_text(json.dumps(state, indent=2), encoding="utf-8")

    file_rows = [
        row for row in state["files"]
        if row["exists"] and row["is_file"] and row["sha256"]
    ]
    archive.parent.mkdir(parents=True, exist_ok=True)
    tmp_archive = archive.with_suffix(archive.suffix + ".tmp")
    with tmp_archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                _add_file(tar, source_manifest, state["excluded_self"])
                for row in sorted(file_rows, key=lambda item: item["path"]):
                    _add_file(tar, ROOT / row["path"], row["path"])
    tmp_archive.replace(archive)

    with tarfile.open(archive, mode="r:gz") as tar:
        archive_members = sorted(member.name for member in tar.getmembers() if member.isfile())
    expected_members = sorted([state["excluded_self"], *[row["path"] for row in file_rows]])
    archive_sha = _sha256(archive)
    source_manifest_sha = _sha256(source_manifest)
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": state["git_head"],
        "archive_path": archive_rel,
        "archive_sha256": archive_sha,
        "archive_size_bytes": archive.stat().st_size,
        "source_state_manifest_path": state["excluded_self"],
        "source_state_manifest_sha256": source_manifest_sha,
        "overlay_file_count": len(expected_members),
        "overlay_payload_file_count": len(file_rows),
        "overlay_payload_size_bytes": int(sum(row["size_bytes"] or 0 for row in file_rows)),
        "member_list_matches_manifest": archive_members == expected_members,
        "excluded_paths": state["excluded_paths"],
        "status": "PASS" if archive_members == expected_members else "FAIL",
        "limitations": [
            "This is a release-state overlay on the recorded git_head.",
            "It does not change scientific readiness decisions and must not be cited as final algorithm-ranking evidence.",
            "The archive excludes itself and its manifest to avoid self-referential hashes.",
        ],
    }
    manifest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    result = build_overlay_archive(args.source_manifest, args.archive, args.manifest)
    print(
        json.dumps(
            {
                "status": result["status"],
                "archive_path": result["archive_path"],
                "archive_sha256": result["archive_sha256"],
                "archive_size_bytes": result["archive_size_bytes"],
                "overlay_file_count": result["overlay_file_count"],
                "member_list_matches_manifest": result["member_list_matches_manifest"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
