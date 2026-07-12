# -*- coding: utf-8 -*-
"""UI 语言解析测试。"""
from cyberpunk_mod_manager.locale import normalize_locale, resolve_locale
from cyberpunk_mod_manager.services.health_audit import _rule_based_audit_summary


def test_normalize_locale():
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("zh-CN") == "zh"
    assert normalize_locale("") == "zh"


def test_resolve_locale_header_priority():
    assert resolve_locale(header_locale="en", config_locale="zh") == "en"


def test_rule_based_audit_summary_english():
    issues = {
        "incomplete": [{"nexus_mod_id": 1}],
        "pending": [{"nexus_mod_id": 2}],
    }
    text = _rule_based_audit_summary(issues, [{"mod_id": 3}], locale="en")
    assert "incomplete dependencies" in text
    assert "pending" in text
