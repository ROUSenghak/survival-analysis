"""Verify that a dirty-state overlay archive replays onto its recorded HEAD."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VERSION = "v0_3_temporal_candidate_revision"
DEFAULT_BASE = ROOT / "reports" / "tables" / "synthetic_benchmark" / DEFAULT_VERSION
DEFAULT_ARCHIVE = DEFAULT_BASE / "dirty_state_overlay.tar.gz"
DEFAULT_MANIFEST = DEFAULT_BASE / "dirty_state_overlay_manifest.json"
DEFAULT_OUTPUT = DEFAULT_BASE / "dirty_state_overlay_verification.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> list[str]:
    dest = dest.resolve()
    names = []
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if dest != target and dest not in target.parents:
            raise ValueError(f"archive member escapes destination: {member.name}")
        if not member.isfile() and not member.isdir():
            raise ValueError(f"archive member is not a regular file/directory: {member.name}")
        names.append(member.name)
    tar.extractall(dest)
    return names


def _extract_git_head(git_head: str, dest: Path) -> None:
    archive_path = dest / "_clean_head.tar"
    with archive_path.open("wb") as f:
        subprocess.run(
            ["git", "archive", "--format=tar", git_head],
            cwd=ROOT,
            check=True,
            stdout=f,
        )
    with tarfile.open(archive_path, mode="r:") as tar:
        _safe_extract(tar, dest)
    archive_path.unlink()


def verify_overlay_archive(archive: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive_sha = _sha256(archive)
    archive_sha_matches_manifest = archive_sha == manifest.get("archive_sha256")
    with tempfile.TemporaryDirectory(prefix="boamp-overlay-") as tmp:
        root = Path(tmp)
        _extract_git_head(str(manifest["git_head"]), root)
        with tarfile.open(archive, mode="r:gz") as tar:
            member_names = sorted(name for name in _safe_extract(tar, root) if not name.endswith("/"))

        source_manifest_rel = manifest["source_state_manifest_path"]
        source_manifest_path = root / source_manifest_rel
        source_manifest_sha = _sha256(source_manifest_path)
        source_manifest_sha_matches = source_manifest_sha == manifest.get("source_state_manifest_sha256")
        source_state = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        # The builder archives only rows that exist and are regular files, so the
        # expected member list must apply the same filter. Comparing against
        # every manifest row made any dirty state containing a deletion or a
        # rename fail with zero missing files and zero hash mismatches, which
        # said nothing about whether the archive was correct.
        payload_rows = [
            row for row in source_state["files"]
            if bool(row["exists"]) and bool(row["is_file"]) and row["sha256"]
        ]
        expected_members = sorted([source_manifest_rel, *[row["path"] for row in payload_rows]])
        member_list_matches_manifest = member_names == expected_members

        # A tar overlay cannot express "this HEAD file is gone". Paths the dirty
        # state deletes are therefore reported, not silently accepted: applying
        # the overlay to a clean HEAD leaves them in place.
        deletions_not_representable = sorted(
            row["path"] for row in source_state["files"] if not bool(row["exists"])
        )

        mismatches = []
        missing = []
        for row in payload_rows:
            path = root / row["path"]
            if not path.exists():
                missing.append(row["path"])
                continue
            digest = _sha256(path)
            if digest != row["sha256"]:
                mismatches.append(
                    {
                        "path": row["path"],
                        "expected_sha256": row["sha256"],
                        "actual_sha256": digest,
                    }
                )

    archive_is_correct = (
        archive_sha_matches_manifest
        and source_manifest_sha_matches
        and member_list_matches_manifest
        and not mismatches
        and not missing
    )
    status = (
        "FAIL" if not archive_is_correct
        else "PASS_WITH_LIMITATIONS" if deletions_not_representable
        else "PASS"
    )
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "archive_path": archive.resolve().relative_to(ROOT).as_posix(),
        "archive_sha256": archive_sha,
        "archive_sha_matches_manifest": archive_sha_matches_manifest,
        "git_head": manifest["git_head"],
        "source_state_manifest_path": source_manifest_rel,
        "source_state_manifest_sha_matches_manifest": source_manifest_sha_matches,
        "member_list_matches_manifest": member_list_matches_manifest,
        "n_members": len(member_names),
        "n_expected_members": len(expected_members),
        "n_hashed_paths_checked": len(payload_rows),
        "n_manifest_rows": len(source_state["files"]),
        "n_missing": len(missing),
        "n_mismatches": len(mismatches),
        "n_deletions_not_representable": len(deletions_not_representable),
        "deletions_not_representable": deletions_not_representable[:50],
        "missing": missing[:50],
        "mismatches": mismatches[:50],
        "limitations": [
            "Verification applies the overlay to a clean git archive of git_head and checks recorded dirty-file hashes.",
            "This verifies archive replayability only; it does not change final algorithm-ranking readiness.",
            "A tar overlay cannot express a deletion. Paths the dirty state removes are listed under "
            "deletions_not_representable and downgrade the status to PASS_WITH_LIMITATIONS: replaying the "
            "overlay onto a clean HEAD leaves those files in place.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = verify_overlay_archive(args.archive, args.manifest)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "archive_sha_matches_manifest": result["archive_sha_matches_manifest"],
                "member_list_matches_manifest": result["member_list_matches_manifest"],
                "n_hashed_paths_checked": result["n_hashed_paths_checked"],
                "n_missing": result["n_missing"],
                "n_mismatches": result["n_mismatches"],
                "n_deletions_not_representable": result["n_deletions_not_representable"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
