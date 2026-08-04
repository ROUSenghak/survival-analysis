"""Build exploratory real-vs-synthetic plausibility visuals for v0.4.

This is deliberately descriptive EDA, not a readiness gate. It compares the
prepared real BOAMP corpus with one synthetic observed-notices artifact and saves
compact figures plus summary tables that are easy to inspect.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.synthetic.compatibility import adapt_observed_notices_to_sources  # noqa: E402

VERSION = "v0_4_population_alias_revision"
DEFAULT_SYNTHETIC = (
    ROOT
    / "data"
    / "processed"
    / "synthetic_benchmark"
    / VERSION
    / "central_provisional"
    / "world_001"
    / "corruption_001"
    / "observed_notices.parquet"
)
DEFAULT_REAL = ROOT / "data" / "interim" / "boamp_common_prepared.csv"
DEFAULT_FIG_DIR = ROOT / "reports" / "figures" / "synthetic_benchmark" / VERSION / "eda_real_synthetic"
DEFAULT_TABLE_DIR = ROOT / "reports" / "tables" / "synthetic_benchmark" / VERSION / "eda_real_synthetic"

REAL_C = "#2a78d6"
SYN_C = "#1baf7a"
INK = "#0b0b0b"
MUTED = "#7a7a72"
GRID = "#e1e0d9"
RULE = "#c3c2b7"

plt.rcParams.update(
    {
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
    }
)


def _despine(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_axisbelow(True)


def _clean_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str)


def _cpv_division(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    out = numeric.astype("Int64").astype(str).replace("<NA>", pd.NA)
    return out.str.zfill(2)


def _read_real(path: Path) -> pd.DataFrame:
    cols = [
        "notice_id",
        "publication_date",
        "publication_year",
        "notice_type_normalized",
        "schema_family",
        "buyer_siret_clean",
        "buyer_siren_clean",
        "buyer_name_normalized",
        "buyer_key",
        "buyer_key_type",
        "cpv_clean",
        "cpv_division",
        "declared_duration_months",
        "objet_clean",
        "text_length",
        "token_count",
    ]
    df = pd.read_csv(path, usecols=cols, low_memory=False)
    df["publication_date"] = pd.to_datetime(df["publication_date"], errors="coerce")
    df["cpv_division"] = _cpv_division(df["cpv_division"])
    df["dataset"] = "Real BOAMP"
    df["notice_id_eda"] = df["notice_id"].astype(str)
    df["siret_present"] = df["buyer_siret_clean"].notna()
    df["siren_present"] = df["buyer_siren_clean"].notna()
    df["objet_clean"] = _clean_text(df["objet_clean"])
    df["text_length"] = pd.to_numeric(df["text_length"], errors="coerce").fillna(df["objet_clean"].str.len())
    df["token_count"] = pd.to_numeric(df["token_count"], errors="coerce").fillna(
        df["objet_clean"].str.split().str.len()
    )
    return df


def _read_synthetic(path: Path) -> pd.DataFrame:
    observed = pd.read_parquet(path)
    df = adapt_observed_notices_to_sources(observed)
    df["publication_date"] = pd.to_datetime(df["publication_date"], errors="coerce")
    df["publication_year"] = df["publication_date"].dt.year
    df["cpv_division"] = _cpv_division(df["cpv_division"])
    df["dataset"] = "Synthetic v0.4"
    df["notice_id_eda"] = df["notice_id_synthetic"].astype(str)
    df["siret_present"] = df["buyer_siret_clean"].notna()
    df["siren_present"] = df["buyer_siren_clean"].notna()
    df["objet_clean"] = _clean_text(df["objet_clean"])
    df["text_length"] = df["objet_clean"].str.len()
    df["token_count"] = df["objet_clean"].str.split().str.len()
    return df


def _share_table(real: pd.DataFrame, syn: pd.DataFrame, column: str, top_n: int | None = None) -> pd.DataFrame:
    rows = []
    for label, df in [("Real BOAMP", real), ("Synthetic v0.4", syn)]:
        values = df[column].fillna("MISSING").astype(str)
        shares = values.value_counts(normalize=True)
        if top_n:
            keep = shares.head(top_n).index
            values = values.where(values.isin(keep), "OTHER")
            shares = values.value_counts(normalize=True)
        rows.extend({"dataset": label, column: k, "share": v} for k, v in shares.items())
    return pd.DataFrame(rows)


def _distribution_tv(real: pd.Series, syn: pd.Series) -> float:
    r = real.fillna("MISSING").astype(str).value_counts(normalize=True)
    s = syn.fillna("MISSING").astype(str).value_counts(normalize=True)
    keys = r.index.union(s.index)
    return float(0.5 * np.abs(r.reindex(keys, fill_value=0) - s.reindex(keys, fill_value=0)).sum())


def _w1_scaled(real: pd.Series, syn: pd.Series) -> float:
    r = pd.to_numeric(real, errors="coerce").dropna().to_numpy()
    s = pd.to_numeric(syn, errors="coerce").dropna().to_numpy()
    if len(r) == 0 or len(s) == 0:
        return np.nan
    grid = np.linspace(0, 1, 401)
    rq = np.quantile(r, grid)
    sq = np.quantile(s, grid)
    scale = np.subtract(*np.quantile(r, [0.95, 0.05]))
    return float(np.mean(np.abs(rq - sq)) / scale) if scale else np.nan


def _top_share(counts: pd.Series, n: int) -> float:
    if counts.empty or counts.sum() == 0:
        return np.nan
    return float(counts.sort_values(ascending=False).head(n).sum() / counts.sum())


def _summaries(real: pd.DataFrame, syn: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    for label, df in [("Real BOAMP", real), ("Synthetic v0.4", syn)]:
        buyer_counts = df.groupby("buyer_key", dropna=True).size()
        summary_rows.extend(
            [
                {"dataset": label, "metric": "notices", "value": len(df)},
                {"dataset": label, "metric": "publication_year_min", "value": df["publication_year"].min()},
                {"dataset": label, "metric": "publication_year_max", "value": df["publication_year"].max()},
                {"dataset": label, "metric": "unique_buyer_keys", "value": buyer_counts.size},
                {"dataset": label, "metric": "buyer_keys_per_notice", "value": buyer_counts.size / len(df)},
                {"dataset": label, "metric": "siret_present_share", "value": df["siret_present"].mean()},
                {"dataset": label, "metric": "siren_present_share", "value": df["siren_present"].mean()},
                {"dataset": label, "metric": "cpv_missing_share", "value": df["cpv_clean"].isna().mean()},
                {"dataset": label, "metric": "text_length_q50", "value": df["text_length"].quantile(0.50)},
                {"dataset": label, "metric": "text_length_q75", "value": df["text_length"].quantile(0.75)},
                {"dataset": label, "metric": "token_count_q50", "value": df["token_count"].quantile(0.50)},
                {"dataset": label, "metric": "notices_per_buyer_q50", "value": buyer_counts.quantile(0.50)},
                {"dataset": label, "metric": "notices_per_buyer_q90", "value": buyer_counts.quantile(0.90)},
                {"dataset": label, "metric": "notices_per_buyer_q99", "value": buyer_counts.quantile(0.99)},
                {"dataset": label, "metric": "top_1_buyer_notice_share", "value": _top_share(buyer_counts, 1)},
                {"dataset": label, "metric": "top_10_buyer_notice_share", "value": _top_share(buyer_counts, 10)},
            ]
        )

    distance_rows = [
        {"comparison": "real_vs_synthetic", "metric": "publication_year_tv", "value": _distribution_tv(real["publication_year"], syn["publication_year"])},
        {"comparison": "real_vs_synthetic", "metric": "schema_family_tv", "value": _distribution_tv(real["schema_family"], syn["schema_family"])},
        {"comparison": "real_vs_synthetic", "metric": "notice_type_tv", "value": _distribution_tv(real["notice_type_normalized"], syn["notice_type_normalized"])},
        {"comparison": "real_vs_synthetic", "metric": "cpv_division_tv", "value": _distribution_tv(real["cpv_division"], syn["cpv_division"])},
        {"comparison": "real_vs_synthetic", "metric": "buyer_key_type_tv", "value": _distribution_tv(real["buyer_key_type"], syn["buyer_key_type"])},
        {"comparison": "real_vs_synthetic", "metric": "text_length_quantile_distance_scaled", "value": _w1_scaled(real["text_length"], syn["text_length"])},
        {"comparison": "real_vs_synthetic", "metric": "token_count_quantile_distance_scaled", "value": _w1_scaled(real["token_count"], syn["token_count"])},
    ]
    return pd.DataFrame(summary_rows), pd.DataFrame(distance_rows)


def _save(fig, fig_dir: Path, stem: str) -> None:
    fig_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf"):
        fig.savefig(fig_dir / f"{stem}.{suffix}")
    plt.close(fig)


def _plot_overview(real: pd.DataFrame, syn: pd.DataFrame, fig_dir: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2))

    year = _share_table(real, syn, "publication_year")
    pivot = year.pivot(index="publication_year", columns="dataset", values="share").fillna(0).sort_index()
    ax = axes[0, 0]
    pivot.plot(ax=ax, color=[REAL_C, SYN_C], marker="o")
    ax.set_title("Publication year distribution")
    ax.set_ylabel("share of notices")
    _despine(ax)

    for ax, column, title, top_n in [
        (axes[0, 1], "schema_family", "Schema family mix", None),
        (axes[1, 0], "notice_type_normalized", "Notice type mix", None),
        (axes[1, 1], "buyer_key_type", "Buyer key type mix", None),
    ]:
        tab = _share_table(real, syn, column, top_n=top_n)
        pivot = tab.pivot(index=column, columns="dataset", values="share").fillna(0)
        pivot = pivot.sort_values("Real BOAMP", ascending=True)
        pivot.plot.barh(ax=ax, color=[REAL_C, SYN_C], width=0.72)
        ax.set_title(title)
        ax.set_xlabel("share of notices")
        ax.set_ylabel("")
        _despine(ax)

    fig.suptitle("Real BOAMP vs synthetic v0.4: core composition", x=0.01, ha="left", fontsize=13)
    fig.tight_layout()
    _save(fig, fig_dir, "eda_core_composition")


def _plot_text_identifier(real: pd.DataFrame, syn: pd.DataFrame, fig_dir: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2))

    ax = axes[0, 0]
    for label, df, color in [("Real BOAMP", real, REAL_C), ("Synthetic v0.4", syn, SYN_C)]:
        x = np.sort(df["text_length"].dropna().to_numpy())
        y = np.arange(1, len(x) + 1) / len(x)
        ax.plot(x, y, label=f"{label} (n={len(x):,})", color=color)
    ax.set_xlim(0, min(500, max(real["text_length"].quantile(0.995), syn["text_length"].quantile(0.995))))
    ax.set_title("Text length ECDF")
    ax.set_xlabel("characters in object text")
    ax.set_ylabel("cumulative share")
    _despine(ax)

    ax = axes[0, 1]
    bins = np.arange(0, 80, 2)
    ax.hist(real["token_count"].dropna(), bins=bins, density=True, alpha=0.35, color=REAL_C, label="Real BOAMP")
    ax.hist(syn["token_count"].dropna(), bins=bins, density=True, alpha=0.35, color=SYN_C, label="Synthetic v0.4")
    ax.set_title("Token count distribution")
    ax.set_xlabel("tokens in object text")
    ax.set_ylabel("density")
    _despine(ax)

    ax = axes[1, 0]
    rates = pd.DataFrame(
        [
            {"dataset": "Real BOAMP", "field": "SIRET present", "share": real["siret_present"].mean()},
            {"dataset": "Synthetic v0.4", "field": "SIRET present", "share": syn["siret_present"].mean()},
            {"dataset": "Real BOAMP", "field": "SIREN present", "share": real["siren_present"].mean()},
            {"dataset": "Synthetic v0.4", "field": "SIREN present", "share": syn["siren_present"].mean()},
            {"dataset": "Real BOAMP", "field": "CPV present", "share": real["cpv_clean"].notna().mean()},
            {"dataset": "Synthetic v0.4", "field": "CPV present", "share": syn["cpv_clean"].notna().mean()},
        ]
    )
    pivot = rates.pivot(index="field", columns="dataset", values="share")
    pivot.plot.bar(ax=ax, color=[REAL_C, SYN_C], rot=0)
    ax.set_title("Identifier and CPV completeness")
    ax.set_ylabel("share present")
    ax.set_ylim(0, 1)
    _despine(ax)

    ax = axes[1, 1]
    top_real = real["cpv_division"].fillna("MISSING").astype(str).value_counts().head(10).index
    tab = _share_table(real.assign(cpv_division=real["cpv_division"].where(real["cpv_division"].isin(top_real), "OTHER")),
                       syn.assign(cpv_division=syn["cpv_division"].where(syn["cpv_division"].isin(top_real), "OTHER")),
                       "cpv_division")
    pivot = tab.pivot(index="cpv_division", columns="dataset", values="share").fillna(0)
    pivot = pivot.sort_values("Real BOAMP", ascending=True)
    pivot.plot.barh(ax=ax, color=[REAL_C, SYN_C], width=0.72)
    ax.set_title("CPV division mix: real top 10 plus other")
    ax.set_xlabel("share of notices")
    ax.set_ylabel("CPV division")
    _despine(ax)

    fig.suptitle("Real BOAMP vs synthetic v0.4: text and identifiers", x=0.01, ha="left", fontsize=13)
    fig.tight_layout()
    _save(fig, fig_dir, "eda_text_identifiers")


def _plot_buyer_activity(real: pd.DataFrame, syn: pd.DataFrame, fig_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    ax = axes[0]
    for label, df, color in [("Real BOAMP", real, REAL_C), ("Synthetic v0.4", syn, SYN_C)]:
        counts = np.sort(df.groupby("buyer_key", dropna=True).size().to_numpy())
        y = np.arange(1, len(counts) + 1) / len(counts)
        ax.step(counts, y, where="post", label=f"{label} (buyers={len(counts):,})", color=color)
    ax.set_xscale("log")
    ax.set_title("Notices per observed buyer key")
    ax.set_xlabel("notices per buyer key, log scale")
    ax.set_ylabel("cumulative share of buyer keys")
    _despine(ax)

    ax = axes[1]
    for label, df, color in [("Real BOAMP", real, REAL_C), ("Synthetic v0.4", syn, SYN_C)]:
        counts = np.sort(df.groupby("buyer_key", dropna=True).size().to_numpy())
        share_buyers = np.arange(1, len(counts) + 1) / len(counts)
        share_notices = np.cumsum(counts) / counts.sum()
        ax.plot(share_buyers, share_notices, label=label, color=color)
    ax.plot([0, 1], [0, 1], color=MUTED, ls=":", lw=1)
    ax.set_title("Buyer activity concentration")
    ax.set_xlabel("cumulative share of buyer keys")
    ax.set_ylabel("cumulative share of notices")
    _despine(ax)

    fig.suptitle("Real BOAMP vs synthetic v0.4: buyer activity", x=0.01, ha="left", fontsize=13)
    fig.tight_layout()
    _save(fig, fig_dir, "eda_buyer_activity")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", type=Path, default=DEFAULT_REAL)
    parser.add_argument("--synthetic", type=Path, default=DEFAULT_SYNTHETIC)
    parser.add_argument("--figure-dir", type=Path, default=DEFAULT_FIG_DIR)
    parser.add_argument("--table-dir", type=Path, default=DEFAULT_TABLE_DIR)
    args = parser.parse_args()

    real = _read_real(args.real)
    syn = _read_synthetic(args.synthetic)
    args.table_dir.mkdir(parents=True, exist_ok=True)

    summary, distances = _summaries(real, syn)
    summary.to_csv(args.table_dir / "eda_summary_metrics.csv", index=False)
    distances.to_csv(args.table_dir / "eda_distribution_distances.csv", index=False)
    _share_table(real, syn, "publication_year").to_csv(args.table_dir / "publication_year_shares.csv", index=False)
    _share_table(real, syn, "schema_family").to_csv(args.table_dir / "schema_family_shares.csv", index=False)
    _share_table(real, syn, "notice_type_normalized").to_csv(args.table_dir / "notice_type_shares.csv", index=False)
    _share_table(real, syn, "cpv_division", top_n=20).to_csv(args.table_dir / "cpv_division_top20_shares.csv", index=False)

    _plot_overview(real, syn, args.figure_dir)
    _plot_text_identifier(real, syn, args.figure_dir)
    _plot_buyer_activity(real, syn, args.figure_dir)

    print(
        {
            "real_rows": int(len(real)),
            "synthetic_rows": int(len(syn)),
            "figures": sorted(path.name for path in args.figure_dir.glob("*.png")),
            "tables": sorted(path.name for path in args.table_dir.glob("*.csv")),
        }
    )


if __name__ == "__main__":
    main()
