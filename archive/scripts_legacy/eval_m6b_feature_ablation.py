"""
Step 14 - Method 6b: feature ablation.

Input:  data/processed/boamp_m0_candidate_pairs.csv
        data/processed/boamp_m0_links_balanced.csv
Output: reports/tables/m6b_feature_ablation.csv

For each of the 4 composite-score components, drop it and renormalize the
remaining 3 weights to sum to 1, recompute the composite score over ALL
6,137 candidate pairs, and - critically - RE-DERIVE candidate_rank per
source under the new formula (the best candidate for a source can change
once a component is dropped, so simply reusing the real candidate_rank
would be wrong). The ablated link set is then built the same way the real
`balanced` variant was: rank-1 candidates only, thresholded at the 50th
percentile of the ablated rank-1 score distribution (NOT the real 0.323
absolute value, which lives on a different, non-comparable scale once
weights change). Jaccard overlap with the real balanced link set measures
how much removing that single component changes who gets linked.
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"

REAL_WEIGHTS = {"s_text": 0.35, "s_cpv": 0.30, "s_time": 0.25, "s_buyer": 0.10}
COMPONENT_LABELS = {"s_text": "text", "s_cpv": "cpv", "s_time": "time", "s_buyer": "buyer"}


def main():
    pairs = pd.read_csv(PROCESSED_DIR / "boamp_m0_candidate_pairs.csv")
    balanced = pd.read_csv(PROCESSED_DIR / "boamp_m0_links_balanced.csv")
    real_linked_sources = set(balanced["source_notice_id"])
    print(f"Real balanced link set: {len(real_linked_sources)} sources")

    rows = []
    for dropped_col, dropped_label in COMPONENT_LABELS.items():
        remaining = {c: w for c, w in REAL_WEIGHTS.items() if c != dropped_col}
        wsum = sum(remaining.values())
        renorm = {c: w / wsum for c, w in remaining.items()}
        print(f"\nDropping {dropped_label}: renormalized weights = "
              f"{ {COMPONENT_LABELS[c]: round(w, 4) for c, w in renorm.items()} }")

        composite_prime = sum(pairs[c] * w for c, w in renorm.items())
        ablated = pairs.copy()
        ablated["composite_prime"] = composite_prime
        ablated = ablated.sort_values(["source_notice_id", "composite_prime"], ascending=[True, False])
        ablated["candidate_rank_prime"] = ablated.groupby("source_notice_id").cumcount() + 1

        rank1_prime = ablated[ablated["candidate_rank_prime"] == 1]
        ablated_threshold = rank1_prime["composite_prime"].quantile(0.5)
        L_k = rank1_prime[rank1_prime["composite_prime"] >= ablated_threshold]
        L_k_sources = set(L_k["source_notice_id"])

        inter = len(L_k_sources & real_linked_sources)
        union = len(L_k_sources | real_linked_sources)
        jaccard = inter / union if union else float("nan")

        rows.append({
            "dropped_component": dropped_label,
            "renormalized_weights": ", ".join(f"{COMPONENT_LABELS[c]}={w:.4f}" for c, w in renorm.items()),
            "ablated_threshold_p50": ablated_threshold,
            "n_linked_ablated": len(L_k_sources),
            "n_intersection_with_real_balanced": inter,
            "n_union_with_real_balanced": union,
            "jaccard_vs_real_balanced": jaccard,
        })
        print(f"  n_linked_ablated={len(L_k_sources)}, jaccard_vs_real_balanced={jaccard:.4f}")

    result_df = pd.DataFrame(rows).sort_values("jaccard_vs_real_balanced")
    result_df.to_csv(TABLES_DIR / "m6b_feature_ablation.csv", index=False)
    print(f"\nWrote {TABLES_DIR / 'm6b_feature_ablation.csv'}")
    print(result_df[["dropped_component", "n_linked_ablated", "jaccard_vs_real_balanced"]].to_string(index=False))
    print(f"\nMost important component (lowest Jaccard when dropped): "
          f"{result_df.iloc[0]['dropped_component']}")


if __name__ == "__main__":
    main()
