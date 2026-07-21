"""Structural validators for the clean latent world (Phase 5).

Used both by tests/test_synthetic_clean_world.py and by
pipeline.generate_clean_world (which raises before any corruption is
applied if structural validation fails — spec: "Do not proceed to Stage 2
automatically if structural validation fails").
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from utils.identifiers import siren_from_siret, validate_siren, validate_siret


@dataclass
class ValidationResult:
    checks: dict[str, bool] = field(default_factory=dict)
    messages: dict[str, str] = field(default_factory=dict)

    def add(self, name: str, ok: bool, message: str = "") -> None:
        self.checks[name] = ok
        self.messages[name] = message

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    def failures(self) -> dict[str, str]:
        return {k: self.messages[k] for k, v in self.checks.items() if not v}


def validate_identifiers(establishments: pd.DataFrame) -> ValidationResult:
    r = ValidationResult()

    siren_ok = establishments["siren_true"].map(lambda s: all(validate_siren(s)))
    r.add("all_siren_valid", bool(siren_ok.all()),
          f"{(~siren_ok).sum()} invalid SIREN(s)")

    siret_ok = establishments["siret_true"].map(lambda s: all(validate_siret(s)))
    r.add("all_siret_valid", bool(siret_ok.all()),
          f"{(~siret_ok).sum()} invalid SIRET(s)")

    hierarchy_ok = (establishments["siret_true"].map(siren_from_siret) == establishments["siren_true"])
    r.add("siret_belongs_to_siren", bool(hierarchy_ok.all()),
          f"{(~hierarchy_ok).sum()} SIRET(s) whose first 9 digits != siren_true")

    return r


def validate_referential_integrity(buyers: pd.DataFrame, establishments: pd.DataFrame,
                                     needs: pd.DataFrame, cycles: pd.DataFrame) -> ValidationResult:
    r = ValidationResult()
    buyer_ids = set(buyers["buyer_id_true"])
    estab_ids = set(establishments["establishment_id_true"])
    need_ids = set(needs["need_id_true"])

    r.add("every_establishment_has_one_buyer",
          establishments["buyer_id_true"].isin(buyer_ids).all(),
          "some establishment.buyer_id_true not in latent_buyers")
    r.add("every_need_has_one_buyer",
          needs["buyer_id_true"].isin(buyer_ids).all(),
          "some need.buyer_id_true not in latent_buyers")
    r.add("every_need_has_one_establishment",
          needs["establishment_id_true"].isin(estab_ids).all(),
          "some need.establishment_id_true not in latent_establishments")
    r.add("every_cycle_has_one_need",
          cycles["need_id_true"].isin(need_ids).all(),
          "some cycle.need_id_true not in latent_needs")
    r.add("every_cycle_has_one_buyer",
          cycles["buyer_id_true"].isin(buyer_ids).all(),
          "some cycle.buyer_id_true not in latent_buyers")
    return r


def validate_relations(cycles: pd.DataFrame, relations: pd.DataFrame) -> ValidationResult:
    r = ValidationResult()

    r.add("valid_relation_types",
          relations["relation_type"].isin(["NEXT_CYCLE", "NO_SUCCESSOR"]).all(),
          "relation_type outside {NEXT_CYCLE, NO_SUCCESSOR} (v0.1 ontology violation)")

    outgoing = relations.groupby("source_cycle_id").size()
    n_cycles = len(cycles)
    r.add("exactly_one_outgoing_edge_per_cycle",
          len(outgoing) == n_cycles and (outgoing == 1).all(),
          f"{n_cycles} cycles but {len(outgoing)} sources with edges "
          f"({(outgoing != 1).sum()} with != 1 outgoing edge)")

    no_succ = relations[relations["relation_type"] == "NO_SUCCESSOR"]
    r.add("no_successor_has_no_target",
          no_succ["target_cycle_id"].isna().all(),
          "some NO_SUCCESSOR row has a non-null target_cycle_id")

    next_cyc = relations[relations["relation_type"] == "NEXT_CYCLE"]
    r.add("next_cycle_is_one_to_one",
          not next_cyc["target_cycle_id"].duplicated().any(),
          "some cycle is the target of more than one NEXT_CYCLE edge")

    merged = next_cyc.merge(
        cycles[["cycle_id_true", "start_date_true"]].rename(
            columns={"cycle_id_true": "source_cycle_id", "start_date_true": "source_start"}),
        on="source_cycle_id", how="left",
    ).merge(
        cycles[["cycle_id_true", "start_date_true"]].rename(
            columns={"cycle_id_true": "target_cycle_id", "start_date_true": "target_start_check"}),
        on="target_cycle_id", how="left",
    )
    after = merged["target_start_check"] > merged["source_start"]
    r.add("successor_after_source", bool(after.all()) if len(merged) else True,
          f"{(~after).sum()} NEXT_CYCLE edge(s) where target does not start after source")

    return r


def validate_notice_families(notice_family_membership: pd.DataFrame) -> ValidationResult:
    r = ValidationResult()
    per_notice_cycles = notice_family_membership.groupby("notice_id_synthetic")["cycle_id_true"].nunique()
    r.add("each_notice_belongs_to_exactly_one_cycle",
          bool((per_notice_cycles == 1).all()),
          f"{(per_notice_cycles != 1).sum()} notice(s) mapped to != 1 cycle")
    return r


def validate_no_real_identifier_leakage(establishments: pd.DataFrame, real_identifier_values: set[str]) -> ValidationResult:
    r = ValidationResult()
    if not real_identifier_values:
        r.add("no_real_identifier_overlap", True, "no real-identifier reference set provided; skipped")
        return r
    overlap = (set(establishments["siret_true"]) | set(establishments["siren_true"])) & real_identifier_values
    r.add("no_real_identifier_overlap", len(overlap) == 0,
          f"{len(overlap)} synthetic identifier(s) collide with a real BOAMP identifier")
    return r


def run_full_structural_validation(world: dict) -> ValidationResult:
    """world: dict with keys buyers, establishments, needs, cycles,
    true_relations, notice_family_membership (+ optional clean_notices)."""
    combined = ValidationResult()
    for sub in (
        validate_identifiers(world["establishments"]),
        validate_referential_integrity(world["buyers"], world["establishments"], world["needs"], world["cycles"]),
        validate_relations(world["cycles"], world["true_relations"]),
        validate_notice_families(world["notice_family_membership"]),
    ):
        combined.checks.update(sub.checks)
        combined.messages.update(sub.messages)
    return combined
