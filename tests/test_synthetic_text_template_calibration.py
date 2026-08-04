from types import SimpleNamespace

import pandas as pd

from boamp.synthetic.corruption import _resolve_same_buyer_admin_template_rate


class ConstantGenericTextModel:
    def __init__(self, rate: float):
        self.rate = rate

    def generic_text_rate(self, notice_type: str, buyer_activity_tier: str) -> float:
        return self.rate


def test_same_buyer_template_target_uses_current_tier_composition():
    clean = pd.DataFrame(
        {
            "notice_type_true": ["CALL"] * 4,
            "notice_id_synthetic": [f"N{i}" for i in range(4)],
        }
    )
    tiers = pd.Series(["6-20", "21+", "2-5", "1 (single)"])
    cfg = SimpleNamespace(
        same_buyer_admin_template_rate=0.35,
        same_buyer_admin_template_target_share=0.25,
        exact_template_share=0.0,
        near_boilerplate_extra_rate=0.0,
        generic_weak_extra_rate=0.0,
    )

    rate = _resolve_same_buyer_admin_template_rate(
        clean, tiers, ConstantGenericTextModel(0.0), cfg
    )

    assert rate == 0.5


def test_same_buyer_template_target_accounts_for_prior_text_replacements():
    clean = pd.DataFrame(
        {
            "notice_type_true": ["CALL"] * 4,
            "notice_id_synthetic": [f"N{i}" for i in range(4)],
        }
    )
    tiers = pd.Series(["6-20", "21+", "2-5", "1 (single)"])
    cfg = SimpleNamespace(
        same_buyer_admin_template_rate=0.35,
        same_buyer_admin_template_target_share=0.25,
        exact_template_share=0.20,
        near_boilerplate_extra_rate=0.0,
        generic_weak_extra_rate=0.0,
    )

    rate = _resolve_same_buyer_admin_template_rate(
        clean, tiers, ConstantGenericTextModel(1.0), cfg
    )

    assert rate == 0.625


def test_same_buyer_template_without_target_preserves_legacy_rate():
    clean = pd.DataFrame(
        {
            "notice_type_true": ["CALL"] * 2,
            "notice_id_synthetic": ["N1", "N2"],
        }
    )
    cfg = SimpleNamespace(same_buyer_admin_template_rate=0.35)

    rate = _resolve_same_buyer_admin_template_rate(
        clean, pd.Series(["6-20", "21+"]), ConstantGenericTextModel(0.0), cfg
    )

    assert rate == 0.35
