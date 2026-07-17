"""
Step 15 - Method 6c: downstream robustness (broad vs strict variant,
Kaplan-Meier by CPV division).

Input:  data/processed/boamp_m0_sources.csv
        data/processed/boamp_m0_links_broad.csv
        data/processed/boamp_m0_links_strict.csv
Output: data/processed/boamp_survival_m0_broad.csv
        data/processed/boamp_survival_m0_strict.csv
        reports/tables/m6c_km_summary.csv
        reports/tables/m6c_km_rank_correlation.csv

Reuses run_m0_linkage.build_survival_dataset() (imported, not
reimplemented) to build the broad- and strict-variant survival datasets
exactly as the real balanced one was built. `cpv_division` is used as the
segment/stratification variable (there is no `segment` field in this
schema - `category_label` is ~always DIGITAL_ICT for this scope-filtered
population and carries no discriminative information).
"""

import sys
from pathlib import Path

import pandas as pd
from lifelines import KaplanMeierFitter
from lifelines.utils import restricted_mean_survival_time
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import run_m0_linkage as rml  # noqa: E402  (reuse build_survival_dataset)

DIGITAL_DIVISIONS = ["32", "35", "48", "72"]
HORIZON_MONTHS = 24
RMST_HORIZON_MONTHS = 60  # ~5 years: between the real balanced (~37.7mo) and
# strict (~44.7mo) median linked-pair gaps, chosen for the RMST ranking
# metric because median survival time is undefined (KM never crosses 0.5
# survival - see below) under this population's heavy censoring.


def main():
    sources = pd.read_csv(
        PROCESSED_DIR / "boamp_m0_sources.csv",
        dtype={c: str for c in rml.CODE_STR_COLS},
        parse_dates=["publication_date", "start_date", "estimated_end_date", "study_end_date"],
    )
    links_broad = pd.read_csv(PROCESSED_DIR / "boamp_m0_links_broad.csv")
    links_strict = pd.read_csv(PROCESSED_DIR / "boamp_m0_links_strict.csv")

    method_summary = pd.read_csv(TABLES_DIR / "m0_method_summary.csv").set_index("variant")

    survivals = {}
    for variant_name, links in [("broad", links_broad), ("strict", links_strict)]:
        surv = rml.build_survival_dataset(sources, links, variant_name)
        out_path = PROCESSED_DIR / f"boamp_survival_m0_{variant_name}.csv"
        surv.to_csv(out_path, index=False)
        survivals[variant_name] = surv
        expected_n = int(method_summary.loc[variant_name, "n_sources_eligible"])
        expected_events = int(method_summary.loc[variant_name, "n_linked_events"])
        actual_n = len(surv)
        actual_events = int(surv["event"].sum())
        print(f"Wrote {out_path} ({actual_n} rows, {actual_events} events; "
              f"expected {expected_n} rows, {expected_events} events)")
        if actual_n != expected_n or actual_events != expected_events:
            raise RuntimeError(
                f"{variant_name}: survival dataset row/event count mismatch vs "
                f"m0_method_summary.csv - do not trust downstream KM fits."
            )
    print("Row/event count cross-check against m0_method_summary.csv passed for both variants.")

    km_rows = []
    for variant_name, surv in survivals.items():
        surv = surv[surv["cpv_division"].isin(DIGITAL_DIVISIONS)]
        for division in DIGITAL_DIVISIONS:
            grp = surv[surv["cpv_division"] == division]
            if len(grp) == 0:
                continue
            kmf = KaplanMeierFitter()
            kmf.fit(durations=grp["time_to_event_or_censor_months"],
                    event_observed=grp["event"], label=f"{variant_name}_{division}")
            median_surv = kmf.median_survival_time_
            surv_at_horizon = kmf.survival_function_at_times(HORIZON_MONTHS).values[0]
            rmst = restricted_mean_survival_time(kmf, t=RMST_HORIZON_MONTHS)
            km_rows.append({
                "variant": variant_name, "cpv_division": division,
                "n": len(grp), "n_events": int(grp["event"].sum()),
                "censoring_rate": 1 - grp["event"].mean(),
                "median_survival_months": median_surv,
                f"survival_at_{HORIZON_MONTHS}m": surv_at_horizon,
                f"rmst_{RMST_HORIZON_MONTHS}m": rmst,
            })

    km_df = pd.DataFrame(km_rows)
    km_df.to_csv(TABLES_DIR / "m6c_km_summary.csv", index=False)
    print(f"\nWrote {TABLES_DIR / 'm6c_km_summary.csv'}")
    print(km_df.to_string(index=False))

    # ---- rank-stability check ----
    # Median survival time is undefined (inf) for every group above: this
    # population's KM curves never cross 50% survival within the study
    # window (event rate per division tops out at ~27% for broad, far
    # lower for strict - i.e. most sources are censored, not observed to
    # renew, before the study ends). Ranking on an all-inf column would be
    # a meaningless tie, so restricted mean survival time (RMST) at
    # RMST_HORIZON_MONTHS is used instead - it is always finite and is the
    # standard fallback summary statistic for heavily-censored KM curves.
    rmst_col = f"rmst_{RMST_HORIZON_MONTHS}m"
    pivot = km_df.pivot(index="cpv_division", columns="variant", values=rmst_col)
    pivot = pivot.dropna()
    print(f"\nDivisions used for rank correlation ({rmst_col}, both variants defined): "
          f"{list(pivot.index)}")
    if len(pivot) >= 3:
        rho, p_value = spearmanr(pivot["broad"], pivot["strict"])
    else:
        rho, p_value = float("nan"), float("nan")
        print(f"WARNING: fewer than 3 divisions with a defined {rmst_col} in both "
              "variants - Spearman rank correlation is not meaningful; reported as NaN.")

    broad_rank = pivot["broad"].rank(method="min").rename("broad_rank")
    strict_rank = pivot["strict"].rank(method="min").rename("strict_rank")
    rank_df = pd.concat([pivot, broad_rank, strict_rank], axis=1).reset_index()
    rank_df["spearman_rho"] = rho
    rank_df["spearman_p_value"] = p_value
    rank_df.to_csv(TABLES_DIR / "m6c_km_rank_correlation.csv", index=False)
    print(f"\nSpearman rank correlation (broad vs strict {rmst_col} ranking): "
          f"rho={rho:.4f}, p={p_value:.4f}")
    print(f"Wrote {TABLES_DIR / 'm6c_km_rank_correlation.csv'}")
    print(rank_df.to_string(index=False))


if __name__ == "__main__":
    main()
