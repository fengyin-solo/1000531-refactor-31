"""电气测试业务规则：测试值与参考区间的比较只保留这一份。

列表、详情、判定动作与合格率统计都从这里的同一份比较结果取数，
页面侧不再各自计算，结论不一致时一律以服务端为准。
"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "measure"
REQUIRED_FIELDS = ["测试单号", "测试项目", "测试设备"]
STATUS_ORDER = ["待测试", "测试中", "合格", "不合格"]
ACTION_RULES = {"开始测试": "测试中", "判定合格": "合格", "判定不合格": "不合格"}

TESTING_STATUS = "测试中"
PASS_STATUS = "合格"
CONCLUDED_STATUSES = {"合格", "不合格"}
JUDGE_FIELDS = ["测试值", "标准范围", "测试人员"]

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_UNIT_RE = r"[a-zA-Z%Ω]*"
_RANGE_RE = re.compile(
    rf"^\s*(-?\d+(?:\.\d+)?)\s*[~～\-–—]\s*(-?\d+(?:\.\d+)?)\s*{_UNIT_RE}\s*$"
)
_LOWER_RE = re.compile(rf"^\s*(?:≥|>=)\s*(-?\d+(?:\.\d+)?)\s*{_UNIT_RE}\s*$")
_UPPER_RE = re.compile(rf"^\s*(?:≤|<=)\s*(-?\d+(?:\.\d+)?)\s*{_UNIT_RE}\s*$")


def _parse_number(text: Any) -> float | None:
    """从「12.5」「12.5V」这类文本里取出数值，取不到返回 None。"""
    match = _NUMBER_RE.search(str(text or ""))
    return float(match.group()) if match else None


def parse_reference_range(text: Any) -> tuple[float | None, float | None] | None:
    """把参考区间解析成 (下限, 上限)，支持「a~b」「≥a」「≤b」三种写法，端点都算区间内。"""
    raw = str(text or "").strip()
    if not raw:
        return None
    match = _RANGE_RE.match(raw)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        return (min(low, high), max(low, high))
    match = _LOWER_RE.match(raw)
    if match:
        return (float(match.group(1)), None)
    match = _UPPER_RE.match(raw)
    if match:
        return (None, float(match.group(1)))
    return None


def compare_with_reference(value_text: Any, range_text: Any) -> dict[str, str | None]:
    """全系统唯一的一份比较：测试值 对 该项目的参考区间。

    返回 {"结论": "合格"/"不合格"/None, "原因": 说明}；结论为 None 表示数据不足、不能判定。
    """
    value = _parse_number(value_text)
    bounds = parse_reference_range(range_text)
    if value is None or bounds is None:
        return {"结论": None, "原因": "测试值或参考区间缺失、无法解析"}
    low, high = bounds
    if low is not None and value < low:
        return {"结论": "不合格", "原因": f"测试值 {value:g} 低于参考区间下限 {low:g}"}
    if high is not None and value > high:
        return {"结论": "不合格", "原因": f"测试值 {value:g} 高于参考区间上限 {high:g}"}
    return {"结论": "合格", "原因": f"测试值 {value:g} 落在参考区间 {str(range_text).strip()} 内"}


def _conclusion_text(verdict: dict[str, str | None]) -> str:
    """判定不合格时把原因一并写进测试结论。"""
    if verdict["结论"] == "不合格":
        return f"不合格：{verdict['原因']}"
    return str(verdict["结论"] or "")


class MeasureService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("测试单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.present_entry(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self.present_entry(entry) if entry is not None else None

    def present_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        """列表页与详情页共用的一份结果：状态与结论都以服务端为准。

        已落库的测试结论会再跟同一份比较对一遍，对不上时以服务端比较结果为准，
        并附上说明，避免两个页面各算各的。
        """
        row = dict(entry)
        row["测试状态"] = str(entry.get("status") or "")
        stored = str(entry.get("测试结论") or "").strip()
        if not stored:
            return row
        verdict = compare_with_reference(entry.get("测试值"), entry.get("标准范围"))
        if verdict["结论"] is None:
            return row
        server_text = _conclusion_text(verdict)
        if stored != server_text:
            row["测试结论"] = server_text
            row["结论说明"] = f"页面结论「{stored}」与服务端判定不一致，已以服务端为准"
        return row

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["测试状态"] = STATUS_ORDER[0]
        entry["测试结论"] = ""
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"测试单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于电气测试可执行范围"
        if action == "开始测试":
            return self._start_test(entry)
        return self._judge(entry, action, values or {})

    def _start_test(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """老的开始测试动作照旧，只是合格之后的单子不允许再退回测试中。"""
        if entry.get("status") == PASS_STATUS:
            return None, "测试单已判定合格，不能退回测试中"
        entry["status"] = TESTING_STATUS
        entry["测试状态"] = TESTING_STATUS
        entry["pending"] = True
        entry["abnormal"] = False
        return entry, "测试单已开始测试"

    def _judge(
        self,
        entry: dict[str, Any],
        action: str,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        """判定合格/不合格：结论只认服务端的同一份比较，重复提交只留最新一条。"""
        for field in JUDGE_FIELDS:
            text = str(values.get(field) or "").strip()
            if text:
                entry[field] = text
        verdict = compare_with_reference(entry.get("测试值"), entry.get("标准范围"))
        if verdict["结论"] is None:
            return None, f"测试值或参考区间缺失、无法解析，不能{action}"
        notes = []
        if ACTION_RULES[action] != verdict["结论"]:
            notes.append(f"页面判定「{ACTION_RULES[action]}」与服务端比较结果不一致，已以服务端为准")
        if str(entry.get("测试结论") or "").strip():
            notes.append("重复提交仅保留最新一条结论")
        entry["测试结论"] = _conclusion_text(verdict)
        entry["status"] = verdict["结论"]
        entry["测试状态"] = verdict["结论"]
        entry["pending"] = False
        entry["abnormal"] = verdict["结论"] == "不合格"
        message = f"测试单已判定{verdict['结论']}"
        if verdict["结论"] == "不合格":
            message = f"{message}，原因：{verdict['原因']}"
        if notes:
            message = f"{message}（{'；'.join(notes)}）"
        return entry, message

    def stats(self) -> list[dict[str, Any]]:
        """合格率口径与判定结论同源：只统计已落结论（合格/不合格）的测试单。"""
        rows = store.rows(MODULE)
        concluded = [row for row in rows if row.get("status") in CONCLUDED_STATUSES]
        passed = sum(1 for row in concluded if row.get("status") == PASS_STATUS)
        rate = f"{passed / len(concluded) * 100:.1f}%" if concluded else "—"
        return [
            {"label": "待测试单据", "value": sum(1 for row in rows if row.get("status") == "待测试")},
            {"label": "测试合格率", "value": rate},
            {"label": "不合格项数", "value": len(concluded) - passed},
        ]
