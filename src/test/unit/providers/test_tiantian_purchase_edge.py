"""tiantian_purchase 解析失败与载荷准入的边缘场景测试。

必须放在 *_edge.py 文件中（边缘测试文件隔离）。

覆盖（设计文档 §3.4-3 / §7 异常样本）：
  - 解析失败各态（前缀缺失 / JSON 破损 / datas 缺失 / 行宽不足 / 限额脏值）→ None，
    垃圾载荷绝不入缓存
  - 载荷准入 purchase_status_payload_is_valid 的值域体检（防上游插列导致的
    位置错位整体误过）：行数下限、语义版本、代码格式、状态枚举、限额非负、
    下一开放日日期格式、必需键齐全
"""

from __future__ import annotations

from typing import Any

import pytest

from src.python.providers import tiantian_purchase as tp
from src.python.providers.tiantian_purchase import (
    MIN_ACCEPT_ROWS,
    PURCHASE_SCHEMA_FIELD,
    parse_purchase_table,
    purchase_status_payload_is_valid,
    stamp_purchase_payload,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers, pytest.mark.edge]


def _well_formed_row(code: str = "000001") -> list[str]:
    """13 列合法原始行（列序见模块 docstring）。"""
    return [
        code,
        "某基金",
        "混合型",
        "1.2220",
        "09-30",
        "开放申购",
        "开放赎回",
        "",
        "10.0",
        "100.0",
        "1.0",
        "1",
        "0.15%",
    ]


def _response_body(datas: list[list[str]]) -> str:
    import json

    inner = ",".join(json.dumps(row, ensure_ascii=False) for row in datas)
    return f"var reData={{datas:[{inner}],count:{len(datas)}}}"


# ============================================================
#  解析失败各态 → None
# ============================================================


class TestParseFailure:
    """parse_purchase_table 对格式破坏的响应一律返回 None（不产垃圾载荷）。"""

    def test_missing_object_body_returns_none(self):
        """既无 var reData= 前缀又非对象体（如错误页 HTML）→ None。"""
        assert parse_purchase_table("<html>500 Service Error</html>") is None

    def test_broken_json_returns_none(self):
        """对象体 JSON 破损 → None。"""
        assert parse_purchase_table("var reData={datas:[['000001',,]}") is None

    def test_missing_datas_returns_none(self):
        """结构可解析但缺 datas 数组（格式疑似变更）→ None。"""
        assert parse_purchase_table("var reData={count:100}") is None

    def test_empty_datas_returns_none(self):
        """datas 为空数组（上游异常空表）→ None。"""
        assert parse_purchase_table("var reData={datas:[],count:0}") is None

    def test_short_row_returns_none(self):
        """行宽不足 13 列（列结构破坏/截断）→ 整次解析判失败。"""
        body = _response_body([["000001", "某基金", "开放申购"]])
        assert parse_purchase_table(body) is None

    def test_unparseable_limit_returns_none(self):
        """日累计限定金额不可解析（位置错位/脏值）→ 整次解析判失败。"""
        row = _well_formed_row()
        row[9] = "abc"
        assert parse_purchase_table(_response_body([row])) is None

    def test_negative_limit_returns_none(self):
        """日累计限定金额为负 → 值域异常，整次解析判失败。"""
        row = _well_formed_row()
        row[9] = "-1"
        assert parse_purchase_table(_response_body([row])) is None

    def test_zero_limit_parses_to_none(self):
        """0 元限额 → daily_limit=None（「限额未知」的解析层单点转换，风险 R4）。"""
        row = _well_formed_row()
        row[9] = "0"
        payload = parse_purchase_table(_response_body([row]))
        assert payload is not None
        assert payload["rows"]["000001"]["daily_limit"] is None

    def test_garbage_min_purchase_parses_to_none(self):
        """购买起点脏值 → 宽松归 None（非准入关键字段，不拖垮整表）。"""
        row = _well_formed_row()
        row[8] = "起购"
        payload = parse_purchase_table(_response_body([row]))
        assert payload is not None
        assert payload["rows"]["000001"]["min_purchase"] is None


# ============================================================
#  载荷准入：purchase_status_payload_is_valid
# ============================================================


def _large_rows(n: int = MIN_ACCEPT_ROWS) -> dict[str, dict[str, Any]]:
    """构造足量合法行（准入要求行数 ≥ MIN_ACCEPT_ROWS）。"""
    return {
        f"{i:06d}": {
            "purchase_status": "开放申购",
            "redemption_status": "开放赎回",
            "next_open_date": "",
            "daily_limit": None,
            "min_purchase": 10.0,
        }
        for i in range(n)
    }


@pytest.fixture(scope="module")
def _valid_payload() -> dict[str, Any]:
    """足量合法载荷基底（浅拷贝后逐项改坏单点）。"""
    return stamp_purchase_payload(_large_rows())


class TestPayloadAdmission:
    """载荷准入：任一校验项不满足即判失败（写侧/读侧同判据）。"""

    def test_valid_payload_passes(self, _valid_payload):
        """合法载荷（行数达标 + 版本一致 + 值域全过）→ 准入通过。"""
        assert purchase_status_payload_is_valid(_valid_payload) is True

    def test_non_dict_payload_rejected(self):
        """非 dict 载荷（损坏缓存体）→ 拒绝。"""
        assert purchase_status_payload_is_valid(None) is False
        assert purchase_status_payload_is_valid("broken") is False

    def test_missing_schema_field_rejected(self):
        """缺 purchase_schema 版本字段 → 拒绝（旧语义条目自动作废）。"""
        payload = stamp_purchase_payload(_large_rows())
        del payload[PURCHASE_SCHEMA_FIELD]
        assert purchase_status_payload_is_valid(payload) is False

    def test_stale_schema_version_rejected(self):
        """purchase_schema 版本不符 → 拒绝（未来字段演进抬版本即失效旧缓存）。"""
        payload = stamp_purchase_payload(_large_rows())
        payload[PURCHASE_SCHEMA_FIELD] = tp.PURCHASE_SCHEMA + 1
        assert purchase_status_payload_is_valid(payload) is False

    def test_row_count_below_threshold_rejected(self, _valid_payload):
        """行数骤降（< MIN_ACCEPT_ROWS）→ 拒绝（上游半表/截断防护）。"""
        payload = stamp_purchase_payload(_large_rows(MIN_ACCEPT_ROWS - 1))
        assert purchase_status_payload_is_valid(payload) is False
        assert purchase_status_payload_is_valid(_valid_payload) is True

    def test_non_dict_rows_rejected(self, _valid_payload):
        """rows 非 dict → 拒绝。"""
        payload = {**_valid_payload, "rows": []}
        assert purchase_status_payload_is_valid(payload) is False

    def test_non_six_digit_code_rejected(self, _valid_payload):
        """值域体检：基金代码非 6 位数字（上游插列错位）→ 拒绝。"""
        rows = dict(_valid_payload["rows"])
        rows["1234567"] = rows.pop("000000")
        payload = {**_valid_payload, "rows": rows}
        assert purchase_status_payload_is_valid(payload) is False

    def test_unknown_purchase_status_rejected(self, _valid_payload):
        """值域体检：申购状态不在已知枚举 → 拒绝（防位置错位整体误过）。"""
        rows = dict(_valid_payload["rows"])
        rows["000000"] = {**rows["000000"], "purchase_status": "未知状态"}
        payload = {**_valid_payload, "rows": rows}
        assert purchase_status_payload_is_valid(payload) is False

    def test_unknown_redemption_status_rejected(self, _valid_payload):
        """值域体检：赎回状态不在已知枚举 → 拒绝。"""
        rows = dict(_valid_payload["rows"])
        rows["000000"] = {**rows["000000"], "redemption_status": "随便赎回"}
        payload = {**_valid_payload, "rows": rows}
        assert purchase_status_payload_is_valid(payload) is False

    def test_non_numeric_limit_rejected(self, _valid_payload):
        """值域体检：daily_limit 非数值 → 拒绝（解析层已拦，此处守缓存体）。"""
        rows = dict(_valid_payload["rows"])
        rows["000000"] = {**rows["000000"], "daily_limit": "100元"}
        payload = {**_valid_payload, "rows": rows}
        assert purchase_status_payload_is_valid(payload) is False

    def test_negative_limit_rejected(self, _valid_payload):
        """值域体检：daily_limit 为负 → 拒绝。"""
        rows = dict(_valid_payload["rows"])
        rows["000000"] = {**rows["000000"], "daily_limit": -1.0}
        payload = {**_valid_payload, "rows": rows}
        assert purchase_status_payload_is_valid(payload) is False

    def test_malformed_next_open_date_rejected(self, _valid_payload):
        """值域体检：next_open_date 非 YYYY-MM-DD → 拒绝。"""
        rows = dict(_valid_payload["rows"])
        rows["000000"] = {**rows["000000"], "next_open_date": "12月08日"}
        payload = {**_valid_payload, "rows": rows}
        assert purchase_status_payload_is_valid(payload) is False

    def test_missing_required_key_rejected(self, _valid_payload):
        """必需字段缺失（五键契约破坏）→ 拒绝。"""
        rows = dict(_valid_payload["rows"])
        broken = dict(rows["000000"])
        del broken["daily_limit"]
        rows["000000"] = broken
        payload = {**_valid_payload, "rows": rows}
        assert purchase_status_payload_is_valid(payload) is False
