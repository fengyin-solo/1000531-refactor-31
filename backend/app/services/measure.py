"""电气测试业务规则。

测试值与标准范围的比较、测试结论的生成与状态流转全部收拢在本模块：
列表与详情两个入口共用 evaluate_entry 的结果，任何接口都不另写一份比较逻辑，
保证同一张测试单在哪里看到的结论都一致，合格率统计也以同一份结论为准。
"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "measure"
REQUIRED_FIELDS = ["测试单号", "测试项目", "测试设备"]
STATUS_ORDER = ["待测试", "测试中", "合格", "不合格"]
ACTION_RULES = {"开始测试": "测试中", "判定合格": "合格", "判定不合格": "不合格"}
# 终态结论动作：重复提交只保留最新一条，统计跟着这条结论走
JUDGE_ACTIONS = {"判定合格", "判定不合格"}

VALUE_FIELD = "测试值"
RANGE_FIELD = "标准范围"
CONCLUSION_FIELD = "测试结论"
DISPLAY_STATUS_FIELD = "测试状态"

_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_RANGE_SPLITTERS = ("~", "～", "—", "–", "-", "至", "到")


def _format_number(value: float) -> str:
    """比较结果里的数值统一去掉无意义的 .0，口径只此一份。"""
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _first_number(text: str) -> float | None:
    match = _NUMBER_RE.search(text)
    return float(match.group()) if match else None


def _parse_range(text: str) -> tuple[float | None, float | None]:
    """把标准范围解析成 (下限, 上限)；单边规格时另一端为 None。"""
    normalized = text.strip()
    for splitter in _RANGE_SPLITTERS:
        if splitter in normalized:
            left, right = normalized.split(splitter, 1)
            low, high = _first_number(left), _first_number(right)
            if low is not None and high is not None:
                return (low, high) if low <= high else (high, low)
            if low is not None:
                return low, None
            if high is not None:
                return None, high
    number = _first_number(normalized)
    if number is None:
        return None, None
    if any(mark in normalized for mark in ("≥", ">=", "≮")):
        return number, None
    if any(mark in normalized for mark in ("≤", "<=", "≯")):
        return None, number
    return number, number


def evaluate_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """用同一份规则比较测试值与标准范围，返回结论与原因。

    返回 passed / reason；reason 非空即为不合格原因，需要写进测试结论。
    """
    value_text = str(entry.get(VALUE_FIELD) or "").strip()
    range_text = str(entry.get(RANGE_FIELD) or "").strip()
    if not value_text:
        return {"passed": False, "reason": "未登记测试值，无法判定"}
    if not range_text:
        return {"passed": False, "reason": "未登记标准范围，无法判定"}
    value = _first_number(value_text)
    if value is None:
        return {"passed": False, "reason": f"测试值「{value_text}」无法识别为数值"}
    low, high = _parse_range(range_text)
    if low is None and high is None:
        return {"passed": False, "reason": f"标准范围「{range_text}」无法识别"}
    value_repr = _format_number(value)
    if low is not None and value < low:
        edge = "下限" if high is not None else "最小允许值"
        return {
            "passed": False,
            "reason": f"测试值 {value_repr} 低于标准范围{edge} {_format_number(low)}（标准范围：{range_text}）",
        }
    if high is not None and value > high:
        edge = "上限" if low is not None else "最大允许值"
        return {
            "passed": False,
            "reason": f"测试值 {value_repr} 高于标准范围{edge} {_format_number(high)}（标准范围：{range_text}）",
        }
    return {"passed": True, "reason": ""}


def _conclusion_text(passed: bool, reason: str) -> str:
    return "合格：测试值在标准范围内" if passed else f"不合格：{reason}"


def _apply_verdict(entry: dict[str, Any], verdict: dict[str, Any]) -> None:
    """把统一比较的结论落到记录上，状态、结论、统计标记始终同进同退。"""
    passed = bool(verdict["passed"])
    entry["status"] = "合格" if passed else "不合格"
    entry[CONCLUSION_FIELD] = _conclusion_text(passed, str(verdict["reason"]))
    entry[DISPLAY_STATUS_FIELD] = entry["status"]
    entry["pending"] = False
    entry["abnormal"] = not passed


def _present(entry: dict[str, Any]) -> dict[str, Any]:
    """列表/详情共用的出参口径：测试状态与流转状态保持一致。"""
    result = dict(entry)
    result[DISPLAY_STATUS_FIELD] = entry.get("status")
    return result


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
        return [_present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _present(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 测试值与标准范围随单登记，判定时由 evaluate_entry 统一比较
        for field in (VALUE_FIELD, RANGE_FIELD, "测试人员"):
            entry[field] = values.get(field)
        entry[CONCLUSION_FIELD] = "待判定"
        entry["status"] = STATUS_ORDER[0]
        entry[DISPLAY_STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return _present(entry), []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """执行测试单动作，返回 (记录, 说明, 是否生效)。

        判定动作一律以服务端 evaluate_entry 的结果为准：页面可能带着自己算出的
        结论提交，与服务端不一致时按服务端结论落库，并在说明里讲清楚差异。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"测试单 {entry_id} 不存在或已归档", False
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于电气测试可执行范围", False

        if action == "开始测试":
            # 老动作照旧：待测试 -> 测试中；合格之后不能退回测试中
            if entry.get("status") == "合格":
                return None, "测试单已判定合格，结论生效后不能退回测试中", False
            if entry.get("status") == "测试中":
                return _present(entry), "测试单已在测试中，无需重复开始", True
            entry["status"] = "测试中"
            entry[DISPLAY_STATUS_FIELD] = "测试中"
            entry["pending"] = True
            if entry.get("abnormal"):
                # 不合格单据复测：旧结论作废，等最新一次判定落库后再进统计
                entry["abnormal"] = False
                entry[CONCLUSION_FIELD] = "待判定"
            return _present(entry), "测试单已开始测试", True

        # 判定合格 / 判定不合格：允许补录/更新测试值，重复提交只保留最新一条结论
        values = values or {}
        for field in (VALUE_FIELD, RANGE_FIELD, "测试人员"):
            text = str(values.get(field) or "").strip()
            if text:
                entry[field] = text
        verdict = evaluate_entry(entry)
        server_passed = bool(verdict["passed"])
        requested_passed = action == "判定合格"
        _apply_verdict(entry, verdict)

        if requested_passed != server_passed:
            server_action = "判定合格" if server_passed else "判定不合格"
            note = (
                f"页面提交的是「{action}」，服务端按测试值与标准范围复核为"
                f"「{server_action}」，结论以服务端为准。"
            )
            if not server_passed:
                note += f"不合格原因：{verdict['reason']}。"
            return _present(entry), note, True
        return _present(entry), f"测试单已{action}，结论已更新", True

    def stats(self) -> dict[str, Any]:
        """合格率统计只认真实落库的结论，与列表/详情看到的口径一致。"""
        rows = store.rows(MODULE)
        waiting = sum(1 for row in rows if row.get("status") == "待测试")
        passed = sum(1 for row in rows if row.get("status") == "合格")
        failed = sum(1 for row in rows if row.get("status") == "不合格")
        judged = passed + failed
        return {
            "waiting": waiting,
            "passed": passed,
            "failed": failed,
            "judged": judged,
            # 已判定单据中的合格占比，分母为 0 时记 0，避免口径漂移
            "pass_rate": round(passed / judged, 4) if judged else 0,
        }
