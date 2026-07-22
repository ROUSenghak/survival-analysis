"""Latent record-quality-class mechanism for dependent/co-occurring
corruption (Phase 6.7).

A single latent class per notice (HIGH/MEDIUM/LOW), correlated with its
buyer's `identifier_quality_propensity`, scales the severity multiplier
applied to every field's base corruption rate at once (identifiers, CPV,
duration, text, linked-notice visibility). This is what makes those fields'
corruption co-occur on the same notices more than independent per-field
sampling would produce — Lam et al.'s core corruption-design principle
("do not sample all field errors independently"), reused here rather than
five separate independent Bernoulli draws per notice.

The real corpus's own field-level joint-pattern lifts
(calib_missingness_phi_matrix.csv / missingness_joint_patterns.csv,
USE_AS_FIDELITY_TARGET) are the target this mechanism should be checked
against in the Phase 9 fidelity notebook, not a value assigned directly here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEVERITY_MULTIPLIER: dict[str, float] = {"HIGH": 0.35, "MEDIUM": 1.0, "LOW": 2.2}

# `duration` gets its own, much flatter severity spread. Empirically, the
# shared SEVERITY_MULTIPLIER (calibrated for identifier/CPV/text, whose
# real-corpus missingness does vary sharply with record quality) makes it
# structurally impossible to reach the real corpus's duration_present_rate
# target (0.1365): even saturating scen_dur.missing_rate well past 1.0 still
# plateaus around present_rate~0.21-0.23, because the HIGH-quality class
# (0.35x) alone contributes more present notices than the entire real-corpus
# target allows. This says something substantive about the real data, not
# just a generator bug: duration appears to be omitted near-uniformly across
# BOAMP notices regardless of overall record quality (an editorial/template
# choice), unlike identifiers/CPV/text which do vary with quality. The
# shared per-notice quality_class is still used (so duration corruption
# still co-occurs with other fields' corruption on the same notices, per
# Lam et al.'s design principle), only the *magnitude* of quality-class
# differentiation is field-specific.
DURATION_SEVERITY_MULTIPLIER: dict[str, float] = {"HIGH": 0.89, "MEDIUM": 1.0, "LOW": 1.15}


def assign_quality_class(notices: pd.DataFrame, buyers: pd.DataFrame, scenario,
                          rng: np.random.Generator) -> pd.Series:
    mix = vars(scenario.quality_class_mix)
    classes = list(mix)
    base_probs = np.array([mix[c] for c in classes], dtype=float)
    base_probs = base_probs / base_probs.sum()

    buyer_prop = buyers.set_index("buyer_id_true")["identifier_quality_propensity"]
    prop = notices["buyer_id_true"].map(buyer_prop).fillna(buyer_prop.mean()).to_numpy()

    hi_idx = classes.index("HIGH")
    lo_idx = classes.index("LOW")
    out = np.empty(len(notices), dtype=object)
    for i in range(len(notices)):
        p = base_probs.copy()
        p[hi_idx] *= (0.5 + prop[i])   # higher buyer propensity -> more HIGH-quality notices
        p[lo_idx] *= (1.5 - prop[i])   # lower buyer propensity -> more LOW-quality notices
        p = np.clip(p, 1e-6, None)
        p = p / p.sum()
        out[i] = rng.choice(classes, p=p)
    return pd.Series(out, index=notices.index, name="quality_class")


def severity_multiplier(quality_class: pd.Series) -> pd.Series:
    return quality_class.map(SEVERITY_MULTIPLIER)


def duration_severity_multiplier(quality_class: pd.Series) -> pd.Series:
    return quality_class.map(DURATION_SEVERITY_MULTIPLIER)
