"""Semi-synthetic corruption / recovery test (extracted from eval_m4).

For each strict-tier link, the SOURCE notice's CPV / text / duration fields
are corrupted at increasing severity and rescored against the same fixed real
candidate pool. Recovery = the true candidate stays arg-max AND still clears
the balanced threshold. R(0) must equal 1.0 for every sweep (sanity gate:
the rescoring reproduces the real pipeline on uncorrupted data).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from boamp.linkage.scoring import build_tfidf_matrix, cpv_pair_score

SEVERITY_LEVELS = [0, 1, 2, 3]
SWEEPS = ["text_only", "cpv_only", "duration_only", "combined"]


def corrupt_cpv(cpv_main: str, level: int) -> str:
    if not isinstance(cpv_main, str) or len(cpv_main) != 8:
        return cpv_main
    if level == 0:
        return cpv_main
    keep = {1: 5, 2: 4, 3: 2}[level]
    return cpv_main[:keep] + "0" * (8 - keep)


def cpv_hierarchy(cpv_main):
    if not isinstance(cpv_main, str) or len(cpv_main) != 8:
        return (np.nan, np.nan, np.nan, np.nan)
    return cpv_main[0:2], cpv_main[0:3], cpv_main[0:4], cpv_main[0:5]


def corrupt_duration(duration_months: float, cpv_division_original, division_medians: pd.Series,
                     global_median: float, level: int) -> float:
    if pd.isna(duration_months) or level == 0:
        return duration_months
    # round half up (not banker's rounding): round(6/12)*12 would map the
    # 6-month median to 0 - an artificial cliff exactly on this corpus.
    if level == 1:
        return max(1.0, math.floor(duration_months / 6.0 + 0.5) * 6.0)
    if level == 2:
        return max(1.0, math.floor(duration_months / 12.0 + 0.5) * 12.0)
    med = division_medians.get(cpv_division_original, np.nan)
    return med if pd.notna(med) else global_median


def corrupt_text(text: str, level: int) -> str:
    if not isinstance(text, str) or not text.strip():
        return text
    tokens = text.split()
    if level == 0:
        return text
    frac = {1: 0.66, 2: 0.33, 3: 0.10}[level]
    keep_n = max(min(3, len(tokens)), int(round(len(tokens) * frac)))
    return " ".join(tokens[:keep_n])


def run_corruption_recovery(sources: pd.DataFrame, pairs: pd.DataFrame,
                            strict_links: pd.DataFrame, balanced_threshold: float,
                            window: int, cfg, verbose: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (per_pair_scores, recovery_by_severity, recovery_summary)."""
    p = cfg.pipeline
    month_days = p.run.month_days
    w = p.scoring.weights
    buyer_type_score = vars(p.buyer_score.boamp_only)

    sources_idx = sources.set_index("notice_id")

    eligible = sources[sources["buyer_key_type"] != "MISSING"].copy()
    eligible = eligible.sort_values(["buyer_key", "publication_date"]).reset_index(drop=True)
    vectorizer, tfidf = build_tfidf_matrix(eligible["objet_clean"].fillna("").tolist(), cfg)
    notice_to_row = {nid: i for i, nid in enumerate(eligible["notice_id"])}

    obs = sources.loc[~sources["dur_was_imputed"].astype(bool), ["cpv_division", "declared_duration_months"]]
    division_medians = obs.groupby("cpv_division")["declared_duration_months"].median()
    global_median = obs["declared_duration_months"].median()

    audit_rows, recovery_records = [], []
    for _, s_row in strict_links.iterrows():
        source_id = s_row["source_notice_id"]
        true_candidate_id = s_row["candidate_notice_id"]
        src = sources_idx.loc[source_id]
        pool = pairs[pairs["source_notice_id"] == source_id]
        if true_candidate_id not in pool["candidate_notice_id"].values:
            raise ValueError(f"true candidate {true_candidate_id} missing from real pool of {source_id}")

        s_buyer = buyer_type_score.get(src["buyer_key_type"], 0.0)
        cpv_main_orig = src["cpv_clean"] if pd.notna(src["cpv_clean"]) else None
        cpv_division_orig = src["cpv_division"] if pd.notna(src["cpv_division"]) else None

        for sweep in SWEEPS:
            for level in SEVERITY_LEVELS:
                cpv_level = level if sweep in ("cpv_only", "combined") else 0
                dur_level = level if sweep in ("duration_only", "combined") else 0
                text_level = level if sweep in ("text_only", "combined") else 0

                corrupted_cpv_main = corrupt_cpv(cpv_main_orig, cpv_level)
                src_div, src_grp, src_cls, src_cat = cpv_hierarchy(corrupted_cpv_main)

                corrupted_duration = corrupt_duration(
                    src["declared_duration_months"], cpv_division_orig,
                    division_medians, global_median, dur_level)
                if pd.notna(src["start_date"]) and pd.notna(corrupted_duration):
                    corrupted_end_date = src["start_date"] + relativedelta(months=int(round(corrupted_duration)))
                else:
                    corrupted_end_date = src["estimated_end_date"]

                corrupted_text = corrupt_text(src["objet_clean"], text_level)
                corrupted_vec = vectorizer.transform(
                    [corrupted_text if isinstance(corrupted_text, str) else ""])

                scored = []
                for _, cand in pool.iterrows():
                    cand_id = cand["candidate_notice_id"]
                    cand_row = sources_idx.loc[cand_id]
                    cand_main = cand_row["cpv_clean"] if pd.notna(cand_row["cpv_clean"]) else None
                    cand_div, cand_grp, cand_cls, cand_cat = cpv_hierarchy(cand_main)
                    s_cpv = cpv_pair_score(
                        corrupted_cpv_main, cand_main, src_cat, cand_cat, src_cls, cand_cls,
                        src_grp, cand_grp, src_div, cand_div, p.cpv_score)
                    abs_gap = abs((cand_row["publication_date"] - corrupted_end_date).total_seconds()) \
                        / 86400.0 / month_days
                    s_time = max(0.0, 1.0 - abs_gap / window)
                    s_text = float(corrupted_vec.dot(tfidf[notice_to_row[cand_id]].T).toarray().ravel()[0])
                    composite = w.text * s_text + w.cpv * s_cpv + w.time * s_time + w.buyer * s_buyer
                    scored.append({"candidate_notice_id": cand_id, "s_text": s_text, "s_cpv": s_cpv,
                                   "s_time": s_time, "s_buyer": s_buyer, "composite": composite})

                scored_df = pd.DataFrame(scored).sort_values(
                    ["composite", "candidate_notice_id"], ascending=[False, True])
                arg_max_id = scored_df.iloc[0]["candidate_notice_id"]
                true_row = scored_df[scored_df["candidate_notice_id"] == true_candidate_id].iloc[0]
                recovered = bool(arg_max_id == true_candidate_id
                                 and true_row["composite"] >= balanced_threshold)

                audit_rows.append({
                    "source_notice_id": source_id, "candidate_notice_id": true_candidate_id,
                    "sweep": sweep, "severity": level,
                    "s_text": true_row["s_text"], "s_cpv": true_row["s_cpv"],
                    "s_time": true_row["s_time"], "s_buyer": true_row["s_buyer"],
                    "composite": true_row["composite"],
                    "is_arg_max": arg_max_id == true_candidate_id,
                    "clears_balanced_threshold": true_row["composite"] >= balanced_threshold,
                    "recovered": recovered,
                })
                recovery_records.append({"sweep": sweep, "severity": level,
                                         "source_notice_id": source_id, "recovered": recovered})

    audit_df = pd.DataFrame(audit_rows)
    rec_df = pd.DataFrame(recovery_records)
    by_sev = (rec_df.groupby(["sweep", "severity"])["recovered"]
              .agg(n_recovered="sum", n_total="count").reset_index())
    by_sev["R"] = by_sev["n_recovered"] / by_sev["n_total"]

    r0 = by_sev[by_sev["severity"] == 0]
    if not np.isclose(r0["R"], 1.0).all():
        raise RuntimeError(
            "R(0) != 1.0 for at least one sweep - the rescoring does not reproduce "
            "the real pipeline on uncorrupted data; fix before trusting L1-L3.")
    if verbose:
        print("Sanity gate passed: R(0) == 1.0 for every sweep.")

    pivot = by_sev.pivot(index="sweep", columns="severity", values="R")
    summary = pd.DataFrame([
        {"sweep": sweep, "R0": pivot.loc[sweep, 0], "R1": pivot.loc[sweep, 1],
         "R2": pivot.loc[sweep, 2], "R3": pivot.loc[sweep, 3],
         "delta_R": pivot.loc[sweep, 0] - pivot.loc[sweep, 3]}
        for sweep in SWEEPS
    ]).sort_values("delta_R", ascending=False)
    return audit_df, by_sev, summary
