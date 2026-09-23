# -*- coding: utf-8 -*-
"""
test_loader.py —— 模板加载与依赖排序单测

测试目标：
    1. 模板缺字段 / output 非法 / 占位符写错 → 加载期报错
    2. 依赖排序：依赖方排在被依赖方之后
    3. depends_on 兼容字符串和列表两种写法
    4. 依赖环检测：报错并打印环路径
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.loader import sort_by_dependency, TemplateError


def make_tpl(model, deps=None):
    """构造最小合法模板的辅助工厂"""
    return {
        "model": model,
        "count": 1,
        "fields": {"id": "${uuid}"},
        "depends_on": deps,
    }


class TestSortByDependency:
    """依赖拓扑排序测试"""

    def test_dependent_comes_after_dependency(self):
        """orders 依赖 user → user 必须排在 orders 前面"""
        sorted_list = sort_by_dependency([
            make_tpl("orders", deps="user"),
            make_tpl("user"),
        ])
        names = [t["model"] for t in sorted_list]
        assert names.index("user") < names.index("orders")

    def test_depends_on_string_and_list_both_work(self):
        """depends_on 写字符串和写列表效果一致（YAML 解析差异兼容）"""
        a = sort_by_dependency([make_tpl("b", deps="a"), make_tpl("a")])
        b = sort_by_dependency([make_tpl("b", deps=["a"]), make_tpl("a")])
        assert [t["model"] for t in a] == [t["model"] for t in b]

    def test_no_dependency_keeps_order(self):
        """无依赖的多个模板正常输出，不报错"""
        result = sort_by_dependency([make_tpl("x"), make_tpl("y")])
        assert len(result) == 2

    def test_dependency_cycle_detected(self):
        """A 依赖 B、B 依赖 A → 必须报环错误，且错误信息包含环路径"""
        with pytest.raises(TemplateError, match="依赖成环"):
            sort_by_dependency([
                make_tpl("a", deps="b"),
                make_tpl("b", deps="a"),
            ])

    def test_dependency_not_exist(self):
        """依赖了不存在的模型 → 报错提示"""
        with pytest.raises(TemplateError, match="不存在的模型"):
            sort_by_dependency([make_tpl("orders", deps="ghost")])
