"""Analyze completed BOAMP manual-validation labels.

Input should be the completed reviewer file produced by
reports/tables/final_blinded_single_reviewer_sample.csv. This script keeps
credible, likely-not, and uncertain/insufficient labels separate and does not
call accepted-link precision "accuracy".
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"

POSITIVE = {"credible_recurrence", "credible"}
NEGATIVE = {"likely_not_recurrence", "not_recurrence"}
UNCERTAIN = {"uncertain", "insufficient_evidence"}


def norm_label(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def summarize(group: pd.DataFrame, label: str) -> dict:
    labels = group["reviewer_label_normalized"]
    c = int(labels.isin(POSITIVE).sum())
    n = int(labels.isin(NEGATIVE).sum())
    u = int(labels.isin(UNCERTAIN).sum())
    total = c + n + u
    decided = c + n
    lo, hi = proportion_confint(c, decided, method="wilson") if decided else (np.nan, np.nan)
    return {
        "breakdown": label,
        "n_reviewed": total,
        "credible": c,
        "likely_not": n,
        "uncertain_or_insufficient": u,
        "p_decided": c / decided if decided else np.nan,
        "p_decided_ci_low": lo,
        "p_decided_ci_high": hi,
        "p_lower": c / total if total else np.nan,
        "p_upper": (c + u) / total if total else np.nan,
        "uncertainty_rate": u / total if total else np.nan,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default=str(TABLES / "final_blinded_single_reviewer_sample.csv"))
    parser.add_argument("--join", default=str(TABLES / "final_validation_technical_join_table.csv"))
    parser.add_argument("--out", default=str(TABLES / "final_manual_validation_label_analysis.csv"))
    args = parser.parse_args()

    labels = pd.read_csv(args.labels, dtype=str)
    if "reviewer_label" not in labels.columns:
        raise SystemExit("Missing reviewer_label column")
    labels["reviewer_label_normalized"] = labels["reviewer_label"].map(norm_label)
    completed = labels[labels["reviewer_label_normalized"].isin(POSITIVE | NEGATIVE | UNCERTAIN)].copy()
    if completed.empty:
        pd.DataFrame([{"breakdown": "overall", "n_reviewed": 0, "note": "no completed labels"}]).to_csv(args.out, index=False)
        return

    rows = [summarize(completed, "overall")]
    if Path(args.join).exists():
        join = pd.read_csv(args.join, dtype=str)
        completed = completed.merge(join, on=["validation_case_id", "source_notice_id", "candidate_notice_id"], how="left")
    for col in [
        "validation_stratum",
        "buyer_match_mechanism",
        "profile_evidence_status",
        "candidate_rank",
        "variant",
    ]:
        if col in completed.columns:
            for value, grp in completed.groupby(col, dropna=False):
                rows.append(summarize(grp, f"{col}={value}"))
    pd.DataFrame(rows).to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
