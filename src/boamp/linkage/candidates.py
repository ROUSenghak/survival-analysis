"""Candidate-pair generation for both layers.

Layer 1 (generate_pairs_single_key): blocking on ONE buyer-key column
(buyer_key) - extracted verbatim from scripts/build_m0_candidate_pairs.py.

Layer 2 (generate_pairs_mechanisms): multi-mechanism blocking (exact SIRET,
same Layer 2 SIREN, historical alias, Layer 1 name fallback) - extracted from
scripts/build_m1_buyer_siren_experiment.py.

Both use the SAME temporal window, TF-IDF settings, CPV ladder, temporal
score, composite weights, and per-source candidate cap (all from cfg), so the
controlled difference between layers is the blocking identity only. The
output score column is named `composite_score` in both layers.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from boamp.linkage.scoring import (
    add_rank_and_margin,
    build_tfidf_matrix,
    cpv_pair_score,
    estimate_window_months,
)


def generate_pairs_single_key(sources: pd.DataFrame, cfg, verbose: bool = True,
                              window_override: int | None = None) -> tuple[pd.DataFrame, int]:
    """Layer 1 candidate generation. Returns (pairs, window_months).

    window_override forces a specific temporal window (used by the
    window-sensitivity sweep in 03_analysis); otherwise the window is
    derived from the observed duration distribution.
    """
    p = cfg.pipeline
    month_days = p.run.month_days
    w = p.scoring.weights
    buyer_type_score = vars(p.buyer_score.boamp_only)
    max_cand = p.candidates.max_candidates_per_source

    eligible = sources[sources["buyer_key_type"] != "MISSING"].copy()
    eligible = eligible.sort_values(["buyer_key", "publication_date"]).reset_index(drop=True)

    window, median_dur = estimate_window_months(eligible, cfg)
    if window_override is not None:
        window, median_dur = int(window_override), float("nan")
    if verbose:
        print(f"Eligible sources: {len(eligible)}; median observed duration {median_dur:.1f}m "
              f"-> temporal window {window}m")

    _, tfidf = build_tfidf_matrix(eligible["objet_clean"].fillna("").tolist(), cfg)

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

    window_td = np.timedelta64(int(round(window * month_days)), "D")
    records = []
    group_indices = eligible.groupby("buyer_key", sort=False).indices

    for buyer_key, idx in group_indices.items():
        n = len(idx)
        if n < 2:
            continue
        idx = np.asarray(idx)
        g_pub = pub_dates_all[idx]
        g_end = end_dates_all[idx]

        for i in range(n):
            expected_end = g_end[i]
            if pd.isna(expected_end):
                continue
            src_date = g_pub[i]
            lo = expected_end - window_td
            hi = expected_end + window_td
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

            abs_gap_arr = np.abs((g_pub[cand_local] - expected_end)) / np.timedelta64(1, "D") / month_days
            if len(cand_local) > max_cand:
                keep = np.argsort(abs_gap_arr)[:max_cand]
                cand_local = cand_local[keep]
                cand_global = cand_global[keep]
                abs_gap_arr = abs_gap_arr[keep]

            gap_months_arr = (g_pub[cand_local] - src_date) / np.timedelta64(1, "D") / month_days
            s_time_arr = np.clip(1.0 - abs_gap_arr / window, 0.0, None)
            sims = tfidf[cand_global].dot(tfidf[i_global].T).toarray().ravel()

            src_cpv_main, src_cpv_cat = cpv_main_all[i_global], cpv_cat_all[i_global]
            src_cpv_cls, src_cpv_grp, src_cpv_div = cpv_cls_all[i_global], cpv_grp_all[i_global], cpv_div_all[i_global]
            src_generic = bool(cpv_generic_all[i_global])
            bkt = buyer_key_type_all[i_global]
            s_buyer = buyer_type_score.get(bkt, 0.0)

            for k, cg in enumerate(cand_global):
                s_cpv = cpv_pair_score(
                    src_cpv_main, cpv_main_all[cg],
                    src_cpv_cat, cpv_cat_all[cg],
                    src_cpv_cls, cpv_cls_all[cg],
                    src_cpv_grp, cpv_grp_all[cg],
                    src_cpv_div, cpv_div_all[cg],
                    p.cpv_score,
                )
                s_text = float(sims[k])
                composite = w.text * s_text + w.cpv * s_cpv + w.time * s_time_arr[k] + w.buyer * s_buyer
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
                    "composite_score": composite,
                    "cpv_missing": bool(pd.isna(src_cpv_main) or pd.isna(cpv_main_all[cg])),
                    "cpv_generic_flag": bool(src_generic or cpv_generic_all[cg]),
                })

    pairs = add_rank_and_margin(pd.DataFrame.from_records(records))
    if verbose:
        print(f"Generated {len(pairs)} Layer 1 candidate pairs "
              f"({pairs['source_notice_id'].nunique() if len(pairs) else 0} sources with >=1 candidate)")
    return pairs, window


def compatible_mechanism(src: pd.Series, cand: pd.Series) -> str | None:
    """Layer 2 reconciliation mechanism for a (source, candidate) pair."""
    if pd.notna(src["buyer_siret_clean"]) and src["buyer_siret_clean"] == cand["buyer_siret_clean"]:
        return "EXACT_SIRET_RECONCILIATION"
    if pd.notna(src["buyer_siren_l2"]) and src["buyer_siren_l2"] == cand["buyer_siren_l2"]:
        if (
            src["buyer_identity_source"] == "UNIQUE_NAME_DEPARTMENT_ALIAS"
            or cand["buyer_identity_source"] == "UNIQUE_NAME_DEPARTMENT_ALIAS"
        ):
            return "HISTORICAL_ALIAS_RECONCILIATION"
        return "SAME_SIREN_RECONCILIATION"
    if pd.notna(src["buyer_key"]) and src["buyer_key"] == cand["buyer_key"]:
        return "M0_NAME_FALLBACK"
    return None


MECHANISM_PRIORITY = {
    "EXACT_SIRET_RECONCILIATION": 4,
    "SAME_SIREN_RECONCILIATION": 3,
    "HISTORICAL_ALIAS_RECONCILIATION": 2,
    "M0_NAME_FALLBACK": 1,
}


def generate_pairs_mechanisms(l2_sources: pd.DataFrame, cfg, verbose: bool = True) -> tuple[pd.DataFrame, int]:
    """Layer 2 candidate generation with multi-mechanism blocking."""
    p = cfg.pipeline
    month_days = p.run.month_days
    w = p.scoring.weights
    mech_score = vars(p.buyer_score.enriched)
    max_cand = p.candidates.max_candidates_per_source

    eligible = l2_sources[l2_sources["buyer_key_type"] != "MISSING"].copy()
    eligible = eligible.sort_values(["publication_date", "notice_id"]).reset_index(drop=True)

    window, median_dur = estimate_window_months(eligible, cfg)
    if verbose:
        print(f"Eligible sources: {len(eligible)}; temporal window {window}m (same derivation as Layer 1)")

    _, tfidf = build_tfidf_matrix(eligible["objet_clean"].fillna("").tolist(), cfg)

    exact_siret_groups = defaultdict(set)
    siren_groups = defaultdict(set)
    name_groups = defaultdict(set)
    for idx, row in eligible.iterrows():
        if pd.notna(row["buyer_siret_clean"]):
            exact_siret_groups[row["buyer_siret_clean"]].add(idx)
        if pd.notna(row["buyer_siren_l2"]):
            siren_groups[row["buyer_siren_l2"]].add(idx)
        if pd.notna(row["buyer_key"]):
            name_groups[row["buyer_key"]].add(idx)

    candidate_index_sets: dict[int, set[int]] = defaultdict(set)
    for groups in [exact_siret_groups, siren_groups, name_groups]:
        for idxs in groups.values():
            if len(idxs) < 2:
                continue
            for idx in idxs:
                candidate_index_sets[idx].update(idxs - {idx})

    records = []
    for src_idx, cand_idxs in candidate_index_sets.items():
        src = eligible.loc[src_idx]
        if pd.isna(src["estimated_end_date"]):
            continue
        candidate_meta = []
        for cand_idx in cand_idxs:
            cand = eligible.loc[cand_idx]
            if cand["publication_date"] <= src["publication_date"]:
                continue
            abs_gap = abs((cand["publication_date"] - src["estimated_end_date"]).total_seconds() / (3600 * 24 * month_days))
            if abs_gap > window:
                continue
            mechanism = compatible_mechanism(src, cand)
            if mechanism is None:
                continue
            candidate_meta.append((cand_idx, abs_gap, mechanism))
        if not candidate_meta:
            continue
        best_by_candidate: dict = {}
        for cand_idx, abs_gap, mechanism in candidate_meta:
            prev = best_by_candidate.get(cand_idx)
            if prev is None or MECHANISM_PRIORITY[mechanism] > MECHANISM_PRIORITY[prev[1]]:
                best_by_candidate[cand_idx] = (abs_gap, mechanism)
        candidate_meta = [(idx, gap, mech) for idx, (gap, mech) in best_by_candidate.items()]
        if len(candidate_meta) > max_cand:
            candidate_meta = sorted(candidate_meta, key=lambda t: t[1])[:max_cand]
        cand_indices = [x[0] for x in candidate_meta]
        sims = tfidf[cand_indices].dot(tfidf[src_idx].T).toarray().ravel()
        for pos, (cand_idx, abs_gap, mechanism) in enumerate(candidate_meta):
            cand = eligible.loc[cand_idx]
            gap_months = (cand["publication_date"] - src["publication_date"]).total_seconds() / (3600 * 24 * month_days)
            s_time = max(1.0 - abs_gap / window, 0.0)
            s_cpv = cpv_pair_score(
                src["cpv_clean"], cand["cpv_clean"],
                src["cpv_category"], cand["cpv_category"],
                src["cpv_class"], cand["cpv_class"],
                src["cpv_group"], cand["cpv_group"],
                src["cpv_division"], cand["cpv_division"],
                p.cpv_score,
            )
            s_text = float(sims[pos])
            s_buyer = mech_score[mechanism]
            composite = w.text * s_text + w.cpv * s_cpv + w.time * s_time + w.buyer * s_buyer
            records.append({
                "source_notice_id": src["notice_id"],
                "candidate_notice_id": cand["notice_id"],
                "source_date": src["publication_date"],
                "candidate_date": cand["publication_date"],
                "buyer_key_l1_source": src["buyer_key"],
                "buyer_key_l1_candidate": cand["buyer_key"],
                "buyer_key_type_source": src["buyer_key_type"],
                "buyer_key_type_candidate": cand["buyer_key_type"],
                "buyer_match_mechanism": mechanism,
                "source_buyer_identity_source": src["buyer_identity_source"],
                "candidate_buyer_identity_source": cand["buyer_identity_source"],
                "source_buyer_siret": src["buyer_siret_clean"],
                "candidate_buyer_siret": cand["buyer_siret_clean"],
                "source_buyer_siren_l2": src["buyer_siren_l2"],
                "candidate_buyer_siren_l2": cand["buyer_siren_l2"],
                "cross_establishment_same_siren": bool(
                    mechanism in {"SAME_SIREN_RECONCILIATION", "HISTORICAL_ALIAS_RECONCILIATION"}
                    and pd.notna(src["buyer_siret_clean"])
                    and pd.notna(cand["buyer_siret_clean"])
                    and src["buyer_siret_clean"] != cand["buyer_siret_clean"]
                ),
                "gap_months": gap_months,
                "expected_end_date": src["estimated_end_date"],
                "abs_gap_to_expected_end": abs_gap,
                "s_time": s_time,
                "s_text": s_text,
                "s_cpv": s_cpv,
                "s_buyer": s_buyer,
                "composite_score": composite,
                "cpv_missing": bool(pd.isna(src["cpv_clean"]) or pd.isna(cand["cpv_clean"])),
                "cpv_generic_flag": bool(src["cpv_generic_flag"] or cand["cpv_generic_flag"]),
            })

    pairs = add_rank_and_margin(pd.DataFrame.from_records(records))
    if verbose:
        print(f"Generated {len(pairs)} Layer 2 candidate pairs "
              f"({pairs['source_notice_id'].nunique() if len(pairs) else 0} sources with >=1 candidate)")
    return pairs, window
