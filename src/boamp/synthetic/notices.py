"""Generate clean notice families and clean notices (Phase 4.6).

Each cycle produces a CALL notice always, plus an AWARD notice with
probability `award_probability` (calibrated from the real corpus's
APPEL_OFFRE:ATTRIBUTION ratio, calibration_parameters_v0_1.yaml#notice_types).
Both notices of one cycle share the same underlying need/text (with only
same-cycle publication-level variation, text_generation.apply_same_cycle_variation)
— they represent one procurement episode, NOT a recurrence relation
(spec: "Notice-family records represent the same procurement cycle and must
not be treated as recurrence relations").

Call-to-award delay is a generator design assumption (no observable
call-to-award numeric distribution was carried into
calibration_parameters_v0_1.yaml — only the provisional-family delay TABLE
exists, calib tables' call_to_award_delays.csv, which is USE_AS_FIDELITY_TARGET,
not USE_DIRECTLY); documented here, not silently invented.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from boamp.synthetic.text_generation import apply_same_cycle_variation, render_text

EFORMS_MANDATE_DATE = pd.Timestamp("2023-10-01")  # legal effective date -- see note below on why it is not used as a hard cutoff

# v0.2 conditional-fidelity follow-up: real notices are 100% LEGACY through
# 2023 -- even the Oct-Dec 2023 window nominally covered by the EFORMS
# mandate above (calib_population_counts_by_year_schema.csv shows EFORMS=0
# for every year through 2023). Practical adoption was gradual, starting in
# 2024, and still incomplete by 2026 (~40% of notices remain LEGACY-tagged).
# A hard publication-date cutoff at EFORMS_MANDATE_DATE overstated EFORMS
# share for years it should have been LEGACY-only and, more importantly,
# gave every post-mandate notice a 100% EFORMS label when the real share
# never exceeds ~60% -- this fed directly into the schema-conditional
# duration/CPV fixes above producing large residual errors for 2023-2026
# specifically. Replaced with a probabilistic draw using the real by-year
# adoption share for years actually observed to have any EFORMS notices.
_EFORMS_ADOPTION_SHARE_BY_YEAR: dict[int, float] = {2024: 0.5385, 2025: 0.5619, 2026: 0.5993}
_EFORMS_ADOPTION_SHARE_LATEST = 0.5993  # years beyond the calibration table's range; last observed share held flat


def _schema_family(publication_date: pd.Timestamp, rng: np.random.Generator) -> str:
    if publication_date.year < 2024:
        return "LEGACY"
    share = _EFORMS_ADOPTION_SHARE_BY_YEAR.get(publication_date.year, _EFORMS_ADOPTION_SHARE_LATEST)
    return "EFORMS" if rng.random() < share else "LEGACY"


def generate_notice_families_and_clean_notices(
    cycles: pd.DataFrame, needs: pd.DataFrame, buyers: pd.DataFrame,
    establishments: pd.DataFrame, rng: np.random.Generator,
    award_probability: float = 0.387,
    same_cycle_variation_severity: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    needs_idx = needs.set_index("need_id_true")
    buyers_idx = buyers.set_index("buyer_id_true")
    estab_idx = establishments.set_index("establishment_id_true")

    membership_rows = []
    notice_rows = []
    notice_seq = 0

    for _, cyc in cycles.iterrows():
        need = needs_idx.loc[cyc["need_id_true"]]
        buyer = buyers_idx.loc[cyc["buyer_id_true"]]
        estab = estab_idx.loc[need["establishment_id_true"]]

        call_date = cyc["start_date_true"]
        call_id = f"NOTICE-{notice_seq:08d}"
        notice_seq += 1
        call_text = render_text(need["base_concepts"], need["base_vocabulary"],
                                 buyer["buyer_name_true"], buyer["department_true"], "CALL", rng)

        common = dict(
            cycle_id_true=cyc["cycle_id_true"], need_id_true=cyc["need_id_true"],
            buyer_id_true=cyc["buyer_id_true"], establishment_id_true=need["establishment_id_true"],
            siret_true=estab["siret_true"], siren_true=estab["siren_true"],
            buyer_name_true=buyer["buyer_name_true"], department_true=buyer["department_true"],
            cpv_true=need["cpv_true"], duration_true_months=cyc["duration_true_months"],
        )
        notice_rows.append(dict(
            notice_id_synthetic=call_id, role="CALL", publication_date_true=call_date,
            notice_type_true="APPEL_OFFRE", schema_family_true=_schema_family(call_date, rng),
            objet_true=call_text, linked_call_notice_id_true=None, **common,
        ))
        membership_rows.append(dict(notice_id_synthetic=call_id, cycle_id_true=cyc["cycle_id_true"], role="CALL"))

        if rng.random() < award_probability:
            delay_days = int(np.clip(rng.normal(90, 45), 10, 400))
            award_date = call_date + pd.to_timedelta(delay_days, unit="D")
            award_id = f"NOTICE-{notice_seq:08d}"
            notice_seq += 1
            award_text = apply_same_cycle_variation(call_text, same_cycle_variation_severity, rng)
            notice_rows.append(dict(
                notice_id_synthetic=award_id, role="AWARD", publication_date_true=award_date,
                notice_type_true="ATTRIBUTION", schema_family_true=_schema_family(award_date, rng),
                objet_true=award_text, linked_call_notice_id_true=call_id, **common,
            ))
            membership_rows.append(dict(notice_id_synthetic=award_id, cycle_id_true=cyc["cycle_id_true"], role="AWARD"))

    clean_notices = pd.DataFrame(notice_rows)
    notice_family_membership = pd.DataFrame(membership_rows)
    return notice_family_membership, clean_notices
