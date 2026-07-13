"""
Step 17 - Two supplementary figures for the comprehensive technical report
(reports/boamp_m0_technical_report.tex), matching the visual system already
used by scripts/make_figures.py and scripts/make_evaluation_figures.py.

Output: reports/figures/17_km_overall_variants.png / .pdf
        reports/figures/18_cox_forest_balanced_noncpv.png / .pdf
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from lifelines import KaplanMeierFitter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
FIG_DIR = PROJECT_ROOT / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

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


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"{name}.pdf")
    fig.savefig(FIG_DIR / f"{name}.png", dpi=200)
    plt.close(fig)
    print(f"Saved {name}.pdf / .png")


def fig17_km_overall():
    colors = {"broad": CAT["aqua"], "balanced": CAT["red"], "strict": CAT["violet"]}
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for variant, color in colors.items():
        surv = pd.read_csv(PROCESSED_DIR / f"boamp_survival_m0_{variant}.csv")
        kmf = KaplanMeierFitter()
        kmf.fit(surv["time_to_event_or_censor_months"], surv["event"], label=variant)
        n = len(surv)
        events = int(surv["event"].sum())
        kmf.plot_survival_function(
            ax=ax, color=color, ci_show=True, linewidth=1.8,
            label=f"{variant} (n={n}, events={events})",
        )
    ax.axhline(0.5, color=INK_MUTED, linestyle=":", linewidth=1.0)
    ax.set_xlim(0, 96)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Months since source publication date")
    ax.set_ylabel("Survival probability (not-yet-linked)")
    ax.set_title("Kaplan–Meier: time to a linked M0 proxy-renewal event")
    ax.legend(fontsize=8.5, frameon=False, loc="lower left")
    save(fig, "17_km_overall_variants")


def fig18_cox_forest():
    cox = pd.read_csv(TABLES_DIR / "survival_cox_models.csv")
    bal = cox[(cox["variant"] == "balanced") & (~cox["term"].str.startswith("cpv_division"))].copy()
    label_map = {
        "log_duration": "log(1 + declared duration, months)",
        "dur_was_imputed": "duration was imputed (0/1)",
        "buyer_key_type_RAW_SIRET": "buyer key = RAW_SIRET (ref: NAME_FALLBACK)",
    }
    bal["label"] = bal["term"].map(label_map).fillna(bal["term"])
    bal = bal.sort_values("exp_coef")

    fig, ax = plt.subplots(figsize=(8.5, 3.4))
    y = list(range(len(bal)))
    colors = [CAT["red"] if p < 0.05 else INK_MUTED for p in bal["p"]]
    for yi, (_, row), c in zip(y, bal.iterrows(), colors):
        xerr_low = row["exp_coef"] - row["ci_lower"]
        xerr_high = row["ci_upper"] - row["exp_coef"]
        ax.errorbar(row["exp_coef"], yi, xerr=[[xerr_low], [xerr_high]], fmt="o",
                    color=c, ecolor=c, elinewidth=1.8, capsize=3, markersize=6)
    ax.axvline(1.0, color=INK_MUTED, linestyle="--", linewidth=1.0)
    ax.set_yticks(y)
    ax.set_yticklabels(bal["label"])
    ax.set_xlabel("Hazard ratio (buyer-clustered robust 95% CI)")
    ax.set_title("Balanced clustered Cox model: non-CPV terms")
    save(fig, "18_cox_forest_balanced_noncpv")


def main():
    fig17_km_overall()
    fig18_cox_forest()


if __name__ == "__main__":
    main()
