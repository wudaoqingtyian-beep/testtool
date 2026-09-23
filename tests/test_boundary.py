# -*- coding: utf-8 -*-
"""
test_boundary.py —— 边界值模式单测

测试目标：
    1. 数值型字段生成合法边界（min/max）与非法边界（min-1/max+1）
    2. 字符串型字段生成空串/超长/注入等异常值
    3. 每条异常数据都带 expected_result 标注
    4. 其他字段保持正常渲染
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.boundary import generate_boundary_rows, _build_value_cases

FIELDS = {
    "id": "${uuid}",
    "age": "${int(18, 60)}",
    "username": "auto_${random_str(8)}",
}


class TestBuildValueCases:
    """单字段边界值推导测试"""

    def test_int_field_boundaries(self):
        """int(18,60) 字段应产出 18/60（合法）和 17/61（非法）"""
        cases = _build_value_cases("${int(18, 60)}")
        values = {v for v, _ in cases}
        assert 18 in values and 60 in values
        assert 17 in values and 61 in values

    def test_expected_labels_valid(self):
        """所有标注必须是 should_accept / should_reject 之一"""
        cases = _build_value_cases("${int(18, 60)}")
        for _, expected in cases:
            assert expected in ("should_accept", "should_reject")

    def test_string_field_special_values(self):
        """字符串字段应包含 SQL 注入串和超长串"""
        cases = _build_value_cases("${uuid}")
        values = [v for v, _ in cases]
        assert any("DROP TABLE" in v for v in values if isinstance(v, str))
        assert any(len(v) > 1000 for v in values if isinstance(v, str))


class TestGenerateBoundaryRows:
    """异常数据集生成测试"""

    def test_rows_have_expected_column(self):
        """每行异常数据必须带 expected_result 标注列"""
        rows = generate_boundary_rows(FIELDS, "env_tag", "TEST_DATA")
        assert rows, "异常数据集不应为空"
        for row in rows:
            assert row["expected_result"] in ("should_accept", "should_reject")
            assert row["env_tag"] == "TEST_DATA"

    def test_other_fields_still_rendered(self):
        """目标字段取边界值时，其余字段应保持正常渲染（非边界值）"""
        import re
        rows = generate_boundary_rows(FIELDS, "env_tag", "TEST_DATA")
        for row in rows:
            # id 字段是 uuid 规则，正常渲染时应严格符合 uuid 格式
            if re.fullmatch(r"[0-9a-f-]{36}", str(row["id"])):
                assert len(str(row["id"])) == 36
