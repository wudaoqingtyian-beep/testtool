# -*- coding: utf-8 -*-
"""
snapshot.py —— 数据集快照与回滚（创新点4）

职责：
    1. 每次造数成功后，记录一个"批次快照"（造了什么、造到哪、多少条）
    2. 支持按批次号精确回滚，按依赖反序删除（先删订单再删用户，避免外键报错）

设计思想（面试话术锚点）：
    解决造数工具普遍回避的"数据残留污染环境"问题。
    造数像网购下单，测完可按订单号整单退货——数据生命周期闭环。
"""
import os
import json
import time


class SnapshotManager:
    """批次快照管理器：负责快照的创建、读取与回滚"""

    def __init__(self, snapshot_dir="snapshots"):
        # 快照目录不存在则自动创建（历史批次以 JSON 文件存放）
        self.snapshot_dir = snapshot_dir
        os.makedirs(snapshot_dir, exist_ok=True)

    def create_batch(self, report, marker):
        """造数完成后创建批次快照，返回批次号。

        参数:
            report: generator 输出的统计报告 {模型名: {...}}
            marker: 测试标记值（回滚时按此字段定位数据）

        快照内容:
            batch_id    批次号（时间戳生成，保证唯一且按时间有序）
            created_at  创建时间
            marker      数据标记（清理依据）
            models      每个模型造数的统计信息
        """
        batch_id = time.strftime("B%Y%m%d%H%M%S")
        snapshot = {
            "batch_id": batch_id,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "marker": marker,
            "models": {k: {"normal": v["normal"], "boundary": v["boundary"]}
                       for k, v in report.items()},
        }
        path = os.path.join(self.snapshot_dir, f"{batch_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        return batch_id

    def rollback(self, batch_id, config):
        """按批次号回滚数据，返回清理报告字典。

        步骤:
            1. 读取快照 JSON
            2. 按模型**逆序**删除带标记的数据（依赖反序：先删子表再删父表）
            3. 返回每个模型的删除条数
        """
        path = os.path.join(self.snapshot_dir, f"{batch_id}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"找不到批次快照: {batch_id}")

        with open(path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)

        # 按快照中记录顺序的**倒序**删除：造数时是先造 User 再造 Order，
        # 回滚必须反过来先删 Order，否则外键约束会报错
        from output.cleaner import delete_by_marker
        report = {}
        for model in reversed(list(snapshot["models"].keys())):
            deleted = delete_by_marker(
                model, snapshot["marker"], config
            )
            report[model] = deleted
        return report

    def list_batches(self):
        """列出所有历史批次号（供 --list 命令展示）"""
        if not os.path.isdir(self.snapshot_dir):
            return []
        return sorted(
            f[:-5] for f in os.listdir(self.snapshot_dir) if f.endswith(".json")
        )