"""
Step 7 - Build M0 candidate pairs for procurement recurrence.

Input:  data/processed/boamp_m0_sources.csv
Output: data/processed/boamp_m0_candidate_pairs.csv

Candidate generation rule (deterministic, no external enrichment):
  - same buyer_key (buyer_key_type != MISSING)
  - candidate is a different APPEL_OFFRE notice from the same buyer,
    published strictly after the source notice
  - within a temporal window around the source's estimated_end_date
    (see TEMPORAL_WINDOW_MONTHS below - derived from the observed duration
    distribution, not a fixed guess)

Text similarity: TF-IDF + cosine similarity (scikit-learn), chosen over
sentence-transformer embeddings because of corpus size and CPU-only runtime
(see requirements.txt and reports/boamp_m0_preprocessing_report.md).

CPV similarity: transparent hierarchy score (exact / category / class /
group / division / different / missing).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
TABLES_DIR.mkdir(parents=True, exist_ok=True)

# Candidate-generation temporal net: generous window used to decide which
# pairs are even considered (see run_log.md for derivation of the value
# actually used at runtime; this constant is a cap only, refined below).
MAX_WINDOW_MONTHS_CAP = 24
MIN_WINDOW_MONTHS_FLOOR = 6

# CPV hierarchy score rungs (documented, transparent; "missing" treated as
# weak-neutral evidence, distinct from - and higher than - a confirmed
# CPV mismatch, since it reflects absence of information rather than proof
# the two notices differ).
CPV_SCORE_EXACT = 1.0
CPV_SCORE_CATEGORY = 0.8
CPV_SCORE_CLASS = 0.6
CPV_SCORE_GROUP = 0.4
CPV_SCORE_DIVISION = 0.2
CPV_SCORE_DIFFERENT = 0.0
CPV_SCORE_MISSING = 0.1

# buyer_key_type reliability weighting for s_buyer (candidate generation
# already restricts to matching buyer_key; this score instead reflects how
# trustworthy that match is).
BUYER_KEY_TYPE_SCORE = {
    "RAW_SIRET": 1.0,
    "RAW_SIREN": 0.85,
    "NAME_FALLBACK": 0.6,
}

# Composite weights (documented rationale in the report): text and CPV are
# the primary content-based recurrence signals; time anchors the match
# around the expected contract end; buyer agreement mostly discounts
# low-confidence name-only matches since generation already conditions on
# buyer_key equality.
W_TEXT, W_CPV, W_TIME, W_BUYER = 0.35, 0.30, 0.25, 0.10


def months_between(d1, d2):
    return (d2 - d1).dt.total_seconds() / (3600 * 24 * 30.44)


def cpv_pair_score(src_main, cand_main, src_cat, cand_cat, src_cls, cand_cls,
                    src_grp, cand_grp, src_div, cand_div):
    if pd.isna(src_main) or pd.isna(cand_main):
        return CPV_SCORE_MISSING
    if src_main == cand_main:
        return CPV_SCORE_EXACT
    if src_cat == cand_cat:
        return CPV_SCORE_CATEGORY
    if src_cls == cand_cls:
        return CPV_SCORE_CLASS
    if src_grp == cand_grp:
        return CPV_SCORE_GROUP
    if src_div == cand_div:
        return CPV_SCORE_DIVISION
    return CPV_SCORE_DIFFERENT


def main():
    print("Loading M0 source population...")
    # CPV/SIRET/SIREN columns are numeric-looking strings with NaNs; force
    # dtype=str so pandas doesn't silently coerce them to float64 (which
    # would break the `==` / `.str[...]`-free comparisons used below).
    str_cols = ["notice_id", "buyer_key", "buyer_key_type", "buyer_name_normalized",
                "buyer_siret_clean", "buyer_siren_clean", "objet_clean",
                "cpv_clean", "cpv_division", "cpv_category", "cpv_class", "cpv_group",
                "category_label"]
    src = pd.read_csv(PROCESSED_DIR / "boamp_m0_sources.csv",
                       dtype={c: str for c in str_cols},
                       parse_dates=["publication_date", "start_date", "estimated_end_date", "study_end_date"])
    print(f"Loaded {len(src)} APPEL_OFFRE source rows")

    eligible = src[src["buyer_key_type"] != "MISSING"].copy()
    eligible = eligible.sort_values(["buyer_key", "publication_date"]).reset_index(drop=True)
    print(f"Eligible (non-missing buyer_key) sources: {len(eligible)}")

    # --- derive the temporal window from the observed duration distribution ---
    dur = eligible.loc[~eligible["dur_was_imputed"], "declared_duration_months"].dropna()
    median_dur = dur.median() if len(dur) else eligible["declared_duration_months"].median()
    window = int(np.clip(round(median_dur * 0.5), MIN_WINDOW_MONTHS_FLOOR, MAX_WINDOW_MONTHS_CAP))
    print(f"Observed (non-imputed) duration median: {median_dur:.1f} months")
    print(f"TEMPORAL_WINDOW_MONTHS derived as clip(0.5 * median_duration, "
          f"{MIN_WINDOW_MONTHS_FLOOR}, {MAX_WINDOW_MONTHS_CAP}) = {window}")

    # --- TF-IDF over all eligible source texts (also serves as the candidate pool) ---
    texts = eligible["objet_clean"].fillna("").tolist()
    vectorizer = TfidfVectorizer(max_features=50000, ngram_range=(1, 2), min_df=2)
    tfidf = vectorizer.fit_transform(texts)
    print(f"TF-IDF matrix: {tfidf.shape}")

    # Practical cap on candidates scored per source. Large, high-frequency
    # buyers (e.g. metropolitan authorities publishing dozens of unrelated
    # tenders a month) can have hundreds of notices falling inside the
    # temporal window; only the temporally-nearest MAX_CANDIDATES_PER_SOURCE
    # are scored. This bounds runtime/memory and does not bias which
    # candidate is eventually linked, since ranking is dominated by
    # text/CPV/time score, not by how many low-relevance candidates were
    # also considered - but it is a real, documented scope limitation (see
    # reports/boamp_m0_preprocessing_report.md).
    MAX_CANDIDATES_PER_SOURCE = 30

    notice_ids = eligible["notice_id"].to_numpy()
    pub_dates_all = eligible["publication_date"].to_numpy()
    end_dates_all = eligible["estimated_end_date"].to_numpy()
    cpv_main_all = eligible["cpv_clean"].to_numpy(dtype=object)
    cpv_cat_all = eligible["cpv_category"].to_numpy(dtype=object)
    cpv_cls_all = eligible["cpv_class"].to_numpy(dtype=object)
    cpv_grp_all = eligible["cpv_group"].to_numpy(dtype=object)
    cpv_div_all = eligible["cpv_division"].to_numpy(dtype=object)
    cpv_generic_all = eligible["cpv_generic_flag"].to_numpy()
    buyer_key_type_all = eligible["buyer_key_type"].to_numpy(dtype=object)
    buyer_key_all = eligible["buyer_key"].to_numpy(dtype=object)

    window_td = np.timedelta64(int(round(window * 30.44)), "D")

    records = []
    group_indices = eligible.groupby("buyer_key", sort=False).indices  # buyer_key -> positional index array
    n_groups = len(group_indices)
    print(f"Processing {n_groups} buyer groups...")

    for gi, (buyer_key, idx) in enumerate(group_indices.items()):
        n = len(idx)
        if n < 2:
            continue
        idx = np.asarray(idx)
        # idx is already date-sorted (eligible was pre-sorted by buyer_key, publication_date)
        g_pub = pub_dates_all[idx]
        g_end = end_dates_all[idx]

        for i in range(n):
            expected_end = g_end[i]
            if pd.isna(expected_end):
                continue
            src_date = g_pub[i]
            lo = expected_end - window_td
            hi = expected_end + window_td
            # binary search on the sorted publication-date array for [lo, hi]
            left = np.searchsorted(g_pub, lo, side="left")
            right = np.searchsorted(g_pub, hi, side="right")
            if right <= left:
                continue
            cand_local = np.arange(left, right)
            cand_local = cand_local[(g_pub[cand_local] > src_date) & (cand_local != i)]
            if len(cand_local) == 0:
                continue

            cand_global = idx[cand_local]
            i_global = idx[i]

            abs_gap_arr = np.abs((g_pub[cand_local] - expected_end)) / np.timedelta64(1, "D") / 30.44
            if len(cand_local) > MAX_CANDIDATES_PER_SOURCE:
                keep = np.argsort(abs_gap_arr)[:MAX_CANDIDATES_PER_SOURCE]
                cand_local = cand_local[keep]
                cand_global = cand_global[keep]
                abs_gap_arr = abs_gap_arr[keep]

            gap_months_arr = (g_pub[cand_local] - src_date) / np.timedelta64(1, "D") / 30.44
            s_time_arr = np.clip(1.0 - abs_gap_arr / window, 0.0, None)

            # batched sparse similarity: one sparse matrix-vector product per source
            sims = tfidf[cand_global].dot(tfidf[i_global].T).toarray().ravel()

            src_cpv_main, src_cpv_cat = cpv_main_all[i_global], cpv_cat_all[i_global]
            src_cpv_cls, src_cpv_grp, src_cpv_div = cpv_cls_all[i_global], cpv_grp_all[i_global], cpv_div_all[i_global]
            src_generic = bool(cpv_generic_all[i_global])
            bkt = buyer_key_type_all[i_global]
            s_buyer = BUYER_KEY_TYPE_SCORE.get(bkt, 0.0)

            for k, cg in enumerate(cand_global):
                s_cpv = cpv_pair_score(
                    src_cpv_main, cpv_main_all[cg],
                    src_cpv_cat, cpv_cat_all[cg],
                    src_cpv_cls, cpv_cls_all[cg],
                    src_cpv_grp, cpv_grp_all[cg],
                    src_cpv_div, cpv_div_all[cg],
                )
                s_text = float(sims[k])
                composite = W_TEXT * s_text + W_CPV * s_cpv + W_TIME * s_time_arr[k] + W_BUYER * s_buyer
                records.append({
                    "source_notice_id": notice_ids[i_global],
                    "candidate_notice_id": notice_ids[cg],
                    "source_date": src_date,
                    "candidate_date": g_pub[cand_local[k]],
                    "buyer_key": buyer_key,
                    "buyer_key_type": bkt,
                    "gap_months": gap_months_arr[k],
                    "expected_end_date": expected_end,
                    "abs_gap_to_expected_end": abs_gap_arr[k],
                    "s_time": s_time_arr[k],
                    "s_text": s_text,
                    "s_cpv": s_cpv,
                    "s_buyer": s_buyer,
                    "m0_composite_score": composite,
                    "cpv_missing": bool(pd.isna(src_cpv_main) or pd.isna(cpv_main_all[cg])),
                    "cpv_generic_flag": bool(src_generic or cpv_generic_all[cg]),
                })

        if gi % 2000 == 0:
            print(f"  ...{gi}/{n_groups} buyer groups processed, {len(records)} pairs so far", flush=True)

    pairs = pd.DataFrame.from_records(records)
    print(f"\nGenerated {len(pairs)} raw candidate pairs")

    if len(pairs):
        pairs = pairs.sort_values(["source_notice_id", "m0_composite_score"], ascending=[True, False])
        pairs["candidate_rank"] = pairs.groupby("source_notice_id").cumcount() + 1
        pairs["n_candidates_for_source"] = pairs.groupby("source_notice_id")["candidate_notice_id"].transform("count")

        top2 = (
            pairs[pairs["candidate_rank"] <= 2]
            .pivot(index="source_notice_id", columns="candidate_rank", values="m0_composite_score")
        )
        margin = (top2.get(1) - top2.get(2)).fillna(top2.get(1))
        pairs["top1_top2_margin"] = pairs["source_notice_id"].map(margin)

    out_path = PROCESSED_DIR / "boamp_m0_candidate_pairs.csv"
    pairs.to_csv(out_path, index=False)
    print(f"Wrote candidate pairs -> {out_path}")

    n_sources_with_candidates = pairs["source_notice_id"].nunique() if len(pairs) else 0
    print("\n=== Candidate pair summary ===")
    print(f"TEMPORAL_WINDOW_MONTHS used: {window}")
    print(f"Eligible sources: {len(eligible)}")
    print(f"Sources with >=1 candidate: {n_sources_with_candidates}")
    print(f"Total candidate pairs: {len(pairs)}")
    if len(pairs):
        print(pairs["m0_composite_score"].describe())

    # Persist the derived window for downstream scripts/report to reuse.
    with open(PROCESSED_DIR / "_m0_window_months.txt", "w") as f:
        f.write(str(window))


if __name__ == "__main__":
    main()
