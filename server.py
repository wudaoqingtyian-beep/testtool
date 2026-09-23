# -*- coding: utf-8 -*-
"""
server.py —— 数据工厂服务层（FastAPI）

职责：
    把 CLI 的造数/回滚能力包成 HTTP 接口，供项目2 自动化框架远程调用。
    core 零改动复用（loader/generator/snapshot 原样调用）——这就是当初
    分层的红利：CLI 和 API 只是同一引擎的两个入口。

接口契约（与项目2 PRD §5 对齐，改动需双方同步）：
    GET  /api/v1/health                 健康检查（框架探活，决定服务/降级模式）
    POST /api/v1/data/generate          造数，返回批次号 + 数据行
    POST /api/v1/data/rollback          按批次精确回滚，返回删除统计
    GET  /api/v1/data/batches           列出历史批次

运行：
    cd 项目1 && uvicorn server:app --host 0.0.0.0 --port 8000
    自带交互文档: http://127.0.0.1:8000/docs
"""
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from main import load_config
from core.loader import load_templates, sort_by_dependency, TemplateError
from core.generator import generate
from core.snapshot import SnapshotManager

app = FastAPI(
    title="测试数据工厂服务",
    description="项目2 自动化框架的造数/回滚后端（契约见 PRD §5）",
    version="1.0.0",
)

CONFIG = load_config()


class GenerateRequest(BaseModel):
    """造数请求体。template 是 templates/ 下的模板名（不带 .yaml 后缀也可）。"""
    template: str = Field(..., description="模板名，如 user / order")
    count: int = Field(1, ge=1, le=100000, description="生成条数")
    boundary: bool = Field(False, description="是否追加边界值异常数据")


class RollbackRequest(BaseModel):
    batch_id: str = Field(..., description="要回滚的批次号，如 B20260905120000")


def _resolve_template(name: str) -> str:
    """把模板名解析为 templates/ 下的实际文件路径（防止路径穿越：只取文件名部分）。"""
    safe = os.path.basename(name)
    for candidate in (safe, f"{safe}.yaml"):
        path = os.path.join("templates", candidate)
        if os.path.exists(path):
            return path
    raise HTTPException(status_code=404, detail=f"模板不存在: {name}")


@app.get("/api/v1/health")
def health():
    """健康检查：框架每次 setup 前探活，失败则走本地降级模式。"""
    return {"status": "ok"}


@app.post("/api/v1/data/generate")
def data_generate(req: GenerateRequest):
    """造数：加载模板 → 拓扑排序 → 生成落地 → 创建批次快照 → 返回数据行。"""
    try:
        templates = sort_by_dependency(load_templates(_resolve_template(req.template)))
    except TemplateError as e:
        raise HTTPException(status_code=422, detail=f"模板错误: {e}")

    report = generate(templates, count=req.count, boundary=req.boundary, config=CONFIG)

    marker = CONFIG.get("marker", {}).get("value", "TEST_DATA")
    manager = SnapshotManager(CONFIG.get("snapshot_dir", "snapshots"))
    batch_id = manager.create_batch(report, marker)

    # 汇总所有模型的行返回给框架（rows 回填变量池；boundary 行单独标注）
    rows, boundary_rows = [], []
    for stat in report.values():
        rows.extend(stat["records"])
        boundary_rows.extend(stat["boundary_records"])

    return {
        "batch_id": batch_id,
        "rows": rows,
        "boundary_rows": boundary_rows,
        "stats": {k: {"normal": v["normal"], "boundary": v["boundary"]}
                  for k, v in report.items()},
    }


@app.post("/api/v1/data/rollback")
def data_rollback(req: RollbackRequest):
    """按批次精确回滚（依赖反序删除），失败必须大声报错——数据残留是环境事故。"""
    manager = SnapshotManager(CONFIG.get("snapshot_dir", "snapshots"))
    try:
        report = manager.rollback(req.batch_id, CONFIG)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"batch_id": req.batch_id, "deleted": report,
            "deleted_rows": sum(report.values())}


@app.get("/api/v1/data/batches")
def data_batches():
    """列出历史批次号。"""
    manager = SnapshotManager(CONFIG.get("snapshot_dir", "snapshots"))
    return {"batches": manager.list_batches()}
