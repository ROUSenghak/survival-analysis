"""
Generate academic-style diagrams for the M1 SIREN enrichment plus
procurement-profile audit workflow.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"
TABLES_DIR = REPORTS_DIR / "tables"
FIGURES_DIR = REPORTS_DIR / "figures"
RUN_LOG_DIR = REPORTS_DIR / "run_logs"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)


def fmt_int(value) -> str:
    return f"{int(value):,}"


def pct(value) -> str:
    return f"{float(value):.1%}"


def add_box(ax, xy, w, h, title, body="", fc="#f8fafc", ec="#334155", fontsize=9):
    x, y = xy
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.015",
        linewidth=1.15,
        edgecolor=ec,
        facecolor=fc,
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h - 0.035, title, ha="center", va="top", fontsize=fontsize, weight="bold", color="#0f172a")
    if body:
        ax.text(x + w / 2, y + h / 2 - 0.01, body, ha="center", va="center", fontsize=fontsize - 1, color="#1f2937", linespacing=1.25)
    return box


def arrow(ax, start, end, color="#475569", rad=0.0):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=11,
        linewidth=1.05,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
    )
    ax.add_patch(patch)


def pipeline_diagram(values: dict) -> None:
    fig, ax = plt.subplots(figsize=(15, 8.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_title("BOAMP Proxy-Recurrence Pipeline With M1 Buyer Enrichment and Profile-Domain Audit", fontsize=15, weight="bold", pad=18)

    add_box(ax, (0.04, 0.74), 0.18, 0.15, "BOAMP Raw Corpus", "PDL notices\n2015-2026\nJSON -> flat table", "#eef2ff")
    add_box(ax, (0.29, 0.74), 0.18, 0.15, "M0 Cleaning", "BOAMP-only buyer keys\nSIRET/SIREN/name fallback\nDigital ICT scope", "#eff6ff")
    add_box(ax, (0.54, 0.74), 0.18, 0.15, "M0 Linkage Baseline", f"{fmt_int(values['m0_sources'])} sources\n{fmt_int(values['m0_pairs'])} pairs\n{fmt_int(values['m0_links'])} links", "#f0f9ff")
    add_box(ax, (0.78, 0.74), 0.18, 0.15, "M0 Survival Handoff", f"Proxy recurrence\nrate {pct(values['m0_rate'])}\nOfficial baseline", "#f8fafc")

    add_box(ax, (0.04, 0.43), 0.18, 0.16, "External SIREN Join", "Data-Gouv-ML\n2024, 2025, 2026\nnotice-id join", "#f0fdf4")
    add_box(ax, (0.29, 0.43), 0.18, 0.16, "Identity Validation", f"SIREN/SIRET agreement\n{pct(values['siren_agreement'])}\n{fmt_int(values['siren_conflicts'])} conflicts traced", "#ecfdf5")
    add_box(ax, (0.54, 0.43), 0.18, 0.16, "Historical Alias Bridge", f"{fmt_int(values['auto_aliases'])} auto aliases\n{fmt_int(values['ambiguous_aliases'])} review-only\nNo fake SIRET", "#f7fee7")
    add_box(ax, (0.78, 0.43), 0.18, 0.16, "M1 Linkage", f"{fmt_int(values['m1_pairs'])} pairs\n{fmt_int(values['m1_links'])} links\nrate {pct(values['m1_rate'])}", "#f0fdf4")

    add_box(ax, (0.04, 0.12), 0.18, 0.16, "Profile Dataset", f"{fmt_int(values['profile_rows'])} rows\nbuyer-name + domains\n2015-2020 observed", "#fff7ed")
    add_box(ax, (0.29, 0.12), 0.18, 0.16, "Domain Normalization", f"{fmt_int(values['profile_domains'])} profile domains\n{fmt_int(values['generic_domains'])} generic platforms\nraw URLs preserved", "#fffbeb")
    add_box(ax, (0.54, 0.12), 0.18, 0.16, "Profile Evidence Audit", f"{fmt_int(values['strong_aliases'])} strong aliases\n{fmt_int(values['neutral_aliases'])} neutral/shared\n{fmt_int(values['no_profile_aliases'])} no evidence", "#fefce8")
    add_box(ax, (0.78, 0.12), 0.18, 0.16, "Profile-Audited M1", f"{fmt_int(values['profile_links'])} links\n{fmt_int(values['profile_removed'])} removed\nJaccard vs M1 {values['profile_jaccard']:.3f}", "#fff7ed")

    for y in [0.815, 0.51, 0.2]:
        arrow(ax, (0.22, y), (0.29, y))
        arrow(ax, (0.47, y), (0.54, y))
        arrow(ax, (0.72, y), (0.78, y))
    arrow(ax, (0.63, 0.74), (0.63, 0.59), rad=-0.08)
    arrow(ax, (0.87, 0.43), (0.87, 0.28), rad=-0.08)
    arrow(ax, (0.47, 0.20), (0.54, 0.49), rad=0.18)

    ax.text(0.5, 0.035, "Profile domains annotate evidence and filter only explicit conflicts; they never create buyer identity matches.", ha="center", fontsize=10, color="#334155")
    for ext in ["png", "pdf"]:
        fig.savefig(FIGURES_DIR / f"m1_enrichment_profile_pipeline.{ext}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def runflow_diagram(values: dict) -> None:
    fig, ax = plt.subplots(figsize=(14, 7.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_title("Reproducible Run Flow and Evidence Surfaces", fontsize=15, weight="bold", pad=16)

    steps = [
        ("1. Audit Inputs", "Repository state\nraw data hashes\nschema checks", "#e0f2fe"),
        ("2. Build M0", "clean notices\ncandidate pairs\nbalanced links", "#dbeafe"),
        ("3. Build M1", "direct SIREN join\nalias bridge\ncandidate reranking", "#dcfce7"),
        ("4. Compare M0/M1", f"+{fmt_int(values['incremental_links'])} incremental links\nJaccard {values['m1_jaccard']:.3f}\nreuse {pct(values['m1_reuse'])}", "#ecfccb"),
        ("5. Profile Audit", "normalize domains\nclassify specificity\nannotate aliases/links", "#fef3c7"),
        ("6. Manual Review", "unlabeled sample\nidentity question\nrecurrence question", "#fae8ff"),
    ]
    x0, w, gap = 0.04, 0.135, 0.027
    y, h = 0.56, 0.25
    centers = []
    for i, (title, body, color) in enumerate(steps):
        x = x0 + i * (w + gap)
        add_box(ax, (x, y), w, h, title, body, color, fontsize=8.8)
        centers.append((x + w / 2, y + h / 2))
    for i in range(len(centers) - 1):
        arrow(ax, (centers[i][0] + w / 2 - 0.006, centers[i][1]), (centers[i + 1][0] - w / 2 + 0.006, centers[i + 1][1]))

    outputs = [
        ("Machine-Readable Tables", "CSV audits, comparisons,\nprofile evidence, consistency checks", 0.12),
        ("Figures", "pipeline diagram\nrun-flow diagram", 0.39),
        ("Reports", "M1 enrichment report\nprofile audit report\nintegrated report", 0.66),
    ]
    for title, body, x in outputs:
        add_box(ax, (x, 0.16), 0.22, 0.16, title, body, "#f8fafc", fontsize=9.5)
        arrow(ax, (x + 0.11, 0.56), (x + 0.11, 0.32), rad=0.0)

    ax.text(0.5, 0.065, "All event outcomes remain constructed proxy recurrences, not verified legal renewals.", ha="center", fontsize=10, color="#334155")
    for ext in ["png", "pdf"]:
        fig.savefig(FIGURES_DIR / f"m1_reproducible_runflow.{ext}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def load_values() -> dict:
    m0m1 = pd.read_csv(TABLES_DIR / "m0_m1_linkage_comparison.csv")
    profile_comp = pd.read_csv(TABLES_DIR / "m0_m1_profile_comparison.csv")
    siren_agreement = pd.read_csv(TABLES_DIR / "buyer_siren_agreement_by_dimension.csv")
    conflicts = pd.read_csv(TABLES_DIR / "buyer_identifier_conflicts.csv")
    hist = pd.read_csv(TABLES_DIR / "m1_historical_alias_recovery_diagnostics.csv")
    profile_audit = pd.read_csv(TABLES_DIR / "procurement_profile_dataset_audit.csv").set_index("metric")["value"]
    domain_class = pd.read_csv(TABLES_DIR / "procurement_profile_domain_classification.csv")
    alias_profile = pd.read_csv(TABLES_DIR / "m1_alias_profile_evidence.csv")
    status = pd.read_csv(TABLES_DIR / "m0_m1_link_status_changes.csv").iloc[0]

    m0 = m0m1[m0m1["method"] == "M0_BALANCED_OFFICIAL"].iloc[0]
    m1 = m0m1[m0m1["method"] == "M1_BUYER_SIREN_ENRICHED"].iloc[0]
    prof = profile_comp[profile_comp["method"] == "M1_PROFILE_AUDITED"].iloc[0]
    hist_lookup = hist.set_index("metric")["value"].to_dict()
    agree = siren_agreement[(siren_agreement["dimension"] == "overall") & (siren_agreement["value"] == "all")].iloc[0]
    return {
        "m0_sources": m0["eligible_source_count"],
        "m0_pairs": m0["candidate_pair_count"],
        "m0_links": m0["accepted_links"],
        "m0_rate": m0["overall_linking_rate"],
        "m1_pairs": m1["candidate_pair_count"],
        "m1_links": m1["accepted_links"],
        "m1_rate": m1["overall_linking_rate"],
        "m1_reuse": m1["candidate_reuse_rate"],
        "m1_jaccard": status["link_set_jaccard_overlap"],
        "incremental_links": status["links_in_m1_not_m0"],
        "siren_agreement": agree["agreement_rate"],
        "siren_conflicts": len(conflicts),
        "auto_aliases": hist_lookup.get("automatic_historical_aliases", 0),
        "ambiguous_aliases": hist_lookup.get("ambiguous_or_review_only_aliases", 0),
        "profile_rows": int(profile_audit["row_count"]),
        "profile_domains": int(profile_audit["distinct_profile_domains"]),
        "generic_domains": int((domain_class["domain_specificity"] == "GENERIC_PLATFORM").sum()),
        "strong_aliases": int((alias_profile["profile_evidence_status"] == "STRONG_SUPPORT").sum()),
        "neutral_aliases": int((alias_profile["profile_evidence_status"] == "NEUTRAL_SHARED_PLATFORM").sum()),
        "no_profile_aliases": int((alias_profile["profile_evidence_status"] == "NO_PROFILE_EVIDENCE").sum()),
        "profile_links": prof["accepted_links"],
        "profile_removed": prof["links_removed_vs_m1"],
        "profile_jaccard": prof["jaccard_vs_m1"],
    }


def write_reporting_summary(values: dict) -> None:
    profile_counts = pd.read_csv(TABLES_DIR / "m1_alias_profile_evidence.csv")["profile_evidence_status"].value_counts().to_dict()
    incremental_counts = pd.read_csv(TABLES_DIR / "m1_incremental_links_profile_audit.csv")["profile_evidence_status"].value_counts().to_dict()
    text = f"""# M1 diagram generation summary

This is a generated run summary, not the canonical human report. The
consolidated M1 report is `reports/boamp_m1_technical_report.tex` / `.pdf`.

Generated: 2026-07-15

## Figures

- Pipeline diagram: `reports/figures/m1_enrichment_profile_pipeline.png` and `.pdf`.
- Reproducible run-flow diagram: `reports/figures/m1_reproducible_runflow.png` and `.pdf`.

## Pipeline Summary

M0 is the BOAMP-only baseline. M1 is a separate SIREN-enriched sensitivity specification that keeps the M0 source population, scoring components, ranking logic, and balanced threshold, while changing buyer blocking through validated SIRET/SIREN and conservative historical aliases. The procurement-profile audit is a second-stage evidence overlay; it annotates aliases and links but never creates buyer identity.

## M0 to M1 Results

- Eligible sources: {fmt_int(values['m0_sources'])}.
- Candidate pairs: M0 {fmt_int(values['m0_pairs'])}; M1 {fmt_int(values['m1_pairs'])}.
- Accepted balanced links: M0 {fmt_int(values['m0_links'])}; M1 {fmt_int(values['m1_links'])}.
- Proxy-recurrence rate: M0 {pct(values['m0_rate'])}; M1 {pct(values['m1_rate'])}.
- Incremental M1 links: {fmt_int(values['incremental_links'])}.
- Link-set Jaccard overlap: {values['m1_jaccard']:.3f}.

## SIREN Evidence

- Direct SIREN enrichment covers 2024, 2025, and 2026.
- Overall BOAMP SIRET-derived SIREN versus enriched SIREN agreement: {pct(values['siren_agreement'])}.
- Identifier conflicts exported for inspection: {fmt_int(values['siren_conflicts'])}.
- Historical aliases eligible for automatic propagation: {fmt_int(values['auto_aliases'])}.
- Ambiguous or review-only aliases: {fmt_int(values['ambiguous_aliases'])}.

## Procurement-Profile Evidence

- Profile rows: {fmt_int(values['profile_rows'])}.
- Distinct normalized profile domains: {fmt_int(values['profile_domains'])}.
- Generic-platform domains: {fmt_int(values['generic_domains'])}.
- Alias profile-evidence counts: {json.dumps(profile_counts, ensure_ascii=False)}.
- Incremental-link profile-evidence counts: {json.dumps(incremental_counts, ensure_ascii=False)}.

## Profile-Audited Variant

The profile-audited M1 variant removes only explicit profile-domain conflicts among historical-alias candidate pairs. Under the conservative rule, no explicit conflicts were found, so the variant is identical to M1:

- Profile-audited accepted links: {fmt_int(values['profile_links'])}.
- Links removed versus M1: {fmt_int(values['profile_removed'])}.
- Jaccard versus M1: {values['profile_jaccard']:.3f}.

## Interpretation

The SIREN enrichment increases coverage and link yield, but it remains a sensitivity specification until the incremental links are manually validated. Procurement-profile domains add useful manual-review context and weak support for some aliases, but they are often shared platforms and should not be treated as legal identifiers. M0 remains the primary conservative baseline; M1 and the profile-audited M1 remain sensitivity analyses.

## Reproducibility

```bash
python3 scripts/build_m1_buyer_siren_experiment.py
python3 scripts/build_m1_profile_domain_audit.py
MPLCONFIGDIR=/tmp/matplotlib-m1-report python3 scripts/make_m1_academic_diagrams.py
```
"""
    (RUN_LOG_DIR / "m1_diagram_generation_summary.md").write_text(text)


def main() -> None:
    values = load_values()
    pipeline_diagram(values)
    runflow_diagram(values)
    write_reporting_summary(values)
    run_log = {
        "generated_figures": [
            "reports/figures/m1_enrichment_profile_pipeline.png",
            "reports/figures/m1_enrichment_profile_pipeline.pdf",
            "reports/figures/m1_reproducible_runflow.png",
            "reports/figures/m1_reproducible_runflow.pdf",
        ],
        "generated_summary": "reports/run_logs/m1_diagram_generation_summary.md",
        "canonical_report": "reports/boamp_m1_technical_report.tex",
    }
    (RUN_LOG_DIR / "m1_reporting_update_run_log.json").write_text(json.dumps(run_log, indent=2))
    print("Generated M1 reporting diagrams.")
    for item in run_log["generated_figures"]:
        print(item)
    print(run_log["generated_summary"])


if __name__ == "__main__":
    main()
