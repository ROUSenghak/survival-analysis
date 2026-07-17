"""Data-dictionary and export-manifest generation."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_sha(project_root: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def describe_dataframe(df: pd.DataFrame, name: str, descriptions: dict | None = None) -> pd.DataFrame:
    """Schema table: column, dtype, non-null rate, sample, description."""
    descriptions = descriptions or {}
    rows = []
    for col in df.columns:
        non_null = int(df[col].notna().sum())
        sample = df[col].dropna().astype(str).unique()[:2]
        rows.append({
            "dataset": name,
            "column": col,
            "dtype": str(df[col].dtype),
            "non_null_count": non_null,
            "non_null_rate": round(non_null / len(df), 4) if len(df) else 0.0,
            "sample_values": " | ".join(s[:60] for s in sample),
            "description": descriptions.get(col, ""),
        })
    return pd.DataFrame(rows)


def write_export_manifest(exported_files: list[Path], cfg, out_name: str = "export_manifest.csv") -> pd.DataFrame:
    """Record file, rows, md5, git sha, timestamp for every exported dataset."""
    rows = []
    sha = git_sha(cfg.project_root)
    now = datetime.now(timezone.utc).isoformat()
    for path in exported_files:
        path = Path(path)
        if not path.exists():
            rows.append({"file": str(path.relative_to(cfg.project_root)), "exists": False})
            continue
        n_rows = None
        if path.suffix == ".csv":
            n_rows = sum(len(c) for c in pd.read_csv(path, usecols=[0], dtype=str, chunksize=200000))
        rows.append({
            "file": str(path.relative_to(cfg.project_root)),
            "exists": True,
            "rows": n_rows,
            "bytes": path.stat().st_size,
            "md5": md5_file(path),
            "git_sha": sha,
            "generated_at": now,
        })
    manifest = pd.DataFrame(rows)
    manifest.to_csv(cfg.paths.processed_dir / out_name, index=False)
    return manifest
