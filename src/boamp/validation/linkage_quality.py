"""Linkage-quality evaluation, layer-agnostic.

Extracted from the legacy evaluation scripts (logic unchanged, hardcoded
constants parametrized):
  - Fellegi-Sunter Beta-mixture EM   <- eval_m3_fellegi_sunter_mixture.py
  - corruption / recovery test       <- eval_m4_corruption_recovery.py
  - threshold sensitivity            <- eval_m6a (N no longer hardcoded)
  - weight / feature ablation        <- eval_m6b
  - duration-leakage variants        <- eval_duration_leakage.py

All estimates here are MODEL-BASED internal diagnostics over the blocked
candidate space - none of them is ground-truth precision/recall. The
mixture recall is defined only over pairs that survived blocking.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import logsumexp
from scipy.stats import beta as beta_dist
from scipy.stats import pearsonr, spearmanr

DIMS = ["s_text", "s_cpv", "s_time", "s_buyer"]
MAX_ITER = 200
TOL = 1e-6
N_RANDOM_RESTARTS = 5
RANDOM_SEED_BASE = 0
REG_FRAC = 0.05


# ---------------------------------------------------------------------------
# Fellegi-Sunter Beta-mixture EM
# ---------------------------------------------------------------------------

def squeeze(x: np.ndarray, eps: float) -> np.ndarray:
    """Smithson-Verkuilen squeeze: map [0,1] into (0,1) for a finite Beta pdf."""
    return x * (1 - 2 * eps) + eps


def logpdf_beta_matrix(X: np.ndarray, alphas: np.ndarray, betas: np.ndarray) -> np.ndarray:
    out = np.zeros(X.shape[0])
    for d in range(X.shape[1]):
        out += beta_dist.logpdf(X[:, d], alphas[d], betas[d])
    return out


def m_step_moment_match(X: np.ndarray, w: np.ndarray, var_floor: np.ndarray, m_min: np.ndarray):
    """Weighted method-of-moments M-step with a variance floor (prevents the
    degenerate zero-variance component on near-discrete dimensions)."""
    wsum = w.sum()
    m = (w[:, None] * X).sum(axis=0) / wsum
    m = np.clip(m, m_min, 1 - m_min)
    v = (w[:, None] * (X - m[None, :]) ** 2).sum(axis=0) / wsum
    v = np.clip(v, var_floor, 0.99 * m * (1 - m))
    common = m * (1 - m) / v - 1
    common = np.maximum(common, 1e-6)
    return m * common, (1 - m) * common, m, v


def run_em(X: np.ndarray, r0: np.ndarray, label: str, var_floor: np.ndarray, m_min: np.ndarray) -> dict:
    r = r0.copy()
    prev_ll = -np.inf
    for it in range(MAX_ITER):
        p = np.clip(r.mean(), 1e-6, 1 - 1e-6)
        aM, bM, mM, vM = m_step_moment_match(X, r, var_floor, m_min)
        aU, bU, mU, vU = m_step_moment_match(X, 1 - r, var_floor, m_min)
        log_num_M = np.log(p) + logpdf_beta_matrix(X, aM, bM)
        log_num_U = np.log(1 - p) + logpdf_beta_matrix(X, aU, bU)
        log_denom = logsumexp(np.vstack([log_num_M, log_num_U]), axis=0)
        r = np.clip(np.exp(log_num_M - log_denom), 1e-12, 1 - 1e-12)
        ll = log_denom.sum()
        if it > 0 and abs(ll - prev_ll) < TOL:
            break
        prev_ll = ll
    return {"label": label, "p": p, "alpha_M": aM, "beta_M": bM, "mean_M": mM, "var_M": vM,
            "alpha_U": aU, "beta_U": bU, "mean_U": mU, "var_U": vU, "r": r,
            "loglik": ll, "n_iter": it + 1}


def fit_fs_beta_mixture(pairs: pd.DataFrame, links: pd.DataFrame,
                        score_col: str = "composite_score", verbose: bool = True) -> dict:
    """Full m3 procedure on one layer's candidate pairs + balanced links.

    Returns dict with params table, posteriors, precision/recall estimates,
    conditional-independence check, and convergence diagnostics.
    """
    pairs = pairs.copy()
    N = len(pairs)
    link_keys = set(zip(links["source_notice_id"], links["candidate_notice_id"]))
    pairs["in_linked_set"] = [
        (s, c) in link_keys for s, c in zip(pairs["source_notice_id"], pairs["candidate_notice_id"])
    ]
    assert pairs["in_linked_set"].sum() == len(links), "all links must appear in the candidate table"

    eps = 1.0 / (2 * N)
    X = np.column_stack([squeeze(pairs[d].to_numpy(dtype=float), eps) for d in DIMS])
    global_var = X.var(axis=0)
    var_floor = REG_FRAC * global_var
    m_min = 0.5 - np.sqrt(np.maximum(0.25 - var_floor, 0.0))

    runs = [run_em(X, np.where(pairs["in_linked_set"].to_numpy(), 0.9, 0.1), "warm_start", var_floor, m_min)]
    rng_master = np.random.RandomState(RANDOM_SEED_BASE)
    for k in range(N_RANDOM_RESTARTS):
        runs.append(run_em(X, rng_master.uniform(0.05, 0.95, size=N), f"random_restart_{k}", var_floor, m_min))

    best = max(runs, key=lambda d: d["loglik"])
    warm = runs[0]
    warm_hard, best_hard = warm["r"] > 0.5, best["r"] > 0.5
    union = np.logical_or(warm_hard, best_hard).sum()
    jaccard_warm_vs_best = (np.logical_and(warm_hard, best_hard).sum() / union) if union else float("nan")

    # label-switching fix: M = component with more content-signal mass
    idx_text, idx_cpv = DIMS.index("s_text"), DIMS.index("s_cpv")
    if best["mean_U"][idx_text] + best["mean_U"][idx_cpv] > best["mean_M"][idx_text] + best["mean_M"][idx_cpv]:
        best["p"] = 1 - best["p"]
        for a, b in [("alpha_M", "alpha_U"), ("beta_M", "beta_U"), ("mean_M", "mean_U"), ("var_M", "var_U")]:
            best[a], best[b] = best[b], best[a]
        best["r"] = 1 - best["r"]

    r = best["r"]
    gaps = best["mean_M"] - best["mean_U"]
    gap_rank = np.argsort(-np.abs(gaps))

    param_rows = [{"class": "mixing_weight", "dimension": "p_hat", "alpha": np.nan, "beta": np.nan,
                   "weighted_mean": best["p"], "weighted_var": np.nan, "gap_m_minus_u": np.nan, "gap_rank": np.nan}]
    for rank_pos, d in enumerate(gap_rank):
        for cls, a_arr, b_arr, m_arr, v_arr in [
            ("M", best["alpha_M"], best["beta_M"], best["mean_M"], best["var_M"]),
            ("U", best["alpha_U"], best["beta_U"], best["mean_U"], best["var_U"]),
        ]:
            param_rows.append({"class": cls, "dimension": DIMS[d], "alpha": a_arr[d], "beta": b_arr[d],
                               "weighted_mean": m_arr[d], "weighted_var": v_arr[d],
                               "gap_m_minus_u": gaps[d], "gap_rank": rank_pos + 1})

    in_link = pairs["in_linked_set"].to_numpy()
    TP_hat = r[in_link].sum()
    FN_hat = r[~in_link].sum()
    n_linked = int(in_link.sum())
    precision_hat = TP_hat / n_linked
    recall_hat = TP_hat / (TP_hat + FN_hat)

    posteriors = pairs[["source_notice_id", "candidate_notice_id", "candidate_rank",
                        score_col, "in_linked_set"]].copy()
    posteriors["posterior_M"] = r

    linked_pairs = pairs[pairs["in_linked_set"]]
    pear_r, pear_p = pearsonr(linked_pairs["s_cpv"], linked_pairs["s_text"])
    spear_r, spear_p = spearmanr(linked_pairs["s_cpv"], linked_pairs["s_text"])

    if verbose:
        print(f"best run {best['label']} logL={best['loglik']:.1f}; p_hat={best['p']:.4f}; "
              f"precision_hat={precision_hat:.4f}, recall_hat={recall_hat:.4f} "
              f"(recall over blocked pairs only)")

    return {
        "params": pd.DataFrame(param_rows),
        "posteriors": posteriors,
        "precision_recall": pd.DataFrame([{
            "TP_hat": TP_hat, "FN_hat": FN_hat, "n_linked": n_linked, "n_omega": N,
            "precision_hat": precision_hat, "recall_hat": recall_hat,
            "scope_caveat": ("Recall_hat is relative to blocked candidate pairs only; "
                             "it cannot bound recall against all possible true renewals."),
        }]),
        "convergence": pd.DataFrame([{
            "best_run_label": best["label"], "best_loglik": best["loglik"],
            "warm_start_loglik": warm["loglik"],
            "loglik_delta_warm_vs_best": best["loglik"] - warm["loglik"],
            "jaccard_warm_vs_best_r_gt_half": jaccard_warm_vs_best,
            "n_restarts_total": len(runs),
        }]),
        "conditional_independence": pd.DataFrame([{
            "n_linked_pairs": len(linked_pairs),
            "pearson_r_cpv_text": pear_r, "pearson_p_cpv_text": pear_p,
            "spearman_r_cpv_text": spear_r, "spearman_p_cpv_text": spear_p,
            "flag_high_correlation_gt_0_3": bool(abs(pear_r) > 0.3 or abs(spear_r) > 0.3),
        }]),
    }


# ---------------------------------------------------------------------------
# Threshold sensitivity (m6a) - N parametrized, no longer hardcoded
# ---------------------------------------------------------------------------

def threshold_sweep(pairs: pd.DataFrame, n_eligible_sources: int,
                    score_col: str = "composite_score") -> pd.DataFrame:
    rank1 = pairs[pairs["candidate_rank"] == 1]
    scores = rank1[score_col].to_numpy()
    rows = []
    for pct in range(10, 91, 5):
        thr = np.percentile(scores, pct)
        n_linked = int((scores >= thr).sum())
        rows.append({
            "percentile": pct, "threshold_value": thr, "n_linked": n_linked,
            "event_rate": n_linked / n_eligible_sources,
            "variant_label": {25: "broad", 50: "balanced", 75: "strict"}.get(pct),
        })
    return pd.DataFrame(rows)


def local_threshold_sensitivity(pairs: pd.DataFrame, thresholds: dict,
                                score_col: str = "composite_score",
                                deltas=(0.005, 0.01, 0.02, 0.05),
                                bin_width: float = 0.01) -> pd.DataFrame:
    rank1 = pairs[pairs["candidate_rank"] == 1]
    scores = rank1[score_col].to_numpy()
    n_rank1 = len(rank1)

    def local_density_at(x):
        count = ((scores >= x - bin_width / 2) & (scores < x + bin_width / 2)).sum()
        return count / (n_rank1 * bin_width)

    hist_counts, hist_edges = np.histogram(
        scores, bins=np.arange(scores.min(), scores.max() + bin_width, bin_width))
    mode_bin_idx = int(np.argmax(hist_counts))
    mode_score = (hist_edges[mode_bin_idx] + hist_edges[mode_bin_idx + 1]) / 2

    rows = []
    for delta in deltas:
        n_flipped = int((np.abs(scores - thresholds["balanced"]) < delta).sum())
        rows.append({
            "delta": delta, "n_flipped": n_flipped, "pct_flipped": n_flipped / n_rank1,
            "local_density_at_balanced": local_density_at(thresholds["balanced"]),
            "local_density_at_broad": local_density_at(thresholds["broad"]),
            "local_density_at_strict": local_density_at(thresholds["strict"]),
            "local_density_at_mode": local_density_at(mode_score),
            "mode_score": mode_score,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Weight / feature ablation (m6b)
# ---------------------------------------------------------------------------

def weight_ablation(pairs: pd.DataFrame, links: pd.DataFrame, cfg,
                    score_col: str = "composite_score") -> pd.DataFrame:
    w = cfg.pipeline.scoring.weights
    real_weights = {"s_text": w.text, "s_cpv": w.cpv, "s_time": w.time, "s_buyer": w.buyer}
    labels = {"s_text": "text", "s_cpv": "cpv", "s_time": "time", "s_buyer": "buyer"}
    real_linked_sources = set(links["source_notice_id"])

    rows = []
    for dropped_col, dropped_label in labels.items():
        remaining = {c: wt for c, wt in real_weights.items() if c != dropped_col}
        wsum = sum(remaining.values())
        renorm = {c: wt / wsum for c, wt in remaining.items()}

        ablated = pairs.copy()
        ablated["composite_prime"] = sum(ablated[c] * wt for c, wt in renorm.items())
        ablated = ablated.sort_values(["source_notice_id", "composite_prime"], ascending=[True, False])
        ablated["candidate_rank_prime"] = ablated.groupby("source_notice_id").cumcount() + 1
        rank1_prime = ablated[ablated["candidate_rank_prime"] == 1]
        thr = rank1_prime["composite_prime"].quantile(0.5)
        lk_sources = set(rank1_prime[rank1_prime["composite_prime"] >= thr]["source_notice_id"])

        inter = len(lk_sources & real_linked_sources)
        union = len(lk_sources | real_linked_sources)
        rows.append({
            "dropped_component": dropped_label,
            "renormalized_weights": ", ".join(f"{labels[c]}={wt:.4f}" for c, wt in renorm.items()),
            "ablated_threshold_p50": thr,
            "n_linked_ablated": len(lk_sources),
            "n_intersection_with_real_balanced": inter,
            "n_union_with_real_balanced": union,
            "jaccard_vs_real_balanced": inter / union if union else float("nan"),
        })
    return pd.DataFrame(rows).sort_values("jaccard_vs_real_balanced")


# ---------------------------------------------------------------------------
# Duration-leakage variants (eval_duration_leakage)
# ---------------------------------------------------------------------------

def no_temporal_weights(cfg) -> dict:
    w = cfg.pipeline.scoring.weights
    s = w.text + w.cpv + w.buyer
    return {"s_text": w.text / s, "s_cpv": w.cpv / s, "s_buyer": w.buyer / s}


def make_links_from_pairs(pairs: pd.DataFrame, name: str, score_col: str) -> tuple[pd.DataFrame, float]:
    """Re-rank on an alternative score and threshold at its rank-1 median."""
    x = pairs.sort_values(["source_notice_id", score_col], ascending=[True, False]).copy()
    x["candidate_rank"] = x.groupby("source_notice_id").cumcount() + 1
    r1 = x[x["candidate_rank"] == 1].copy()
    thr = r1[score_col].quantile(0.5)
    links = r1[r1[score_col] >= thr].copy()
    links["composite_score"] = links[score_col]
    links["variant"] = name
    links["threshold_used"] = thr
    return links, thr


def forward_pairs(eligible: pd.DataFrame, tfidf, cfg, months: int = 24) -> pd.DataFrame:
    """Forward-window candidate generation with NO duration/expected-end input.

    Leakage check: if the duration variable (82.7% imputed) were driving the
    linkage, links built without it should tell a different survival story.
    """
    p = cfg.pipeline
    month_days = p.run.month_days
    w_nt = no_temporal_weights(cfg)
    buyer_type_score = vars(p.buyer_score.boamp_only)
    maxcand = p.candidates.max_candidates_per_source
    from boamp.linkage.scoring import cpv_pair_score  # local import to avoid cycle

    ids = eligible["notice_id"].to_numpy()
    pub = eligible["publication_date"].to_numpy()
    bk = eligible["buyer_key"].to_numpy(object)
    bkt = eligible["buyer_key_type"].to_numpy(object)
    main = eligible["cpv_clean"].to_numpy(object)
    cat = eligible["cpv_category"].to_numpy(object)
    cls = eligible["cpv_class"].to_numpy(object)
    grp = eligible["cpv_group"].to_numpy(object)
    div = eligible["cpv_division"].to_numpy(object)
    gen = eligible["cpv_generic_flag"].to_numpy()
    rec = []
    for _, idx in eligible.groupby("buyer_key", sort=False).indices.items():
        idx = np.asarray(idx)
        gp = pub[idx]
        n = len(idx)
        if n < 2:
            continue
        for i in range(n):
            hi = gp[i] + np.timedelta64(int(round(months * month_days)), "D")
            loc = np.where((gp > gp[i]) & (gp <= hi))[0]
            if len(loc) == 0:
                continue
            glob = idx[loc]
            gaps = (gp[loc] - gp[i]) / np.timedelta64(1, "D") / month_days
            if len(loc) > maxcand:
                keep = np.argsort(gaps)[:maxcand]
                loc, glob, gaps = loc[keep], glob[keep], gaps[keep]
            sims = tfidf[glob].dot(tfidf[idx[i]].T).toarray().ravel()
            sb = buyer_type_score.get(bkt[idx[i]], 0.0)
            for k, cg in enumerate(glob):
                scpv = cpv_pair_score(main[idx[i]], main[cg], cat[idx[i]], cat[cg],
                                      cls[idx[i]], cls[cg], grp[idx[i]], grp[cg],
                                      div[idx[i]], div[cg], p.cpv_score)
                stext = float(sims[k])
                score = w_nt["s_text"] * stext + w_nt["s_cpv"] * scpv + w_nt["s_buyer"] * sb
                rec.append(dict(
                    source_notice_id=ids[idx[i]], candidate_notice_id=ids[cg],
                    source_date=gp[i], candidate_date=gp[loc[k]],
                    buyer_key=bk[idx[i]], buyer_key_type=bkt[idx[i]],
                    gap_months=gaps[k], expected_end_date=pd.NaT,
                    abs_gap_to_expected_end=np.nan, s_time=np.nan,
                    s_text=stext, s_cpv=scpv, s_buyer=sb,
                    composite_score=score,
                    cpv_missing=bool(pd.isna(main[idx[i]]) or pd.isna(main[cg])),
                    cpv_generic_flag=bool(gen[idx[i]] or gen[cg]),
                    score_forward_no_duration=score,
                ))
    out = pd.DataFrame(rec)
    if len(out):
        out = out.sort_values(["source_notice_id", "score_forward_no_duration"], ascending=[True, False])
        out["candidate_rank"] = out.groupby("source_notice_id").cumcount() + 1
        out["n_candidates_for_source"] = out.groupby("source_notice_id")["candidate_notice_id"].transform("count")
        top2 = out[out["candidate_rank"] <= 2].pivot(
            index="source_notice_id", columns="candidate_rank", values="score_forward_no_duration")
        out["top1_top2_margin"] = out["source_notice_id"].map((top2.get(1) - top2.get(2)).fillna(top2.get(1)))
    return out
