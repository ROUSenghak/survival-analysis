"""
Step 12 - Method 4: semi-synthetic corruption / recovery test.

Input:  data/processed/boamp_m0_sources.csv
        data/processed/boamp_m0_candidate_pairs.csv
        data/processed/boamp_m0_links_strict.csv
        data/processed/_m0_window_months.txt
        reports/tables/m0_method_summary.csv
Output: data/processed/m4_corrupted_pair_scores.csv
        reports/tables/m4_recovery_by_severity.csv
        reports/tables/m4_recovery_summary.csv

S* = the 309 strict-variant links (already the highest-confidence real
subset by construction - 75th percentile of the rank-1 composite-score
distribution - so no new, arbitrary "top quartile" cut needs to be
invented).

For each pair in S*, the SOURCE notice's fields are corrupted at
increasing severity (0 = none, 3 = most severe) and rescored against the
SAME fixed real candidate pool that source already had in
boamp_m0_candidate_pairs.csv (no re-blocking, no synthetic distractors -
"genuinely real high-confidence pairs" per the method's own goal). Only
CPV, contract-object text, and duration are corrupted; there is no amount
field anywhere in this schema, and buyer-key reliability (s_buyer) is not
a falsifiable data-quality field in the same sense, so neither is
corrupted (documented scope exclusions).

Recovery: the true candidate is "recovered" at a given severity if it is
still the arg-max composite score in its (fixed) pool AND its composite
score still clears the real `balanced` threshold - the operative
definition of "still linked" in the real pipeline (only candidate_rank==1
pairs are ever eligible to be linked at all).
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from sklearn.feature_extraction.text import TfidfVectorizer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_m0_candidate_pairs as bmcp  # noqa: E402  (reuse cpv_pair_score, weights, constants)

SEVERITY_LEVELS = [0, 1, 2, 3]
SWEEPS = ["text_only", "cpv_only", "duration_only", "combined"]


def corrupt_cpv(cpv_main: str, level: int) -> str:
    """L1: keep 5 digits (category-level); L2: keep 4 (class-level);
    L3: keep 2 (division-level) - identical pattern to the real
    cpv_generic_flag definition (XX000000)."""
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
    """L1: round to nearest 6-month bucket; L2: nearest 12-month bucket;
    L3: replace with the division-level median of OBSERVED (non-imputed)
    durations, computed exactly as preprocess_boamp_m0.py does (falls back
    to the global observed median) - i.e. "treat this row as if its
    duration had been missing and impute it the standard pipeline way",
    directly grounded in the real 88.03% imputation rate for this
    population. The lookup uses the source's ORIGINAL (pre-corruption)
    cpv_division, matching how the real pipeline's imputation actually
    used the true division, not a hypothetically-also-corrupted one."""
    if pd.isna(duration_months):
        return duration_months
    if level == 0:
        return duration_months
    # "round half up" (not Python's banker's round-half-to-even), since
    # round(x/bucket)*bucket silently maps x == 0.5*bucket down to 0 for
    # even quotients (e.g. round(6/12)*12 == 0, not 12) - an artificial
    # cliff landing exactly on this population's 6-month median duration.
    if level == 1:
        return max(1.0, math.floor(duration_months / 6.0 + 0.5) * 6.0)
    if level == 2:
        return max(1.0, math.floor(duration_months / 12.0 + 0.5) * 12.0)
    # level == 3
    med = division_medians.get(cpv_division_original, np.nan)
    return med if pd.notna(med) else global_median


def corrupt_text(text: str, level: int) -> str:
    """Keep first 66% / 33% / 10% of whitespace tokens (minimum 3 tokens
    unless the source text itself has fewer)."""
    if not isinstance(text, str) or not text.strip():
        return text
    tokens = text.split()
    if level == 0:
        return text
    frac = {1: 0.66, 2: 0.33, 3: 0.10}[level]
    keep_n = max(min(3, len(tokens)), int(round(len(tokens) * frac)))
    return " ".join(tokens[:keep_n])


def main():
    print("Loading sources, candidate pairs, strict links, thresholds, window...")
    sources = pd.read_csv(
        PROCESSED_DIR / "boamp_m0_sources.csv",
        dtype={"cpv_clean": str, "cpv_division": str, "cpv_group": str,
               "cpv_class": str, "cpv_category": str, "buyer_key_type": str},
        parse_dates=["publication_date", "start_date", "estimated_end_date", "study_end_date"],
    )
    pairs = pd.read_csv(PROCESSED_DIR / "boamp_m0_candidate_pairs.csv",
                         parse_dates=["source_date", "candidate_date", "expected_end_date"])
    strict_links = pd.read_csv(PROCESSED_DIR / "boamp_m0_links_strict.csv")
    method_summary = pd.read_csv(TABLES_DIR / "m0_method_summary.csv")
    balanced_threshold = method_summary.loc[
        method_summary["variant"] == "balanced", "threshold_composite_score"
    ].iloc[0]
    window = int((PROCESSED_DIR / "_m0_window_months.txt").read_text().strip())
    print(f"S* (strict links): {len(strict_links)} pairs")
    print(f"Real balanced threshold: {balanced_threshold:.6f}, temporal window: {window} months")

    sources_idx = sources.set_index("notice_id")

    # ---- re-derive the exact same eligible corpus / TF-IDF fit used by
    # build_m0_candidate_pairs.py, so .transform() on corrupted text is
    # scored on an identical vector space to the real pipeline ----
    eligible = sources[sources["buyer_key_type"] != "MISSING"].copy()
    eligible = eligible.sort_values(["buyer_key", "publication_date"]).reset_index(drop=True)
    texts = eligible["objet_clean"].fillna("").tolist()
    vectorizer = TfidfVectorizer(max_features=50000, ngram_range=(1, 2), min_df=2)
    tfidf = vectorizer.fit_transform(texts)
    notice_to_row = {nid: i for i, nid in enumerate(eligible["notice_id"])}

    # ---- division-level observed-duration medians, exactly as
    # preprocess_boamp_m0.py computes them (digital + PdL APPEL_OFFRE
    # population, i.e. this same `sources` table, non-imputed rows only) ----
    obs = sources.loc[~sources["dur_was_imputed"], ["cpv_division", "declared_duration_months"]]
    division_medians = obs.groupby("cpv_division")["declared_duration_months"].median()
    global_median = obs["declared_duration_months"].median()

    W_TEXT, W_CPV, W_TIME, W_BUYER = bmcp.W_TEXT, bmcp.W_CPV, bmcp.W_TIME, bmcp.W_BUYER

    audit_rows = []
    recovery_records = []

    for _, s_row in strict_links.iterrows():
        source_id = s_row["source_notice_id"]
        true_candidate_id = s_row["candidate_notice_id"]
        src = sources_idx.loc[source_id]
        pool = pairs[pairs["source_notice_id"] == source_id]
        if true_candidate_id not in pool["candidate_notice_id"].values:
            raise ValueError(f"true candidate {true_candidate_id} missing from real pool of {source_id}")

        s_buyer = bmcp.BUYER_KEY_TYPE_SCORE.get(src["buyer_key_type"], 0.0)
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
                    division_medians, global_median, dur_level,
                )
                if pd.notna(src["start_date"]) and pd.notna(corrupted_duration):
                    corrupted_end_date = src["start_date"] + relativedelta(
                        months=int(round(corrupted_duration)))
                else:
                    corrupted_end_date = src["estimated_end_date"]

                corrupted_text = corrupt_text(src["objet_clean"], text_level)
                corrupted_vec = vectorizer.transform([corrupted_text if isinstance(corrupted_text, str) else ""])

                scored = []
                for _, cand in pool.iterrows():
                    cand_id = cand["candidate_notice_id"]
                    cand_row = sources_idx.loc[cand_id]

                    cand_main = cand_row["cpv_clean"] if pd.notna(cand_row["cpv_clean"]) else None
                    cand_div, cand_grp, cand_cls, cand_cat = cpv_hierarchy(cand_main)
                    s_cpv = bmcp.cpv_pair_score(
                        corrupted_cpv_main, cand_main,
                        src_cat, cand_cat, src_cls, cand_cls,
                        src_grp, cand_grp, src_div, cand_div,
                    )

                    abs_gap = abs((cand_row["publication_date"] - corrupted_end_date).total_seconds()) \
                        / 86400.0 / 30.44
                    s_time = max(0.0, 1.0 - abs_gap / window)

                    cand_tfidf_row = notice_to_row[cand_id]
                    s_text = float(corrupted_vec.dot(tfidf[cand_tfidf_row].T).toarray().ravel()[0])

                    composite = W_TEXT * s_text + W_CPV * s_cpv + W_TIME * s_time + W_BUYER * s_buyer
                    scored.append({
                        "candidate_notice_id": cand_id, "s_text": s_text, "s_cpv": s_cpv,
                        "s_time": s_time, "s_buyer": s_buyer, "composite": composite,
                    })

                scored_df = pd.DataFrame(scored).sort_values(
                    ["composite", "candidate_notice_id"], ascending=[False, True])
                arg_max_id = scored_df.iloc[0]["candidate_notice_id"]
                true_row = scored_df[scored_df["candidate_notice_id"] == true_candidate_id].iloc[0]
                recovered = bool(arg_max_id == true_candidate_id and
                                  true_row["composite"] >= balanced_threshold)

                audit_rows.append({
                    "source_notice_id": source_id, "candidate_notice_id": true_candidate_id,
                    "sweep": sweep, "severity": level,
                    "s_text": true_row["s_text"], "s_cpv": true_row["s_cpv"],
                    "s_time": true_row["s_time"], "s_buyer": true_row["s_buyer"],
                    "composite": true_row["composite"], "is_arg_max": arg_max_id == true_candidate_id,
                    "clears_balanced_threshold": true_row["composite"] >= balanced_threshold,
                    "recovered": recovered,
                })
                recovery_records.append({
                    "sweep": sweep, "severity": level, "source_notice_id": source_id,
                    "recovered": recovered,
                })

    audit_df = pd.DataFrame(audit_rows)
    audit_df.to_csv(PROCESSED_DIR / "m4_corrupted_pair_scores.csv", index=False)
    print(f"Wrote {PROCESSED_DIR / 'm4_corrupted_pair_scores.csv'} ({len(audit_df)} rows)")

    rec_df = pd.DataFrame(recovery_records)
    by_sev = (
        rec_df.groupby(["sweep", "severity"])["recovered"]
        .agg(n_recovered="sum", n_total="count")
        .reset_index()
    )
    by_sev["R"] = by_sev["n_recovered"] / by_sev["n_total"]
    by_sev.to_csv(TABLES_DIR / "m4_recovery_by_severity.csv", index=False)
    print(f"Wrote {TABLES_DIR / 'm4_recovery_by_severity.csv'}")

    # ---- hard sanity gate ----
    r0 = by_sev[by_sev["severity"] == 0]
    print("\nR(0) by sweep (must all be 1.0):")
    print(r0[["sweep", "R"]].to_string(index=False))
    if not np.isclose(r0["R"], 1.0).all():
        raise RuntimeError(
            "R(0) != 1.0 for at least one sweep - rescoring logic does not reproduce "
            "the real pipeline's behavior on uncorrupted data. Fix before trusting L1-L3."
        )
    print("Sanity gate passed: R(0) == 1.0 for every sweep.")

    pivot = by_sev.pivot(index="sweep", columns="severity", values="R")
    print("\nRecovery R(level) by sweep:")
    print(pivot.to_string())
    monotonic_ok = (pivot.diff(axis=1).iloc[:, 1:] <= 1e-9).all(axis=1).all()
    if not monotonic_ok:
        print("WARNING: R(level) is not monotonically non-increasing for at least one "
              "sweep - inspect m4_recovery_by_severity.csv, this should not happen "
              "since more corruption should never help recovery.")

    summary_rows = []
    for sweep in SWEEPS:
        row = pivot.loc[sweep]
        summary_rows.append({
            "sweep": sweep, "R0": row[0], "R1": row[1], "R2": row[2], "R3": row[3],
            "delta_R": row[0] - row[3],
        })
    summary_df = pd.DataFrame(summary_rows).sort_values("delta_R", ascending=False)
    summary_df.to_csv(TABLES_DIR / "m4_recovery_summary.csv", index=False)
    print(f"\nWrote {TABLES_DIR / 'm4_recovery_summary.csv'}")
    print(summary_df.to_string(index=False))
    print(f"\nDominant breaking-point field (steepest R0->R3 drop, excluding 'combined'): "
          f"{summary_df[summary_df.sweep != 'combined'].iloc[0]['sweep']}")


if __name__ == "__main__":
    main()
