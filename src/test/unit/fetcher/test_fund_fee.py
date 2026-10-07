"""fetcher/fund_fee.py 单元测试 — 双链路接线、准入、会话复用与费率索引装配。

测试目标（whatif-cost-benchmark-design §11 迭代 2）：
  - 链注册：_DEFAULT_CHAINS 槽位与 provider 映射同构（同序同集）
  - 降级阶梯：主链路成功 → 备链路递补 → 过期缓存 → 暂不可用
  - 载荷准入：写侧失败不污染缓存；读侧 fee_schema 语义版本不符按未命中丢弃
  - 会话缓存：同一次报告生成内每代码单次经链（None 亦缓存）
  - 费率索引装配 fetch_fee_index：逐侧来源优先级（f10_tier → table_single →
    config）、未知代码不入索引、单代码失败不中断批

运行：
  pytest src/test/unit/fetcher/test_fund_fee.py -v
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.python.fetcher import chain, fund_fee
from src.python.fetcher.fund_fee import (
    fetch_fund_fee,
    fetch_fund_fee_cached,
    fetch_fee_index,
)
from src.python.providers.tiantian_fund_fee import (
    FEE_SCHEMA_FIELD,
    stamp_fee_payload,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]

_STALE_FETCHED_AT = "2026-09-25T09:00:00+08:00"


def _payload(fetched_at: str | None = None) -> dict[str, Any]:
    """可通过准入的合法载荷（可指定 fetched_at 以断言陈旧载荷原样透传）。"""
    payload = stamp_fee_payload(
        [
            ["小于7天", "1.50%"],
            ["大于等于7天，小于30天", "0.75%"],
            ["大于等于30天，小于730天", "0.50%"],
            ["大于等于730天", "0.00%"],
        ],
        [["小于100万元", "1.50% | 0.15%"], ["大于等于100万元", "0.90% | 0.09%"]],
    )
    if fetched_at is not None:
        payload["fetched_at"] = fetched_at
    return payload


def _redemption_only_payload() -> dict[str, Any]:
    """无申购表的载荷（C 类/无优惠档形态）——赎回已知、申购待单档/配置兜底。"""
    payload = stamp_fee_payload(
        [["小于7天", "1.50%"], ["大于等于7天，小于730天", "0.75%"], ["大于等于730天", "0.00%"]], []
    )
    return payload


def _invalid_payload() -> dict[str, Any]:
    """赎回阶梯缺失的载荷（不过准入——模拟场内页/解析漂移）。"""
    return stamp_fee_payload([], [])


def _use_provider(monkeypatch: pytest.MonkeyPatch, name: str, label: str, fn) -> None:
    """把指定槽位换成受控 fake（其余槽位保持真实）。"""
    monkeypatch.setitem(fund_fee._FEE_PROVIDERS, name, (label, fn))


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
    """fund_fee 链注册进 _DEFAULT_CHAINS 的结构约束。"""

    def test_chain_slots_match_provider_map_in_order(self):
        """槽位清单与 provider 映射键**同序同集**（漏槽/多槽/顺序错均不成立）。"""
        slots = chain._DEFAULT_CHAINS["fund_fee"]
        assert slots
        assert list(fund_fee._FEE_PROVIDERS) == list(slots)

    def test_provider_entries_carry_label_and_callable(self):
        """每个槽位都有展示名与可调用 fetch 函数（降级诊断与链路遍历的前提）。"""
        for label, fn in fund_fee._FEE_PROVIDERS.values():
            assert label
            assert callable(fn)


# ============================================================
#  降级阶梯
# ============================================================


class TestDegradationLadder:
    """主链路 → 备链路 → 过期缓存 → 暂不可用，逐级断言。"""

    def test_level1_primary_success_stamped_and_cached(self, monkeypatch: pytest.MonkeyPatch):
        """主链路成功 → 盖链路展示名、写缓存；二次调用直接命中缓存不再经链。"""
        calls: list[str] = []

        def primary(code: str = "") -> dict[str, Any]:
            calls.append("tiantian_f10")
            return _payload()

        def backup(code: str = "") -> dict[str, Any]:
            calls.append("akshare")
            return None

        _use_provider(monkeypatch, "tiantian_f10", "天天基金F10", primary)
        _use_provider(monkeypatch, "akshare_fee", "天天基金F10(akshare)", backup)

        result = fetch_fund_fee("002943")
        assert result is not None
        assert result["source"] == "天天基金F10"
        assert result[FEE_SCHEMA_FIELD]
        assert calls == ["tiantian_f10"]

        again = fetch_fund_fee("002943")
        assert again is not None
        assert again["fetched_at"] == result["fetched_at"]
        assert calls == ["tiantian_f10"]  # 缓存命中，链路不再被触发

    def test_level2_backup_used_when_primary_returns_empty(self, monkeypatch: pytest.MonkeyPatch):
        """主链路取不到（页面无赎回表/解析失败）→ 备链路递补成功并盖自己的展示名。"""
        calls: list[str] = []

        def primary(code: str = "") -> None:
            calls.append("tiantian_f10")
            return None

        def backup(code: str = "") -> dict[str, Any]:
            calls.append("akshare")
            return _payload()

        _use_provider(monkeypatch, "tiantian_f10", "天天基金F10", primary)
        _use_provider(monkeypatch, "akshare_fee", "天天基金F10(akshare)", backup)

        result = fetch_fund_fee("002943")
        assert result is not None
        assert result["source"] == "天天基金F10(akshare)"
        assert calls == ["tiantian_f10", "akshare"]

    def test_level3_stale_cache_used_when_all_providers_fail(self, monkeypatch: pytest.MonkeyPatch):
        """全链失败 → 过期缓存兜底，载荷（含 fetched_at）原样透传且不回写。"""
        stale = _payload(fetched_at=_STALE_FETCHED_AT)
        spy = _stale_cache_only(monkeypatch, stale)
        _use_provider(monkeypatch, "tiantian_f10", "天天基金F10", lambda **_: None)
        _use_provider(monkeypatch, "akshare_fee", "天天基金F10(akshare)", lambda **_: None)

        result = fetch_fund_fee("002943")
        assert result is not None
        assert result["fetched_at"] == _STALE_FETCHED_AT  # 陈旧阶梯据此判定时效
        spy.assert_not_called()

    def test_level4_unavailable_when_no_cache_at_all(self, monkeypatch: pytest.MonkeyPatch):
        """全链失败且无任何缓存 → 返回 None（消费侧按费率未知标注）。"""
        _no_cache(monkeypatch)
        _use_provider(monkeypatch, "tiantian_f10", "天天基金F10", lambda **_: None)
        _use_provider(monkeypatch, "akshare_fee", "天天基金F10(akshare)", lambda **_: None)

        assert fetch_fund_fee("002943") is None


# ============================================================
#  准入校验：失败不污染旧缓存
# ============================================================


class TestAdmissionProtectsCache:
    """写侧准入失败 → 不回写缓存；读侧 fee_schema 不符 → 按未命中丢弃。"""

    def test_invalid_primary_result_never_cached(self, monkeypatch: pytest.MonkeyPatch):
        """无任何缓存时，不过准入的载荷直接判不可用，绝不写缓存。"""
        _no_cache(monkeypatch)
        spy = MagicMock(name="cache_set")
        monkeypatch.setattr(chain, "cache_set", spy)
        _use_provider(monkeypatch, "tiantian_f10", "天天基金F10", lambda **_: _invalid_payload())
        _use_provider(monkeypatch, "akshare_fee", "天天基金F10(akshare)", lambda **_: None)

        assert fetch_fund_fee("561910") is None
        spy.assert_not_called()

    def test_invalid_primary_falls_through_to_stale_cache(self, monkeypatch: pytest.MonkeyPatch):
        """主链路给出不过准入的载荷 → 走降级，旧缓存原样返回且不被回写。"""
        old = _payload(fetched_at=_STALE_FETCHED_AT)
        spy = _stale_cache_only(monkeypatch, old)
        _use_provider(monkeypatch, "tiantian_f10", "天天基金F10", lambda **_: _invalid_payload())
        _use_provider(monkeypatch, "akshare_fee", "天天基金F10(akshare)", lambda **_: None)

        result = fetch_fund_fee("002943")
        assert result is not None
        assert result["fetched_at"] == _STALE_FETCHED_AT
        spy.assert_not_called()

    def test_stale_schema_version_discarded_on_read(self, monkeypatch: pytest.MonkeyPatch):
        """读侧同判据：fee_schema 版本过期的缓存条目 → 丢弃重取（进降级阶梯）。"""
        old_schema = {**_payload(), FEE_SCHEMA_FIELD: 999}
        reads: list[int] = []

        def _fake_cache_get(_key: str, *_args: Any, **_kwargs: Any):
            reads.append(1)
            return old_schema if len(reads) == 1 else None

        spy = MagicMock(name="cache_set")
        monkeypatch.setattr(chain, "cache_get", _fake_cache_get)
        monkeypatch.setattr(chain, "cache_set", spy)
        _use_provider(monkeypatch, "tiantian_f10", "天天基金F10", lambda **_: None)
        _use_provider(monkeypatch, "akshare_fee", "天天基金F10(akshare)", lambda **_: None)

        assert fetch_fund_fee("002943") is None
        assert reads, "缓存读取应发生（语义版本判据挂在 cache_validate 上）"


# ============================================================
#  会话缓存
# ============================================================


class TestSessionReuse:
    """fetch_fund_fee_cached — 同一次报告生成内每代码单次经链。"""

    def test_second_call_served_from_session_cache(self, monkeypatch: pytest.MonkeyPatch):
        """会话命中直接返回，链路不再被触发（None 亦缓存）。"""
        calls: list[str] = []

        def primary(code: str = "") -> dict[str, Any]:
            calls.append("tiantian_f10")
            return _payload()

        _use_provider(monkeypatch, "tiantian_f10", "天天基金F10", primary)
        _use_provider(monkeypatch, "akshare_fee", "天天基金F10(akshare)", lambda **_: None)

        first = fetch_fund_fee_cached("002943")
        second = fetch_fund_fee_cached("002943")
        assert first is not None
        assert second is first  # 同一会话对象复用（无二次序列化）
        assert len(calls) == 1

    def test_none_result_cached_in_session(self, monkeypatch: pytest.MonkeyPatch):
        """全链失败的 None 亦入会话缓存，同会话内不再反复重试。"""
        calls: list[str] = []

        def primary(code: str = "") -> None:
            calls.append("tiantian_f10")
            return None

        _no_cache(monkeypatch)
        _use_provider(monkeypatch, "tiantian_f10", "天天基金F10", primary)
        _use_provider(monkeypatch, "akshare_fee", "天天基金F10(akshare)", lambda **_: None)

        assert fetch_fund_fee_cached("002943") is None
        assert fetch_fund_fee_cached("002943") is None
        assert len(calls) == 1


# ============================================================
#  费率索引装配：fetch_fee_index
# ============================================================


def _config(entries: dict[str, Any]) -> dict[str, Any]:
    return {"fund_fee_fallback": entries}


class TestFeeIndexAssembly:
    """逐侧来源优先级与未知降级（消费侧 = whatif 交易成本面板）。"""

    @pytest.fixture(autouse=True)
    def _purchase_table_unavailable(self, monkeypatch: pytest.MonkeyPatch):
        """全量申购状态表默认打桩为不可得（懒加载点；具体用例可再覆写）。"""
        monkeypatch.setattr(
            "src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached",
            lambda: None,
        )

    def test_both_schedules_from_f10(self, monkeypatch: pytest.MonkeyPatch):
        """F10 双侧可得 → 均标 f10_tier；全量申购状态表**不被触发**（惰性）。"""
        table_spy = MagicMock(name="fetch_fund_purchase_status_cached", return_value=None)
        monkeypatch.setattr("src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached", table_spy)
        monkeypatch.setattr(fund_fee, "fetch_fund_fee_cached", lambda code: _payload())

        index = fetch_fee_index(["002943"])
        entry = index["002943"]
        assert entry["purchase"]["source"] == "f10_tier"
        assert entry["redemption"]["source"] == "f10_tier"
        table_spy.assert_not_called()

    def test_purchase_falls_back_to_table_single(self, monkeypatch: pytest.MonkeyPatch):
        """F10 无申购表 → 全量表 col12 单档（table_single）；赎回仍 f10_tier。"""
        monkeypatch.setattr(fund_fee, "fetch_fund_fee_cached", lambda code: _redemption_only_payload())
        monkeypatch.setattr(
            "src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached",
            lambda: {"rows": {"002943": {"purchase_fee_rate": 0.0015}}},
        )

        index = fetch_fee_index(["002943"])
        entry = index["002943"]
        assert entry["purchase"]["source"] == "table_single"
        assert entry["purchase"]["tiers"][0]["rate"] == 0.0015
        assert entry["redemption"]["source"] == "f10_tier"

    def test_table_single_not_used_when_f10_purchase_known(self, monkeypatch: pytest.MonkeyPatch):
        """F10 申购档已知 → 全量表不触发（优先级 F10 > 单档）。"""
        table_spy = MagicMock(name="fetch_fund_purchase_status_cached", return_value=None)
        monkeypatch.setattr("src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached", table_spy)
        monkeypatch.setattr(fund_fee, "fetch_fund_fee_cached", lambda code: _payload())

        fetch_fee_index(["002943"])
        table_spy.assert_not_called()

    def test_config_fallback_fills_both_sides(self, monkeypatch: pytest.MonkeyPatch):
        """在线来源全无 → 配置兜底两侧生效（source=config）。"""
        monkeypatch.setattr(fund_fee, "fetch_fund_fee_cached", lambda code: None)
        monkeypatch.setattr("src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached", lambda **_: None)
        monkeypatch.setattr(
            fund_fee,
            "get_config",
            lambda: _config(
                {
                    "002943": {
                        "purchase_rate": 0.0015,
                        "redemption_tiers": [
                            {"max_days": 7, "rate": 0.015},
                            {"max_days": None, "rate": 0.0},
                        ],
                    }
                }
            ),
        )

        index = fetch_fee_index(["002943"])
        entry = index["002943"]
        assert entry["purchase"]["source"] == "config"
        assert entry["redemption"]["source"] == "config"
        assert entry["redemption"]["tiers"][0]["max_days"] == 7

    def test_config_fallback_fills_only_missing_side(self, monkeypatch: pytest.MonkeyPatch):
        """赎回已知（F10）→ 配置只补申购侧，不覆盖在线已知侧。"""
        monkeypatch.setattr(fund_fee, "fetch_fund_fee_cached", lambda code: _redemption_only_payload())
        monkeypatch.setattr("src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached", lambda **_: None)
        monkeypatch.setattr(
            fund_fee,
            "get_config",
            lambda: _config({"002943": {"purchase_rate": 0.0015}}),
        )

        index = fetch_fee_index(["002943"])
        entry = index["002943"]
        assert entry["purchase"]["source"] == "config"
        assert entry["redemption"]["source"] == "f10_tier"  # 在线侧不被配置覆盖

    def test_unknown_code_omitted_from_index(self, monkeypatch: pytest.MonkeyPatch):
        """两侧全未知（无 F10、无单档、无配置）→ 不入索引（消费侧按未知腿标注）。"""
        monkeypatch.setattr(fund_fee, "fetch_fund_fee_cached", lambda code: None)
        monkeypatch.setattr("src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached", lambda **_: None)
        monkeypatch.setattr(fund_fee, "get_config", lambda: _config({}))

        assert fetch_fee_index(["999999"]) == {}

    def test_invalid_config_entry_ignored(self, monkeypatch: pytest.MonkeyPatch):
        """非法配置条目（阶梯无末档开区间/费率越界）→ 忽略，未知语义不被污染。"""
        monkeypatch.setattr(fund_fee, "fetch_fund_fee_cached", lambda code: None)
        monkeypatch.setattr("src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached", lambda **_: None)
        monkeypatch.setattr(
            fund_fee,
            "get_config",
            lambda: _config({"002943": {"redemption_tiers": [{"max_days": 7, "rate": 5.0}]}}),
        )

        assert fetch_fee_index(["002943"]) == {}

    def test_one_code_failure_does_not_break_batch(self, monkeypatch: pytest.MonkeyPatch):
        """单代码取数抛异常 → 该代码按未知，其余代码照常入索引。"""
        monkeypatch.setattr(
            fund_fee,
            "fetch_fund_fee_cached",
            lambda code: (_ for _ in ()).throw(RuntimeError("boom")) if code == "999991" else _payload(),
        )
        monkeypatch.setattr(fund_fee, "get_config", lambda: _config({}))

        index = fetch_fee_index(["999991", "002943"])
        assert "999991" not in index
        assert "002943" in index

    def test_empty_and_blank_codes_skipped(self, monkeypatch: pytest.MonkeyPatch):
        """空清单 → 空索引；空白代码被跳过（不产生空键请求）。"""
        fee_spy = MagicMock(name="fetch_fund_fee_cached", return_value=_payload())
        monkeypatch.setattr(fund_fee, "fetch_fund_fee_cached", fee_spy)

        assert fetch_fee_index([]) == {}
        assert fetch_fee_index(["", "   "]) == {}
        fee_spy.assert_not_called()
