"""
Step 11 - Method 3: unsupervised Fellegi-Sunter mixture estimate of M0
linkage quality.

Input:  data/processed/boamp_m0_candidate_pairs.csv
        data/processed/boamp_m0_links_balanced.csv
Output: reports/tables/m3_beta_mixture_params.csv
        reports/tables/m3_posteriors.csv
        reports/tables/m3_precision_recall.csv
        reports/tables/m3_conditional_independence_check.csv

Population Omega = ALL 6,137 candidate pairs (not just candidate_rank==1).
Rank-1 pairs are each source's *best* candidate by construction, so
restricting to them would sample "winners" rather than "compared pairs"
and would distort the apparent U-class (non-match) distribution. The full
candidate table is the realized output of blocking (same buyer_key,
temporal window around estimated_end_date) and is the correct Fellegi-
Sunter comparison space, exactly analogous to classical record linkage
where Omega is all blocked pairs, not just the arg-max per block.

Model: 2 latent classes M (match/renewal) and U (non-match), 4 comparison
dimensions gamma = (s_text, s_cpv, s_time, s_buyer), conditionally
independent given class. Each dimension is Beta-distributed per class
(s_text and s_time are continuous in [0,1]; s_cpv/s_buyer are ordinal/
multi-valued rather than binary - modeling all 4 as Beta per the
project's pre-approved fallback avoids an arbitrary binarization cutoff
for s_text and keeps a single unified model).

    P(gamma | M) = prod_d Beta(gamma_d; alpha_{M,d}, beta_{M,d})
    P(gamma | U) = prod_d Beta(gamma_d; alpha_{U,d}, beta_{U,d})
    P(gamma)     = p * P(gamma | M) + (1-p) * P(gamma | U)

Fit by EM (hand-rolled - see stability note below).
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist
from scipy.special import logsumexp
from scipy.stats import pearsonr, spearmanr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
TABLES_DIR.mkdir(parents=True, exist_ok=True)

DIMS = ["s_text", "s_cpv", "s_time", "s_buyer"]
MAX_ITER = 200
TOL = 1e-6
N_RANDOM_RESTARTS = 5
RANDOM_SEED_BASE = 0


def squeeze(x: np.ndarray, eps: float) -> np.ndarray:
    """Smithson-Verkuilen squeeze: maps [0,1] (with exact 0/1 mass) into
    the open interval (0,1) required for a finite, well-defined Beta
    density. eps = 1/(2N) is small enough not to distort the fit but
    large enough to avoid float underflow at the boundary."""
    return x * (1 - 2 * eps) + eps


def logpdf_beta_matrix(X: np.ndarray, alphas: np.ndarray, betas: np.ndarray) -> np.ndarray:
    """X: (N, D) squeezed comparison vectors. alphas/betas: (D,) Beta
    params for one class. Returns (N,) sum of per-dimension log-densities
    (conditional independence given class)."""
    out = np.zeros(X.shape[0])
    for d in range(X.shape[1]):
        out += beta_dist.logpdf(X[:, d], alphas[d], betas[d])
    return out


def m_step_moment_match(X: np.ndarray, w: np.ndarray, var_floor: np.ndarray, m_min: np.ndarray):
    """Weighted method-of-moments M-step, one class, all D dimensions.

    Why moment-matching instead of scipy.stats.beta.fit (weighted MLE):
      (a) scipy's Beta MLE fitter has no native support for per-observation
          responsibility weights; using it inside EM would require either
          resampling by weight (adds Monte Carlo noise every iteration) or
          a hand-rolled weighted Newton/digamma fixed-point solve (Minka's
          fixed-point method for Beta MLE) - substantially more code and a
          second, less stable source of non-convergence.
      (b) MLE Beta fitting is numerically fragile exactly where this data
          is worst-behaved: s_cpv and s_buyer are near-degenerate (few
          distinct values - s_buyer is empirically only 2-valued in this
          corpus, {0.6, 1.0}), and Newton-Raphson on the digamma equations
          can diverge or walk to a boundary for spiky/discrete-like data.
      (c) Weighted moment-matching is closed-form (no inner iteration per
          M-step), always well-defined given the variance-floor guard
          below, and is standard practice for Beta-mixture EM on bounded
          scores (e.g. methylation / ChIP-seq beta-mixture models).

    M-step update equations:
        m_d = sum_j w_j * x_{j,d} / sum_j w_j                (weighted mean)
        v_d = sum_j w_j * (x_{j,d} - m_d)^2 / sum_j w_j       (weighted var)

    var_floor / m_min regularization (NOT optional - see below): a first,
    unregularized run of this EM on the real candidate-pairs table converged
    to a spurious global-likelihood-maximizing solution where one component
    isolated the subset of pairs with s_buyer == 1.0 (RAW_SIRET-keyed
    sources) and drove its s_buyer variance to ~0, which makes the Beta
    density -> infinity at that point and the mixture log-likelihood
    unbounded above - the classical degenerate-component failure mode of
    finite mixture EM (identical in spirit to a zero-variance component in
    a Gaussian mixture), triggered here because s_buyer is only 2-valued.
    That solution had ~1740 higher log-likelihood than every other
    initialization and is *not* a genuine match/non-match split - it is a
    likelihood singularity. Fixed by flooring each class-conditional
    variance at var_floor_d = 0.05 * Var_d(all of Omega, unconditional) -
    i.e. no component may claim less than 5% of the overall spread on any
    dimension - and, since a Beta's variance is bounded above by m(1-m),
    also clipping the mean away from {0,1} to m_min_d (solved from
    m_min*(1-m_min) = var_floor_d) so the floor is always satisfiable.
        v_d <- clip(v_d, var_floor_d, 0.99 * m_d * (1 - m_d))
        common_d = m_d * (1 - m_d) / v_d - 1
        alpha_d = m_d * common_d
        beta_d  = (1 - m_d) * common_d
    """
    wsum = w.sum()
    m = (w[:, None] * X).sum(axis=0) / wsum
    m = np.clip(m, m_min, 1 - m_min)
    v = (w[:, None] * (X - m[None, :]) ** 2).sum(axis=0) / wsum
    v = np.clip(v, var_floor, 0.99 * m * (1 - m))
    common = m * (1 - m) / v - 1
    common = np.maximum(common, 1e-6)
    alpha = m * common
    beta_ = (1 - m) * common
    return alpha, beta_, m, v


def run_em(X: np.ndarray, r0: np.ndarray, label: str, var_floor: np.ndarray, m_min: np.ndarray):
    """Runs EM to convergence from initial responsibilities r0 (P(M|gamma)
    for each pair). Returns dict with final params, responsibilities, and
    log-likelihood trace."""
    N, D = X.shape
    r = r0.copy()
    prev_ll = -np.inf
    ll_trace = []

    for it in range(MAX_ITER):
        # ---- M-step ----
        p = r.mean()
        p = np.clip(p, 1e-6, 1 - 1e-6)
        aM, bM, mM, vM = m_step_moment_match(X, r, var_floor, m_min)
        aU, bU, mU, vU = m_step_moment_match(X, 1 - r, var_floor, m_min)

        # ---- E-step (log-space for numerical stability) ----
        log_num_M = np.log(p) + logpdf_beta_matrix(X, aM, bM)
        log_num_U = np.log(1 - p) + logpdf_beta_matrix(X, aU, bU)
        log_denom = logsumexp(np.vstack([log_num_M, log_num_U]), axis=0)
        r = np.exp(log_num_M - log_denom)
        r = np.clip(r, 1e-12, 1 - 1e-12)

        ll = log_denom.sum()
        ll_trace.append(ll)
        if it > 0 and abs(ll - prev_ll) < TOL:
            break
        prev_ll = ll

    print(f"  [{label}] converged after {it + 1} iterations, final logL = {ll:.4f}")
    return {
        "label": label,
        "p": p,
        "alpha_M": aM, "beta_M": bM, "mean_M": mM, "var_M": vM,
        "alpha_U": aU, "beta_U": bU, "mean_U": mU, "var_U": vU,
        "r": r,
        "loglik": ll,
        "n_iter": it + 1,
    }


def main():
    print("Loading candidate pairs (Omega)...")
    pairs = pd.read_csv(PROCESSED_DIR / "boamp_m0_candidate_pairs.csv")
    N = len(pairs)
    print(f"Omega size (all candidate pairs): {N}")

    balanced = pd.read_csv(PROCESSED_DIR / "boamp_m0_links_balanced.csv")
    balanced_keys = set(zip(balanced["source_notice_id"], balanced["candidate_notice_id"]))
    pairs["in_balanced_linked_set"] = [
        (s, c) in balanced_keys
        for s, c in zip(pairs["source_notice_id"], pairs["candidate_notice_id"])
    ]
    n_balanced = pairs["in_balanced_linked_set"].sum()
    print(f"Balanced-linked pairs found within Omega: {n_balanced} (expect {len(balanced)})")
    assert n_balanced == len(balanced), "balanced links must all be present in the candidate table"

    eps = 1.0 / (2 * N)
    X = np.column_stack([squeeze(pairs[d].to_numpy(dtype=float), eps) for d in DIMS])

    # Regularization floor (see m_step_moment_match docstring): no component
    # may claim less than 5% of Omega's unconditional per-dimension spread,
    # and the mean is clipped away from {0,1} accordingly. This is what
    # rules out the degenerate single-point-mass solution that an
    # unregularized run of this EM converged to on s_buyer (only 2-valued
    # in this corpus).
    REG_FRAC = 0.05
    global_var = X.var(axis=0)
    var_floor = REG_FRAC * global_var
    m_min = 0.5 - np.sqrt(np.maximum(0.25 - var_floor, 0.0))
    print(f"Global (unconditional) variance per dimension: "
          f"{dict(zip(DIMS, np.round(global_var, 5)))}")
    print(f"Variance floor (5% of global var): {dict(zip(DIMS, np.round(var_floor, 6)))}")

    # ---- multiple EM initializations ----
    runs = []

    # Warm start: responsibilities seeded from balanced-linked membership
    # (0.9/0.1, not hard 0/1, so the first M-step is not degenerate).
    r0_warm = np.where(pairs["in_balanced_linked_set"].to_numpy(), 0.9, 0.1)
    runs.append(run_em(X, r0_warm, "warm_start", var_floor, m_min))

    rng_master = np.random.RandomState(RANDOM_SEED_BASE)
    for k in range(N_RANDOM_RESTARTS):
        r0_rand = rng_master.uniform(0.05, 0.95, size=N)
        runs.append(run_em(X, r0_rand, f"random_restart_{k}", var_floor, m_min))

    max_ab = max(
        max(run["alpha_M"].max(), run["beta_M"].max(), run["alpha_U"].max(), run["beta_U"].max())
        for run in runs
    )
    if max_ab > 500:
        print(f"WARNING: at least one run has an extreme alpha/beta (max={max_ab:.1f}) "
              f"even after regularization - inspect m3_beta_mixture_params.csv before trusting it.")

    best = max(runs, key=lambda d: d["loglik"])
    warm = runs[0]
    print(f"\nBest run: {best['label']} (logL={best['loglik']:.4f})")

    # Convergence-robustness note: compare warm-start vs. best-overall.
    warm_hard = warm["r"] > 0.5
    best_hard = best["r"] > 0.5
    inter = np.logical_and(warm_hard, best_hard).sum()
    union = np.logical_or(warm_hard, best_hard).sum()
    jaccard_warm_vs_best = inter / union if union else float("nan")
    ll_delta_warm_vs_best = best["loglik"] - warm["loglik"]
    print(f"Warm-start vs best-restart: loglik delta = {ll_delta_warm_vs_best:.4f}, "
          f"Jaccard(r>0.5) = {jaccard_warm_vs_best:.4f}")

    # ---- post-hoc label-switching fix: "M" = component with the larger
    # weighted mean of s_text + s_cpv (the two content-based signals) ----
    idx_text, idx_cpv = DIMS.index("s_text"), DIMS.index("s_cpv")
    comp0_content = best["mean_M"][idx_text] + best["mean_M"][idx_cpv]
    comp1_content = best["mean_U"][idx_text] + best["mean_U"][idx_cpv]
    if comp1_content > comp0_content:
        print("Swapping M/U labels post-hoc (component 1 has more content-signal mass).")
        best["p"] = 1 - best["p"]
        (best["alpha_M"], best["alpha_U"]) = (best["alpha_U"], best["alpha_M"])
        (best["beta_M"], best["beta_U"]) = (best["beta_U"], best["beta_M"])
        (best["mean_M"], best["mean_U"]) = (best["mean_U"], best["mean_M"])
        (best["var_M"], best["var_U"]) = (best["var_U"], best["var_M"])
        best["r"] = 1 - best["r"]

    p_hat = best["p"]
    r = best["r"]
    gaps = best["mean_M"] - best["mean_U"]
    gap_rank = np.argsort(-np.abs(gaps))

    print(f"\np_hat = {p_hat:.4f}")
    for d in gap_rank:
        print(f"  {DIMS[d]:8s}: mean_M={best['mean_M'][d]:.4f}  mean_U={best['mean_U'][d]:.4f}"
              f"  gap={gaps[d]:+.4f}")

    # ---- m3_beta_mixture_params.csv ----
    param_rows = [{
        "class": "mixing_weight", "dimension": "p_hat", "alpha": np.nan, "beta": np.nan,
        "weighted_mean": p_hat, "weighted_var": np.nan, "gap_m_minus_u": np.nan,
        "gap_rank": np.nan,
    }]
    for rank_pos, d in enumerate(gap_rank):
        for cls, a_arr, b_arr, m_arr, v_arr in [
            ("M", best["alpha_M"], best["beta_M"], best["mean_M"], best["var_M"]),
            ("U", best["alpha_U"], best["beta_U"], best["mean_U"], best["var_U"]),
        ]:
            param_rows.append({
                "class": cls, "dimension": DIMS[d],
                "alpha": a_arr[d], "beta": b_arr[d],
                "weighted_mean": m_arr[d], "weighted_var": v_arr[d],
                "gap_m_minus_u": gaps[d], "gap_rank": rank_pos + 1,
            })
    params_df = pd.DataFrame(param_rows)
    params_df.to_csv(TABLES_DIR / "m3_beta_mixture_params.csv", index=False)
    print(f"\nWrote {TABLES_DIR / 'm3_beta_mixture_params.csv'}")

    # ---- convergence robustness note appended to params file's sibling ----
    conv_row = pd.DataFrame([{
        "best_run_label": best["label"], "best_loglik": best["loglik"],
        "warm_start_loglik": warm["loglik"],
        "loglik_delta_warm_vs_best": ll_delta_warm_vs_best,
        "jaccard_warm_vs_best_r_gt_half": jaccard_warm_vs_best,
        "n_restarts_total": len(runs),
    }])
    conv_row.to_csv(TABLES_DIR / "m3_em_convergence_check.csv", index=False)

    # ---- m3_posteriors.csv ----
    post_df = pairs[["source_notice_id", "candidate_notice_id", "candidate_rank",
                      "m0_composite_score", "in_balanced_linked_set"]].copy()
    post_df["posterior_M"] = r
    post_df.to_csv(TABLES_DIR / "m3_posteriors.csv", index=False)
    print(f"Wrote {TABLES_DIR / 'm3_posteriors.csv'}")

    # ---- m3_precision_recall.csv ----
    in_link = pairs["in_balanced_linked_set"].to_numpy()
    TP_hat = r[in_link].sum()
    FN_hat = r[~in_link].sum()
    n_linked = int(in_link.sum())
    precision_hat = TP_hat / n_linked
    recall_hat = TP_hat / (TP_hat + FN_hat)
    pr_df = pd.DataFrame([{
        "TP_hat": TP_hat, "FN_hat": FN_hat, "n_linked_balanced": n_linked,
        "n_omega": N, "precision_hat": precision_hat, "recall_hat": recall_hat,
        "scope_caveat": (
            "Recall_hat is defined relative to Omega (all 6,137 candidate pairs, "
            "i.e. pairs surviving buyer_key + temporal-window blocking) only. It "
            "structurally excludes the 1,923 of 3,159 eligible sources that had zero "
            "candidates in blocking, so it cannot bound recall against all possible "
            "true renewals - only against renewals that could in principle have been "
            "found given the current blocking rule."
        ),
    }])
    pr_df.to_csv(TABLES_DIR / "m3_precision_recall.csv", index=False)
    print(f"\nPrecision_hat = {precision_hat:.4f}  Recall_hat = {recall_hat:.4f}")
    print(f"Wrote {TABLES_DIR / 'm3_precision_recall.csv'}")

    # ---- m3_conditional_independence_check.csv ----
    linked_pairs = pairs[pairs["in_balanced_linked_set"]]
    pear_r, pear_p = pearsonr(linked_pairs["s_cpv"], linked_pairs["s_text"])
    spear_r, spear_p = spearmanr(linked_pairs["s_cpv"], linked_pairs["s_text"])
    ci_df = pd.DataFrame([{
        "n_linked_pairs": len(linked_pairs),
        "pearson_r_cpv_text": pear_r, "pearson_p_cpv_text": pear_p,
        "spearman_r_cpv_text": spear_r, "spearman_p_cpv_text": spear_p,
        "flag_high_correlation_gt_0_3": bool(abs(pear_r) > 0.3 or abs(spear_r) > 0.3),
    }])
    ci_df.to_csv(TABLES_DIR / "m3_conditional_independence_check.csv", index=False)
    print(f"Conditional-independence check (s_cpv vs s_text among balanced links): "
          f"pearson r={pear_r:.4f}, spearman r={spear_r:.4f}")
    if abs(pear_r) > 0.3 or abs(spear_r) > 0.3:
        print("WARNING: conditional-independence assumption looks violated "
              "(|r| > 0.3) - a known bias source for Fellegi-Sunter mixture "
              "estimates; not corrected here, only flagged per the method spec.")
    print(f"Wrote {TABLES_DIR / 'm3_conditional_independence_check.csv'}")


if __name__ == "__main__":
    main()
