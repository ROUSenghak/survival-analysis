"""Figures for the synthetic-benchmark technical report.

Each figure supports one specific methodological claim in the report; none is
decorative. Every figure is regenerated from the current artifacts, carries its
sample definition in the caption block written alongside it, and is written to
both PDF (for LaTeX) and PNG (for quick review).

Colour: three categorical slots from the project's validated palette --
blue #2a78d6, orange #eb6834, aqua #1baf7a -- which is the documented
all-pairs-safe prefix of that palette. Identity is never carried by colour
alone: every series is also direct-labelled or legended, and the two-condition
comparisons additionally differ in line style.
"""

from __future__ import annotations

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
from boamp.synthetic.validation_framework.difficulty import (  # noqa: E402
    scoped_sources,
    true_match_pairs,
)
from boamp.synthetic.validation_framework.loaders import (  # noqa: E402
    available_replicates,
    load_benchmark_data,
)
from boamp.linkage.candidates import generate_pairs_single_key  # noqa: E402
from boamp.linkage.scoring import add_rank_and_margin  # noqa: E402

VERSION = "v0_3_temporal_candidate_revision"
SCENARIO = "central_provisional"

TABLES = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION
VF = TABLES / "validation_framework"
FIG_DIR = ROOT / "reports" / "figures" / "synthetic_benchmark" / "report"

REAL = "#2a78d6"      # categorical slot 1
SYN = "#eb6834"       # categorical slot 2
PREV = "#1baf7a"      # categorical slot 3
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

plt.rcParams.update({
    "figure.dpi": 160,
    "savefig.dpi": 160,
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.edgecolor": BASELINE,
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
})


def _finish(fig, stem: str, index: list[dict], caption: str, source: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in ("pdf", "png"):
        fig.savefig(FIG_DIR / f"{stem}.{suffix}")
    plt.close(fig)
    index.append({"figure": stem, "caption": caption, "source": source})
    print(f"wrote {stem}")


def _despine(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_axisbelow(True)


def _ecdf(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.sort(np.asarray(values, dtype=float))
    return x, np.arange(1, len(x) + 1) / len(x)


# ---------------------------------------------------------------------------
def fig_candidate_environment(data, index) -> None:
    """Candidate-set sizes: the single property that decides whether a linker
    is even given a chance to find the successor."""
    cfg = load_config(ROOT)
    real_counts = (
        data.real_pairs.groupby("source_notice_id").size()
        .reindex(data.real_sources.loc[data.real_sources["buyer_key_type"].ne("MISSING"), "notice_id"])
        .fillna(0).to_numpy()
    )
    scoped = scoped_sources(data)
    pairs, _ = generate_pairs_single_key(scoped, cfg, verbose=False)
    syn_counts = (
        pairs.groupby("source_notice_id").size().reindex(scoped["notice_id"]).fillna(0).to_numpy()
        if len(pairs) else np.zeros(len(scoped))
    )

    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0))
    ax = axes[0]
    for values, colour, label, style in ((real_counts, REAL, "Real BOAMP", "-"),
                                         (syn_counts, SYN, "Synthetic v0.3", "--")):
        x, y = _ecdf(values)
        ax.step(x, y, where="post", color=colour, lw=2, ls=style, label=label)
    ax.set_xlim(0, 30)
    ax.set_xlabel("candidates generated per eligible source (count)")
    ax.set_ylabel("empirical CDF")
    ax.set_title("(a) Candidate-set size", loc="left")
    ax.legend(loc="lower right")
    _despine(ax)

    ax = axes[1]
    labels = ["Real\nBOAMP", "Synthetic\nv0.3"]
    zero_rates = [float((real_counts == 0).mean()), float((syn_counts == 0).mean())]
    bars = ax.bar(labels, [100 * z for z in zero_rates], color=[REAL, SYN], width=0.5)
    for bar, z in zip(bars, zero_rates):
        ax.annotate(f"{100 * z:.1f}%", (bar.get_x() + bar.get_width() / 2, 100 * z),
                    ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_ylabel("sources with zero candidates (%)")
    ax.set_ylim(0, max(100 * max(zero_rates) * 1.35, 10))
    ax.set_title("(b) Structural censoring by blocking", loc="left")
    _despine(ax)

    fig.tight_layout()
    _finish(fig, "fig_candidate_environment", index,
            "Per-source candidate-set size under the production Layer-1 blocker. Sample: eligible "
            "digital-scope APPEL_OFFRE sources with a non-missing buyer key "
            f"(real n={len(real_counts):,}; synthetic n={len(syn_counts):,}). Unit: candidates per source.",
            "scripts/build_report_figures.py::fig_candidate_environment")


def fig_true_vs_hard_negative_scores(data, index) -> None:
    """Composite scores of true successor pairs against same-buyer distractors.

    Separability here is what makes the benchmark discriminative rather than
    trivially solvable or hopeless.
    """
    cfg = load_config(ROOT)
    scoped = scoped_sources(data)
    pairs, _ = generate_pairs_single_key(scoped, cfg, verbose=False)
    if not len(pairs):
        return
    pairs = add_rank_and_margin(pairs)
    truth = true_match_pairs(data)
    truth_keys = {
        tuple(sorted((str(a), str(b)))) for a, b in zip(truth["notice_a"], truth["notice_b"])
    }
    keys = [tuple(sorted((str(a), str(b))))
            for a, b in zip(pairs["source_notice_id"], pairs["candidate_notice_id"])]
    pairs = pairs.assign(is_true_match=[k in truth_keys for k in keys])

    matches = pairs.loc[pairs["is_true_match"], "composite_score"].to_numpy()
    negatives = pairs.loc[~pairs["is_true_match"], "composite_score"].to_numpy()

    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    bins = np.linspace(0, max(pairs["composite_score"].max(), 0.8), 34)
    ax.hist(negatives, bins=bins, density=True, color=SYN, alpha=0.85,
            label=f"blocked non-matches (n={len(negatives):,})")
    ax.hist(matches, bins=bins, density=True, histtype="step", lw=2, color=REAL,
            label=f"true successor pairs (n={len(matches):,})")
    threshold = cfg.pipeline.thresholds.balanced
    ax.axvline(threshold, color=INK, lw=1.2, ls=":")
    ax.annotate(f"production balanced\nthreshold {threshold:.3f}",
                (threshold, ax.get_ylim()[1] * 0.82), xytext=(6, 0),
                textcoords="offset points", fontsize=7.5, color=INK)
    ax.set_xlabel(r"composite candidate score $S_{ij}$ (unitless, 0-1)")
    ax.set_ylabel("density")
    ax.set_title("Score separability of sealed truth from same-buyer distractors", loc="left")
    ax.legend(loc="upper right")
    _despine(ax)
    fig.tight_layout()
    _finish(fig, "fig_score_separability", index,
            "Composite production score for blocked candidate pairs in the central synthetic world, "
            "split by sealed truth. Sample: all pairs produced by the Layer-1 blocker on the synthetic "
            "digital-scope source population. Densities, not counts, because the two groups differ in size "
            "by orders of magnitude.",
            "scripts/build_report_figures.py::fig_true_vs_hard_negative_scores")


def fig_true_gap_vs_window(data, index) -> None:
    """Where true renewal gaps fall relative to the production blocking window."""
    gaps = data.true_relations.loc[
        data.true_relations["relation_type"].eq("NEXT_CYCLE"), "true_gap_months"
    ].dropna().to_numpy()
    window = load_config(ROOT).pipeline.temporal_window.expected_value_months

    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ax.hist(gaps, bins=40, color=SYN, alpha=0.9)
    ax.axvspan(-window, window, color=REAL, alpha=0.16)
    ax.axvline(window, color=REAL, lw=1.6)
    inside = float((np.abs(gaps) <= window).mean())
    ax.annotate(
        f"production window $\\pm${window} months\naround the estimated end date\n"
        f"covers {100 * inside:.1f}% of true gaps",
        (window, ax.get_ylim()[1] * 0.68), xytext=(10, 0), textcoords="offset points",
        fontsize=8, color=INK,
    )
    ax.set_xlabel("true gap between a cycle's expected end and its successor's start (months)")
    ax.set_ylabel("number of true successor relations")
    ax.set_title("True renewal timing versus the production blocking window", loc="left")
    _despine(ax)
    fig.tight_layout()
    _finish(fig, "fig_true_gap_vs_window", index,
            f"Distribution of true successor gaps in the central synthetic world (n={len(gaps):,} "
            "NEXT_CYCLE relations). The shaded band is the production 6-month blocking window. The gap "
            "distribution is a scenario assumption, deliberately not centred on that window.",
            "scripts/build_report_figures.py::fig_true_gap_vs_window")


def fig_buyer_activity(data, index) -> None:
    """Heavy-tailed buyer activity: emergent in the generator, never assigned."""
    real_counts = data.real.groupby("buyer_key").size().sort_values(ascending=False).to_numpy()
    syn_counts = data.observed.groupby("buyer_name_raw").size().sort_values(ascending=False).to_numpy()

    def lorenz(counts):
        s = np.sort(np.asarray(counts, dtype=float))
        return np.arange(1, len(s) + 1) / len(s), np.cumsum(s) / s.sum()

    def gini(counts):
        x, y = lorenz(counts)
        return float(1 - 2 * np.trapezoid(y, x))

    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0))
    ax = axes[0]
    for counts, colour, label, style in ((real_counts, REAL, "Real BOAMP", "-"),
                                         (syn_counts, SYN, "Synthetic v0.3", "--")):
        ranks = np.arange(1, len(counts) + 1)
        ax.plot(ranks / len(counts), counts / counts.sum(), color=colour, lw=2, ls=style, label=label)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("buyer rank / number of buyers (log)")
    ax.set_ylabel("share of notices (log)")
    ax.set_title("(a) Rank-frequency of buyer activity", loc="left")
    ax.legend(loc="lower left")
    _despine(ax)

    ax = axes[1]
    for counts, colour, label, style in ((real_counts, REAL, "Real BOAMP", "-"),
                                         (syn_counts, SYN, "Synthetic v0.3", "--")):
        x, y = lorenz(counts)
        ax.plot(x, y, color=colour, lw=2, ls=style, label=f"{label} (Gini {gini(counts):.3f})")
    ax.plot([0, 1], [0, 1], color=BASELINE, lw=1, ls=":")
    ax.set_xlabel("cumulative share of buyers")
    ax.set_ylabel("cumulative share of notices")
    ax.set_title("(b) Lorenz curve of notice concentration", loc="left")
    ax.legend(loc="upper left")
    _despine(ax)

    fig.tight_layout()
    _finish(fig, "fig_buyer_activity", index,
            "Buyer-level notice concentration, real corpus versus the central synthetic world. Unit: "
            "notices per buyer identity (real: production buyer key; synthetic: observed buyer name, the "
            "only identity a linker sees). Concentration is an emergent property of the generator's "
            "Pareto activity draw, never assigned directly.",
            "scripts/build_report_figures.py::fig_buyer_activity")


def fig_conditional_identifier_fidelity(data, index) -> None:
    """SIRET presence by year: the conditional the marginal rate hides."""
    from utils.identifiers import validate_siret

    real = data.real.copy()
    real["year"] = pd.to_datetime(real["publication_date"]).dt.year
    real_rate = real.groupby("year")["buyer_siret_clean"].apply(lambda s: s.notna().mean())

    syn = data.observed.copy()
    syn["year"] = pd.to_datetime(syn["publication_date"]).dt.year
    syn["present"] = syn["buyer_siret_raw"].map(
        lambda v: bool(pd.notna(v) and all(validate_siret(v)))
    )
    syn_rate = syn.groupby("year")["present"].mean()

    years = sorted(set(real_rate.index) & set(syn_rate.index))
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0), gridspec_kw={"width_ratios": [1.35, 1]})
    ax = axes[0]
    ax.plot(years, [100 * real_rate[y] for y in years], color=REAL, lw=2, marker="o", ms=4,
            label="Real BOAMP")
    ax.plot(years, [100 * syn_rate[y] for y in years], color=SYN, lw=2, ls="--", marker="s", ms=4,
            label="Synthetic v0.3")
    ax.set_xlabel("publication year")
    ax.set_ylabel("checksum-valid SIRET present (%)")
    ax.set_title("(a) Identifier availability by year", loc="left")
    ax.legend(loc="upper left")
    _despine(ax)

    ax = axes[1]
    diff = [100 * (syn_rate[y] - real_rate[y]) for y in years]
    ax.bar([str(y) for y in years], diff, color=[SYN if d >= 0 else REAL for d in diff], width=0.7)
    ax.axhline(0, color=BASELINE, lw=1)
    ax.set_xlabel("publication year")
    ax.set_ylabel("synthetic $-$ real (percentage points)")
    ax.set_title("(b) Signed conditional discrepancy", loc="left")
    ax.tick_params(axis="x", rotation=90)
    _despine(ax)

    fig.tight_layout()
    _finish(fig, "fig_conditional_identifier_fidelity", index,
            "Checksum-valid buyer-SIRET presence by publication year, real versus synthetic. Sample: all "
            "notices in each corpus. This conditional is the object the generator targets; the marginal "
            "presence rate alone would hide the 2022 regime shift.",
            "scripts/build_report_figures.py::fig_conditional_identifier_fidelity")


def fig_duration_qq(data, index) -> None:
    """Quantile-quantile comparison of the declared duration actually visible."""
    real = pd.to_numeric(data.real["duration_raw"], errors="coerce").dropna()
    real = real[real.between(1, 120)].to_numpy()
    syn = pd.to_numeric(data.observed["declared_duration_months"], errors="coerce").dropna()
    syn = syn[syn.between(1, 120)].to_numpy()
    if not len(real) or not len(syn):
        return
    q = np.linspace(0.01, 0.99, 99)
    fig, ax = plt.subplots(figsize=(4.2, 4.0))
    ax.plot(np.quantile(real, q), np.quantile(syn, q), color=SYN, lw=0, marker="o", ms=3.2)
    lim = [0, max(np.quantile(real, 0.99), np.quantile(syn, 0.99)) * 1.05]
    ax.plot(lim, lim, color=BASELINE, lw=1.2, ls=":")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("real declared duration quantile (months)")
    ax.set_ylabel("synthetic declared duration quantile (months)")
    ax.set_title("Declared-duration quantiles", loc="left")
    ax.grid(True, axis="both")
    _despine(ax)
    fig.tight_layout()
    _finish(fig, "fig_duration_qq", index,
            "Quantile-quantile plot of the observed declared duration, percentiles 1 to 99. Sample: "
            f"in-range (1-120 month) declared durations, real n={len(real):,}, synthetic n={len(syn):,}. "
            "The dotted line is equality. Points on the line mean the visible duration distribution "
            "matches; the latent contract length is a separate, unobserved quantity.",
            "scripts/build_report_figures.py::fig_duration_qq")


def fig_marginal_fidelity(index) -> None:
    """How far each observable marginal sits from its tolerance.

    Distributional distances live in ``effect_size``, not in
    ``synthetic_estimate``: a distribution is not a scalar, so the long table
    leaves the estimate columns empty for these rows.
    """
    metrics = pd.read_csv(VF / "validation_metrics_long.csv")
    sel = metrics.loc[
        metrics["scope"].eq("marginals") & metrics["metric"].isin(["TV", "JS", "W1_scaled"])
    ].copy()
    sel = sel.dropna(subset=["effect_size"])
    if sel.empty:
        return
    sel["label"] = sel["property"].str.replace("_", " ")
    pivot = sel.pivot_table(index="label", columns="metric", values="effect_size")
    tolerance = sel.groupby("label")["tolerance"].first().astype(float)
    order = pivot.max(axis=1).sort_values().index
    pivot = pivot.loc[order]
    tolerance = tolerance.loc[order]

    fig, ax = plt.subplots(figsize=(6.6, max(2.6, 0.36 * len(pivot) + 1.4)))
    y = np.arange(len(pivot))
    specs = [("TV", REAL, "o", -0.18), ("JS", SYN, "s", 0.0), ("W1_scaled", PREV, "^", 0.18)]
    for column, colour, marker, offset in specs:
        if column in pivot.columns:
            values = pivot[column]
            mask = values.notna()
            ax.scatter(values[mask], y[mask.to_numpy()] + offset, color=colour, s=30,
                       marker=marker, label=column, zorder=3)
    ax.scatter(tolerance.to_numpy(), y, marker="|", s=180, color=INK, lw=1.4,
               label="tolerance", zorder=4)
    ax.set_yticks(y)
    ax.set_yticklabels(pivot.index)
    ax.set_xlabel("distance between real and synthetic distributions (0 = identical)")
    ax.set_title("Marginal-distribution agreement, with the tolerance each was judged against",
                 loc="left")
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncols=4)
    _despine(ax)
    fig.tight_layout()
    _finish(fig, "fig_marginal_fidelity", index,
            "Total-variation and Jensen-Shannon distance for categorical marginals, and "
            "interquartile-range-scaled first Wasserstein distance for continuous ones, each against the "
            "tolerance it was judged by. All are bounded effect sizes requiring no distributional "
            "assumption, which is why they replace significance testing on a corpus where every "
            "difference is significant. Source: validation_metrics_long.csv.",
            "scripts/build_report_figures.py::fig_marginal_fidelity")


def fig_seed_robustness(index) -> None:
    """Per-seed spread of the two headline difficulty metrics."""
    probes = pd.read_csv(VF / "probe_replicate_results.csv")
    if probes.empty:
        return
    metrics = pd.read_csv(VF / "validation_metrics_long.csv")
    rob = metrics.loc[metrics["scope"].eq("robustness")]

    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2))
    ax = axes[0]
    scenarios = [s for s in ["easier", "moderate", SCENARIO, "difficult", "stress"]
                 if s in set(probes["scenario"])]
    best = (probes.groupby(["scenario", "world"])["pair_f1"].max().reset_index())
    for i, scenario in enumerate(scenarios):
        vals = best.loc[best["scenario"].eq(scenario), "pair_f1"].to_numpy()
        jitter = (np.arange(len(vals)) - (len(vals) - 1) / 2) * 0.035
        ax.scatter(np.full(len(vals), i) + jitter, vals, color=SYN, s=22, alpha=0.85, zorder=3)
        if len(vals):
            ax.hlines(vals.mean(), i - 0.28, i + 0.28, color=REAL, lw=2, zorder=4)
    ax.set_xticks(range(len(scenarios)))
    ax.set_xticklabels(["central" if s == SCENARIO else s for s in scenarios], fontsize=8)
    ax.set_ylabel(r"best probe pair $F_1$ per seed")
    ax.set_title("(a) Difficulty across scenarios and seeds", loc="left")
    _despine(ax)

    ax = axes[1]
    labels, means, stds = [], [], []
    for prop, label in (("blocking_pairs_completeness", "blocking\ncompleteness"),
                        ("probe_headroom", "probe\nheadroom"),
                        ("match_vs_hard_negative_score", "match / hard-neg.\noverlap")):
        sel = rob.loc[rob["subgroup"].eq(f"seed_replicates:{SCENARIO}") & rob["property"].eq(prop)]
        by = sel.set_index("metric")["synthetic_estimate"]
        if "mean" not in by.index:
            continue
        labels.append(label)
        means.append(float(by["mean"]))
        stds.append(float(by["std"]))
    ax.bar(labels, means, yerr=stds, color=SYN, width=0.55, capsize=4,
           error_kw={"ecolor": INK, "elinewidth": 1.2})
    for i, (m, s) in enumerate(zip(means, stds)):
        ax.annotate(f"{m:.3f}\n$\\pm${s:.3f}", (i, m + s), xytext=(0, 7),
                    textcoords="offset points", ha="center", fontsize=7.5, color=INK)
    ax.set_ylabel("central scenario, mean over 10 world seeds")
    ax.set_ylim(0, max(np.array(means) + np.array(stds)) * 1.45 if means else 1)
    ax.set_title("(b) Seed variability of the central world", loc="left")
    _despine(ax)

    fig.tight_layout()
    _finish(fig, "fig_seed_robustness", index,
            "Seed-to-seed variability of the difficulty metrics. Left: best probe pair-F1 per generated "
            "world (one point per seed, bar = scenario mean). Right: mean and standard deviation over the "
            "ten central-scenario seeds. Wide spread here is why controlled algorithm comparison is not yet "
            "supported. Source: probe_replicate_results.csv, validation_metrics_long.csv.",
            "scripts/build_report_figures.py::fig_seed_robustness")


def fig_provenance_composition(index) -> None:
    """How much of the generator is estimated and how much is assumed."""
    registry = pd.read_csv(TABLES / "registries" / "parameter_registry.csv")
    counts = registry["provenance_class"].value_counts()
    order = ["EMPIRICAL_OBSERVABLE", "SILVER_STANDARD_APPROXIMATION", "SCENARIO_UNIDENTIFIED",
             "FIDELITY_TARGET", "ALGORITHM_PARAMETER", "IMPLEMENTATION_CONSTANT"]
    order = [c for c in order if counts.get(c, 0) > 0]
    values = [int(counts[c]) for c in order]
    colours = [REAL if c in ("EMPIRICAL_OBSERVABLE",) else
               PREV if c in ("SILVER_STANDARD_APPROXIMATION", "FIDELITY_TARGET") else SYN
               for c in order]

    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    y = np.arange(len(order))
    ax.barh(y, values, color=colours, height=0.6)
    for i, val in enumerate(values):
        ax.annotate(f"{val}", (val, i), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=8, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([c.replace("_", " ").title() for c in order], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("registry rows")
    ax.set_xlim(0, max(values) * 1.16)
    ax.set_title("Provenance of every registered generator parameter and validation rule", loc="left")
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    _despine(ax)
    fig.tight_layout()
    _finish(fig, "fig_provenance_composition", index,
            "Rows of the parameter registry by provenance class. Blue is estimated from observable real "
            "BOAMP; green is proxy-estimated or held out as a fidelity target; orange is a scenario "
            "assumption or an implementation constant with no empirical anchor. Source: "
            "registries/parameter_registry.csv.",
            "scripts/build_report_figures.py::fig_provenance_composition")


def fig_gate_scorecard(index) -> None:
    """The validation gates, showing where the evidence is and is not strong."""
    gates = pd.read_csv(VF / "validation_gate_summary.csv")
    gates = gates.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(6.6, max(3.0, 0.30 * len(gates) + 1.0)))
    y = np.arange(len(gates))
    # Every metric in the gate must appear, including inconclusive ones: a gate
    # can read WARNING purely because a metric could not be decided, and a bar
    # that omitted those would not explain its own status.
    ax.barh(y, gates["n_pass"], color=REAL, height=0.62, label="pass")
    ax.barh(y, gates["n_warning"], left=gates["n_pass"], color=PREV, height=0.62, label="warning")
    ax.barh(y, gates["n_inconclusive"], left=gates["n_pass"] + gates["n_warning"],
            color=BASELINE, height=0.62, label="inconclusive")
    ax.barh(y, gates["n_fail"],
            left=gates["n_pass"] + gates["n_warning"] + gates["n_inconclusive"],
            color=SYN, height=0.62, label="fail")
    labels = [f"{g}{' *' if c else ''}" for g, c in zip(gates["gate"], gates["critical"])]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    for i, status in enumerate(gates["status"]):
        total = gates.loc[i, ["n_pass", "n_warning", "n_fail", "n_inconclusive"]].sum()
        ax.annotate(status, (total, i), xytext=(5, 0), textcoords="offset points",
                    va="center", fontsize=7.5, color=INK)
    ax.set_xlabel("metrics evaluated in the gate (count)")
    ax.set_xlim(0, gates[["n_pass", "n_warning", "n_fail", "n_inconclusive"]].sum(axis=1).max() * 1.5)
    ax.set_title("Validation gates: metric outcomes ($*$ marks a critical gate)", loc="left")
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    ax.legend(loc="lower right", ncols=4)
    _despine(ax)
    fig.tight_layout()
    _finish(fig, "fig_gate_scorecard", index,
            "Per-gate metric outcomes for the current validation run. A critical gate fails the release on "
            "its own; a non-critical gate can only downgrade the run to PASS_WITH_WARNINGS, which is why a "
            "gate can read WARNING while still carrying metric-level failures. Source: "
            "validation_gate_summary.csv.",
            "scripts/build_report_figures.py::fig_gate_scorecard")


def main() -> None:
    data = load_benchmark_data(ROOT, VERSION, SCENARIO)
    index: list[dict] = []
    fig_candidate_environment(data, index)
    fig_true_vs_hard_negative_scores(data, index)
    fig_true_gap_vs_window(data, index)
    fig_buyer_activity(data, index)
    fig_conditional_identifier_fidelity(data, index)
    fig_duration_qq(data, index)
    fig_marginal_fidelity(index)
    fig_seed_robustness(index)
    fig_provenance_composition(index)
    fig_gate_scorecard(index)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    (FIG_DIR / "figure_index.json").write_text(
        json.dumps({"benchmark_version": VERSION, "scenario": SCENARIO,
                    "n_replicates_available": len(available_replicates(ROOT, VERSION)),
                    "figures": index}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"figures": len(index), "dir": str(FIG_DIR.relative_to(ROOT))}, indent=2))


if __name__ == "__main__":
    main()
