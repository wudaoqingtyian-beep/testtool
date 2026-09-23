# -*- coding: utf-8 -*-
"""
db_output.py —— 数据库注入器

职责：
    把生成的数据批量写入数据库表（模板 model 名即表名）。

实现说明：
    使用 SQLAlchemy 的文本 SQL + 参数绑定（executemany 批量插入），
    不依赖 ORM 模型定义——因为被测表结构千差万别，
    直接按数据行的 key 拼 INSERT 语句最通用。
"""
from sqlalchemy import create_engine, text

from output.base import BaseOutput


class DbOutput(BaseOutput):
    """数据库输出器：批量 INSERT"""

    def __init__(self, tpl, config):
        self.table = tpl["model"]                      # 模板模型名 = 目标表名
        db_conf = config.get("database", {})
        # 每次初始化都建引擎成本高，这里用模块级缓存复用连接池
        self.engine = _get_engine(db_conf.get("url"))
        self.batch_size = int(db_conf.get("batch_size", 100))

    def write(self, rows):
        """批量写入数据行，返回写入条数。按 batch_size 分批提交。

        列对齐策略：
            数据行里的字段可能比表多（如边界数据的 expected_result 标注列，
            数据库表里并没有这个列）。这里先查出目标表的实际列，
            只写两者交集，多余字段自动忽略——保证工具对表结构零侵入。
        """
        if not rows:
            return 0

        # 查询目标表的实际列名（information_schema，跨 MySQL 版本通用）
        existing_cols = self._get_table_columns()

        # 以第一行为字段基准，过滤掉表里不存在的列
        columns = [c for c in rows[0].keys() if c in existing_cols]
        dropped = set(rows[0].keys()) - set(columns)
        if dropped:
            print(f"[db_output] 表 {self.table} 不存在以下列，已忽略: {sorted(dropped)}")

        # 清洗每行数据：只保留有效列（避免 executemany 参数不一致报错）
        clean_rows = [{c: row.get(c) for c in columns} for row in rows]

        # 按列长度限制截断超长值（如边界数据的 1024 字符串）
        clean_rows = self._sanitize(clean_rows, columns)

        # 参数化 INSERT 语句：列名显式拼入（来自模板定义），值全部走参数绑定防注入
        sql = "INSERT INTO {table} ({cols}) VALUES ({ph})".format(
            table=self.table,
            cols=", ".join(columns),
            ph=", ".join(f":{c}" for c in columns),
        )

        total = 0
        # 分批插入：一次性插几万条会撑爆事务日志和内存
        for i in range(0, len(clean_rows), self.batch_size):
            chunk = clean_rows[i:i + self.batch_size]
            with self.engine.begin() as conn:  # begin：每批一个事务，失败整批回滚
                conn.execute(text(sql), chunk)
            total += len(chunk)
        return total

    def _get_table_columns(self):
        """查询目标表的列名及长度限制（带缓存：同一张表只查一次）

        返回: {列名: 最大字符长度或 None}
            None 表示该列无长度限制（如 INT/TEXT/DECIMAL）
        """
        if not hasattr(self, "_cols_cache"):
            sql = text(
                "SELECT COLUMN_NAME, CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
            )
            with self.engine.connect() as conn:
                self._cols_cache = {
                    r[0]: r[1] for r in conn.execute(sql, {"t": self.table})
                }
        return self._cols_cache

    def _sanitize(self, clean_rows, columns):
        """按列长度限制截断超长的字符串值（如边界数据的 1024 个 'A'）

        说明（面试话术锚点）：
            直接落库只是"存数据"，不校验业务规则；超长、格式校验应该由
            被测系统的接口层负责。所以这里按表结构截断保证可存储，
            截断行为会打印明细，信息不静默丢失。
        """
        limits = self._get_table_columns()
        truncated = 0
        for row in clean_rows:
            for c in columns:
                max_len = limits.get(c)
                v = row[c]
                if max_len and isinstance(v, str) and len(v) > max_len:
                    row[c] = v[:max_len]
                    truncated += 1
        if truncated:
            print(f"[db_output] 有 {truncated} 个字段值超长，已按表列定义截断")
        return clean_rows


# 引擎缓存：同一连接串全局只建一次（单命令行进程内复用）
_engine_cache = {}


def _get_engine(url):
    """获取（或创建）SQLAlchemy 引擎"""
    from sqlalchemy import create_engine
    if not url:
        raise ValueError("config.yaml 缺少 database.url 配置，无法连接数据库")
    if url not in _engine_cache:
        _engine_cache[url] = create_engine(url, pool_pre_ping=True)
    return _engine_cache[url]


# SQLAlchemy text 的便捷引用
from sqlalchemy import text  # noqa: E402