# -*- coding: utf-8 -*-
"""
cleaner.py —— 数据清理器（配合创新4快照回滚）

职责：
    按测试标记（marker）删除指定表中的造数数据。

说明：
    回滚以「标记字段 + 表名」定位数据，不依赖主键区间，
    这样即使造数过程中主键不连续（有自增空洞）也能完整清理。
"""
from sqlalchemy import text


def delete_by_marker(table, marker_value, config):
    """删除表中所有带指定测试标记的数据，返回删除条数。

    参数:
        table:        目标表名（来自快照记录的模型名）
        marker_value: 标记值（如 TEST_DATA）
        config:       全局配置（取数据库连接与标记字段名）
    """
    marker_field = config.get("marker", {}).get("field", "env_tag")

    from output.db_output import _get_engine
    engine = _get_engine(config.get("database", {}).get("url"))

    # 删除语句：WHERE 标记字段 = 标记值，只删本工具造的数据，
    # 绝不带 WHERE 1=1 之类的全删逻辑——安全第一
    sql = text(f"DELETE FROM {table} WHERE {marker_field} = :marker")
    with engine.begin() as conn:
        result = conn.execute(sql, {"marker": marker_value})
        return result.rowcount  # 实际删除的行数（写进清理报告）