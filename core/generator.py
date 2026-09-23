# -*- coding: utf-8 -*-
"""
generator.py —— 生成调度器

职责：
    按依赖顺序编排各模型 → 循环 count 次渲染每条数据 → 处理外键回填
    → 交给输出层落地 → 汇总统计报告。

核心流程：
    1. loader 给出拓扑排序后的模板列表
    2. 对每个模板循环 count 次，逐字段调用 rules.render 渲染
    3. 模板若声明 depends_on，渲染时把依赖模型已生成记录传给 ${ref()} 规则
    4. 造数结果交给 output 层落地，同时记录进快照（供回滚）
"""
import random

# 渲染函数从规则引擎导入（数据生成的统一入口）
from core.rules import render


def generate(templates, count=None, boundary=False, config=None):
    """主生成入口：按拓扑序渲染所有模板的数据。

    参数:
        templates: loader 排序后的模板列表
        count:     命令行覆盖的条数（不传则用模板里的 count，默认 100）
        boundary:  创新3 边界值开关；True 时每模板额外追加异常数据
        config:    全局配置字典（数据库/标记/快照目录等）

    返回:
        报告字典：{模型名: {"normal": n, "boundary": m, "records": [...]}}
    """
    config = config or {}
    marker_field = config.get("marker", {}).get("field", "env_tag")
    marker_value = config.get("marker", {}).get("value", "TEST_DATA")

    report = {}
    # 已生成记录缓存：模型名 → 该模型所有记录，供依赖模型的 ${ref()} 取值
    generated_pool = {}

    for tpl in templates:
        model = tpl["model"]
        n = int(count if count is not None else tpl.get("count", 100))
        fields = tpl["fields"]

        # ref 解析器：从依赖模型的记录池里随机挑一条，取指定字段值
        def _resolve_ref(model_field, _pool=generated_pool):
            """把 ${ref(User.id)} 解析为依赖模型某条真实记录的值"""
            dep_model, dep_field = model_field.split(".", 1)
            records = _pool.get(dep_model, [])
            if not records:
                raise RuntimeError(f"依赖模型 '{dep_model}' 尚未生成数据，无法回填 {model_field}")
            return random.choice(records)[dep_field]

        # 每个模型的渲染上下文：携带 ref 解析器，rules.render 会用到
        ctx = {"ref_resolver": _resolve_ref}

        # ---------- 1. 正常数据 ----------
        normal_records = []
        for _ in range(n):
            row = {f: render(v, ctx) for f, v in fields.items()}
            row[marker_field] = marker_value  # 打上测试标记（清理依据）
            normal_records.append(row)

        # ---------- 2. 边界/异常数据（创新3：开关打开时追加） ----------
        boundary_records = []
        if boundary:
            from core.boundary import generate_boundary_rows
            # 边界数据与正常数据用同一套字段定义，但每个字段取极端值组合
            # 传入 ctx 让边界数据中的 ${ref()} 也能正常回填依赖
            boundary_records = generate_boundary_rows(fields, marker_field, marker_value, ctx)

        # 合并进缓存池（依赖模型取值用正常数据即可）
        generated_pool[model] = normal_records

        # ---------- 3. 交给输出层落地 ----------
        from output.base import create_output
        output = create_output(tpl, config)
        # 正常与异常数据分开输出，报告也分开统计（异常数据要单独核对）
        output.write(normal_records)
        if boundary_records:
            output.write(boundary_records)

        report[model] = {
            "normal": len(normal_records),
            "boundary": len(boundary_records),
            "total": len(normal_records) + len(boundary_records),
            # 服务模式（FastAPI）需要把造出的行返回给调用方（项目2 框架回填变量池）
            "records": normal_records,
            "boundary_records": boundary_records,
        }

    return report