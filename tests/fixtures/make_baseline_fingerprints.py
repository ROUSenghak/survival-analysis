"""Freeze baseline fingerprints of the current two-layer pipeline outputs.

Run after an approved end-to-end refresh. The resulting JSON is the parity
oracle used by the slow tests: counts, link/source identities, and event counts,
not byte equality.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "baseline_fingerprints.json"

FILES = {
    "clean_m0": "data/interim/boamp_common_prepared.csv",
    "m0_sources": "data/processed/boamp_only/boamp_only_sources.csv",
    "m0_pairs": "data/processed/boamp_only/boamp_only_candidate_pairs.csv",
    "m0_links_broad": "data/processed/boamp_only/boamp_only_links_broad.csv",
    "m0_links_balanced": "data/processed/boamp_only/boamp_only_links_balanced.csv",
    "m0_links_strict": "data/processed/boamp_only/boamp_only_links_strict.csv",
    "m0_survival_balanced": "data/processed/boamp_only/boamp_only_survival.csv",
    "m1_clean_sources": "data/processed/enriched/enriched_sources.csv",
    "m1_pairs": "data/processed/enriched/enriched_candidate_pairs.csv",
    "m1_links_balanced": "data/processed/enriched/enriched_links_balanced.csv",
    "m1_survival_balanced": "data/processed/enriched/enriched_survival.csv",
}


def sha256_of_values(values) -> str:
    joined = "\n".join(sorted(str(v) for v in values))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def first_present(df: pd.DataFrame, candidates) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def main() -> None:
    fingerprints: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Parity oracle for the current two-layer pipeline. Counts and "
            "sorted-ID hashes are generated from the refreshed boamp_only and "
            "enriched artifacts."
        ),
        "files": {},
    }

    link_ids: dict[str, set] = {}

    for key, name in FILES.items():
        path = REPO / name
        if not path.exists():
            fingerprints["files"][key] = {"path": name, "missing": True}
            continue
        # The prepared corpus is large; count logical CSV rows only (raw line counts are
        # inflated by embedded newlines in quoted text fields)
        if key == "clean_m0":
            n_rows = sum(
                len(c)
                for c in pd.read_csv(path, dtype=str, usecols=[0], chunksize=200000)
            )
            fingerprints["files"][key] = {"path": name, "rows": int(n_rows)}
            continue
        df = pd.read_csv(path, dtype=str, low_memory=False)
        entry: dict = {"path": name, "rows": int(len(df)), "cols": int(df.shape[1])}
        id_col = first_present(df, ["source_notice_id", "source_id", "notice_id", "idweb"])
        if id_col is not None:
            entry["id_col"] = id_col
            entry["ids_sha256"] = sha256_of_values(df[id_col].dropna())
        if "links" in key and id_col is not None:
            link_ids[key] = set(df[id_col].dropna())
        if key.endswith("survival_balanced") and "event" in df.columns:
            entry["events"] = int(pd.to_numeric(df["event"]).sum())
        fingerprints["files"][key] = entry

    if "m0_links_balanced" in link_ids and "m1_links_balanced" in link_ids:
        a, b = link_ids["m0_links_balanced"], link_ids["m1_links_balanced"]
        fingerprints["layer_overlap"] = {
            "common": len(a & b),
            "m0_only": len(a - b),
            "m1_only": len(b - a),
            "jaccard": round(len(a & b) / len(a | b), 4) if a | b else None,
        }

    OUT.write_text(json.dumps(fingerprints, indent=2))
    print(json.dumps(fingerprints, indent=2)[:3000])
    print(f"\nWritten to {OUT}")


if __name__ == "__main__":
    main()
