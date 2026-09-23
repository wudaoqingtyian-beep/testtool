# -*- coding: utf-8 -*-
"""
test_db_output.py —— 数据库输出层单测（不依赖真实数据库）

测试目标：
    DbOutput 的数据清洗逻辑：
    1. _sanitize 按列长度限制截断超长字符串
    2. 列对齐：只保留表中存在的列（通过单测间接验证 _get_table_columns 缓存）

说明：
    通过 __new__ 跳过 __init__（避免真实连库），手工装配内部状态，
    这是测试"重 I/O 类"的常用解耦手法。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from output.db_output import DbOutput


def make_output_without_db(col_limits):
    """构造一个不连数据库的 DbOutput 实例（预置表结构缓存）"""
    obj = DbOutput.__new__(DbOutput)   # 跳过 __init__，不发起真实连接
    obj.table = "user"
    obj._cols_cache = col_limits       # 直接注入模拟的表结构
    return obj


class TestSanitize:
    """超长值截断逻辑测试"""

    def test_truncate_overlong_string(self):
        """超过 VARCHAR(64) 限制的字符串应被截断到 64"""
        out = make_output_without_db({"id": 64, "username": 64, "age": None})
        rows = [{"id": "A" * 1000, "username": "ok", "age": 20}]
        cleaned = out._sanitize(rows, ["id", "username", "age"])
        assert len(cleaned[0]["id"]) == 64   # 截断到列长
        assert cleaned[0]["username"] == "ok"  # 正常值不动
        assert cleaned[0]["age"] == 20

    def test_non_string_values_untouched(self):
        """数字类型不受字符长度限制影响"""
        out = make_output_without_db({"age": None})
        rows = [{"age": 99999}]
        cleaned = out._sanitize(rows, ["age"])
        assert cleaned[0]["age"] == 99999

    def test_unlimited_column_not_truncated(self):
        """无长度限制的列（TEXT 等，限制为 None）不截断"""
        out = make_output_without_db({"address": None})
        rows = [{"address": "B" * 5000}]
        cleaned = out._sanitize(rows, ["address"])
        assert len(cleaned[0]["address"]) == 5000
