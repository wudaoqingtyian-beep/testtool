# -*- coding: utf-8 -*-
"""
test_rules.py —— 规则引擎单测

测试目标：
    1. 每个规则函数的输出符合预期类型/格式
    2. render 渲染引擎：纯占位符保留原生类型、混合字符串正确拼接
    3. 未知规则报错清晰
"""
import re
import sys
import os

# 保证从项目根目录可导入 core 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.rules import render, RULES

class TestRuleRegistry:
    """规则注册表的完整性测试"""

    def test_core_rules_registered(self):
        """核心规则必须全部注册成功"""
        for name in ("phone", "email", "name", "uuid", "int",
                     "decimal", "enum", "random_str", "datetime_recent"):
            assert name in RULES, f"规则 '{name}' 未注册"

    def test_unknown_rule_raises(self):
        """模板里写错规则名，渲染时应立即报错并提示可用规则"""
        with pytest.raises(ValueError, match="未知规则"):
            render("${no_such_rule}")


class TestRender:
    """渲染引擎行为测试"""

    def test_pure_placeholder_keeps_type(self):
        """整串是占位符时，应保留生成函数的原生返回类型（int/float）"""
        val = render("${int(18, 60)}")
        assert isinstance(val, int)
        assert 18 <= val <= 60

        val2 = render("${decimal(0.01, 99.99)}")
        assert isinstance(val2, float)
        assert 0.01 <= val2 <= 99.99

    def test_mixed_string(self):
        """混合字符串应把占位符替换后拼接"""
        val = render("auto_${random_str(8)}")
        assert val.startswith("auto_")
        assert len(val) == 8 + len("auto_")

    def test_enum_returns_from_options(self):
        """enum 规则只能返回给定选项之一"""
        options = {"created", "paid", "shipped"}
        for _ in range(10):
            assert render("${enum(created, paid, shipped)}") in options

    def test_non_string_passthrough(self):
        """非字符串模板值（数字/布尔）原样返回，不做渲染"""
        assert render(123) == 123
        assert render(True) is True

    def test_no_placeholder_passthrough(self):
        """不含占位符的字符串原样返回"""
        assert render("hello") == "hello"

    def test_phone_format(self):
        """手机号应为 11 位数字"""
        phone = render("${phone}")
        assert re.fullmatch(r"\d{11}", phone)

    def test_multiple_placeholders_in_one_string(self):
        """一个字符串里多个占位符都应被替换"""
        val = render("${int(1,9)}-${int(1,9)}")
        a, b = val.split("-")
        assert 1 <= int(a) <= 9 and 1 <= int(b) <= 9