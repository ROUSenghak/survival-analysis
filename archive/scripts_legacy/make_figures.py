"""
Step 10 - Academic-style figures for the BOAMP M0 pipeline.

Palette and mark choices follow the project's dataviz guidance: light
surface, soft/desaturated categorical hues assigned in a fixed order,
one axis per chart, thin recessive gridlines, no 3D, minimal clutter.
Every figure is saved as both PDF and PNG under reports/figures/.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
FIG_DIR = PROJECT_ROOT / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ---- palette tokens (light mode, from the project's dataviz reference) ----
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


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"{name}.pdf")
    fig.savefig(FIG_DIR / f"{name}.png", dpi=200)
    plt.close(fig)
    print(f"Saved {name}.pdf / .png")


def bar_by_year(series, title, ylabel, name, color=CAT["blue"]):
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(series.index.astype(str), series.values, color=color, width=0.62,
           edgecolor="none")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Publication year")
    ax.grid(axis="x")
    for spine in ["left"]:
        ax.spines[spine].set_color(BASELINE)
    save(fig, name)


def main():
    clean = pd.read_csv(PROCESSED_DIR / "boamp_clean_m0_no_enrichment.csv", low_memory=False,
                         parse_dates=["publication_date"])
    sources = pd.read_csv(PROCESSED_DIR / "boamp_m0_sources.csv",
                           parse_dates=["publication_date", "estimated_end_date"])
    pairs = pd.read_csv(PROCESSED_DIR / "boamp_m0_candidate_pairs.csv")
    event_counts = pd.read_csv(TABLES_DIR / "m0_event_counts.csv")
    score_dist = pd.read_csv(TABLES_DIR / "m0_score_distribution_summary.csv")

    clean["publication_year"] = clean["publication_date"].dt.year
    sources["publication_year"] = sources["publication_date"].dt.year

    # 1. Notice count by year
    bar_by_year(clean.groupby("publication_year").size(),
                "BOAMP notices retrieved by publication year",
                "Notices", "01_notice_count_by_year", color=CAT["blue"])

    # 2. APPEL_OFFRE count by year
    bar_by_year(sources.groupby("publication_year").size(),
                "APPEL_OFFRE (source) notices by publication year",
                "APPEL_OFFRE notices", "02_appel_offre_count_by_year", color=CAT["aqua"])

    # 3. Buyer key type by year (stacked, share)
    bkt = (clean.groupby(["publication_year", "buyer_key_type"]).size()
           .unstack(fill_value=0))
    bkt_share = bkt.div(bkt.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    bottom = pd.Series(0.0, index=bkt_share.index)
    key_types = ["RAW_SIRET", "RAW_SIREN", "NAME_FALLBACK", "MISSING"]
    colors = [CAT["blue"], CAT["aqua"], CAT["yellow"], INK_MUTED]
    for kt, col in zip(key_types, colors):
        if kt not in bkt_share.columns:
            continue
        ax.bar(bkt_share.index.astype(str), bkt_share[kt], bottom=bottom, label=kt,
               color=col, width=0.62, edgecolor=SURFACE, linewidth=1.5)
        bottom += bkt_share[kt]
    ax.set_title("Buyer identifier source (buyer_key_type) share by year")
    ax.set_ylabel("Share of notices")
    ax.set_xlabel("Publication year")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=4, fontsize=9)
    save(fig, "03_buyer_key_type_by_year")

    # 4. CPV coverage by year (sources)
    cpv_cov = sources.groupby("publication_year").apply(lambda g: 1 - g["cpv_clean"].isna().mean())
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(cpv_cov.index.astype(str), cpv_cov.values, marker="o", color=CAT["violet"],
            linewidth=2, markersize=6)
    ax.set_ylim(0, 1.02)
    ax.set_title("CPV coverage among APPEL_OFFRE sources, by year")
    ax.set_ylabel("Share with a valid CPV code")
    ax.set_xlabel("Publication year")
    save(fig, "04_cpv_coverage_by_year")

    # 5. Duration missingness by year (pre-imputation)
    dur_missing = sources.groupby("publication_year").apply(
        lambda g: g["dur_was_imputed"].mean()
    )
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(dur_missing.index.astype(str), dur_missing.values, marker="o", color=CAT["orange"],
            linewidth=2, markersize=6)
    ax.set_ylim(0, 1.02)
    ax.set_title("Declared-duration imputation rate among APPEL_OFFRE sources, by year")
    ax.set_ylabel("Share with imputed duration")
    ax.set_xlabel("Publication year")
    save(fig, "05_duration_missingness_by_year")

    # 6. Candidate count distribution (per source)
    if len(pairs):
        n_cand = pairs.groupby("source_notice_id").size()
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(n_cand.values, bins=range(1, int(n_cand.max()) + 2), color=CAT["blue"],
                edgecolor=SURFACE, linewidth=0.8)
        ax.set_title("Distribution of candidate count per source notice")
        ax.set_xlabel("Number of candidates")
        ax.set_ylabel("Number of source notices")
        save(fig, "06_candidate_count_distribution")

    # 7. M0 score distribution (composite, rank-1 best candidate)
    if len(pairs):
        rank1 = pairs[pairs["candidate_rank"] == 1]
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(rank1["m0_composite_score"], bins=30, color=CAT["aqua"], edgecolor=SURFACE, linewidth=0.6)
        ax.set_title("M0 composite score distribution (best candidate per source)")
        ax.set_xlabel("m0_composite_score")
        ax.set_ylabel("Source notices")
        save(fig, "07_m0_score_distribution")

    # 8. Event count by method variant
    method_summary = pd.read_csv(TABLES_DIR / "m0_method_summary.csv")
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(method_summary["variant"], method_summary["n_linked_events"],
           color=[CAT["yellow"], CAT["aqua"], CAT["blue"]], width=0.55)
    ax.set_title("M0 event count by method variant")
    ax.set_ylabel("Linked events")
    ax.set_xlabel("Variant")
    save(fig, "08_event_count_by_variant")

    # 9. M0 event count by year (balanced variant)
    ev_balanced = event_counts[event_counts["variant"] == "balanced"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(ev_balanced["publication_year"].astype(str), ev_balanced["n_events"],
           color=CAT["blue"], width=0.6)
    ax.set_title("M0 event count by publication year (balanced variant)")
    ax.set_xlabel("Publication year")
    ax.set_ylabel("Linked events")
    save(fig, "09_event_count_by_year_balanced")

    # 10. Top buyer event counts (balanced)
    links_balanced = pd.read_csv(PROCESSED_DIR / "boamp_m0_links_balanced.csv")
    if len(links_balanced):
        top_buyers = links_balanced["buyer_key"].value_counts().head(10)[::-1]
        fig, ax = plt.subplots(figsize=(7.5, 5))
        ax.barh([str(b)[:40] for b in top_buyers.index], top_buyers.values, color=CAT["violet"])
        ax.set_title("Top 10 buyers by M0 event count (balanced variant)")
        ax.set_xlabel("Linked events")
        save(fig, "10_top_buyer_event_counts")

    print("\nAll figures written to", FIG_DIR)


if __name__ == "__main__":
    main()
