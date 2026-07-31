"""持仓追踪器测试。

测试策略：
  - compute_holdings_fingerprint() 验证 MD5 指纹确定性 + 变更敏感性
  - compute_holdings_codes() 验证代码提取
  - check_and_refresh_caches() mock 缓存文件路径，验证指纹匹配/变更/新增代码
"""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


# ── 辅助 mock 持有类 ─────────────────────────────────────────


class _MockHolding:
    """模拟持仓记录的最小结构。"""

    def __init__(self, code: str, account: str = "主账户", shares: float = 100, cost_price: float = 10.0):
        self.code = code
        self.account = account
        self.shares = shares
        self.cost_price = cost_price


# ── compute_holdings_fingerprint 测试 ─────────────────────────


class TestComputeHoldingsFingerprint:
    """持仓指纹计算测试。"""

    def test_same_holdings_same_fingerprint(self):
        """相同持仓 → 相同指纹。"""
        from src.python.cache.services.holdings_tracker import compute_holdings_fingerprint

        h1 = [_MockHolding("600519"), _MockHolding("000001")]
        h2 = [_MockHolding("600519"), _MockHolding("000001")]
        fp1 = compute_holdings_fingerprint(h1)
        fp2 = compute_holdings_fingerprint(h2)
        assert fp1 == fp2
        assert isinstance(fp1, str)
        assert len(fp1) == 32  # MD5

    def test_order_independent(self):
        """不同顺序 → 相同指纹（内部排序）。"""
        from src.python.cache.services.holdings_tracker import compute_holdings_fingerprint

        h1 = [_MockHolding("600519"), _MockHolding("000001")]
        h2 = [_MockHolding("000001"), _MockHolding("600519")]
        assert compute_holdings_fingerprint(h1) == compute_holdings_fingerprint(h2)

    def test_different_code_different_fingerprint(self):
        """不同代码 → 不同指纹。"""
        from src.python.cache.services.holdings_tracker import compute_holdings_fingerprint

        h1 = [_MockHolding("600519")]
        h2 = [_MockHolding("600001")]
        assert compute_holdings_fingerprint(h1) != compute_holdings_fingerprint(h2)

    def test_different_shares_different_fingerprint(self):
        """不同份额 → 不同指纹。"""
        from src.python.cache.services.holdings_tracker import compute_holdings_fingerprint

        h1 = [_MockHolding("600519", shares=100)]
        h2 = [_MockHolding("600519", shares=200)]
        assert compute_holdings_fingerprint(h1) != compute_holdings_fingerprint(h2)

    def test_different_account_different_fingerprint(self):
        """不同账户 → 不同指纹。"""
        from src.python.cache.services.holdings_tracker import compute_holdings_fingerprint

        h1 = [_MockHolding("600519", account="主账户")]
        h2 = [_MockHolding("600519", account="信用账户")]
        assert compute_holdings_fingerprint(h1) != compute_holdings_fingerprint(h2)

    def test_different_cost_different_fingerprint(self):
        """不同成本 → 不同指纹。"""
        from src.python.cache.services.holdings_tracker import compute_holdings_fingerprint

        h1 = [_MockHolding("600519", cost_price=10.0)]
        h2 = [_MockHolding("600519", cost_price=20.0)]
        assert compute_holdings_fingerprint(h1) != compute_holdings_fingerprint(h2)

    def test_empty_holdings(self):
        """空持仓 → 确定性指纹。"""
        from src.python.cache.services.holdings_tracker import compute_holdings_fingerprint

        fp = compute_holdings_fingerprint([])
        assert isinstance(fp, str)
        assert len(fp) == 32


# ── compute_holdings_codes 测试 ────────────────────────────────


class TestComputeHoldingsCodes:
    """持仓代码提取测试。"""

    def test_basic_extraction(self):
        """基本代码提取。"""
        from src.python.cache.services.holdings_tracker import compute_holdings_codes

        holdings = [_MockHolding("600519"), _MockHolding("000001"), _MockHolding("00700")]
        codes = compute_holdings_codes(holdings)
        assert codes == {"600519", "000001", "00700"}

    def test_duplicate_codes(self):
        """重复代码 → 去重。"""
        from src.python.cache.services.holdings_tracker import compute_holdings_codes

        holdings = [_MockHolding("600519"), _MockHolding("600519")]
        codes = compute_holdings_codes(holdings)
        assert codes == {"600519"}

    def test_empty(self):
        """空列表 → 空集合。"""
        from src.python.cache.services.holdings_tracker import compute_holdings_codes

        assert compute_holdings_codes([]) == set()


# ── check_and_refresh_caches 测试 ─────────────────────────────


class TestCheckAndRefreshCaches:
    """持仓变更检测与缓存刷新测试。"""

    def test_first_run_no_prev_data(self, monkeypatch):
        """首次运行（无历史跟踪数据）→ 应清除关联缓存并存储跟踪数据。"""
        from src.python.cache.services.holdings_tracker import check_and_refresh_caches

        monkeypatch.setattr("src.python.cache.services.holdings_tracker._read_holdings_tracking", lambda k: None)
        cleared: list[str] = []

        def _mock_clear_related() -> list[str]:
            cleared.append("cleared")
            return ["fund_benchmarks"]

        monkeypatch.setattr("src.python.cache.services.holdings_tracker._clear_holdings_related_caches", _mock_clear_related)
        monkeypatch.setattr("src.python.cache.services.holdings_tracker.set", lambda k, v: None)

        holdings = [_MockHolding("600519"), _MockHolding("000001")]
        new_codes = check_and_refresh_caches(holdings)
        assert len(cleared) == 1  # 清除操作被调用

    def test_fingerprint_match_returns_empty(self, monkeypatch):
        """指纹相同 → 返回空列表，不刷新缓存。"""
        from src.python.cache.services.holdings_tracker import check_and_refresh_caches

        monkeypatch.setattr(
            "src.python.cache.services.holdings_tracker._read_holdings_tracking",
            lambda k: {"fingerprint": "same_fp", "codes": ["600519", "000001"]},
        )
        cleared: list[str] = []
        monkeypatch.setattr("src.python.cache.services.holdings_tracker._clear_holdings_related_caches", lambda: cleared)
        monkeypatch.setattr("src.python.cache.services.holdings_tracker.set", lambda k, v: None)

        holdings = [_MockHolding("600519"), _MockHolding("000001")]
        result = check_and_refresh_caches(holdings)
        assert result == []
        assert len(cleared) == 0  # 未调用清除

    def test_fingerprint_mismatch_new_codes(self, monkeypatch):
        """指纹不同且出现新代码 → 返回新代码列表。"""
        from src.python.cache.services.holdings_tracker import (
            check_and_refresh_caches,
            compute_holdings_fingerprint,
        )

        prev_fp = compute_holdings_fingerprint([_MockHolding("600519")])
        monkeypatch.setattr(
            "src.python.cache.services.holdings_tracker._read_holdings_tracking",
            lambda k: {"fingerprint": prev_fp, "codes": ["600519"]},
        )
        cleared: list[str] = []
        monkeypatch.setattr("src.python.cache.services.holdings_tracker._clear_holdings_related_caches", lambda: cleared)
        stored_data: dict = {}
        monkeypatch.setattr("src.python.cache.services.holdings_tracker.set", lambda k, v: stored_data.update(v))

        holdings = [_MockHolding("600519"), _MockHolding("000001")]
        result = check_and_refresh_caches(holdings)
        assert "000001" in result
        assert "600519" not in result  # 原有代码不算新增
        assert "600519" in stored_data.get("codes", [])

    def test_fingerprint_mismatch_no_new_codes(self, monkeypatch):
        """指纹不同但代码集合不变（仅份额/成本变动）→ 返回空列表。"""
        from src.python.cache.services.holdings_tracker import (
            check_and_refresh_caches,
            compute_holdings_fingerprint,
        )

        prev_fp = compute_holdings_fingerprint([_MockHolding("600519", shares=100)])
        monkeypatch.setattr(
            "src.python.cache.services.holdings_tracker._read_holdings_tracking",
            lambda k: {"fingerprint": prev_fp, "codes": ["600519"]},
        )

        stored_data: dict = {}
        monkeypatch.setattr("src.python.cache.services.holdings_tracker._clear_holdings_related_caches", lambda: [])
        monkeypatch.setattr("src.python.cache.services.holdings_tracker.set", lambda k, v: stored_data.update(v))

        holdings = [_MockHolding("600519", shares=200)]  # 仅份额变
        result = check_and_refresh_caches(holdings)
        assert result == []  # 无新增代码
