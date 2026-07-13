"""
Step 13 - Method 6a: threshold sensitivity analysis.

Input:  data/processed/boamp_m0_candidate_pairs.csv
        reports/tables/m0_method_summary.csv
Output: reports/tables/m6a_threshold_sweep.csv
        reports/tables/m6a_threshold_sensitivity.csv

Since M0 thresholds are already percentile-derived (broad/balanced/strict =
25th/50th/75th percentile of the rank-1 composite-score distribution), a
naive rate-vs-percentile sweep is close to a straight line by construction
(the rate is ~"1 - percentile/100" up to sampling noise) and cannot answer
whether the balanced threshold sits on a flat or steep part of anything
meaningful. Two analyses are produced instead:

  (a) rho(tau): linkage rate at percentile-derived thresholds 10..90 (step
      5), reported mainly to confirm the near-linear relationship and mark
      where broad/balanced/strict sit on it (m6a_threshold_sweep.csv).
  (b) local threshold sensitivity: how many sources would flip linked
      status under a small perturbation delta of the *balanced* threshold,
      and how the local score density compares at the balanced threshold
      vs. broad/strict/the distribution mode - this is what actually
      answers "is the link set fragile to small changes in the cutoff"
      (m6a_threshold_sensitivity.csv).
"""

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"

N_ELIGIBLE_SOURCES = 3159
DELTAS = [0.005, 0.01, 0.02, 0.05]
DENSITY_BIN_WIDTH = 0.01


def local_density_at(scores: np.ndarray, x: float, bin_width: float, n_total: int) -> float:
    count = ((scores >= x - bin_width / 2) & (scores < x + bin_width / 2)).sum()
    return count / (n_total * bin_width)


def main():
    pairs = pd.read_csv(PROCESSED_DIR / "boamp_m0_candidate_pairs.csv")
    rank1 = pairs[pairs["candidate_rank"] == 1].copy()
    n_rank1 = len(rank1)
    scores = rank1["m0_composite_score"].to_numpy()
    print(f"Rank-1 population: {n_rank1} sources")

    method_summary = pd.read_csv(TABLES_DIR / "m0_method_summary.csv").set_index("variant")
    broad_thr = method_summary.loc["broad", "threshold_composite_score"]
    balanced_thr = method_summary.loc["balanced", "threshold_composite_score"]
    strict_thr = method_summary.loc["strict", "threshold_composite_score"]
    print(f"broad={broad_thr:.6f}  balanced={balanced_thr:.6f}  strict={strict_thr:.6f}")

    # ---- (a) rho(tau): percentile sweep ----
    percentiles = list(range(10, 91, 5))
    sweep_rows = []
    for pct in percentiles:
        thr = np.percentile(scores, pct)
        n_linked = int((scores >= thr).sum())
        variant_label = None
        if pct == 25:
            variant_label = "broad"
        elif pct == 50:
            variant_label = "balanced"
        elif pct == 75:
            variant_label = "strict"
        sweep_rows.append({
            "percentile": pct, "threshold_value": thr, "n_linked": n_linked,
            "event_rate": n_linked / N_ELIGIBLE_SOURCES, "variant_label": variant_label,
        })
    sweep_df = pd.DataFrame(sweep_rows)
    sweep_df.to_csv(TABLES_DIR / "m6a_threshold_sweep.csv", index=False)
    print(f"Wrote {TABLES_DIR / 'm6a_threshold_sweep.csv'}")

    # ---- (b) local sensitivity around the balanced threshold ----
    sens_rows = []
    # distribution mode via a fine histogram over the rank-1 score range
    hist_counts, hist_edges = np.histogram(
        scores, bins=np.arange(scores.min(), scores.max() + DENSITY_BIN_WIDTH, DENSITY_BIN_WIDTH))
    mode_bin_idx = int(np.argmax(hist_counts))
    mode_score = (hist_edges[mode_bin_idx] + hist_edges[mode_bin_idx + 1]) / 2
    print(f"Distribution mode (approx, {DENSITY_BIN_WIDTH}-wide bins): {mode_score:.4f}")

    density_balanced = local_density_at(scores, balanced_thr, DENSITY_BIN_WIDTH, n_rank1)
    density_broad = local_density_at(scores, broad_thr, DENSITY_BIN_WIDTH, n_rank1)
    density_strict = local_density_at(scores, strict_thr, DENSITY_BIN_WIDTH, n_rank1)
    density_mode = local_density_at(scores, mode_score, DENSITY_BIN_WIDTH, n_rank1)

    for delta in DELTAS:
        n_flipped = int((np.abs(scores - balanced_thr) < delta).sum())
        sens_rows.append({
            "delta": delta, "n_flipped": n_flipped, "pct_flipped": n_flipped / n_rank1,
            "local_density_at_balanced": density_balanced,
            "local_density_at_broad": density_broad,
            "local_density_at_strict": density_strict,
            "local_density_at_mode": density_mode,
            "mode_score": mode_score,
        })
    sens_df = pd.DataFrame(sens_rows)
    sens_df.to_csv(TABLES_DIR / "m6a_threshold_sensitivity.csv", index=False)
    print(f"Wrote {TABLES_DIR / 'm6a_threshold_sensitivity.csv'}")
    print(sens_df[["delta", "n_flipped", "pct_flipped"]].to_string(index=False))
    print(f"\nLocal density at balanced={density_balanced:.3f}, broad={density_broad:.3f}, "
          f"strict={density_strict:.3f}, mode={density_mode:.3f}")
    if density_balanced >= max(density_broad, density_strict, density_mode) * 0.9:
        print("The balanced threshold sits near the densest part of the score "
              "distribution -> the link set is relatively SENSITIVE to small threshold "
              "perturbations there.")
    else:
        print("The balanced threshold sits on a comparatively flatter part of the "
              "score distribution -> the link set is relatively STABLE to small "
              "threshold perturbations there.")


if __name__ == "__main__":
    main()
