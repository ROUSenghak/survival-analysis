"""Freeze the real-BOAMP buyer-level fidelity holdout used by v0.4.

Writes `config/synthetic/real_holdout_buyer_keys.csv` plus a coverage summary and
a provenance record. Re-running with the same seed reproduces the same split; the
script refuses to overwrite an existing split unless `--force` is given, because
downstream calibration and the fresh-seed evaluation both assume it is frozen.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.holdout import (  # noqa: E402
    CALIBRATION,
    DEFAULT_HOLDOUT_FRACTION,
    DEFAULT_SPLIT_SEED,
    HOLDOUT,
    HOLDOUT_RELATIVE_PATH,
    build_real_buyer_holdout,
    summarise_split,
    write_real_buyer_holdout,
)

VERSION = "v0_4_population_alias_revision"
OUT_TABLES = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION / "holdout"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout-fraction", type=float, default=DEFAULT_HOLDOUT_FRACTION)
    parser.add_argument("--seed", type=int, default=DEFAULT_SPLIT_SEED)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    target = ROOT / HOLDOUT_RELATIVE_PATH
    if target.exists() and not args.force:
        raise SystemExit(f"{target} already exists; pass --force to redraw the frozen split")

    table = build_real_buyer_holdout(
        ROOT, holdout_fraction=args.holdout_fraction, seed=args.seed
    )
    path = write_real_buyer_holdout(ROOT, table)
    OUT_TABLES.mkdir(parents=True, exist_ok=True)

    summary = summarise_split(table)
    summary.to_csv(OUT_TABLES / "holdout_coverage.csv", index=False)

    n_cal = int(table["split"].eq(CALIBRATION).sum())
    n_hold = int(table["split"].eq(HOLDOUT).sum())
    notices_cal = int(table.loc[table["split"].eq(CALIBRATION), "n_notices"].sum())
    notices_hold = int(table.loc[table["split"].eq(HOLDOUT), "n_notices"].sum())
    provenance = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": VERSION,
        "split_unit": "buyer_key",
        "holdout_fraction_target": args.holdout_fraction,
        "split_seed": args.seed,
        "path": str(HOLDOUT_RELATIVE_PATH),
        "content_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "n_buyer_keys_total": int(len(table)),
        "n_buyer_keys_calibration": n_cal,
        "n_buyer_keys_holdout": n_hold,
        "realized_holdout_key_share": n_hold / len(table) if len(table) else None,
        "n_notices_calibration": notices_cal,
        "n_notices_holdout": notices_hold,
        "realized_holdout_notice_share": (
            notices_hold / (notices_cal + notices_hold) if (notices_cal + notices_hold) else None
        ),
        "n_strata": int(table["stratum"].nunique()),
        "note": (
            "Calibration side estimates every observable generator parameter. The holdout side "
            "is read once, at fresh-seed evaluation. Notice shares differ from key shares because "
            "buyer activity is heavy-tailed; holdout metrics are therefore scale-free."
        ),
    }
    (OUT_TABLES / "holdout_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )

    print(f"wrote {path}")
    print(
        f"keys: {n_cal} calibration / {n_hold} holdout "
        f"({provenance['realized_holdout_key_share']:.3f})"
    )
    print(
        f"notices: {notices_cal} calibration / {notices_hold} holdout "
        f"({provenance['realized_holdout_notice_share']:.3f})"
    )
    worst = summary.dropna(subset=["holdout_key_share"]).nlargest(3, "holdout_key_share")
    print("largest per-level holdout key shares:")
    print(worst[["dimension", "level", "n_keys_calibration", "n_keys_holdout", "holdout_key_share"]])


if __name__ == "__main__":
    main()
