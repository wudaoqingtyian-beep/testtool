# -*- coding: utf-8 -*-
"""
main.py —— 数据工厂命令行入口

支持的命令：
    造数:     python main.py --template templates/user.yaml --count 100
    边界模式: python main.py --template templates/order.yaml --boundary
    回滚:     python main.py --rollback B20260903xxxxxx
    批次列表: python main.py --list

全局流程：
    加载配置 → 加载并校验模板 → 拓扑排序 → 生成渲染 → 输出落地 → 快照存档
"""
import os
import sys
import argparse

import yaml

from core.loader import load_templates, sort_by_dependency
from core.generator import generate
from core.snapshot import SnapshotManager


def load_config(config_path="config.yaml"):
    """加载全局配置；没有 config.yaml 时使用默认值（file 输出不需要配置也能跑）"""
    if not os.path.exists(config_path):
        # 提供零配置默认值，方便先用 file 输出方式体验工具
        return {
            "database": {"url": "", "batch_size": 100},
            "marker": {"field": "env_tag", "value": "TEST_DATA"},
            "snapshot_dir": "snapshots",
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="测试数据工厂：基于模板的测试数据一键生成工具")
    parser.add_argument("--template", "-t", help="模板文件路径（造数模式必填）")
    parser.add_argument("--count", "-c", type=int, default=None, help="生成条数（覆盖模板里的 count）")
    parser.add_argument("--boundary", action="store_true", help="开启边界值模式：额外生成异常数据（创新3）")
    parser.add_argument("--rollback", metavar="BATCH_ID", help="按批次号回滚造数（创新4）")
    parser.add_argument("--list", action="store_true", help="列出所有历史造数批次")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径，默认 config.yaml")
    return parser.parse_args()


def main():
    args = build_args()
    config = load_config(args.config)

    # ---------- 回滚模式 ----------
    if args.rollback:
        manager = SnapshotManager(config.get("snapshot_dir", "snapshots"))
        report = manager.rollback(args.rollback, config)
        print(f"\n===== 回滚批次 {args.rollback} 完成 =====")
        for model, deleted in report.items():
            print(f"  {model}: 删除 {deleted} 条")
        return

    # ---------- 批次列表 ----------
    if args.list:
        manager = SnapshotManager(config.get("snapshot_dir", "snapshots"))
        batches = manager.list_batches()
        if not batches:
            print("暂无历史批次")
        for b in batches:
            print(b)
        return

    # ---------- 造数模式 ----------
    if not args.template:
        sys.exit("错误：请通过 --template 指定模板文件（或使用 --rollback/--list）")

    # 1. 加载并校验模板（写错规则名/缺字段在这里就会报错）
    templates = load_templates(args.template)
    # 2. 按依赖拓扑排序（依赖模型先生成，保证外键可回填；依赖环在这里报错）
    templates = sort_by_dependency(templates)

    # 3. 生成 + 落地
    import time
    start = time.time()
    report = generate(templates, count=args.count, boundary=args.boundary, config=config)

    # 4. 创建批次快照（供后续回滚）
    marker = config.get("marker", {}).get("value", "TEST_DATA")
    manager = SnapshotManager(config.get("snapshot_dir", "snapshots"))
    batch_id = manager.create_batch(report, marker)

    # 5. 输出统计报告（正常/异常数据分开统计）
    elapsed = time.time() - start
    print(f"\n===== 造数完成，批次号: {batch_id}，耗时 {elapsed:.2f}s =====")
    for model, stat in report.items():
        line = f"  {model}: 正常 {stat['normal']} 条"
        if stat["boundary"]:
            line += f"，边界异常 {stat['boundary']} 条（已标注 expected_result）"
        print(line)
    print(f"回滚命令: python main.py --rollback {batch_id}")


if __name__ == "__main__":
    main()