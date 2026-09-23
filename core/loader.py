# -*- coding: utf-8 -*-
"""
loader.py —— 模板加载与校验

职责：
    1. 读取 YAML 模板文件（支持一个文件里多个文档，用 --- 分隔）
    2. 校验模板必填字段、占位符合法性（加载期就报错，避免运行到一半才炸）
    3. 构建模型依赖图，检测依赖环（创新设计：DAG 环检测）

校验原则：
    「尽早失败」——所有能静态发现的问题（写错规则名、依赖成环）
    都在加载期暴露，并给出清晰错误信息。
"""
import yaml


class TemplateError(Exception):
    """模板格式/内容错误的自定义异常，便于上层统一捕获并友好提示"""


def load_templates(path):
    """加载 YAML 模板文件，返回模板列表。

    一个文件内可用 '---' 分隔多个模型模板（如 user.yaml + order.yaml 合一）。
    """
    with open(path, "r", encoding="utf-8") as f:
        # safe_load_all：解析多文档 YAML；None 项是文件末尾多余的 --- 造成的空文档，过滤掉
        docs = [d for d in yaml.safe_load_all(f) if d]

    if not docs:
        raise TemplateError(f"模板文件 {path} 中没有任何有效模板")

    # 逐个做结构校验
    for doc in docs:
        _validate(doc)

    return docs


def _validate(tpl):
    """校验单个模板的结构完整性。

    必填项：
        model   模型名（如 User）
        fields  字段规则字典（至少一个字段）
    可选项：
        count       生成条数，默认 100
        output      输出方式：database / file，默认 database
        depends_on  依赖的模型名，用于外键回填
    """
    # model 和 fields 是必须存在的两项
    if not tpl.get("model"):
        raise TemplateError(f"模板缺少 'model' 字段: {tpl}")
    if not tpl.get("fields"):
        raise TemplateError(f"模板 '{tpl.get('model')}' 缺少 'fields' 字段定义")

    # output 方式只允许已知值，防止拼错（如 datbase）静默走错分支
    output = tpl.get("output", "database")
    if output not in ("database", "file"):
        raise TemplateError(f"模板 '{tpl['model']}' 的 output 只支持 database/file，当前: {output}")

    # 加载期占位符校验：每个字段里的 ${规则} 必须能在规则注册表里找到
    # 这样模板写错规则名，启动时立刻报错，而不是造到第 37 条才炸
    from core import rules  # 延迟导入避免循环依赖

    for field, rule in tpl["fields"].items():
        if isinstance(rule, str):
            for match in rules.PLACEHOLDER_PATTERN.finditer(rule):
                rule_name = match.group(1)
                # ref 规则合法性在依赖检查阶段处理，这里跳过
                if rule_name != "ref" and rule_name not in rules.RULES:
                    raise TemplateError(
                        f"模板 '{tpl['model']}' 字段 '{field}' 使用了未知规则 '{rule_name}'"
                    )


def sort_by_dependency(templates):
    """按依赖关系对模板列表做拓扑排序（依赖方排前面，先生成）。

    规则：
        模板 A 的 depends_on 含 B → B 必须排在 A 之前（先造 B 回填 A 的外键）
        检测到依赖环（A 依赖 B、B 又依赖 A）时直接报错并打印环路径。

    返回:
        排好序的模板列表（新的列表，不修改原列表）
    """
    # 模型名 → 模板 的索引，方便按名字查依赖
    by_name = {t["model"]: t for t in templates}

    result = []          # 拓扑排序结果
    visiting = set()     # 当前递归栈（用于检测环）
    visited = set()      # 已完成排序的模型

    def visit(model, chain):
        """深度优先访问模型，chain 记录访问路径用于报错时展示环"""
        if model in visited:       # 已经排过序，直接跳过
            return
        if model in visiting:      # 又回到递归栈里的节点 → 说明成环了！
            cycle = " -> ".join(chain + [model])
            raise TemplateError(f"模板依赖成环，无法生成: {cycle}")

        visiting.add(model)

        # 先递归处理所有依赖（保证依赖方先进入 result）
        # 兼容 depends_on 的三种情况：缺失 / 单字符串 / 列表
        deps = by_name[model].get("depends_on") or []
        if isinstance(deps, str):
            deps = [deps]
        for dep in deps:
            if dep not in by_name:
                raise TemplateError(f"模型 '{model}' 依赖了不存在的模型 '{dep}'")
            visit(dep, chain + [model])

        visiting.remove(model)
        visited.add(model)
        result.append(by_name[model])

    # 对每个模板都做一次 visit（图可能不连通，比如两组独立模型）
    for tpl in templates:
        visit(tpl["model"], [])

    return result