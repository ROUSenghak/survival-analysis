"""Diagnostic and report figures for the v0.4 population/alias revision.

Every figure carries one specific claim in the v0.4 report; none is decorative.
Each shows real BOAMP, the original v0.3 synthetic corpus and the revised v0.4
corpus wherever all three exist, states its evaluation population and sample
size, marks the predeclared tolerance band where one applies, and records the
artifact it was built from.

Colour: the project's validated three-slot categorical palette -- blue #2a78d6
(real), orange #eb6834 (original v0.3), aqua #1baf7a (revised v0.4). Checked as
an all-pairs set in OKLab: normal-vision separations are 24.0-33.6 and the worst
CVD separation is 9.2 (deuteranope, v0.3 vs v0.4), both above the >=15 and >=8
floors. Identity is never colour-alone: every series is also legended and drawn
in its own line style, and marker shape distinguishes the two synthetic
versions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.config import load_config  # noqa: E402
from boamp.data.prepare import tag_digital_scope  # noqa: E402
from boamp.linkage.candidates import generate_pairs_single_key  # noqa: E402
from boamp.synthetic.acceptance import (  # noqa: E402
    _candidate_count_frame,
    within_group_similarity,
)
from boamp.synthetic.compatibility import adapt_observed_notices_to_sources  # noqa: E402
from boamp.synthetic.validation_framework.loaders import load_benchmark_data  # noqa: E402
from utils.text_clean import normalize_objet  # noqa: E402

NEW_VERSION = "v0_4_population_alias_revision"
OLD_VERSION = "v0_3_temporal_candidate_revision"
SCENARIO = "central_provisional"

FIG_DIR = ROOT / "reports" / "figures" / "synthetic_benchmark" / NEW_VERSION
TABLES = ROOT / "reports" / "tables" / "synthetic_benchmark" / NEW_VERSION
BASELINE = TABLES / "baseline_v0_3"

REAL_C = "#2a78d6"
OLD_C = "#eb6834"
NEW_C = "#1baf7a"
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
RULE = "#c3c2b7"
TOL_C = "#898781"

SERIES = {
    "real": {"color": REAL_C, "ls": "-", "marker": "o", "label": "Real BOAMP"},
    "old": {"color": OLD_C, "ls": "--", "marker": "s", "label": "Synthetic v0.3"},
    "new": {"color": NEW_C, "ls": "-.", "marker": "^", "label": "Synthetic v0.4"},
}

plt.rcParams.update({
    "figure.dpi": 160,
    "savefig.dpi": 160,
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.edgecolor": RULE,
    "axes.labelcolor": INK,
    "axes.titlecolor": INK,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.frameon": False,
    "legend.fontsize": 8,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "figure.facecolor": "white",
    "savefig.bbox": "tight",
    "lines.linewidth": 2.0,
})

INDEX: list[dict] = []


def _despine(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_axisbelow(True)


def _finish(fig, stem: str, caption: str, source: str, population: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.text(
        0.005, -0.02, f"Source: {source}", ha="left", va="top", fontsize=6.5, color=MUTED
    )
    for suffix in ("pdf", "png"):
        fig.savefig(FIG_DIR / f"{stem}.{suffix}")
    plt.close(fig)
    INDEX.append(
        {"figure": stem, "caption": caption, "source": source, "evaluation_population": population}
    )
    print(f"  wrote {stem}")


def _ecdf(values) -> tuple[np.ndarray, np.ndarray]:
    x = np.sort(np.asarray(values, dtype=float))
    x = x[np.isfinite(x)]
    return x, np.arange(1, len(x) + 1) / max(1, len(x))


def _lorenz(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.sort(np.asarray(values, dtype=float))
    cum = np.cumsum(x)
    return np.arange(1, len(x) + 1) / len(x), cum / cum[-1]


def _gini(values: np.ndarray) -> float:
    x = np.sort(np.asarray(values, dtype=float))
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum())) if n and x.sum() else np.nan


def _tolerance_band(ax, centre: float, tolerance: float, label: str = "tolerance") -> None:
    """Shaded predeclared tolerance band, labelled clear of the plotted marks."""
    ax.axhspan(centre - tolerance, centre + tolerance, color=TOL_C, alpha=0.12, zorder=0)
    ax.axhline(centre, color=TOL_C, lw=0.8, ls=":", zorder=1)
    ax.annotate(
        label, xy=(0.5, 1.0), xycoords="axes fraction", xytext=(0, 3),
        textcoords="offset points", ha="center", va="bottom", fontsize=7, color=MUTED,
    )


# ---------------------------------------------------------------------------
# shared data assembly
# ---------------------------------------------------------------------------


class Corpora:
    """Real, v0.3 and v0.4 corpora in one comparable shape."""

    def __init__(self, project_root: Path, scenario: str = SCENARIO) -> None:
        self.cfg = load_config(project_root)
        self.real = pd.read_csv(
            project_root / "data" / "interim" / "boamp_common_prepared.csv",
            usecols=[
                "notice_id", "publication_date", "publication_year", "schema_family",
                "notice_type_normalized", "buyer_siret_clean", "buyer_siren_clean",
                "buyer_name_normalized", "buyer_key", "buyer_key_type", "cpv_clean",
                "duration_raw",
            ],
            parse_dates=["publication_date"], low_memory=False,
        )
        self.real_sources = pd.read_csv(
            project_root / "data" / "processed" / "boamp_only" / "boamp_only_sources.csv",
            parse_dates=["publication_date"],
        )
        self.real_pairs = pd.read_csv(
            project_root / "data" / "processed" / "boamp_only" / "boamp_only_candidate_pairs.csv"
        )
        self.old = self._load_version(project_root, OLD_VERSION, scenario)
        self.new = self._load_version(project_root, NEW_VERSION, scenario)

    @staticmethod
    def _load_version(project_root: Path, version: str, scenario: str) -> pd.DataFrame | None:
        try:
            data = load_benchmark_data(project_root, version, scenario, "001", "001")
        except FileNotFoundError:
            print(f"  (skipping {version}: no generated artifact)")
            return None
        sources = adapt_observed_notices_to_sources(data.observed)
        sources["publication_year"] = pd.to_datetime(sources["publication_date"]).dt.year
        return sources

    def available(self) -> dict[str, pd.DataFrame]:
        return {k: v for k, v in (("old", self.old), ("new", self.new)) if v is not None}

    def activity(self, frame: pd.DataFrame) -> pd.Series:
        eligible = frame.loc[frame["buyer_key_type"].astype(str).ne("MISSING")]
        return eligible.groupby("buyer_key").size()

    def candidate_counts(self, frame: pd.DataFrame) -> pd.DataFrame:
        scoped = frame.copy()
        scoped["objet_normalized"] = scoped["objet_clean"].map(normalize_objet)
        scoped["is_digital_scope"] = scoped.apply(
            lambda row: tag_digital_scope(row["cpv_division"], row["objet_normalized"], self.cfg),
            axis=1,
        )
        scoped = scoped.loc[
            scoped["notice_type_normalized"].eq("APPEL_OFFRE") & scoped["is_digital_scope"]
        ].copy()
        pairs, _ = generate_pairs_single_key(scoped, self.cfg, verbose=False)
        return _candidate_count_frame(scoped, pairs)


# ---------------------------------------------------------------------------
# 1. buyer activity
# ---------------------------------------------------------------------------


def fig_buyer_activity(c: Corpora) -> None:
    real_a = c.activity(c.real)
    series = {"real": real_a} | {k: c.activity(v) for k, v in c.available().items()}

    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.2))
    for key, activity in series.items():
        style = SERIES[key]
        ordered = np.sort(activity.to_numpy())[::-1]
        rank = np.arange(1, len(ordered) + 1) / len(ordered)
        axes[0].plot(rank, ordered, color=style["color"], ls=style["ls"],
                     label=f"{style['label']} (n={len(ordered):,})")
        x, y = _lorenz(activity.to_numpy())
        axes[1].plot(x, y, color=style["color"], ls=style["ls"],
                     label=f"{style['label']}  G={_gini(activity.to_numpy()):.3f}")
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("buyer rank (normalised, log scale)")
    axes[0].set_ylabel("notices published (log scale)")
    axes[0].set_title("Rank-frequency of buyer activity")
    axes[1].plot([0, 1], [0, 1], color=RULE, lw=0.8, ls=":")
    axes[1].set_xlabel("cumulative share of buyers")
    axes[1].set_ylabel("cumulative share of notices")
    axes[1].set_title("Lorenz curve and Gini")
    for ax in axes:
        _despine(ax)
        ax.legend(loc="best")
    fig.suptitle(
        "Buyer activity concentration, measured on observed production buyer keys",
        y=1.02, fontsize=10.5,
    )
    fig.tight_layout()
    _finish(
        fig, "v04_fig_buyer_activity_concentration",
        "v0.3 spread the same notice volume over roughly twice as many observed buyer keys as "
        "real BOAMP, flattening the rank-frequency curve and lowering the Gini; v0.4 restores "
        "both. Units: notices per buyer key.",
        "data/processed/synthetic_benchmark/{v0_3,v0_4}/central_provisional/world_001 and "
        "data/interim/boamp_common_prepared.csv",
        "all notices with a non-MISSING production buyer key",
    )


def fig_activity_tail(c: Corpora) -> None:
    real_a = c.activity(c.real)
    series = {"real": real_a} | {k: c.activity(v) for k, v in c.available().items()}
    quantiles = [0.50, 0.75, 0.90, 0.95, 0.99]

    fig, axes = plt.subplots(1, 3, figsize=(10.4, 3.3))

    # CCDF -- the shape the tail fit is about.
    for key, activity in series.items():
        style = SERIES[key]
        x, y = _ecdf(activity.to_numpy())
        axes[0].plot(x, 1 - y, color=style["color"], ls=style["ls"], label=style["label"])
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("notices per buyer key (log scale)")
    axes[0].set_ylabel("P(activity > x)")
    axes[0].set_title("Survival function of buyer activity")
    axes[0].legend(loc="best")

    # Relative quantiles -- the gated statistic.
    width = 0.26
    positions = np.arange(len(quantiles))
    for offset, (key, activity) in enumerate(series.items()):
        style = SERIES[key]
        relative = activity / activity.mean()
        axes[1].bar(
            positions + (offset - 1) * width,
            [relative.quantile(q) for q in quantiles],
            width=width * 0.92, color=style["color"], label=style["label"],
            edgecolor="white", linewidth=1.0,
        )
    axes[1].set_xticks(positions)
    axes[1].set_xticklabels([f"q{int(q * 100)}" for q in quantiles])
    axes[1].set_yscale("log")
    axes[1].set_xlabel("quantile of the activity distribution")
    axes[1].set_ylabel("activity / corpus mean activity")
    axes[1].set_title("Scale-free activity quantiles")
    axes[1].legend(loc="best")

    # q99 deviation against its predeclared tolerance -- the failing metric.
    real_rel = real_a / real_a.mean()
    deviations = {}
    for key, activity in series.items():
        if key == "real":
            continue
        rel = activity / activity.mean()
        deviations[key] = float(rel.quantile(0.99) - real_rel.quantile(0.99))
    axes[2].axhline(0, color=RULE, lw=0.8)
    _tolerance_band(axes[2], 0.0, 1.0, "predeclared tolerance +/-1.0")
    for i, (key, value) in enumerate(deviations.items()):
        style = SERIES[key]
        axes[2].bar(i, value, width=0.5, color=style["color"], edgecolor="white", linewidth=1.0)
        axes[2].annotate(
            f"{value:+.2f}", xy=(i, value), ha="center",
            va="bottom" if value >= 0 else "top", fontsize=8, color=INK,
        )
    axes[2].set_xticks(range(len(deviations)))
    axes[2].set_xticklabels([SERIES[k]["label"] for k in deviations])
    axes[2].set_ylabel("synthetic minus real, relative q99")
    axes[2].set_title("q99 deviation vs tolerance")

    for ax in axes:
        _despine(ax)
    fig.suptitle("Upper tail of buyer activity", y=1.03, fontsize=10.5)
    fig.tight_layout()
    _finish(
        fig, "v04_fig_buyer_activity_tail",
        "The extreme tail (q99.9, maximum) already matched in v0.3; the deficit was in the "
        "upper-middle tail and was produced by buyer-key fragmentation, not by the tail family. "
        "Units: notices per buyer key, divided by each corpus's own mean.",
        "data/processed/synthetic_benchmark/{v0_3,v0_4}/central_provisional/world_001",
        "all notices with a non-MISSING production buyer key",
    )


# ---------------------------------------------------------------------------
# 2. candidate environment
# ---------------------------------------------------------------------------


def fig_candidate_environment(c: Corpora) -> None:
    real_counts = _candidate_count_frame(c.real_sources, c.real_pairs)
    series = {"real": real_counts} | {k: c.candidate_counts(v) for k, v in c.available().items()}
    cap = c.cfg.pipeline.candidates.max_candidates_per_source

    fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.2))
    for key, counts in series.items():
        style = SERIES[key]
        x, y = _ecdf(counts["candidate_count"].to_numpy())
        axes[0].step(x, y, where="post", color=style["color"], ls=style["ls"],
                     label=f"{style['label']} (n={len(counts):,})")
    axes[0].set_xlabel("candidates per source notice")
    axes[0].set_ylabel("cumulative share of sources")
    axes[0].set_xlim(0, cap)
    axes[0].set_title("Candidate-count ECDF")
    axes[0].legend(loc="lower right")

    quantiles = [("zero rate", None), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90), ("p95", 0.95)]
    positions = np.arange(len(quantiles))
    width = 0.26
    for offset, (key, counts) in enumerate(series.items()):
        style = SERIES[key]
        values = [
            float((counts["candidate_count"] == 0).mean() * 100) if q is None
            else float(counts["candidate_count"].quantile(q))
            for _label, q in quantiles
        ]
        axes[1].bar(positions + (offset - 1) * width, values, width=width * 0.92,
                    color=style["color"], label=style["label"], edgecolor="white", linewidth=1.0)
    axes[1].set_xticks(positions)
    axes[1].set_xticklabels([label for label, _ in quantiles])
    axes[1].set_xlabel("statistic (zero rate in %, quantiles in candidates)")
    axes[1].set_ylabel("value")
    axes[1].set_title("Zero rate and candidate quantiles")
    axes[1].legend(loc="best")

    # High-activity buyers: the subgroup a concentration change hits hardest.
    for key, counts in series.items():
        style = SERIES[key]
        if "buyer_key_type" not in counts.columns:
            continue
        subset = counts.loc[counts["buyer_key_type"].eq("RAW_SIRET"), "candidate_count"]
        if len(subset) < 30:
            continue
        x, y = _ecdf(subset.to_numpy())
        axes[2].step(x, y, where="post", color=style["color"], ls=style["ls"],
                     label=f"{style['label']} (n={len(subset):,})")
    axes[2].set_xlabel("candidates per source notice")
    axes[2].set_ylabel("cumulative share of sources")
    axes[2].set_xlim(0, cap)
    axes[2].set_title("SIRET-keyed sources only")
    axes[2].legend(loc="lower right")

    for ax in axes:
        _despine(ax)
    fig.suptitle(
        "Candidate environment produced by the unchanged production blocking rule",
        y=1.03, fontsize=10.5,
    )
    fig.tight_layout()
    _finish(
        fig, "v04_fig_candidate_environment",
        "Candidate counts are an emergent property: the same production blocking code is run on "
        "each corpus. Concentrating the buyer population raises candidate density, so this is the "
        "figure that constrains how far the activity correction may go. Units: candidates per "
        "eligible source notice.",
        "data/processed/boamp_only/boamp_only_candidate_pairs.csv and the generated worlds",
        "digital-scope APPEL_OFFRE sources with a non-MISSING buyer key",
    )


# ---------------------------------------------------------------------------
# 3. SIRET availability, including the decomposition that carries the diagnosis
# ---------------------------------------------------------------------------


def fig_siret_availability(c: Corpora) -> None:
    real = c.real.assign(siret_present=c.real["buyer_siret_clean"].notna())
    versions = {
        k: v.assign(siret_present=v["buyer_siret_raw"].notna()) for k, v in c.available().items()
    }

    fig, axes = plt.subplots(2, 2, figsize=(9.2, 6.0))
    ax = axes[0][0]
    labels, values, colors = [], [], []
    for key, frame in {"real": real, **versions}.items():
        labels.append(SERIES[key]["label"])
        values.append(float(frame["siret_present"].mean()) * 100)
        colors.append(SERIES[key]["color"])
    ax.bar(labels, values, color=colors, width=0.55, edgecolor="white", linewidth=1.0)
    _tolerance_band(ax, values[0], 2.0, "tolerance +/-2 pp around real")
    for i, value in enumerate(values):
        ax.annotate(f"{value:.1f}%", xy=(i, value), xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_ylim(0, max(values) * 1.22)
    ax.set_ylabel("checksum-valid SIRET present (%)")
    ax.set_title("Aggregate availability")

    ax = axes[0][1]
    real_by_year = real.groupby("publication_year")["siret_present"].mean() * 100
    ax.plot(real_by_year.index, real_by_year.to_numpy(), color=REAL_C, ls="-",
            marker="o", ms=4, label="Real BOAMP")
    for key, frame in versions.items():
        style = SERIES[key]
        by_year = frame.groupby("publication_year")["siret_present"].mean() * 100
        ax.plot(by_year.index, by_year.to_numpy(), color=style["color"], ls=style["ls"],
                marker=style["marker"], ms=4, label=style["label"])
    ax.set_xlabel("publication year")
    ax.set_ylabel("SIRET present (%)")
    ax.set_title("By year: the conditional shape was never wrong")
    ax.legend(loc="best")

    ax = axes[1][0]
    real_year_share = real["publication_year"].value_counts(normalize=True).sort_index() * 100
    ax.plot(real_year_share.index, real_year_share.to_numpy(), color=REAL_C, ls="-",
            marker="o", ms=4, label="Real BOAMP")
    for key, frame in versions.items():
        style = SERIES[key]
        share = frame["publication_year"].value_counts(normalize=True).sort_index() * 100
        ax.plot(share.index, share.to_numpy(), color=style["color"], ls=style["ls"],
                marker=style["marker"], ms=4, label=style["label"])
    ax.set_xlabel("publication year")
    ax.set_ylabel("share of notices (%)")
    ax.set_title("By year: the composition was")
    ax.legend(loc="best")

    # The decomposition panel: marginal vs standardised to real cell weights.
    ax = axes[1][1]
    cell_cols = ["schema_family", "publication_year", "notice_type_normalized"]
    real_cells = real.groupby(cell_cols)["siret_present"].agg(["mean", "size"])
    real_cells["weight"] = real_cells["size"] / real_cells["size"].sum()
    rows = []
    for key, frame in versions.items():
        syn_cells = frame.groupby(cell_cols)["siret_present"].mean()
        joined = real_cells.join(syn_cells.rename("syn_rate"), how="inner").dropna()
        weights = joined["weight"] / joined["weight"].sum()
        rows.append(
            {
                "version": SERIES[key]["label"],
                "marginal": (float(frame["siret_present"].mean()) - float(real["siret_present"].mean())) * 100,
                "standardised": (float((weights * joined["syn_rate"]).sum())
                                 - float((weights * joined["mean"]).sum())) * 100,
                "color": SERIES[key]["color"],
            }
        )
    table = pd.DataFrame(rows)
    positions = np.arange(len(table))
    ax.bar(positions - 0.18, table["marginal"], width=0.34, color=table["color"],
           edgecolor="white", linewidth=1.0, label="marginal (raw corpus mix)")
    ax.bar(positions + 0.18, table["standardised"], width=0.34, color=table["color"],
           edgecolor="white", linewidth=1.0, hatch="///", label="standardised to real cell weights")
    ax.axhline(0, color=RULE, lw=0.8)
    _tolerance_band(ax, 0.0, 2.0, "tolerance +/-2 pp")
    ax.set_xticks(positions)
    ax.set_xticklabels(table["version"])
    ax.set_ylabel("synthetic minus real (pp)")
    ax.set_title("Why marginal and conditional disagree")
    ax.legend(loc="best")

    for row in axes:
        for ax in row:
            _despine(ax)
    fig.suptitle("Checksum-valid SIRET availability", y=1.0, fontsize=10.5)
    fig.tight_layout()
    _finish(
        fig, "v04_fig_siret_availability",
        "The v0.3 aggregate SIRET failure was a composition artifact: standardised to real "
        "schema x year x notice-type weights the v0.3 rate is within tolerance, while its raw "
        "marginal is not, because its publication-year mix over-weighted the high-SIRET years. "
        "Units: percentage points of checksum-valid SIRET presence.",
        "data/interim/boamp_common_prepared.csv and the generated worlds",
        "all notices; cells with data on both sides for the standardised bars",
    )


# ---------------------------------------------------------------------------
# 4. buyer-name variation
# ---------------------------------------------------------------------------


def fig_name_variation(c: Corpora) -> None:
    real_sim = within_group_similarity(c.real, "buyer_siren_clean", "buyer_name_normalized")
    sims = {"real": real_sim} | {
        k: within_group_similarity(v, "buyer_siren_clean", "buyer_name_normalized")
        for k, v in c.available().items()
    }
    sims = {k: v for k, v in sims.items() if len(v)}

    fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.2))
    for key, sim in sims.items():
        style = SERIES[key]
        x, y = _ecdf(sim["token_jaccard"].to_numpy())
        axes[0].step(x, y, where="post", color=style["color"], ls=style["ls"],
                     label=f"{style['label']} (n={len(sim):,} pairs)")
    axes[0].set_xlabel("token Jaccard similarity")
    axes[0].set_ylabel("cumulative share of name pairs")
    axes[0].set_title("Within-SIREN token Jaccard")
    axes[0].legend(loc="lower right")

    for key, sim in sims.items():
        style = SERIES[key]
        x, y = _ecdf(sim["jaro_winkler"].to_numpy())
        axes[1].step(x, y, where="post", color=style["color"], ls=style["ls"], label=style["label"])
    axes[1].set_xlabel("Jaro-Winkler similarity")
    axes[1].set_ylabel("cumulative share of name pairs")
    axes[1].set_title("Within-SIREN Jaro-Winkler")
    axes[1].legend(loc="lower right")

    grid = np.linspace(0.02, 0.98, 49)
    real_q = np.quantile(real_sim["token_jaccard"].dropna(), grid)
    for key, sim in sims.items():
        if key == "real":
            continue
        style = SERIES[key]
        axes[2].plot(real_q, np.quantile(sim["token_jaccard"].dropna(), grid),
                     color=style["color"], ls="none", marker=style["marker"], ms=4,
                     label=style["label"])
    axes[2].plot([0, 1], [0, 1], color=RULE, lw=0.8, ls=":")
    axes[2].set_xlabel("real token Jaccard quantile")
    axes[2].set_ylabel("synthetic token Jaccard quantile")
    axes[2].set_title("Q-Q against real")
    axes[2].legend(loc="best")

    for ax in axes:
        _despine(ax)
    fig.suptitle(
        "Buyer-name variation within one checksum-valid SIREN (silver standard)",
        y=1.03, fontsize=10.5,
    )
    fig.tight_layout()
    _finish(
        fig, "v04_fig_name_variation",
        "A quarter of real same-SIREN name pairs share no token at all; v0.3 produced 0.5% of "
        "those and put 18.6% of pairs at an identical token set, because two of its six edit "
        "modes could not change the normalised token set. Dimensionless similarity in [0, 1].",
        "data/interim/boamp_common_prepared.csv and the generated worlds",
        "distinct normalised buyer names within one checksum-valid SIREN, <=20 sampled pairs per group",
    )


def fig_alias_structure(c: Corpora) -> None:
    def variants(frame: pd.DataFrame) -> pd.Series:
        return (
            frame.dropna(subset=["buyer_siren_clean", "buyer_name_normalized"])
            .groupby("buyer_siren_clean")["buyer_name_normalized"].nunique()
        )

    series = {"real": variants(c.real)} | {k: variants(v) for k, v in c.available().items()}
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.2))

    levels = [1, 2, 3, 4, 5, 6]
    positions = np.arange(len(levels))
    width = 0.26
    for offset, (key, counts) in enumerate(series.items()):
        style = SERIES[key]
        shares = counts.clip(upper=6).value_counts(normalize=True).reindex(levels, fill_value=0) * 100
        axes[0].bar(positions + (offset - 1) * width, shares.to_numpy(), width=width * 0.92,
                    color=style["color"], edgecolor="white", linewidth=1.0,
                    label=f"{style['label']} (n={len(counts):,})")
    axes[0].set_xticks(positions)
    axes[0].set_xticklabels(["1", "2", "3", "4", "5", "6+"])
    axes[0].set_xlabel("distinct normalised names per SIREN")
    axes[0].set_ylabel("share of SIRENs (%)")
    axes[0].set_title("Alias-set size distribution")
    axes[0].legend(loc="best")

    real_sim = within_group_similarity(c.real, "buyer_siren_clean", "buyer_name_normalized")
    bands = {"real": real_sim} | {
        k: within_group_similarity(v, "buyer_siren_clean", "buyer_name_normalized")
        for k, v in c.available().items()
    }
    bands = {k: v for k, v in bands.items() if len(v)}
    band_labels = ["zero overlap\n(Jaccard = 0)", "partial\n(0 < J < 1)", "identical tokens\n(J = 1)"]
    positions = np.arange(3)
    for offset, (key, sim) in enumerate(bands.items()):
        style = SERIES[key]
        j = sim["token_jaccard"]
        shares = [float((j == 0).mean()), float(((j > 0) & (j < 1)).mean()), float((j == 1).mean())]
        axes[1].bar(positions + (offset - 1) * width, np.array(shares) * 100, width=width * 0.92,
                    color=style["color"], edgecolor="white", linewidth=1.0, label=style["label"])
    axes[1].set_xticks(positions)
    axes[1].set_xticklabels(band_labels)
    axes[1].set_ylabel("share of name pairs (%)")
    axes[1].set_title("Overlap bands: before vs after the alias mechanism")
    axes[1].legend(loc="best")

    for ax in axes:
        _despine(ax)
    fig.suptitle("Persistent buyer alias sets", y=1.03, fontsize=10.5)
    fig.tight_layout()
    _finish(
        fig, "v04_fig_alias_structure",
        "v0.4 replaces per-notice independent name edits with a persistent per-buyer alias set "
        "whose size distribution and overlap bands are calibrated to the observable real ones. "
        "Units: percentage of SIRENs and of within-SIREN name pairs.",
        "data/interim/boamp_common_prepared.csv and the generated worlds",
        "SIRENs with at least one observed normalised name",
    )


# ---------------------------------------------------------------------------
# 5. missingness structure
# ---------------------------------------------------------------------------


def fig_missingness_structure(c: Corpora) -> None:
    fields = [("SIRET", "buyer_siret_clean"), ("SIREN", "buyer_siren_clean"),
              ("CPV", "cpv_clean"), ("duration", "duration_raw")]
    syn_fields = [("SIRET", "buyer_siret_clean"), ("SIREN", "buyer_siren_clean"),
                  ("CPV", "cpv_clean"), ("duration", "declared_duration_months")]

    def matrix(frame: pd.DataFrame, spec) -> pd.DataFrame:
        return pd.DataFrame({label: frame[col].isna() for label, col in spec if col in frame.columns})

    real_m = matrix(c.real, fields)
    mats = {"real": real_m} | {k: matrix(v, syn_fields) for k, v in c.available().items()}

    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.4))
    patterns = {}
    for key, m in mats.items():
        keys = m.astype(int).astype(str).agg("".join, axis=1)
        patterns[key] = keys.value_counts(normalize=True)
    top = patterns["real"].nlargest(8).index.tolist()
    positions = np.arange(len(top))
    width = 0.26
    for offset, (key, shares) in enumerate(patterns.items()):
        style = SERIES[key]
        axes[0].bar(positions + (offset - 1) * width,
                    shares.reindex(top, fill_value=0).to_numpy() * 100,
                    width=width * 0.92, color=style["color"], edgecolor="white", linewidth=1.0,
                    label=style["label"])
    axes[0].set_xticks(positions)
    axes[0].set_xticklabels(top, rotation=45, ha="right", fontsize=7)
    axes[0].set_xlabel("missingness pattern (SIRET,SIREN,CPV,duration; 1 = missing)")
    axes[0].set_ylabel("share of notices (%)")
    axes[0].set_title("Joint missingness patterns (8 most common in real)")
    axes[0].legend(loc="best")

    labels = list(real_m.columns)
    new_m = mats.get("new")
    if new_m is not None:
        gap = real_m.astype(float).corr().to_numpy() - new_m.astype(float).corr().to_numpy()
        image = axes[1].imshow(gap, cmap="RdBu_r", vmin=-0.5, vmax=0.5)
        axes[1].set_xticks(range(len(labels)), labels, fontsize=7)
        axes[1].set_yticks(range(len(labels)), labels, fontsize=7)
        for i in range(len(labels)):
            for j in range(len(labels)):
                axes[1].text(j, i, f"{gap[i, j]:+.2f}", ha="center", va="center", fontsize=7,
                             color=INK if abs(gap[i, j]) < 0.3 else "white")
        axes[1].set_title("Correlation of missingness indicators:\nreal minus synthetic v0.4")
        axes[1].grid(False)
        fig.colorbar(image, ax=axes[1], fraction=0.046, label="correlation difference")

    _despine(axes[0])
    fig.suptitle("Joint structure of missing fields", y=1.02, fontsize=10.5)
    fig.tight_layout()
    _finish(
        fig, "v04_fig_missingness_structure",
        "Which fields go missing together sets linkage difficulty more than any marginal rate "
        "does. A diverging scale is used for the correlation gap because its sign is meaningful; "
        "zero is the neutral midpoint. Units: percentage of notices and correlation difference.",
        "data/interim/boamp_common_prepared.csv and the generated worlds",
        "all notices",
    )


# ---------------------------------------------------------------------------
# 6. validation before/after
# ---------------------------------------------------------------------------


def fig_validation_before_after(new_metrics: Path, old_metrics: Path) -> None:
    if not new_metrics.exists() or not old_metrics.exists():
        print("  (skipping validation before/after: metrics not available)")
        return
    old = pd.read_csv(old_metrics)
    new = pd.read_csv(new_metrics)
    keys = ["scope", "subgroup", "property", "metric"]
    merged = old.merge(new, on=keys, how="inner", suffixes=("_old", "_new"))
    merged = merged.loc[merged["tolerance_old"].astype(str).str.replace(".", "", 1).str.isnumeric()]
    merged["tolerance_value"] = pd.to_numeric(merged["tolerance_old"], errors="coerce")
    merged = merged.dropna(subset=["tolerance_value", "effect_size_old", "effect_size_new"])
    merged["ratio_old"] = merged["effect_size_old"] / merged["tolerance_value"]
    merged["ratio_new"] = merged["effect_size_new"] / merged["tolerance_value"]
    merged["label"] = merged["property"] + ":" + merged["metric"]

    changed = merged.loc[(merged["ratio_old"] - merged["ratio_new"]).abs() > 0.05]
    changed = changed.reindex(
        (changed["ratio_old"] - changed["ratio_new"]).abs().sort_values(ascending=False).index
    ).head(22)

    fig, axes = plt.subplots(1, 2, figsize=(9.6, max(3.6, 0.26 * len(changed) + 1.2)))
    ax = axes[0]
    y = np.arange(len(changed))[::-1]
    ax.hlines(y, changed["ratio_old"], changed["ratio_new"], color=RULE, lw=1.2, zorder=1)
    ax.scatter(changed["ratio_old"], y, color=OLD_C, marker="s", s=34, zorder=2, label="v0.3")
    ax.scatter(changed["ratio_new"], y, color=NEW_C, marker="^", s=40, zorder=3, label="v0.4")
    ax.axvline(1.0, color=TOL_C, ls=":", lw=1.0)
    ax.annotate("tolerance", xy=(1.0, len(changed)), xytext=(1.04, len(changed) - 0.5),
                fontsize=7, color=MUTED)
    ax.set_yticks(y, changed["label"], fontsize=7)
    ax.set_xlabel("|deviation| / predeclared tolerance (1.0 = at tolerance)")
    ax.set_title("Metrics that moved, v0.3 -> v0.4")
    ax.legend(loc="lower right")
    ax.grid(axis="x")
    _despine(ax)

    ax = axes[1]
    counts = pd.DataFrame(
        {
            "v0.3": old["status"].value_counts(),
            "v0.4": new["status"].value_counts(),
        }
    ).fillna(0).reindex(["PASS", "WARNING", "FAIL", "INCONCLUSIVE"]).fillna(0)
    positions = np.arange(len(counts))
    ax.bar(positions - 0.19, counts["v0.3"], width=0.36, color=OLD_C, edgecolor="white",
           linewidth=1.0, label="v0.3")
    ax.bar(positions + 0.19, counts["v0.4"], width=0.36, color=NEW_C, edgecolor="white",
           linewidth=1.0, label="v0.4")
    for i, (a, b) in enumerate(zip(counts["v0.3"], counts["v0.4"], strict=False)):
        ax.annotate(f"{int(a)}", xy=(i - 0.19, a), ha="center", va="bottom", fontsize=8)
        ax.annotate(f"{int(b)}", xy=(i + 0.19, b), ha="center", va="bottom", fontsize=8)
    ax.set_xticks(positions, counts.index)
    ax.set_ylabel("number of metrics")
    ax.set_title("Validation outcomes")
    ax.legend(loc="best")
    _despine(ax)

    fig.suptitle("Validation framework: before and after the revision", y=1.02, fontsize=10.5)
    fig.tight_layout()
    _finish(
        fig, "v04_fig_validation_before_after",
        "Deviations are shown relative to their own predeclared tolerance so metrics on different "
        "scales are comparable; 1.0 is exactly at tolerance. Only metrics present in both runs "
        "and moving by more than 0.05 tolerance units are drawn. Dimensionless.",
        "reports/tables/synthetic_benchmark/v0_4_population_alias_revision/"
        "{baseline_v0_3,validation_framework}/validation_metrics_long.csv",
        "metrics with a numeric tolerance evaluated in both versions",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default=SCENARIO)
    parser.add_argument("--skip-candidates", action="store_true",
                        help="Skip the candidate-environment figure (the slowest).")
    args = parser.parse_args()

    print("loading corpora")
    c = Corpora(ROOT, args.scenario)
    print("building figures")
    fig_buyer_activity(c)
    fig_activity_tail(c)
    if not args.skip_candidates:
        fig_candidate_environment(c)
    fig_siret_availability(c)
    fig_name_variation(c)
    fig_alias_structure(c)
    fig_missingness_structure(c)
    fig_validation_before_after(
        TABLES / "validation_framework" / "validation_metrics_long.csv",
        BASELINE / "validation_metrics_long.csv",
    )

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    (FIG_DIR / "figure_index.json").write_text(json.dumps(INDEX, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(INDEX)} figures written to {FIG_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
