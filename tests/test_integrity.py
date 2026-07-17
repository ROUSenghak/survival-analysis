import pandas as pd
import pytest

from boamp.validation import integrity as I


def _l1():
    return pd.DataFrame({
        "notice_id": ["a", "b"],
        "cpv_division": ["48", "72"],
        "buyer_key": ["K1", "K2"],
    })


def test_layer_parity_passes_when_only_identity_differs():
    l2 = _l1().copy()
    l2["buyer_key_l2"] = ["S1", "S2"]
    l2["buyer_key"] = ["K1", "K2"]
    I.assert_layer_parity(_l1(), l2, identity_columns=["buyer_key_l2"])


def test_layer_parity_catches_non_identity_difference():
    l2 = _l1().copy()
    l2["cpv_division"] = ["48", "99"]  # a shared, non-identity column changed
    with pytest.raises(AssertionError, match="cpv_division"):
        I.assert_layer_parity(_l1(), l2, identity_columns=["buyer_key_l2"])


def test_layer_parity_catches_row_mismatch():
    with pytest.raises(AssertionError, match="row counts"):
        I.assert_layer_parity(_l1(), _l1().iloc[:1], identity_columns=[])


def test_assert_unique():
    df = pd.DataFrame({"k": ["a", "a"]})
    with pytest.raises(AssertionError, match="duplicated"):
        I.assert_unique(df, "k", "t")


def test_run_all_reports_and_raises():
    checks = [
        ("ok", lambda: None),
        ("bad", lambda: (_ for _ in ()).throw(AssertionError("boom"))),
    ]
    with pytest.raises(AssertionError, match="bad"):
        I.run_all(checks)
