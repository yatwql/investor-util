"""fetcher/fund_purchase.py 单元测试 — 双链路接线、准入与四级降级阶梯。

测试目标（设计文档 docs/plan/fund-purchase-limit-design.md §7 用例清单）：
  - 链注册：_DEFAULT_CHAINS 槽位与 provider 映射同构（同序同集）
  - 四级降级逐级断言：主链路成功 → 备链路递补 → 过期缓存 → 暂不可用
  - 校验失败不污染旧缓存（写侧准入失败 → 不回写；垃圾载荷不入缓存）
  - 会话缓存：同一次报告生成内单次经链（None 亦缓存，避免反复重试）
  - data_status 追踪：成功/失败均登记

运行：
  pytest src/test/unit/fetcher/test_fund_purchase.py -v
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.python.fetcher import chain, fund_purchase
from src.python.fetcher.fund_purchase import (
    fetch_fund_purchase_status,
    fetch_fund_purchase_status_cached,
)
from src.python.providers.tiantian_purchase import (
    MIN_ACCEPT_ROWS,
    PURCHASE_SCHEMA_FIELD,
    stamp_purchase_payload,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]

_STALE_FETCHED_AT = "2026-09-25T09:00:00+08:00"


def _large_rows(n: int = MIN_ACCEPT_ROWS) -> dict[str, dict[str, Any]]:
    """构造足量合法行（准入要求行数 ≥ MIN_ACCEPT_ROWS）。"""
    return {
        f"{i:06d}": {
            "purchase_status": "开放申购",
            "redemption_status": "开放赎回",
            "next_open_date": "",
            "daily_limit": None,
            "min_purchase": 10.0,
            "purchase_fee_rate": 0.0015,
        }
        for i in range(n)
    }


def _payload(fetched_at: str | None = None) -> dict[str, Any]:
    """可通过准入的合法载荷（可指定 fetched_at 以断言陈旧载荷原样透传）。"""
    payload = stamp_purchase_payload(_large_rows())
    if fetched_at is not None:
        payload["fetched_at"] = fetched_at
    return payload


def _invalid_payload() -> dict[str, Any]:
    """行数骤降的载荷（不过准入 —— 模拟上游半表/格式破坏）。"""
    return stamp_purchase_payload(_large_rows(3))


def _use_provider(monkeypatch: pytest.MonkeyPatch, name: str, label: str, fn) -> None:
    """把指定槽位换成受控 fake（其余槽位保持真实）。"""
    monkeypatch.setitem(fund_purchase._PURCHASE_PROVIDERS, name, (label, fn))


def _no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """链路两级缓存读取均未命中（最新 + 过期降级）。"""
    monkeypatch.setattr(chain, "cache_get", lambda *_args, **_kwargs: None)


def _stale_cache_only(monkeypatch: pytest.MonkeyPatch, stale: dict[str, Any]):
    """最新缓存未命中、过期降级命中（side_effect 顺序：最新 → 过期）。"""
    reads: list[float] = []

    def _fake_cache_get(_key: str, ttl: float, *_args: Any, **_kwargs: Any):
        reads.append(ttl)
        return None if len(reads) == 1 else stale

    spy = MagicMock(name="cache_set")
    monkeypatch.setattr(chain, "cache_get", _fake_cache_get)
    monkeypatch.setattr(chain, "cache_set", spy)
    return spy


# ============================================================
#  链注册
# ============================================================


class TestChainRegistration:
    """新链注册进 _DEFAULT_CHAINS 的结构约束。"""

    def test_chain_slots_match_provider_map_in_order(self):
        """槽位清单与 provider 映射键**同序同集**（漏槽/多槽/顺序错均不成立）。"""
        slots = chain._DEFAULT_CHAINS["fund_purchase"]
        assert slots
        assert list(fund_purchase._PURCHASE_PROVIDERS) == list(slots)

    def test_provider_entries_carry_label_and_callable(self):
        """每个槽位都有展示名与可调用 fetch 函数（降级诊断与链路遍历的前提）。"""
        for label, fn in fund_purchase._PURCHASE_PROVIDERS.values():
            assert label
            assert callable(fn)


# ============================================================
#  四级降级阶梯
# ============================================================


class TestDegradationLadder:
    """主链路 → 备链路 → 过期缓存 → 暂不可用，逐级断言。"""

    def test_level1_primary_success_stamped_and_cached(self, monkeypatch: pytest.MonkeyPatch):
        """主链路成功 → 盖链路展示名、写缓存；二次调用直接命中缓存不再经链。"""
        calls: list[str] = []

        def primary() -> dict[str, Any]:
            calls.append("tiantian")
            return _payload()

        def backup() -> dict[str, Any]:
            calls.append("akshare")
            return None

        _use_provider(monkeypatch, "tiantian", "天天基金", primary)
        _use_provider(monkeypatch, "akshare_purchase", "天天基金(akshare)", backup)

        result = fetch_fund_purchase_status()
        assert result is not None
        assert result["source"] == "天天基金"
        assert result[PURCHASE_SCHEMA_FIELD]
        assert calls == ["tiantian"]

        again = fetch_fund_purchase_status()
        assert again is not None
        assert again["fetched_at"] == result["fetched_at"]
        assert calls == ["tiantian"]  # 缓存命中，链路不再被触发

    def test_level2_backup_used_when_primary_returns_empty(self, monkeypatch: pytest.MonkeyPatch):
        """主链路取不到（代码级空）→ 备链路递补成功并盖自己的展示名。"""
        calls: list[str] = []

        def primary() -> None:
            calls.append("tiantian")
            return None

        def backup() -> dict[str, Any]:
            calls.append("akshare")
            return _payload()

        _use_provider(monkeypatch, "tiantian", "天天基金", primary)
        _use_provider(monkeypatch, "akshare_purchase", "天天基金(akshare)", backup)

        result = fetch_fund_purchase_status()
        assert result is not None
        assert result["source"] == "天天基金(akshare)"
        assert calls == ["tiantian", "akshare"]

    def test_level2_backup_used_when_primary_raises_transport_error(self, monkeypatch: pytest.MonkeyPatch):
        """主链路传输级异常 → 同源重试后落备链路（退避置零不白等）。"""
        monkeypatch.setattr(chain, "_TRANSIENT_RETRY_BACKOFF", 0.0)
        calls: list[str] = []

        def primary() -> dict[str, Any]:
            calls.append("tiantian")
            raise RuntimeError("connection timeout")

        def backup() -> dict[str, Any]:
            calls.append("akshare")
            return _payload()

        _use_provider(monkeypatch, "tiantian", "天天基金", primary)
        _use_provider(monkeypatch, "akshare_purchase", "天天基金(akshare)", backup)

        result = fetch_fund_purchase_status()
        assert result is not None
        assert result["source"] == "天天基金(akshare)"
        assert calls[0] == "tiantian"
        assert "akshare" in calls

    def test_level3_stale_cache_used_when_all_providers_fail(self, monkeypatch: pytest.MonkeyPatch):
        """全链失败 → 过期缓存兜底，载荷（含 fetched_at）原样透传且不回写。"""
        stale = _payload(fetched_at=_STALE_FETCHED_AT)
        spy = _stale_cache_only(monkeypatch, stale)
        _use_provider(monkeypatch, "tiantian", "天天基金", lambda: None)
        _use_provider(monkeypatch, "akshare_purchase", "天天基金(akshare)", lambda: None)

        result = fetch_fund_purchase_status()
        assert result is not None
        assert result["fetched_at"] == _STALE_FETCHED_AT  # 陈旧阶梯据此判定时效
        spy.assert_not_called()

    def test_level4_unavailable_when_no_cache_at_all(self, monkeypatch: pytest.MonkeyPatch):
        """全链失败且无任何缓存 → 返回 None（展示层静默隐列）。"""
        _no_cache(monkeypatch)
        _use_provider(monkeypatch, "tiantian", "天天基金", lambda: None)
        _use_provider(monkeypatch, "akshare_purchase", "天天基金(akshare)", lambda: None)

        assert fetch_fund_purchase_status() is None


# ============================================================
#  准入校验：失败不污染旧缓存
# ============================================================


class TestAdmissionProtectsCache:
    """写侧准入失败 → 不回写缓存（旧缓存不被垃圾载荷覆盖）。"""

    def test_invalid_primary_result_falls_through_to_stale_cache(self, monkeypatch: pytest.MonkeyPatch):
        """主链路给出不过准入的载荷 → 判失败走降级，旧缓存原样返回且不被回写。"""
        old = _payload(fetched_at=_STALE_FETCHED_AT)
        spy = _stale_cache_only(monkeypatch, old)
        _use_provider(monkeypatch, "tiantian", "天天基金", _invalid_payload)
        _use_provider(monkeypatch, "akshare_purchase", "天天基金(akshare)", lambda: None)

        result = fetch_fund_purchase_status()
        assert result is not None
        assert result["fetched_at"] == _STALE_FETCHED_AT
        spy.assert_not_called()

    def test_invalid_payload_never_enters_cache_without_fallback(self, monkeypatch: pytest.MonkeyPatch):
        """无任何缓存时，不过准入的载荷直接判不可用，绝不写缓存。"""
        _no_cache(monkeypatch)
        spy = MagicMock(name="cache_set")
        monkeypatch.setattr(chain, "cache_set", spy)
        _use_provider(monkeypatch, "tiantian", "天天基金", _invalid_payload)
        _use_provider(monkeypatch, "akshare_purchase", "天天基金(akshare)", lambda: None)

        assert fetch_fund_purchase_status() is None
        spy.assert_not_called()

    def test_cache_payload_admission_applied_on_read(self, monkeypatch: pytest.MonkeyPatch):
        """读侧同判据：最新缓存条目损坏 → 视为未命中、丢弃重取（进降级阶梯）。"""
        corrupted = _invalid_payload()
        reads: list[Any] = []

        def _fake_cache_get(_key: str, *_args: Any, **_kwargs: Any):
            reads.append(1)
            return corrupted if len(reads) == 1 else None

        spy = MagicMock(name="cache_set")
        monkeypatch.setattr(chain, "cache_get", _fake_cache_get)
        monkeypatch.setattr(chain, "cache_set", spy)
        _use_provider(monkeypatch, "tiantian", "天天基金", lambda: None)
        _use_provider(monkeypatch, "akshare_purchase", "天天基金(akshare)", lambda: None)

        assert fetch_fund_purchase_status() is None
        assert reads, "缓存读取应发生（准入判据挂在 cache_validate 上）"


# ============================================================
#  data_status 追踪
# ============================================================


class TestDataStatusTracking:
    """成功/失败均接入 data_status tracker（可用性矩阵的数据来源）。"""

    @pytest.fixture()
    def tracker(self, monkeypatch: pytest.MonkeyPatch):
        from src.python.report import data_status

        mock = MagicMock(name="tracker")
        monkeypatch.setattr(data_status, "get_tracker", lambda: mock)
        return mock

    def test_success_recorded(self, monkeypatch: pytest.MonkeyPatch, tracker):
        """主链路成功 → 记 T2 成功。"""
        _use_provider(monkeypatch, "tiantian", "天天基金", _payload)

        assert fetch_fund_purchase_status() is not None
        tracker.record.assert_called_once_with("fund_purchase", "T2", success=True)

    def test_failure_recorded_with_diagnostics(self, monkeypatch: pytest.MonkeyPatch, tracker):
        """全链失败无缓存 → 记 T2 失败，message 承载诊断摘要。"""
        _no_cache(monkeypatch)
        _use_provider(monkeypatch, "tiantian", "天天基金", lambda: None)
        _use_provider(monkeypatch, "akshare_purchase", "天天基金(akshare)", lambda: None)

        assert fetch_fund_purchase_status() is None
        tracker.record.assert_called_once()
        args, kwargs = tracker.record.call_args
        assert args[:2] == ("fund_purchase", "T2")
        assert kwargs.get("success") is False
        assert kwargs.get("failure_type") == "unreachable"


# ============================================================
#  会话缓存
# ============================================================


class TestSessionReuse:
    """fetch_fund_purchase_status_cached — 同一次报告生成内单次经链。"""

    def test_second_call_served_from_session_cache(self, monkeypatch: pytest.MonkeyPatch):
        """会话命中直接返回，链路不再被触发。"""
        calls: list[str] = []

        def primary() -> dict[str, Any]:
            calls.append("tiantian")
            return _payload()

        _use_provider(monkeypatch, "tiantian", "天天基金", primary)
        _use_provider(monkeypatch, "akshare_purchase", "天天基金(akshare)", lambda: None)

        first = fetch_fund_purchase_status_cached()
        second = fetch_fund_purchase_status_cached()
        assert first is not None
        assert second is first  # 同一会话对象复用（无二次序列化）
        assert len(calls) == 1

    def test_none_result_cached_in_session(self, monkeypatch: pytest.MonkeyPatch):
        """全链失败的 None 亦入会话缓存，同会话内不再反复重试。"""
        calls: list[str] = []

        def primary() -> None:
            calls.append("tiantian")
            return None

        _no_cache(monkeypatch)
        _use_provider(monkeypatch, "tiantian", "天天基金", primary)
        _use_provider(monkeypatch, "akshare_purchase", "天天基金(akshare)", lambda: None)

        assert fetch_fund_purchase_status_cached() is None
        assert fetch_fund_purchase_status_cached() is None
        assert len(calls) == 1
