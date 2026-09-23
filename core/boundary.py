# -*- coding: utf-8 -*-
"""
boundary.py —— 边界值模式（创新点3）

职责：
    根据字段的规则定义，自动生成"故意找茬"的异常数据：
    min/min±1/max/max±1/空/超长/特殊字符（SQL 注入、emoji）等。

设计思想（面试话术锚点）：
    把测试用例设计方法（等价类划分、边界值分析）工具化。
    随机数据只能覆盖正常路径，异常数据才能暴露程序健壮性缺陷。

开关设计：
    通过命令行 --boundary 打开；每条异常数据带 expected 标注
    （should_accept / should_reject），便于下游自动化断言。
"""
from core.rules import PLACEHOLDER_PATTERN, render


def _extract_range(rule_str):
    """从字段规则串里提取 int/decimal 规则的数值范围 (min, max)。

    只识别整串就是单个 int(...) / decimal(...) 占位符的字段，
    混合字符串（如 "auto_${random_str(8)}"）不参与数值边界推导。
    """
    if not isinstance(rule_str, str):
        return None
    m = PLACEHOLDER_PATTERN.fullmatch(rule_str.strip())
    if not m:
        return None
    name, raw_args = m.group(1), m.group(2) or ""
    if name not in ("int", "decimal"):
        return None
    try:
        parts = [p.strip() for p in raw_args.split(",") if p.strip()]
        # int(a,b) 取前两个参数；decimal(a,b,digits) 同理（digits 与边界无关）
        return float(parts[0]), float(parts[1])
    except (IndexError, ValueError):
        return None


def _build_value_cases(rule_str):
    """根据字段规则推导该字段的边界值列表。

    返回值格式：[(值, 预期结果标注), ...]
        should_accept  → 合法边界内的值，程序应当接受
        should_reject  → 非法值，程序应当拒绝（供自动化断言用）
    """
    cases = []

    # ---- 数值型字段的边界 ----
    rng = _extract_range(rule_str)
    if rng:
        lo, hi = rng
        is_int = PLACEHOLDER_PATTERN.fullmatch(rule_str.strip()).group(1) == "int"
        # 合法边界：min 和 max（期望被接受）
        cases.append((int(lo) if is_int else lo, "should_accept"))
        cases.append((int(hi) if is_int else hi, "should_accept"))
        # 非法边界：min-1 和 max+1（期望被拒绝）
        cases.append((int(lo) - 1 if is_int else round(lo - 0.01, 2), "should_reject"))
        cases.append((int(hi) + 1 if is_int else round(hi + 0.01, 2), "should_reject"))
        # 常见异常：负数、超大值
        cases.append((-999999, "should_reject"))
        return cases

    # ---- 字符串型字段的边界 ----
    # 空字符串（必填字段应拒绝）
    cases.append(("", "should_reject"))
    # 超长字符串（1024 个 'A'，测字段长度限制）
    cases.append(("A" * 1024, "should_reject"))
    # SQL 注入试探串（测 SQL 拼接漏洞）
    cases.append(("'; DROP TABLE users;--", "should_reject"))
    # XSS 脚本片段（测转义处理）
    cases.append(("<script>alert(1)</script>", "should_reject"))
    # emoji 特殊字符（测编码兼容性，部分库会异常）
    cases.append(("😀🎉测试", "should_accept"))
    return cases


def generate_boundary_rows(fields, marker_field, marker_value, context=None):
    """生成一个模型的边界异常数据集。

    参数:
        fields:       模板的字段规则字典
        marker_field: 测试标记字段名
        marker_value: 测试标记值
        context:      渲染上下文（含 ref 解析器，供依赖字段回填）

    策略：
        对每个字段取它的全部边界值，横向展开成多行
        （每行一个字段处于异常态、其余字段取正常随机值），
        避免全笛卡尔积导致的组合爆炸。

    返回:
        异常数据行列表，每行额外带 'expected_result' 标注列
    """
    rows = []

    for field, rule in fields.items():
        if not isinstance(rule, str):
            continue  # 非字符串规则（纯数字/布尔字面量）跳过边界分析

        for value, expected in _build_value_cases(rule):
            # 每行：目标字段取边界值，其他字段正常渲染（保持数据整体可用）
            row = {f: render(v, context) for f, v in fields.items() if f != field}
            row[field] = value
            row[marker_field] = marker_value
            row["expected_result"] = expected  # 异常数据预期结果标注
            rows.append(row)

    return rows