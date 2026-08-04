"""Diagnostic figure for the synthetic-versus-real notice-text gap.

The v0.4 release carries one metric failure (`text_length W1_scaled`) and three
text warnings (`unigram_distribution JS`, `bigram_distribution JS`,
`token_count q50`). This figure exists to show what is actually behind them,
because the two are not the same problem and the distinction decides what a v0.5
should do:

* the *length* gap is a composition effect of one short repeated template, which
  the v0.4 buyer-population correction made more frequent;
* the *vocabulary* gap is structural and predates v0.4 -- the generator draws
  from a fixed word pool two orders of magnitude smaller than real BOAMP's.

Fixing the first does not touch the second.

Colour: the project's validated three-slot categorical palette -- blue #2a78d6
(real), orange #eb6834 (v0.3), aqua #1baf7a (v0.4) -- checked as an all-pairs set
in OKLab (normal-vision separations 24.0-33.6, worst CVD separation 9.2). Every
series is also legended and line-styled, so identity is never colour-alone.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

NEW_VERSION = "v0_4_population_alias_revision"
OLD_VERSION = "v0_3_temporal_candidate_revision"
SCENARIO = "central_provisional"
FIG_DIR = ROOT / "reports" / "figures" / "synthetic_benchmark" / NEW_VERSION

REAL_C, OLD_C, NEW_C = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, RULE = "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = {
    "real": {"color": REAL_C, "ls": "-", "label": "Real BOAMP"},
    "old": {"color": OLD_C, "ls": "--", "label": "Synthetic v0.3"},
    "new": {"color": NEW_C, "ls": "-.", "label": "Synthetic v0.4"},
}
TOKEN_RE = re.compile(r"[a-z0-9]+")

plt.rcParams.update({
    "figure.dpi": 160, "savefig.dpi": 160, "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9, "axes.edgecolor": RULE,
    "axes.labelcolor": INK, "axes.titlecolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 8,
    "ytick.labelsize": 8, "legend.frameon": False, "legend.fontsize": 8,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.grid": True,
    "axes.grid.axis": "y", "figure.facecolor": "white",
    "savefig.bbox": "tight", "lines.linewidth": 2.0,
})


def _despine(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_axisbelow(True)


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _ngram_counts(texts: pd.Series, n: int = 1) -> Counter:
    counter: Counter = Counter()
    for text in texts:
        words = _tokens(text)
        counter.update(tuple(words[i : i + n]) for i in range(len(words) - n + 1))
    return counter


def _load(version: str) -> pd.Series:
    path = (
        ROOT / "data" / "processed" / "synthetic_benchmark" / version / SCENARIO
        / "world_001" / "corruption_001" / "observed_notices.parquet"
    )
    return pd.read_parquet(path)["objet_clean"].dropna().astype(str)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stem", default="v04_fig_text_gap_diagnosis")
    args = parser.parse_args()

    real = pd.read_csv(
        ROOT / "data" / "interim" / "boamp_common_prepared.csv",
        usecols=["objet_clean"], low_memory=False,
    )["objet_clean"].dropna().astype(str)
    old, new = _load(OLD_VERSION), _load(NEW_VERSION)
    corpora = {"real": real, "old": old, "new": new}

    counts = {key: _ngram_counts(series) for key, series in corpora.items()}
    totals = {key: sum(counter.values()) for key, counter in counts.items()}

    fig, axes = plt.subplots(2, 2, figsize=(10.2, 7.0))

    # -- 1. length ECDF: the failing metric ------------------------------
    ax = axes[0][0]
    for key, series in corpora.items():
        style = SERIES[key]
        lengths = np.sort(series.str.len().to_numpy())
        ax.plot(lengths, np.arange(1, len(lengths) + 1) / len(lengths),
                color=style["color"], ls=style["ls"],
                label=f"{style['label']} (n={len(lengths):,})")
    ax.axvline(49, color=MUTED, lw=1.0, ls=":")
    ax.annotate("49 chars:\nthe repeated\nadmin template", xy=(49, 0.06), xytext=(78, 0.06),
                fontsize=7, color=MUTED, va="center",
                arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 0.8})
    ax.set_xlim(0, 320)
    ax.set_xlabel("notice text length (characters)")
    ax.set_ylabel("cumulative share of notices")
    ax.set_title("Length: synthetic is short at the low end")
    ax.legend(loc="lower right")

    # -- 2. vocabulary rank-frequency: the structural gap ----------------
    ax = axes[0][1]
    for key in corpora:
        style = SERIES[key]
        freq = np.array(sorted(counts[key].values(), reverse=True), dtype=float) / totals[key]
        ax.plot(np.arange(1, len(freq) + 1), freq, color=style["color"], ls=style["ls"],
                label=f"{style['label']} ({len(freq):,} words)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("word rank (log scale)")
    ax.set_ylabel("share of all tokens (log scale)")
    ax.set_title("Vocabulary: synthetic falls off a cliff")
    ax.legend(loc="lower left")

    # -- 3. vocabulary coverage ------------------------------------------
    ax = axes[1][0]
    rows = []
    for key in ("old", "new"):
        shared = set(counts["real"]) & set(counts[key])
        rows.append({
            "version": SERIES[key]["label"],
            "color": SERIES[key]["color"],
            "types_share": 100 * len(shared) / len(counts["real"]),
            "real_mass": 100 * sum(counts["real"][w] for w in shared) / totals["real"],
        })
    table = pd.DataFrame(rows)
    positions = np.arange(len(table))
    ax.bar(positions - 0.19, table["types_share"], width=0.36, color=table["color"],
           edgecolor="white", linewidth=1.0, label="share of real vocabulary present")
    ax.bar(positions + 0.19, table["real_mass"], width=0.36, color=table["color"],
           edgecolor="white", linewidth=1.0, hatch="///",
           label="share of real word usage covered")
    for i, row in table.iterrows():
        ax.annotate(f"{row['types_share']:.1f}%", xy=(i - 0.19, row["types_share"]),
                    xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8)
        ax.annotate(f"{row['real_mass']:.0f}%", xy=(i + 0.19, row["real_mass"]),
                    xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8)
    ax.set_xticks(positions, table["version"])
    ax.set_ylim(0, 100)
    ax.set_ylabel("percent of real BOAMP")
    ax.set_title("Coverage: common words yes, long tail no")
    ax.legend(loc="upper left")

    # -- 4. duplication: how much text is not unique ---------------------
    ax = axes[1][1]
    labels, values, colors = [], [], []
    for key, series in corpora.items():
        labels.append(SERIES[key]["label"])
        values.append(100 * (1 - series.nunique() / len(series)))
        colors.append(SERIES[key]["color"])
    ax.bar(labels, values, color=colors, width=0.55, edgecolor="white", linewidth=1.0)
    for i, value in enumerate(values):
        ax.annotate(f"{value:.1f}%", xy=(i, value), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=8, color=INK)
    ax.set_ylim(0, max(values) * 1.25)
    ax.set_ylabel("percent of notices repeating another notice's text")
    ax.set_title("Duplication: v0.4 repeats itself more than real")

    for row in axes:
        for ax in row:
            _despine(ax)
    fig.suptitle(
        "Why synthetic notice text differs from real BOAMP: two separate problems",
        y=1.0, fontsize=11,
    )
    fig.tight_layout()
    fig.text(0.005, -0.02,
             "Source: data/interim/boamp_common_prepared.csv and "
             "data/processed/synthetic_benchmark/{v0_3,v0_4}/central_provisional/world_001. "
             "Population: all notices with non-null objet_clean.",
             ha="left", va="top", fontsize=6.5, color=MUTED)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf"):
        fig.savefig(FIG_DIR / f"{args.stem}.{suffix}")
    plt.close(fig)

    summary = {
        "figure": args.stem,
        "caption": (
            "The length failure and the vocabulary warnings are different problems. Panel 1: "
            "synthetic text is too short at the low end, driven by a 49-character repeated "
            "administrative template. Panel 2: the generator draws from a word pool an order of "
            "magnitude smaller than real BOAMP's, so its rank-frequency curve ends where the real "
            "one continues. Panel 3: the shared vocabulary covers most real word *usage* but a "
            "tiny share of real word *types*. Panel 4: v0.4 repeats itself more than v0.3 or real."
        ),
        "corpora": {
            key: {
                "n_notices": int(len(series)),
                "n_unique_texts": int(series.nunique()),
                "duplicate_share": float(1 - series.nunique() / len(series)),
                "vocabulary_types": int(len(counts[key])),
                "tokens": int(totals[key]),
                "length_q10": float(series.str.len().quantile(0.10)),
                "length_q50": float(series.str.len().quantile(0.50)),
                "length_q90": float(series.str.len().quantile(0.90)),
            }
            for key, series in corpora.items()
        },
        "coverage": table.drop(columns="color").to_dict(orient="records"),
    }
    (FIG_DIR / f"{args.stem}.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {(FIG_DIR / args.stem).relative_to(ROOT)}.{{png,pdf,json}}")
    for key, stats in summary["corpora"].items():
        print(f"  {SERIES[key]['label']:<16} vocab={stats['vocabulary_types']:>6,} "
              f"unique texts={stats['n_unique_texts']:>6,} "
              f"dup={100 * stats['duplicate_share']:.1f}% "
              f"len q50={stats['length_q50']:.0f}")


if __name__ == "__main__":
    main()
