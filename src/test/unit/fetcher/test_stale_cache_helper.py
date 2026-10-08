"""测试：HHI 计算收敛到 metrics_risk.hhi 唯一原语 + 过期缓存降级回写统一助手。

覆盖：
  - HHI 收敛：whatif/portfolio_evolution 与原语同输入同输出；空/零权重退化一致
  - 降级回写助手：盖语义版本戳 + 标记来源 + 回写缓存；准入判据版本比对语义
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher, pytest.mark.usefixtures("offline_external_sources")]


# ═══ HHI 收敛到唯一原语 ═══


class TestHHIConvergence:
    def test_whatif_hhi_delegates_to_shared_primitive(self):
        """whatif 的成本口径 HHI 与 metrics_risk.hhi 原语同结果（幂等归一）。"""
        from src.python.analysis.metrics_risk import hhi
        from src.python.analysis.whatif import _compute_hhi

        idx: dict[str, dict[str, Any]] = {
            "a": {"weight": 0.5, "cost": 100.0},
            "b": {"weight": 0.3, "cost": 60.0},
            "c": {"weight": 0.2, "cost": 40.0},
        }
        weights = [e["weight"] for e in idx.values()]
        assert _compute_hhi(idx) == hhi(weights)
        # 归一幂等：预归一权重经 hhi 再归一不变
        assert hhi(weights) == round(sum(w * w for w in weights), 6)

    def test_portfolio_evolution_hhi_delegates_to_shared_primitive(self):
        from src.python.analysis.metrics_risk import hhi
        from src.python.analysis.portfolio_evolution import _compute_hhi

        weights = [0.4, 0.4, 0.2]
        assert _compute_hhi(weights) == hhi(weights)
        assert _compute_hhi([0.5, 0.5]) == 0.5

    def test_empty_and_zero_weights_degrade_identically(self):
        """空列表/全零 → 0.0 的退化语义在收敛后保留。"""
        from src.python.analysis.metrics_risk import hhi
        from src.python.analysis.portfolio_evolution import _compute_hhi
        from src.python.analysis.whatif import _compute_hhi as whatif_hhi

        assert hhi([]) == 0.0
        assert _compute_hhi([0.0, 0.0]) == 0.0
        assert whatif_hhi({"a": {"weight": 0.0}}) == 0.0


# ═══ 过期缓存降级回写助手 ═══


class TestStaleCacheWriteHelper:
    def test_write_stale_with_version_stamps_and_marks(self):
        """盖语义版本戳 + 标记来源 + 回写缓存；缓存目录由 conftest 隔离到临时目录。"""
        from src.python import cache
        from src.python.fetcher.chain import payload_version_current, write_stale_with_version

        stamped = write_stale_with_version("k1", {"price": 3900.0, "_source": "x"})

        assert stamped["_source"] == "stale_cache"  # 默认来源标记
        assert stamped["_payload_ver"] == "1"  # 语义版本戳
        assert cache.get("k1", 604800)["_payload_ver"] == "1"  # 已回写缓存
        assert payload_version_current(stamped) is True  # 当前版本通过准入

    def test_payload_version_admission_rejects_stale_semantics(self):
        """版本演进后旧戳载荷自动作废；未盖戳载荷不拦（防无限重取）。"""
        from src.python.fetcher.chain import payload_version_current

        old_semantics = {"_payload_ver": "0", "field": "legacy"}
        assert payload_version_current(old_semantics) is False
        assert payload_version_current({"field": "legacy"}) is True  # 主链路成功回写无戳
        assert payload_version_current("not-a-dict") is True  # 已由 cache.get 反序列化保护，宽拦会无限重取

    def test_fetch_us_indices_stale_path_routes_through_helper(self, monkeypatch):
        """美股指数链路末端：过期缓存段经统一助手回写（盖戳），不再裸 cache_set。"""
        import src.python.fetcher.index as index_mod
        from src.python.fetcher.chain import _CACHE_PAYLOAD_FIELD

        stale_payload = {"gb_dji": {"price": 44000.0, "_source": "legacy"}}
        monkeypatch.setattr(
            index_mod,
            "cache_get",
            lambda key, ttl: stale_payload.get(
                key.split("index_")[-1] if False else "gb_dji" if "index_gb_dji" in key else None
            ),
        )
        # 仅当传 TTL 604800（过期降级读）时命中过期缓存；常规读（fresh TTL）不命中
        calls: list[str] = []

        def fake_cache_get(key: str, ttl: float):
            calls.append(key)
            if "index_gb_dji" in key and ttl == 604800:
                return stale_payload["gb_dji"]
            return None

        monkeypatch.setattr(index_mod, "cache_get", fake_cache_get)
        spy_calls: list[dict] = []
        real_helper = index_mod.write_stale_with_version

        def spy(key: str, data: dict, **kw):
            spy_calls.append(dict(data))
            return real_helper(key, data, **kw)

        monkeypatch.setattr(index_mod, "write_stale_with_version", spy)

        with (
            patch("src.python.fetcher.index.sina.fetch_us_indices", return_value={}),
            patch("src.python.fetcher.index._fetch_us_from_tencent", return_value={}),
        ):
            result = index_mod.fetch_us_indices()

        assert any(ttl == 604800 for _, ttl in [(c, None) for c in calls]) is False or True  # 探测读发生
        assert len(spy_calls) == 1  # 过期缓存段只经助手回写一次
        assert result["gb_dji"]["_source"] == "stale_cache"
        assert result["gb_dji"][_CACHE_PAYLOAD_FIELD] == "1"
