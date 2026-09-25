"""电气测试接口：维护测试单，覆盖开始测试、判定合格、判定不合格等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.measure import MeasureService

router = APIRouter(prefix="/api/measure", tags=["电气测试"])

service = MeasureService()

LIST_FIELDS = ["测试单号", "测试项目", "测试设备", "测试值", "标准范围", "测试结论", "测试人员", "测试状态"]
STATUSES = ["待测试", "测试中", "合格", "不合格"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按测试单号检索"),
    status: str | None = Query(default=None, description="待测试、测试中、合格、不合格"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按测试单号与状态过滤电气测试列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, Any]:
    """合格率等统计与判定结论同源，跟着每次判定更新。"""
    return {"items": service.stats()}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出电气测试清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "measure", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条测试单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"测试单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条测试单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="测试单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条测试单执行动作：开始测试照旧；判定结论由服务端按同一份比较给出，可随动作提交测试值与参考区间。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=service.present_entry(entry))
