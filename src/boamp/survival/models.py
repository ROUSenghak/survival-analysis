"""Survival models: KM, log-rank, Cox (clustered/robust), AFT, calibration.

Extracted from scripts/run_survival_analysis.py and the inline logic of the
legacy robustness notebook, with two fixes found in the pre-refactor audit:
  - cpv_division is normalized to a clean string before the log-rank group
    filter (the legacy script read it back as float ("32.0"), so
    `.isin(['32',...])` never matched and survival_logrank_tests.csv came
    out empty);
  - the variant list (incl. window_6m) comes from config.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter, KaplanMeierFitter, LogNormalAFTFitter, WeibullAFTFitter
from lifelines.statistics import logrank_test, proportional_hazard_test
from lifelines.utils import concordance_index, restricted_mean_survival_time


def normalize_cpv_division(series: pd.Series) -> pd.Series:
    """'32.0' / 32.0 / '32' -> '32'; missing -> 'MISSING'."""
    s = series.astype(str).str.replace(r"\.0$", "", regex=True)
    s = s.where(~series.isna(), "MISSING")
    return s.replace({"nan": "MISSING", "None": "MISSING"})


def km_summary(df: pd.DataFrame, label: str, cfg) -> dict:
    horizon = cfg.pipeline.survival.rmst_horizon_months
    km = KaplanMeierFitter()
    km.fit(df["time_to_event_or_censor_months"], df["event"], label=label)
    return {
        "variant": label,
        "n": len(df),
        "events": int(df["event"].sum()),
        "censoring_rate": 1 - df["event"].mean(),
        "median_survival_months": km.median_survival_time_,
        "survival_at_12m": float(km.survival_function_at_times(12).iloc[0]),
        "survival_at_24m": float(km.survival_function_at_times(24).iloc[0]),
        f"rmst_{horizon}m": float(restricted_mean_survival_time(km, t=horizon)),
    }


def fit_km(df: pd.DataFrame, label: str = "") -> KaplanMeierFitter:
    km = KaplanMeierFitter()
    km.fit(df["time_to_event_or_censor_months"], df["event"], label=label)
    return km


def logrank_between(df_a: pd.DataFrame, df_b: pd.DataFrame, label_a: str, label_b: str) -> dict:
    res = logrank_test(
        df_a["time_to_event_or_censor_months"], df_b["time_to_event_or_censor_months"],
        event_observed_A=df_a["event"], event_observed_B=df_b["event"],
    )
    return {"group_a": label_a, "group_b": label_b,
            "test_statistic": res.test_statistic, "p": res.p_value}


def logrank_by_cpv_division(df: pd.DataFrame, cfg, variant: str) -> list[dict]:
    """Pairwise log-rank tests across the digital CPV divisions."""
    df = df.copy()
    df["cpv_division"] = normalize_cpv_division(df["cpv_division"])
    divisions = list(cfg.pipeline.scope.digital_cpv_divisions)
    groups = [g for _, g in df[df["cpv_division"].isin(divisions)].groupby("cpv_division")
              if g["event"].sum() > 0]
    rows = []
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            a, b = groups[i], groups[j]
            row = logrank_between(a, b, str(a["cpv_division"].iloc[0]), str(b["cpv_division"].iloc[0]))
            row["variant"] = variant
            rows.append(row)
    return rows


def prep_covariates(df: pd.DataFrame) -> pd.DataFrame:
    x = df[["time_to_event_or_censor_months", "event", "declared_duration_months",
            "dur_was_imputed", "buyer_key", "buyer_key_type", "cpv_division",
            "publication_date"]].copy()
    x = x[x["time_to_event_or_censor_months"] > 0].dropna(subset=["declared_duration_months"])
    x["log_duration"] = np.log1p(x["declared_duration_months"])
    x["duration_sq"] = x["log_duration"] ** 2
    x["dur_was_imputed"] = x["dur_was_imputed"].astype(int)
    x["start_year"] = x["publication_date"].dt.year
    x["cpv_division"] = normalize_cpv_division(x["cpv_division"])
    x["buyer_key_type"] = x["buyer_key_type"].fillna("MISSING").astype(str)
    return pd.get_dummies(x, columns=["cpv_division", "buyer_key_type"], drop_first=True)


def fit_cox(df: pd.DataFrame, variant: str, cfg, quadratic: bool = False):
    """Clustered robust Cox. Returns (summary_rows, fitter_or_None, design_df, ph_df_or_None)."""
    penalizer = cfg.pipeline.survival.cox_penalizer
    x = prep_covariates(df)
    base = ["time_to_event_or_censor_months", "event", "buyer_key", "log_duration", "dur_was_imputed"]
    cols = base + (["duration_sq"] if quadratic else []) + [
        c for c in x.columns if c.startswith("cpv_division_") or c.startswith("buyer_key_type_")
    ]
    x = x[cols].copy()
    rows = []
    model_name = "cox_clustered_quadratic" if quadratic else "cox_clustered"
    try:
        c = CoxPHFitter(penalizer=penalizer)
        c.fit(x, duration_col="time_to_event_or_censor_months", event_col="event",
              cluster_col="buyer_key", robust=True)
        for term, r in c.summary.iterrows():
            rows.append(dict(variant=variant, model=model_name, term=term, coef=r.coef,
                             exp_coef=r["exp(coef)"], p=r.p,
                             ci_lower=r["exp(coef) lower 95%"], ci_upper=r["exp(coef) upper 95%"]))
        ph = proportional_hazard_test(c, x, duration_col="time_to_event_or_censor_months", event_col="event")
        phdf = ph.summary.reset_index().rename(columns={"index": "term"})
        phdf.insert(0, "variant", variant)
        return rows, c, x, phdf
    except Exception as e:
        rows.append(dict(variant=variant, model=model_name, term="ERROR", coef=np.nan,
                         exp_coef=np.nan, p=np.nan, ci_lower=np.nan, ci_upper=np.nan, error=str(e)))
        return rows, None, x, None


def fit_aft(df: pd.DataFrame, variant: str, cfg) -> list[dict]:
    penalizer = cfg.pipeline.survival.cox_penalizer
    x = prep_covariates(df).drop(columns=["buyer_key", "publication_date"], errors="ignore")
    rows = []
    for cls, name in [(WeibullAFTFitter, "weibull_aft"), (LogNormalAFTFitter, "lognormal_aft")]:
        try:
            m = cls(penalizer=penalizer)
            m.fit(x, duration_col="time_to_event_or_censor_months", event_col="event")
            rows.append(dict(variant=variant, model=name, AIC=m.AIC_,
                             log_likelihood=m.log_likelihood_,
                             concordance_index=getattr(m, "concordance_index_", np.nan)))
        except Exception as e:
            rows.append(dict(variant=variant, model=name, AIC=np.nan, log_likelihood=np.nan,
                             concordance_index=np.nan, error=str(e)))
    return rows


def prediction_calibration(df: pd.DataFrame, variant: str, c, x, cfg) -> list[dict]:
    if c is None:
        return []
    horizons = cfg.pipeline.survival.prediction_horizons_months
    rows = []
    for h in horizons:
        try:
            risk = 1 - c.predict_survival_function(x, times=[h]).T.iloc[:, 0].to_numpy()
            tmp = df.loc[x.index].copy()
            tmp["pred_risk"] = risk
            tmp["observed_by_horizon"] = ((tmp["event"] == 1)
                                          & (tmp["time_to_event_or_censor_months"] <= h)).astype(int)
            tmp["risk_group"] = pd.qcut(pd.Series(risk).rank(method="first"), 5, labels=False) + 1
            for g, z in tmp.groupby("risk_group"):
                rows.append(dict(variant=variant, horizon_months=h, risk_group=int(g), n=len(z),
                                 mean_predicted_risk=z["pred_risk"].mean(),
                                 observed_event_rate=z["observed_by_horizon"].mean(),
                                 brier_score=np.mean((z["observed_by_horizon"] - z["pred_risk"]) ** 2)))
        except Exception as e:
            rows.append(dict(variant=variant, horizon_months=h, risk_group=-1, n=0,
                             mean_predicted_risk=np.nan, observed_event_rate=np.nan,
                             brier_score=np.nan, error=str(e)))
    return rows


def temporal_validation(df: pd.DataFrame, variant: str, cfg) -> dict:
    max_year = cfg.pipeline.survival.temporal_validation_train_max_year
    train = df[df["publication_date"].dt.year <= max_year]
    test = df[df["publication_date"].dt.year > max_year]
    try:
        _, c2, xtr, _ = fit_cox(train, f"{variant}_train_to_{max_year}", cfg, quadratic=False)
        if c2 is not None and len(test) > 0:
            xt = prep_covariates(test)
            xt = xt.reindex(columns=xtr.columns, fill_value=0)
            score = -c2.predict_partial_hazard(xt).to_numpy().ravel()
            return dict(variant=variant, train_n=len(train), train_events=int(train["event"].sum()),
                        test_n=len(test), test_events=int(test["event"].sum()),
                        test_c_index=concordance_index(
                            test.loc[xt.index, "time_to_event_or_censor_months"], score,
                            test.loc[xt.index, "event"]))
        return dict(variant=variant, error="train fit failed or empty test set")
    except Exception as e:
        return dict(variant=variant, error=str(e))
