# -*- coding: utf-8 -*-
"""
file_output.py —— 文件导出器

职责：
    把生成的数据导出为 CSV 或 JSON 文件（不直接落库的场景，
    例如给压测脚本当数据源、给同事人工核对）。

文件名规则：
    exports/<模型名>_<时间戳>.csv / .json
"""
import os
import csv
import json
import time

from output.base import BaseOutput


class FileOutput(BaseOutput):
    """文件输出器：支持 CSV / JSON 两种格式"""

    def __init__(self, tpl, config):
        self.table = tpl["model"]
        # 模板可用 file_format 指定格式，默认 csv
        self.fmt = tpl.get("file_format", "csv").lower()
        self.export_dir = config.get("export_dir", "exports")
        os.makedirs(self.export_dir, exist_ok=True)

    def write(self, rows):
        """按格式写出数据，返回写入条数"""
        if not rows:
            return 0

        # 文件名带时间戳，多次导出不互相覆盖
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.export_dir, f"{self.table}_{ts}.{self.fmt}")

        if self.fmt == "json":
            # JSON：直接序列化整批数据（ensure_ascii=False 保留中文）
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
        else:
            # CSV：以第一行的 key 为表头，逐行写入
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                # utf-8-sig：带 BOM，保证 Excel 打开中文不乱码
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

        print(f"[file_output] 已导出 {len(rows)} 条 -> {path}")
        return len(rows)


import json  # noqa: E402  （置于文件末尾统一引入，保持顶部为标准库分组说明性布局）