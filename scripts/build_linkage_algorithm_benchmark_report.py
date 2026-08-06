"""Build a standalone written report for the linkage algorithm benchmark.

`--version` selects which benchmark version's tables are rendered. It defaults to
v0.3, whose report keeps its original unversioned filename so existing links and
the compiled PDF stay valid; any other version is written to a version-prefixed
stem so it cannot overwrite an earlier release's report.
"""

from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VERSION = "v0_3_temporal_candidate_revision"
VERSION = DEFAULT_VERSION
TABLE_DIR = (
    PROJECT_ROOT
    / "reports"
    / "tables"
    / "synthetic_benchmark"
    / VERSION
    / "linkage_algorithm_benchmark"
)
FIGURE_DIR = (
    PROJECT_ROOT
    / "reports"
    / "figures"
    / "synthetic_benchmark"
    / VERSION
    / "linkage_algorithm_benchmark"
)
OUTPUT_DIR = PROJECT_ROOT / "reports" / "generated" / "synthetic_benchmark"
REPORT_STEM = "linkage_algorithm_benchmark_report"
GENERATED_DATE = "2026-07-30"
NOTEBOOK_NAME = "14_linkage_algorithm_benchmark.ipynb"


def configure(version: str) -> None:
    """Point the module's paths and labels at one benchmark version.

    The rendering functions read these as module globals, so rebinding them here
    keeps every builder function untouched. The v0.3 report retains its original
    stem and hardcoded date so re-running it reproduces the released file exactly;
    other versions take a version-prefixed stem and a date read from the tables
    they actually describe, which is what a reader needs to know.
    """
    global VERSION, TABLE_DIR, FIGURE_DIR, REPORT_STEM, GENERATED_DATE, NOTEBOOK_NAME
    VERSION = version
    TABLE_DIR = (
        PROJECT_ROOT / "reports" / "tables" / "synthetic_benchmark" / version
        / "linkage_algorithm_benchmark"
    )
    FIGURE_DIR = (
        PROJECT_ROOT / "reports" / "figures" / "synthetic_benchmark" / version
        / "linkage_algorithm_benchmark"
    )
    if version == DEFAULT_VERSION:
        return
    label = version.split("_")[1] if "_" in version else version
    REPORT_STEM = f"v0_{label}_linkage_algorithm_benchmark_report"
    NOTEBOOK_NAME = f"14_linkage_algorithm_benchmark_v0_{label}.ipynb"
    source = TABLE_DIR / "summary_metrics.csv"
    GENERATED_DATE = (
        _dt.date.fromtimestamp(source.stat().st_mtime).isoformat()
        if source.exists()
        else _dt.date.today().isoformat()
    )


ALGORITHM_LABELS = {
    "gradient_boosting": "Gradient boosting",
    "logistic_regression": "Logistic regression",
    "current_weighted_composite": "Current weighted composite",
    "fellegi_sunter_style": "Fellegi-Sunter style",
}


def pct(value: float, digits: int = 1) -> str:
    return f"{100 * value:.{digits}f}%"


def pct_tex(value: float, digits: int = 1) -> str:
    return rf"{100 * value:.{digits}f}\%"


def num(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def tex_escape(value) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def markdown_table(df: pd.DataFrame) -> str:
    headers = list(df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def latex_table(df: pd.DataFrame, caption: str, label: str, align: str | None = None) -> str:
    cols = list(df.columns)
    if align is None:
        align = "l" + "r" * (len(cols) - 1)
    header = " & ".join(tex_escape(c) for c in cols) + r" \\"
    body_lines = []
    for row in df.itertuples(index=False):
        body_lines.append(" & ".join(tex_escape(v) for v in row) + r" \\")
    body = "\n".join(body_lines)
    return rf"""
\begin{{table}}[H]
\centering
\caption{{{tex_escape(caption)}}}
\label{{{label}}}
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{{align}}}
\toprule
{header}
\midrule
{body}
\bottomrule
\end{{tabular}}%
}}
\end{{table}}
""".strip()


def latex_figure(filename: str, caption: str, label: str, width: str = "0.92\\textwidth") -> str:
    path = rel(FIGURE_DIR / filename)
    return rf"""
\begin{{figure}}[H]
\centering
\includegraphics[width={width}]{{{tex_escape(path)}}}
\caption{{{tex_escape(caption)}}}
\label{{{label}}}
\end{{figure}}
""".strip()


def load_outputs() -> dict[str, pd.DataFrame]:
    files = {
        "summary": "summary_metrics.csv",
        "thresholds": "algorithm_thresholds.csv",
        "scenario": "scenario_summary_metrics.csv",
        "bias": "bias_gap_summary.csv",
        "metadata": "world_candidate_metadata.csv",
        "recall_slices": "recall_slices.csv",
        "diagnostic_curves": "diagnostic_curve_summary.csv",
    }
    return {name: pd.read_csv(TABLE_DIR / filename) for name, filename in files.items()}


def prepare_tables(outputs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    summary = outputs["summary"].copy()
    summary["Algorithm"] = summary["algorithm"].map(ALGORITHM_LABELS)
    summary_table = summary[
        [
            "Algorithm",
            "n_predicted_pairs",
            "true_positive_pairs",
            "pair_precision",
            "pair_recall_fixed_candidate",
            "pair_recall_end_to_end",
            "pair_f1_end_to_end",
        ]
    ].rename(
        columns={
            "n_predicted_pairs": "Predicted links",
            "true_positive_pairs": "True positives",
            "pair_precision": "Precision",
            "pair_recall_fixed_candidate": "Fixed-candidate recall",
            "pair_recall_end_to_end": "End-to-end recall",
            "pair_f1_end_to_end": "End-to-end F1",
        }
    )
    for col in ["Precision", "Fixed-candidate recall", "End-to-end recall", "End-to-end F1"]:
        summary_table[col] = summary_table[col].map(lambda v: f"{v:.3f}")
    for col in ["Predicted links", "True positives"]:
        summary_table[col] = summary_table[col].map(num)

    thresholds = outputs["thresholds"].copy()
    thresholds["Algorithm"] = thresholds["algorithm"].map(ALGORITHM_LABELS)
    threshold_table = thresholds[["Algorithm", "score_col", "threshold", "threshold_source"]].rename(
        columns={
            "score_col": "Score column",
            "threshold": "Threshold",
            "threshold_source": "Threshold source",
        }
    )
    threshold_table["Threshold"] = threshold_table["Threshold"].map(lambda v: f"{v:.6g}")

    scenario = outputs["scenario"].copy()
    scenario["Algorithm"] = scenario["algorithm"].map(ALGORITHM_LABELS)
    scenario_table = scenario[
        ["scenario", "Algorithm", "mean_f1", "mean_precision", "mean_recall", "sd_f1"]
    ].rename(
        columns={
            "scenario": "Scenario",
            "mean_f1": "Mean F1",
            "mean_precision": "Mean precision",
            "mean_recall": "Mean recall",
            "sd_f1": "SD F1",
        }
    )
    for col in ["Mean F1", "Mean precision", "Mean recall", "SD F1"]:
        scenario_table[col] = scenario_table[col].map(lambda v: f"{v:.3f}")

    eval_meta = outputs["metadata"].loc[outputs["metadata"]["split"].eq("evaluation")].copy()
    scenario_meta = (
        eval_meta.groupby("scenario", as_index=False)
        .agg(
            n_worlds=("world", "count"),
            total_pairs=("n_candidate_pairs", "sum"),
            total_truth=("n_truth_in_scope", "sum"),
            total_reachable=("n_reachable_truth", "sum"),
            mean_blocking=("blocking_recall", "mean"),
            min_blocking=("blocking_recall", "min"),
            max_blocking=("blocking_recall", "max"),
        )
        .rename(
            columns={
                "scenario": "Scenario",
                "n_worlds": "Worlds",
                "total_pairs": "Candidate pairs",
                "total_truth": "Truth links",
                "total_reachable": "Reachable truth",
                "mean_blocking": "Mean blocking recall",
                "min_blocking": "Min",
                "max_blocking": "Max",
            }
        )
    )
    for col in ["Candidate pairs", "Truth links", "Reachable truth"]:
        scenario_meta[col] = scenario_meta[col].map(num)
    for col in ["Mean blocking recall", "Min", "Max"]:
        scenario_meta[col] = scenario_meta[col].map(lambda v: f"{v:.3f}")

    diagnostics = outputs["diagnostic_curves"].copy()
    diagnostics["Algorithm"] = diagnostics["algorithm"].map(ALGORITHM_LABELS)
    diagnostic_table = diagnostics[
        [
            "Algorithm",
            "roc_auc_candidate_pairs",
            "average_precision_candidate_pairs",
            "frozen_rank1_pair_precision",
            "frozen_rank1_pair_recall_end_to_end",
            "frozen_rank1_pair_f1_end_to_end",
        ]
    ].rename(
        columns={
            "roc_auc_candidate_pairs": "ROC-AUC",
            "average_precision_candidate_pairs": "Average precision",
            "frozen_rank1_pair_precision": "Frozen precision",
            "frozen_rank1_pair_recall_end_to_end": "Frozen end-to-end recall",
            "frozen_rank1_pair_f1_end_to_end": "Frozen end-to-end F1",
        }
    )
    for col in [
        "ROC-AUC",
        "Average precision",
        "Frozen precision",
        "Frozen end-to-end recall",
        "Frozen end-to-end F1",
    ]:
        diagnostic_table[col] = diagnostic_table[col].map(lambda v: f"{v:.3f}")

    return {
        "summary": summary_table,
        "thresholds": threshold_table,
        "scenario": scenario_table,
        "scenario_meta": scenario_meta,
        "diagnostics": diagnostic_table,
    }


def build_markdown(outputs: dict[str, pd.DataFrame], tables: dict[str, pd.DataFrame]) -> str:
    summary = outputs["summary"].set_index("algorithm")
    eval_meta = outputs["metadata"].loc[outputs["metadata"]["split"].eq("evaluation")]
    total_pairs = int(eval_meta["n_candidate_pairs"].sum())
    total_truth = int(eval_meta["n_truth_in_scope"].sum())
    total_reachable = int(eval_meta["n_reachable_truth"].sum())
    weighted_blocking = total_reachable / total_truth
    mean_blocking = float(eval_meta["blocking_recall"].mean())

    gb = summary.loc["gradient_boosting"]
    lr = summary.loc["logistic_regression"]
    comp = summary.loc["current_weighted_composite"]
    fs = summary.loc["fellegi_sunter_style"]

    recall_slices = outputs["recall_slices"]
    candidate_slice = recall_slices.loc[
        recall_slices["slice"].eq("candidate_count_bin")
        & recall_slices["algorithm"].eq("gradient_boosting")
    ].set_index("slice_value")
    buyer_slice = recall_slices.loc[
        recall_slices["slice"].eq("buyer_key_type")
        & recall_slices["algorithm"].eq("gradient_boosting")
    ].set_index("slice_value")
    cpv_slice = recall_slices.loc[
        recall_slices["slice"].eq("cpv_missing")
        & recall_slices["algorithm"].eq("gradient_boosting")
    ].set_index("slice_value")

    return f"""
# Synthetic BOAMP Linkage Algorithm Benchmark Report

Generated: {GENERATED_DATE}  
Benchmark version: `{VERSION}`  
Primary source notebook: `{rel(PROJECT_ROOT / 'notebooks' / NOTEBOOK_NAME)}`

## Technical Summary

Gradient boosting is the strongest current linker on the corrected synthetic benchmark. It reaches
precision **{gb['pair_precision']:.3f}**, end-to-end recall **{gb['pair_recall_end_to_end']:.3f}**,
and end-to-end pair-F1 **{gb['pair_f1_end_to_end']:.3f}** across the held-out evaluation grid.

The result is not mainly a "which classifier can separate pairs" story. It is a pipeline story:
the production candidate generator exposes only **{num(total_reachable)}** of **{num(total_truth)}**
in-scope truth links to scoring, a weighted blocking recall of **{pct(weighted_blocking)}**
and an unweighted world-average recall of **{mean_blocking:.3f}**. This is why gradient boosting has
fixed-candidate F1 **{gb['pair_f1_fixed_candidate']:.3f}** but end-to-end F1 only
**{gb['pair_f1_end_to_end']:.3f}**.

Logistic regression recovers essentially the same number of true links as gradient boosting
({num(lr['true_positive_pairs'])} versus {num(gb['true_positive_pairs'])}), but accepts far more
links ({num(lr['n_predicted_pairs'])} versus {num(gb['n_predicted_pairs'])}). The extra volume lowers
precision from **{gb['pair_precision']:.3f}** to **{lr['pair_precision']:.3f}**. The current weighted
composite and Fellegi-Sunter-style baseline remain useful comparators, but they are not the preferred
scorers under this benchmark.

## Gradient Boosting Wins, Mostly By Reducing False Positives

The four algorithms were evaluated on the same held-out candidate-pair universe. Gradient boosting
accepts fewer links than logistic regression and the composite baseline, while retaining nearly the
same true-positive count as logistic regression. That makes it the best current choice for synthetic
benchmark ranking and the least risky of the tested options for downstream survival-analysis pilots.

![Pair-F1 by evaluation mode]({rel(FIGURE_DIR / 'pair_f1_by_mode.png')})

{markdown_table(tables['summary'])}

Interpretation: logistic regression and gradient boosting have nearly identical end-to-end recall
({lr['pair_recall_end_to_end']:.3f} versus {gb['pair_recall_end_to_end']:.3f}), but gradient boosting
is much more selective. Compared with the current weighted composite, gradient boosting improves
precision by **{gb['pair_precision'] / comp['pair_precision']:.1f}x** and end-to-end F1 by
**{gb['pair_f1_end_to_end'] / comp['pair_f1_end_to_end']:.1f}x**.

## Score Diagnostics: ROC, Precision-Recall, Threshold F1, And GBM Loss

Because the synthetic benchmark has known truth, the algorithm evaluation can report full
candidate-pair discrimination curves as well as rank-1 threshold behavior. These are benchmark-truth
diagnostics only; they do not measure real BOAMP precision or recall.

![Candidate-pair ROC curves]({rel(FIGURE_DIR / 'roc_curves.png')})

![Candidate-pair precision-recall curves]({rel(FIGURE_DIR / 'precision_recall_curves.png')})

{markdown_table(tables['diagnostics'])}

The ROC curves show broad pair separability; the precision-recall curves are more informative under the
low true-match prevalence of the candidate-pair universe. Gradient boosting has the strongest average
precision and the highest frozen-threshold rank-1 F1.

![Rank-1 F1 threshold curves]({rel(FIGURE_DIR / 'rank1_f1_threshold_curves.png')})

The threshold curves mark each algorithm's frozen acceptance threshold. They show that the selected
gradient-boosting threshold is at the held-out F1 peak in this grid, while logistic regression is close
to its peak but at much lower precision.

![Gradient boosting loss curve]({rel(FIGURE_DIR / 'gbm_loss_curve.png')})

The gradient-boosting staged log-loss falls smoothly on both the training and calibration worlds. The
calibration curve remains above training loss, as expected, but does not show late-stage instability over
the 160 boosting stages used by the frozen benchmark model.

## Candidate Generation Is The Binding Constraint

End-to-end performance is much lower than fixed-candidate performance because most truth links never
enter the candidate set. The evaluation run scored **{num(total_pairs)}** candidate pairs over
**{num(total_truth)}** in-scope truth links, but only **{num(total_reachable)}** truth links were
reachable by the production candidate generator.

{markdown_table(tables['scenario_meta'])}

The stress scenario makes this clearest: it creates **386,410** candidate pairs but exposes only
**648** of **4,030** truth links to scoring. No scoring model can recover links that were never
generated. Therefore the next major gain should come from candidate generation, not only from another
classifier.

## Scenario Results Show Robust Ranking But Different Difficulty

Gradient boosting ranks first in every evaluated scenario. The ranking is stable, but the absolute
performance changes sharply as the benchmark gets harder.

![Scenario F1]({rel(FIGURE_DIR / 'scenario_pair_f1.png')})

{markdown_table(tables['scenario'])}

The easier, central, and moderate settings support useful discrimination among algorithms. The
difficult and stress settings are more diagnostic of failure modes. In stress, gradient boosting still
leads, but end-to-end F1 falls to **0.122** because blocking recall and candidate ambiguity both worsen.
Central and moderate are identical in this executed run, so they should not be interpreted as separate
difficulty levels until their scenario definitions diverge.

## Mechanical Bias Remains Visible

The benchmark shows systematic performance differences by identifier quality, candidate count, schema,
and CPV availability. These are expected linkage failure modes, but they matter because survival analysis
could inherit them.

![Recall by candidate count bin]({rel(FIGURE_DIR / 'recall_by_candidate_count_bin.png')})

For gradient boosting, end-to-end recall is **{candidate_slice.loc['1', 'recall_end_to_end']:.3f}**
when a source has exactly one candidate, but only **{candidate_slice.loc['16+', 'recall_end_to_end']:.3f}**
when it has sixteen or more candidates. This is the strongest bias diagnostic: crowded candidate
environments are under-linked.

![Recall by buyer key type]({rel(FIGURE_DIR / 'recall_by_buyer_key_type_heatmap.png')})

Identifier quality also matters. Gradient boosting recall is
**{buyer_slice.loc['RAW_SIRET', 'recall_end_to_end']:.3f}** for `RAW_SIRET` truth links versus
**{buyer_slice.loc['NAME_FALLBACK', 'recall_end_to_end']:.3f}** for `NAME_FALLBACK`. CPV availability
matters as well: recall is **{cpv_slice.loc['False', 'recall_end_to_end']:.3f}** when CPV is present
and **{cpv_slice.loc['True', 'recall_end_to_end']:.3f}** when CPV is missing.

## Thresholds And Model Setup

The current composite and Fellegi-Sunter thresholds are frozen. Logistic regression and gradient
boosting thresholds are selected on central calibration worlds `005` and `006` by F1 maximization.
Training uses central worlds `001` through `004`; evaluation uses worlds `007` through `010` across
central provisional, easier, moderate, difficult, and stress scenarios.

{markdown_table(tables['thresholds'])}

The supervised models use pair-level scoring features already produced by the project pipeline:
text similarity, CPV similarity, time score, buyer reliability score, gap features, candidate count,
schema family, buyer key type, CPV missingness, and duration missingness indicators. The report does
not claim these features are unbiased; the bias diagnostics above show that several are mechanically
important.

## Limitations And Robustness Notes

These results are valid for the current synthetic benchmark, not for real BOAMP ground truth. The
synthetic truth labels are generated, so model ranking can still contain generator-mechanism bias.
The report supports the claim that gradient boosting is best among the four tested linkers on this
synthetic benchmark; it does not prove real-world BOAMP linkage accuracy.

The aggregate metrics are corrected to use a global pair key containing scenario, world, and notice
pair. This avoids collisions from repeated synthetic notice IDs across generated worlds. The notebook
was rerun after that correction and all tables in this report use the corrected outputs.

The fixed-candidate view is useful for comparing scorers, but the end-to-end view is the decision-relevant
pipeline metric. If downstream survival analysis needs low false positives, gradient boosting is the
best candidate among the tested models. If it needs high recall, the current candidate generation must
be widened or redesigned.

## Recommended Next Steps

1. Use gradient boosting as the primary supervised linker for the next synthetic benchmark round.
2. Keep logistic regression as the interpretable supervised baseline, and keep the current composite
   and Fellegi-Sunter style models as frozen reference baselines.
3. Improve candidate generation before treating linkage as production-ready. Test wider temporal
   windows, alternate buyer-name blocking, CPV fallback blocking, and high-activity buyer handling.
4. Add a manually labeled real BOAMP validation set before making claims about real BOAMP accuracy.
5. Run survival-analysis sensitivity with at least three linkage layers: current composite, gradient
   boosting, and a high-precision conservative subset.

## Further Questions

1. How much end-to-end recall is recovered by widening candidate generation without creating too many
   false-positive candidates?
2. Are high-activity buyers under-linked enough to bias survival estimates?
3. Can a conservative gradient-boosting threshold provide a high-precision survival layer while a broader
   threshold supports recall sensitivity?
4. Do manually labeled real BOAMP pairs preserve the same algorithm ranking observed in synthetic truth?

## Source Artifacts

- Executed notebook: `{rel(PROJECT_ROOT / 'notebooks' / NOTEBOOK_NAME)}`
- Summary table: `{rel(TABLE_DIR / 'summary_metrics.csv')}`
- Scenario table: `{rel(TABLE_DIR / 'scenario_summary_metrics.csv')}`
- Bias diagnostics: `{rel(TABLE_DIR / 'recall_slices.csv')}`
- ROC curve points: `{rel(TABLE_DIR / 'roc_curve_points.csv')}`
- Precision-recall curve points: `{rel(TABLE_DIR / 'precision_recall_curve_points.csv')}`
- Rank-1 F1 threshold curve: `{rel(TABLE_DIR / 'rank1_f1_threshold_curve.csv')}`
- GBM loss curve: `{rel(TABLE_DIR / 'gbm_loss_curve.csv')}`
- Diagnostic curve summary: `{rel(TABLE_DIR / 'diagnostic_curve_summary.csv')}`
"""


def build_latex(outputs: dict[str, pd.DataFrame], tables: dict[str, pd.DataFrame]) -> str:
    summary = outputs["summary"].set_index("algorithm")
    eval_meta = outputs["metadata"].loc[outputs["metadata"]["split"].eq("evaluation")]
    total_pairs = int(eval_meta["n_candidate_pairs"].sum())
    total_truth = int(eval_meta["n_truth_in_scope"].sum())
    total_reachable = int(eval_meta["n_reachable_truth"].sum())
    weighted_blocking = total_reachable / total_truth
    mean_blocking = float(eval_meta["blocking_recall"].mean())

    gb = summary.loc["gradient_boosting"]
    lr = summary.loc["logistic_regression"]
    comp = summary.loc["current_weighted_composite"]

    recall_slices = outputs["recall_slices"]
    candidate_slice = recall_slices.loc[
        recall_slices["slice"].eq("candidate_count_bin")
        & recall_slices["algorithm"].eq("gradient_boosting")
    ].set_index("slice_value")
    buyer_slice = recall_slices.loc[
        recall_slices["slice"].eq("buyer_key_type")
        & recall_slices["algorithm"].eq("gradient_boosting")
    ].set_index("slice_value")
    cpv_slice = recall_slices.loc[
        recall_slices["slice"].eq("cpv_missing")
        & recall_slices["algorithm"].eq("gradient_boosting")
    ].set_index("slice_value")

    return rf"""
\documentclass[11pt]{{article}}
\usepackage[margin=0.75in]{{geometry}}
\usepackage{{booktabs}}
\usepackage{{array}}
\usepackage{{graphicx}}
\usepackage{{float}}
\usepackage{{hyperref}}
\usepackage{{xurl}}
\usepackage{{xcolor}}
\usepackage{{caption}}
\usepackage{{enumitem}}
\hypersetup{{colorlinks=true, linkcolor=blue, urlcolor=blue}}
\setlist[itemize]{{topsep=2pt,itemsep=2pt}}
\setlist[enumerate]{{topsep=2pt,itemsep=2pt}}

\title{{Synthetic BOAMP Linkage Algorithm Benchmark Report}}
\author{{Generated from the corrected synthetic benchmark notebook}}
\date{{{GENERATED_DATE}}}

\begin{{document}}
\maketitle

\section*{{Technical Summary}}

Gradient boosting is the strongest current linker on the corrected synthetic benchmark. It reaches
precision \textbf{{{gb['pair_precision']:.3f}}}, end-to-end recall \textbf{{{gb['pair_recall_end_to_end']:.3f}}},
and end-to-end pair-F1 \textbf{{{gb['pair_f1_end_to_end']:.3f}}} across the held-out evaluation grid.

The result is not mainly a classifier-only story. It is a pipeline story: the production candidate
generator exposes only \textbf{{{num(total_reachable)}}} of \textbf{{{num(total_truth)}}} in-scope truth links
to scoring, a weighted blocking recall of \textbf{{{pct_tex(weighted_blocking)}}} and an unweighted
world-average recall of \textbf{{{mean_blocking:.3f}}}. This is why gradient boosting has
fixed-candidate F1 \textbf{{{gb['pair_f1_fixed_candidate']:.3f}}} but end-to-end F1 only
\textbf{{{gb['pair_f1_end_to_end']:.3f}}}.

Logistic regression recovers essentially the same number of true links as gradient boosting
({num(lr['true_positive_pairs'])} versus {num(gb['true_positive_pairs'])}), but accepts far more links
({num(lr['n_predicted_pairs'])} versus {num(gb['n_predicted_pairs'])}). The extra volume lowers
precision from \textbf{{{gb['pair_precision']:.3f}}} to \textbf{{{lr['pair_precision']:.3f}}}. The current
weighted composite and Fellegi-Sunter-style baseline remain useful comparators, but they are not the
preferred scorers under this benchmark.

\section*{{Gradient Boosting Wins, Mostly By Reducing False Positives}}

The four algorithms were evaluated on the same held-out candidate-pair universe. Gradient boosting
accepts fewer links than logistic regression and the composite baseline, while retaining nearly the same
true-positive count as logistic regression. That makes it the best current choice for synthetic
benchmark ranking and the least risky of the tested options for downstream survival-analysis pilots.

{latex_figure('pair_f1_by_mode.png', 'Pair-F1 by algorithm and evaluation mode. Fixed-candidate performance is much higher because unreachable truth links are excluded from that denominator.', 'fig:pair-f1')}

{latex_table(tables['summary'], 'Aggregate held-out performance by algorithm.', 'tab:summary')}

Compared with the current weighted composite, gradient boosting improves precision by
\textbf{{{gb['pair_precision'] / comp['pair_precision']:.1f}x}} and end-to-end F1 by
\textbf{{{gb['pair_f1_end_to_end'] / comp['pair_f1_end_to_end']:.1f}x}}.

\section*{{Score Diagnostics: ROC, Precision-Recall, Threshold F1, And GBM Loss}}

Because the synthetic benchmark has known truth, the algorithm evaluation can report full candidate-pair
discrimination curves as well as rank-1 threshold behavior. These are benchmark-truth diagnostics only;
they do not measure real BOAMP precision or recall.

{latex_figure('roc_curves.png', 'Candidate-pair ROC curves. Gradient boosting and logistic regression separate candidate pairs best by ROC-AUC.', 'fig:roc-curves')}

{latex_figure('precision_recall_curves.png', 'Candidate-pair precision-recall curves. Average precision is more diagnostic than ROC-AUC under low true-match prevalence.', 'fig:pr-curves')}

{latex_table(tables['diagnostics'], 'Curve diagnostics and frozen-threshold rank-1 performance.', 'tab:curve-diagnostics')}

The ROC curves show broad pair separability; the precision-recall curves are more informative under the
low true-match prevalence of the candidate-pair universe. Gradient boosting has the strongest average
precision and the highest frozen-threshold rank-1 F1.

{latex_figure('rank1_f1_threshold_curves.png', 'Rank-1 end-to-end F1 over acceptance thresholds. Points mark the frozen thresholds used in the benchmark.', 'fig:rank1-threshold')}

The threshold curves show that the selected gradient-boosting threshold is at the held-out F1 peak in
this grid, while logistic regression is close to its peak but at much lower precision.

{latex_figure('gbm_loss_curve.png', 'Gradient boosting staged log-loss on fit and calibration worlds.', 'fig:gbm-loss')}

The gradient-boosting staged log-loss falls smoothly on both the training and calibration worlds. The
calibration curve remains above training loss, as expected, but does not show late-stage instability over
the 160 boosting stages used by the frozen benchmark model.

\section*{{Candidate Generation Is The Binding Constraint}}

End-to-end performance is much lower than fixed-candidate performance because most truth links never
enter the candidate set. The evaluation run scored \textbf{{{num(total_pairs)}}} candidate pairs over
\textbf{{{num(total_truth)}}} in-scope truth links, but only \textbf{{{num(total_reachable)}}} truth links
were reachable by the production candidate generator.

{latex_table(tables['scenario_meta'], 'Candidate-generation reachability by evaluation scenario.', 'tab:blocking')}

The stress scenario makes this clearest: it creates 386,410 candidate pairs but exposes only 648 of
4,030 truth links to scoring. No scoring model can recover links that were never generated. Therefore
the next major gain should come from candidate generation, not only from another classifier.

\section*{{Scenario Results Show Robust Ranking But Different Difficulty}}

Gradient boosting ranks first in every evaluated scenario. The ranking is stable, but absolute
performance changes sharply as the benchmark gets harder.

{latex_figure('scenario_pair_f1.png', 'Held-out end-to-end pair-F1 by scenario. Gradient boosting leads throughout, but stress and difficult scenarios lower all algorithms.', 'fig:scenario-f1')}

{latex_table(tables['scenario'], 'Mean held-out performance by scenario and algorithm.', 'tab:scenario')}

The easier, central, and moderate settings support useful discrimination among algorithms. The
difficult and stress settings are more diagnostic of failure modes. In stress, gradient boosting still
leads, but end-to-end F1 falls to \textbf{{0.122}} because blocking recall and candidate ambiguity both
worsen. Central and moderate are identical in this executed run, so they should not be interpreted as
separate difficulty levels until their scenario definitions diverge.

\section*{{Mechanical Bias Remains Visible}}

The benchmark shows systematic performance differences by identifier quality, candidate count, schema,
and CPV availability. These are expected linkage failure modes, but they matter because survival
analysis could inherit them.

{latex_figure('recall_by_candidate_count_bin.png', 'End-to-end recall by candidate count bin. Crowded candidate lists sharply reduce recall.', 'fig:candidate-bin')}

For gradient boosting, end-to-end recall is \textbf{{{candidate_slice.loc['1', 'recall_end_to_end']:.3f}}}
when a source has exactly one candidate, but only
\textbf{{{candidate_slice.loc['16+', 'recall_end_to_end']:.3f}}} when it has sixteen or more candidates.
This is the strongest bias diagnostic: crowded candidate environments are under-linked.

{latex_figure('recall_by_buyer_key_type_heatmap.png', 'End-to-end recall by buyer key type. Cleaner identifiers remain easier to link.', 'fig:buyer-key')}

Identifier quality also matters. Gradient boosting recall is
\textbf{{{buyer_slice.loc['RAW_SIRET', 'recall_end_to_end']:.3f}}} for RAW\_SIRET truth links versus
\textbf{{{buyer_slice.loc['NAME_FALLBACK', 'recall_end_to_end']:.3f}}} for NAME\_FALLBACK. CPV availability
matters as well: recall is \textbf{{{cpv_slice.loc['False', 'recall_end_to_end']:.3f}}} when CPV is present
and \textbf{{{cpv_slice.loc['True', 'recall_end_to_end']:.3f}}} when CPV is missing.

\section*{{Thresholds And Model Setup}}

The current composite and Fellegi-Sunter thresholds are frozen. Logistic regression and gradient
boosting thresholds are selected on central calibration worlds 005 and 006 by F1 maximization. Training
uses central worlds 001 through 004; evaluation uses worlds 007 through 010 across central provisional,
easier, moderate, difficult, and stress scenarios.

{latex_table(tables['thresholds'], 'Algorithm score columns and thresholds used in the executed benchmark.', 'tab:thresholds')}

The supervised models use pair-level scoring features already produced by the project pipeline: text
similarity, CPV similarity, time score, buyer reliability score, gap features, candidate count, schema
family, buyer key type, CPV missingness, and duration missingness indicators. The report does not claim
these features are unbiased; the bias diagnostics above show that several are mechanically important.

\section*{{Limitations, Robustness, And Interpretation}}

These results are valid for the current synthetic benchmark, not for real BOAMP ground truth. The
synthetic truth labels are generated, so model ranking can still contain generator-mechanism bias. The
report supports the claim that gradient boosting is best among the four tested linkers on this synthetic
benchmark; it does not prove real-world BOAMP linkage accuracy.

The aggregate metrics are corrected to use a global pair key containing scenario, world, and notice
pair. This avoids collisions from repeated synthetic notice IDs across generated worlds. The notebook
was rerun after that correction and all tables in this report use the corrected outputs.

The fixed-candidate view is useful for comparing scorers, but the end-to-end view is the
decision-relevant pipeline metric. If downstream survival analysis needs low false positives, gradient
boosting is the best candidate among the tested models. If it needs high recall, the current candidate
generation must be widened or redesigned.

\section*{{Recommended Next Steps}}

\begin{{enumerate}}
\item Use gradient boosting as the primary supervised linker for the next synthetic benchmark round.
\item Keep logistic regression as the interpretable supervised baseline, and keep the current composite
and Fellegi-Sunter style models as frozen reference baselines.
\item Improve candidate generation before treating linkage as production-ready. Test wider temporal
windows, alternate buyer-name blocking, CPV fallback blocking, and high-activity buyer handling.
\item Add a manually labeled real BOAMP validation set before making claims about real BOAMP accuracy.
\item Run survival-analysis sensitivity with at least three linkage layers: current composite, gradient
boosting, and a high-precision conservative subset.
\end{{enumerate}}

\section*{{Further Questions}}

\begin{{enumerate}}
\item How much end-to-end recall is recovered by widening candidate generation without creating too many
false-positive candidates?
\item Are high-activity buyers under-linked enough to bias survival estimates?
\item Can a conservative gradient-boosting threshold provide a high-precision survival layer while a
broader threshold supports recall sensitivity?
\item Do manually labeled real BOAMP pairs preserve the same algorithm ranking observed in synthetic truth?
\end{{enumerate}}

\section*{{Source Artifacts}}

\begin{{itemize}}
\item Benchmark version: \texttt{{{tex_escape(VERSION)}}}
\item Executed notebook: \path{{{rel(PROJECT_ROOT / 'notebooks' / NOTEBOOK_NAME)}}}
\item Summary table: \path{{{rel(TABLE_DIR / 'summary_metrics.csv')}}}
\item Scenario table: \path{{{rel(TABLE_DIR / 'scenario_summary_metrics.csv')}}}
\item Bias diagnostics: \path{{{rel(TABLE_DIR / 'recall_slices.csv')}}}
\item ROC curve points: \path{{{rel(TABLE_DIR / 'roc_curve_points.csv')}}}
\item Precision-recall curve points: \path{{{rel(TABLE_DIR / 'precision_recall_curve_points.csv')}}}
\item Rank-1 F1 threshold curve: \path{{{rel(TABLE_DIR / 'rank1_f1_threshold_curve.csv')}}}
\item GBM loss curve: \path{{{rel(TABLE_DIR / 'gbm_loss_curve.csv')}}}
\item Diagnostic curve summary: \path{{{rel(TABLE_DIR / 'diagnostic_curve_summary.csv')}}}
\end{{itemize}}

\end{{document}}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    args = parser.parse_args()
    configure(args.version)

    outputs = load_outputs()
    tables = prepare_tables(outputs)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    markdown = build_markdown(outputs, tables)
    latex = build_latex(outputs, tables)

    md_path = OUTPUT_DIR / f"{REPORT_STEM}.md"
    tex_path = OUTPUT_DIR / f"{REPORT_STEM}.tex"
    md_path.write_text(markdown.strip() + "\n", encoding="utf-8")
    tex_path.write_text(latex.strip() + "\n", encoding="utf-8")
    print(f"Wrote {md_path.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {tex_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
