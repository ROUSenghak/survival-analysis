"""Direct Layer 1 vs Layer 2 comparison tables.

Extracted from scripts/build_m1_buyer_siren_experiment.py (comparison_tables)
and extended: both the (source, candidate)-pair view and the source-ID view
are reported, because a "removed" link whose source is re-linked to a
different candidate is a CHANGED link, not a lost source.
"""

from __future__ import annotations

import pandas as pd


def layer_link_comparison(l1_links: pd.DataFrame, l2_links: pd.DataFrame,
                          eligible_sources: pd.DataFrame) -> pd.DataFrame:
    """Per-source table: linked status and selected candidate in each layer."""
    l1 = l1_links.set_index("source_notice_id")
    l2 = l2_links.set_index("source_notice_id")
    rows = []
    for nid in eligible_sources["notice_id"]:
        in1, in2 = nid in l1.index, nid in l2.index
        cand1 = l1.loc[nid, "candidate_notice_id"] if in1 else None
        cand2 = l2.loc[nid, "candidate_notice_id"] if in2 else None
        if in1 and in2:
            status = "SAME_LINK" if cand1 == cand2 else "CHANGED_CANDIDATE"
        elif in2:
            status = "ADDED_BY_ENRICHMENT"
        elif in1:
            status = "REMOVED_BY_ENRICHMENT"
        else:
            status = "UNLINKED_BOTH"
        rows.append({
            "source_notice_id": nid,
            "linked_l1": in1, "linked_l2": in2,
            "candidate_l1": cand1, "candidate_l2": cand2,
            "score_l1": l1.loc[nid, "composite_score"] if in1 else None,
            "score_l2": l2.loc[nid, "composite_score"] if in2 else None,
            "margin_l1": l1.loc[nid, "top1_top2_margin"] if in1 else None,
            "margin_l2": l2.loc[nid, "top1_top2_margin"] if in2 else None,
            "confidence_tier_l1": l1.loc[nid, "confidence_tier"] if in1 else None,
            "confidence_tier_l2": l2.loc[nid, "confidence_tier"] if in2 else None,
            "mechanism_l2": l2.loc[nid, "buyer_match_mechanism"] if (in2 and "buyer_match_mechanism" in l2.columns) else None,
            "link_status": status,
        })
    return pd.DataFrame(rows)


def layer_changed_links(link_comparison: pd.DataFrame, l2_links: pd.DataFrame) -> pd.DataFrame:
    """Detail table for links added / removed / changed by enrichment."""
    changed = link_comparison[link_comparison["link_status"].isin(
        ["ADDED_BY_ENRICHMENT", "REMOVED_BY_ENRICHMENT", "CHANGED_CANDIDATE"])].copy()
    detail_cols = [c for c in ["source_notice_id", "candidate_notice_id", "s_text", "s_cpv",
                               "s_time", "s_buyer", "composite_score", "top1_top2_margin",
                               "buyer_match_mechanism", "confidence_tier"] if c in l2_links.columns]
    return changed.merge(
        l2_links[detail_cols].add_prefix("l2_"),
        left_on="source_notice_id", right_on="l2_source_notice_id", how="left",
    ).drop(columns=["l2_source_notice_id"], errors="ignore")


def layer_comparison_summary(l1_sources: pd.DataFrame, l2_sources: pd.DataFrame,
                             l1_pairs: pd.DataFrame, l2_pairs: pd.DataFrame,
                             l1_links: pd.DataFrame, l2_links: pd.DataFrame,
                             l1_survival: pd.DataFrame, l2_survival: pd.DataFrame) -> pd.DataFrame:
    n_eligible = len(l1_sources[l1_sources["buyer_key_type"] != "MISSING"])

    def method_row(method, sources, pairs, links, survival, key_col):
        reuse = links["candidate_notice_id"].value_counts() if len(links) else pd.Series(dtype=int)
        n_with_cand = pairs["source_notice_id"].nunique() if len(pairs) else 0
        return {
            "layer": method,
            "eligible_source_count": n_eligible,
            "unique_buyer_keys": int(sources[key_col].nunique()),
            "sources_with_at_least_one_candidate": n_with_cand,
            "zero_candidate_sources": n_eligible - n_with_cand,
            "blocking_coverage": n_with_cand / n_eligible if n_eligible else 0,
            "candidate_pair_count": len(pairs),
            "accepted_links": len(links),
            "overall_linking_rate": len(links) / n_eligible if n_eligible else 0,
            "acceptance_rate_conditional_on_candidates": len(links) / n_with_cand if n_with_cand else 0,
            "unique_selected_candidates": int(links["candidate_notice_id"].nunique()) if len(links) else 0,
            "candidate_reuse_rate": float((reuse > 1).mean()) if len(reuse) else 0,
            "maximum_candidate_multiplicity": int(reuse.max()) if len(reuse) else 0,
            "n_potential_tier_links": int((links["confidence_tier"] == "POTENTIAL").sum()) if "confidence_tier" in links.columns and len(links) else None,
            "event_rate_survival_handoff": float(pd.to_numeric(l1_survival["event"] if method == "boamp_only" else l2_survival["event"], errors="coerce").mean()),
            "median_link_text_similarity": float(links["s_text"].median()) if len(links) else None,
            "median_link_margin": float(links["top1_top2_margin"].median()) if len(links) else None,
        }

    l1_set = set(zip(l1_links["source_notice_id"], l1_links["candidate_notice_id"]))
    l2_set = set(zip(l2_links["source_notice_id"], l2_links["candidate_notice_id"]))
    l1_src, l2_src = set(l1_links["source_notice_id"]), set(l2_links["source_notice_id"])
    l1_by_source = l1_links.set_index("source_notice_id")["candidate_notice_id"].to_dict()
    l2_by_source = l2_links.set_index("source_notice_id")["candidate_notice_id"].to_dict()

    summary = pd.DataFrame([
        method_row("boamp_only", l1_sources, l1_pairs, l1_links, l1_survival, "buyer_key"),
        method_row("enriched", l2_sources, l2_pairs, l2_links, l2_survival, "buyer_key_l2"),
    ])
    overlap = pd.DataFrame([{
        "pairs_common": len(l1_set & l2_set),
        "pairs_only_l1": len(l1_set - l2_set),
        "pairs_only_l2": len(l2_set - l1_set),
        "pair_jaccard": len(l1_set & l2_set) / len(l1_set | l2_set) if (l1_set | l2_set) else 0,
        "sources_common": len(l1_src & l2_src),
        "sources_only_l1": len(l1_src - l2_src),
        "sources_only_l2": len(l2_src - l1_src),
        "source_jaccard": len(l1_src & l2_src) / len(l1_src | l2_src) if (l1_src | l2_src) else 0,
        "same_source_different_candidate": sum(
            1 for sid in (l1_src & l2_src) if l1_by_source[sid] != l2_by_source[sid]),
        "sources_gaining_candidates_l2": len(set(l2_pairs["source_notice_id"]) - set(l1_pairs["source_notice_id"])),
        "sources_losing_candidates_l2": len(set(l1_pairs["source_notice_id"]) - set(l2_pairs["source_notice_id"])),
    }])
    return summary, overlap


def buyer_identity_crosswalk(l2_sources: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in [
        "notice_id", "buyer_name_raw", "buyer_name_normalized",
        "buyer_siret_clean", "buyer_siren_clean", "buyer_identifier_source",
        "buyer_key", "buyer_key_type",
        "buyer_siren_enriched", "buyer_siren_alias", "buyer_siren_l2", "buyer_key_l2",
        "buyer_identity_source", "buyer_identity_confidence",
        "buyer_identity_conflict", "buyer_siren_agrees_with_boamp_siret",
        "enrichment_join_status",
    ] if c in l2_sources.columns]
    return l2_sources[cols].copy()
