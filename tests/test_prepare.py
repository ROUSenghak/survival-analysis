from boamp.data.prepare import cpv_is_generic, normalize_notice_type, tag_digital_scope


def test_notice_type_normalization():
    assert normalize_notice_type("APPEL_OFFRE") == "APPEL_OFFRE"
    assert normalize_notice_type(" attribution ") == "ATTRIBUTION"
    assert normalize_notice_type("RECTIFICATIF") == "OTHER"
    assert normalize_notice_type(None) == "OTHER"
    assert normalize_notice_type("") == "OTHER"


def test_cpv_generic_pattern():
    assert cpv_is_generic("48000000") is True
    assert cpv_is_generic("48151000") is False
    assert cpv_is_generic("4800000") is False  # wrong length


def test_digital_scope_by_cpv(cfg):
    assert tag_digital_scope("48", None, cfg) is True
    assert tag_digital_scope("45", None, cfg) is False


def test_digital_scope_by_keyword(cfg):
    assert tag_digital_scope("45", "maintenance du logiciel de paie", cfg) is True
    assert tag_digital_scope("45", "travaux de voirie", cfg) is False
