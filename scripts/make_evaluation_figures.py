"""
Step 16 - Figures for the linkage quality evaluation (Methods 3, 4, 6).

Input:  reports/tables/m3_beta_mixture_params.csv, m3_posteriors.csv
        reports/tables/m4_recovery_by_severity.csv
        reports/tables/m6a_threshold_sweep.csv, m6a_threshold_sensitivity.csv
        reports/tables/m6b_feature_ablation.csv
        data/processed/boamp_survival_m0_broad.csv, boamp_survival_m0_strict.csv
        data/processed/boamp_m0_candidate_pairs.csv, boamp_m0_links_balanced.csv
        reports/tables/m0_method_summary.csv
Output: reports/figures/11_..16_*.png / .pdf

Palette/rcParams block copied verbatim from scripts/make_figures.py so all
figures in the report render as one visual system.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter
from scipy.stats import beta as beta_dist

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
FIG_DIR = PROJECT_ROOT / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ---- palette tokens (copied from scripts/make_figures.py) ----
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

CAT = {
    "blue": "#2a78d6", "aqua": "#1baf7a", "yellow": "#eda100", "green": "#008300",
    "violet": "#4a3aa7", "red": "#e34948", "magenta": "#e87ba4", "orange": "#eb6834",
}
CAT_ORDER = ["blue", "aqua", "yellow", "green", "violet", "red", "magenta", "orange"]

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK_PRIMARY,
    "text.color": INK_PRIMARY,
    "xtick.color": INK_SECONDARY,
    "ytick.color": INK_SECONDARY,
    "axes.grid": True,
    "grid.color": GRIDLINE,
    "grid.linewidth": 0.7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.family": "sans-serif",
    "font.size": 10.5,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "figure.dpi": 120,
})

DIMS = ["s_text", "s_cpv", "s_time", "s_buyer"]
DIM_LABELS = {"s_text": "s_text (TF-IDF cosine)", "s_cpv": "s_cpv (CPV hierarchy)",
              "s_time": "s_time (temporal decay)", "s_buyer": "s_buyer (buyer-key reliability)"}


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"{name}.pdf")
    fig.savefig(FIG_DIR / f"{name}.png", dpi=200)
    plt.close(fig)
    print(f"Saved {name}.pdf / .png")


def fig11_beta_mixture_densities():
    pairs = pd.read_csv(PROCESSED_DIR / "boamp_m0_candidate_pairs.csv")
    params = pd.read_csv(TABLES_DIR / "m3_beta_mixture_params.csv")
    p_hat = params.loc[params["dimension"] == "p_hat", "weighted_mean"].iloc[0]

    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    for ax, dim in zip(axes.ravel(), DIMS):
        x = pairs[dim].to_numpy(dtype=float)
        ax.hist(x, bins=40, density=True, color=CAT["blue"], alpha=0.35,
                edgecolor="none", label="empirical (Omega)")
        grid = np.linspace(1e-4, 1 - 1e-4, 400)
        row_M = params[(params["class"] == "M") & (params["dimension"] == dim)].iloc[0]
        row_U = params[(params["class"] == "U") & (params["dimension"] == dim)].iloc[0]
        dens_M = p_hat * beta_dist.pdf(grid, row_M["alpha"], row_M["beta"])
        dens_U = (1 - p_hat) * beta_dist.pdf(grid, row_U["alpha"], row_U["beta"])
        ax.plot(grid, dens_M, color=CAT["red"], linewidth=1.8, label="p * P(gamma|M)")
        ax.plot(grid, dens_U, color=CAT["aqua"], linewidth=1.8, label="(1-p) * P(gamma|U)")
        ax.set_title(DIM_LABELS[dim])
        ax.set_xlabel("score value")
        ax.set_ylabel("density")
    axes[0, 0].legend(fontsize=8, frameon=False)
    fig.suptitle("Method 3: fitted Beta-mixture densities vs. empirical score histograms", y=1.02)
    save(fig, "11_beta_mixture_densities")


def fig12_posterior_by_linkage():
    post = pd.read_csv(TABLES_DIR / "m3_posteriors.csv")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    bins = np.linspace(0, 1, 41)
    ax.hist(post.loc[~post["in_balanced_linked_set"], "posterior_M"], bins=bins, density=True,
            color=CAT["aqua"], alpha=0.55, label="not in balanced-linked set (n=%d)" %
            (~post["in_balanced_linked_set"]).sum())
    ax.hist(post.loc[post["in_balanced_linked_set"], "posterior_M"], bins=bins, density=True,
            color=CAT["red"], alpha=0.55, label="in balanced-linked set (n=%d)" %
            post["in_balanced_linked_set"].sum())
    ax.set_xlabel("Posterior P(M | gamma)")
    ax.set_ylabel("density")
    ax.set_title("Method 3: posterior match probability by real linkage status")
    ax.legend(fontsize=9, frameon=False)
    save(fig, "12_beta_mixture_posterior_by_linkage")


def fig13_corruption_recovery_curves():
    rec = pd.read_csv(TABLES_DIR / "m4_recovery_by_severity.csv")
    colors = {"text_only": CAT["blue"], "cpv_only": CAT["yellow"],
              "duration_only": CAT["aqua"], "combined": CAT["red"]}
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for sweep, color in colors.items():
        sub = rec[rec["sweep"] == sweep].sort_values("severity")
        ax.plot(sub["severity"], sub["R"], marker="o", color=color, linewidth=1.8, label=sweep)
    ax.set_xlabel("Corruption severity level")
    ax.set_ylabel("Recovery rate R(level)")
    ax.set_xticks([0, 1, 2, 3])
    ax.set_ylim(0, 1.05)
    ax.set_title("Method 4: recovery of S* (n=309 strict links) under corruption")
    ax.legend(fontsize=9, frameon=False)
    save(fig, "13_corruption_recovery_curves")


def fig14_threshold_sensitivity():
    sweep = pd.read_csv(TABLES_DIR / "m6a_threshold_sweep.csv")
    pairs = pd.read_csv(PROCESSED_DIR / "boamp_m0_candidate_pairs.csv")
    rank1_scores = pairs.loc[pairs["candidate_rank"] == 1, "m0_composite_score"].to_numpy()
    method_summary = pd.read_csv(TABLES_DIR / "m0_method_summary.csv").set_index("variant")
    thr = {v: method_summary.loc[v, "threshold_composite_score"] for v in ["broad", "balanced", "strict"]}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

    ax1.plot(sweep["percentile"], sweep["event_rate"], color=CAT["blue"], linewidth=1.8, marker="o", markersize=3)
    for v, color in zip(["broad", "balanced", "strict"], [CAT["aqua"], CAT["red"], CAT["violet"]]):
        pct = {"broad": 25, "balanced": 50, "strict": 75}[v]
        ax1.axvline(pct, color=color, linestyle="--", linewidth=1.1, label=v)
    ax1.set_xlabel("Threshold percentile (of rank-1 score distribution)")
    ax1.set_ylabel("Linkage rate rho(tau)")
    ax1.set_title("(a) rho(tau) sweep")
    ax1.legend(fontsize=8, frameon=False)

    ax2.hist(rank1_scores, bins=60, color=CAT["blue"], alpha=0.4, edgecolor="none")
    for v, color in zip(["broad", "balanced", "strict"], [CAT["aqua"], CAT["red"], CAT["violet"]]):
        ax2.axvline(thr[v], color=color, linestyle="--", linewidth=1.4, label=f"{v} ({thr[v]:.3f})")
    ax2.set_xlim(thr["broad"] - 0.08, thr["strict"] + 0.08)
    ax2.set_xlabel("m0_composite_score (rank-1 candidates)")
    ax2.set_ylabel("count")
    ax2.set_title("(b) local score density near thresholds")
    ax2.legend(fontsize=8, frameon=False)

    save(fig, "14_threshold_sensitivity")


def fig15_feature_ablation_jaccard():
    abl = pd.read_csv(TABLES_DIR / "m6b_feature_ablation.csv").sort_values("jaccard_vs_real_balanced")
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = [CAT_ORDER[i % len(CAT_ORDER)] for i in range(len(abl))]
    bar_colors = [CAT[c] for c in colors]
    ax.barh(abl["dropped_component"], abl["jaccard_vs_real_balanced"], color=bar_colors)
    ax.set_xlabel("Jaccard overlap with real balanced link set")
    ax.set_xlim(0, 1)
    ax.set_title("Method 6b: link-set stability when each component is dropped")
    for i, v in enumerate(abl["jaccard_vs_real_balanced"]):
        ax.text(v + 0.015, i, f"{v:.3f}", va="center", fontsize=9)
    save(fig, "15_feature_ablation_jaccard")


def fig16_km_by_division():
    divisions = ["32", "35", "48", "72"]
    div_colors = {"32": CAT["blue"], "35": CAT["aqua"], "48": CAT["yellow"], "72": CAT["red"]}
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, variant in zip([ax1, ax2], ["broad", "strict"]):
        surv = pd.read_csv(PROCESSED_DIR / f"boamp_survival_m0_{variant}.csv",
                            dtype={"cpv_division": str})
        for div in divisions:
            grp = surv[surv["cpv_division"] == div]
            if len(grp) == 0:
                continue
            kmf = KaplanMeierFitter()
            kmf.fit(grp["time_to_event_or_censor_months"], grp["event"], label=f"CPV {div}")
            kmf.plot_survival_function(ax=ax, color=div_colors[div], ci_show=False, linewidth=1.6)
        ax.set_title(f"{variant} variant")
        ax.set_xlabel("Months since publication")
        ax.set_xlim(0, 72)
        ax.legend(fontsize=8, frameon=False)
    ax1.set_ylabel("Survival probability (not-yet-renewed)")
    fig.suptitle("Method 6c: Kaplan-Meier by CPV division, broad vs strict linkage variant", y=1.02)
    save(fig, "16_km_by_cpv_division_broad_vs_strict")


def main():
    fig11_beta_mixture_densities()
    fig12_posterior_by_linkage()
    fig13_corruption_recovery_curves()
    fig14_threshold_sensitivity()
    fig15_feature_ablation_jaccard()
    fig16_km_by_division()


if __name__ == "__main__":
    main()
