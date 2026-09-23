# -*- coding: utf-8 -*-
"""
base.py —— 输出层统一接口（工厂 + 策略模式）

职责：
    定义所有输出器的统一契约（BaseOutput），并提供工厂函数 create_output
    按模板的 output 声明创建对应实现。

设计说明（面试话术锚点）：
    输出方式可插拔：新增输出方式（如 API 注入）只需新增一个 BaseOutput
    子类并在工厂里注册一行，不改动任何老代码——开闭原则。
"""


class BaseOutput:
    """输出器抽象基类：所有落地方式必须实现 write 方法"""

    def write(self, rows):
        """把一批数据行写入目标（数据库/文件/...），由子类实现"""
        raise NotImplementedError


def create_output(tpl, config):
    """工厂函数：根据模板的 output 字段创建对应输出器实例"""
    if tpl.get("output", "database") == "database":
        from output.db_output import DbOutput
        return DbOutput(tpl, config)
    from output.file_output import FileOutput
    return FileOutput(tpl, config)