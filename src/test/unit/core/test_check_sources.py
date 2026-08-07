"""数据源健康检查（check_sources.run_health_checks）整体预算回归测试。

覆盖：max_timeout 预算生效、未完成项标记超时、正常完成、异常不崩溃、边界去重。

回归背景：max_timeout 曾是死参数——Web /api/health 传 8s 预算未生效，
最慢检查项（硬编码最高 30s）拖垮整接口，总耗时超过前端 15s abort，
浏览器报「健康检测失败，请稍后重试」。当前实现以 max_timeout 为整体
耗时上限，超预算即返回部分结果并把未完成项标记"超时"。
"""

from __future__ import annotations

import time
from unittest import mock

import pytest

import src.python.core.check_sources as cs

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestRunHealthChecksBudget:
    """run_health_checks 整体预算（max_timeout）回归测试。"""

    def test_budget_cuts_hung_check(self):
        """预算内未完成的检查项标记超时，且整体在预算附近返回。"""
        checks = [
            ("快源A", "测试", lambda: (cs._OK, 5.0, "5ms 正常")),
            ("快源B", "测试", lambda: (cs._OK, 8.0, "8ms 正常")),
            ("慢源C", "测试", lambda: (time.sleep(30), (cs._OK, 1.0, "1ms 正常"))[1]),
        ]
        with mock.patch.object(cs, "_checks", checks):
            t0 = time.perf_counter()
            results = cs.run_health_checks(max_timeout=1.0)
            elapsed = time.perf_counter() - t0

        by_name = {r["name"]: r for r in results}
        # 整体远小于慢源 30s —— 预算必须生效
        assert elapsed < 3.0
        # 快源结果保留
        assert by_name["快源A"]["ok"] is True
        assert by_name["快源B"]["ok"] is True
        # 慢源被预算切断并标记超时
        assert by_name["慢源C"]["ok"] is False
        assert by_name["慢源C"]["latency_ms"] == 0.0
        assert by_name["慢源C"]["message"].startswith("超时")

    def test_all_fast_within_budget_no_timeout(self):
        """全部检查项在预算内完成时，无超时标记。"""
        checks = [
            ("快源A", "测试", lambda: (cs._OK, 5.0, "5ms 正常")),
            ("快源B", "测试", lambda: (cs._OK, 8.0, "8ms 正常")),
        ]
        with mock.patch.object(cs, "_checks", checks):
            results = cs.run_health_checks(max_timeout=5.0)
        assert len(results) == 2
        assert all(r["ok"] for r in results)
        assert not any(r["message"].startswith("超时") for r in results)

    def test_check_exception_marked_not_ok(self):
        """检查函数抛异常时标记 ok=False 并带错误信息（不崩溃）。"""
        checks = [("异常源", "测试", lambda: (_ for _ in ()).throw(RuntimeError("boom")))]
        with mock.patch.object(cs, "_checks", checks):
            results = cs.run_health_checks(max_timeout=5.0)
        assert results[0]["name"] == "异常源"
        assert results[0]["ok"] is False
        assert "boom" in results[0]["message"]

    def test_boundary_no_duplicate_and_result_wins(self):
        """正常完成下同 name 不重复，真实结果保留。"""
        checks = [("快源A", "测试", lambda: (cs._OK, 5.0, "5ms 正常"))]
        with mock.patch.object(cs, "_checks", checks):
            results = cs.run_health_checks(max_timeout=5.0)
        names = [r["name"] for r in results]
        assert names.count("快源A") == 1
        assert results[0]["ok"] is True


class TestProxyHint:
    """全部数据源被拒时追加代理诊断提示（回归：另一台电脑 WinError 10061 全灭）。"""

    def _check(self, symbol: str, msg: str):
        return lambda: (symbol, 5.0, msg)

    def test_all_refused_appends_hint(self):
        """全部失败且多数为连接被拒（WinError 10061 / Errno 111）→ 追加 hint 项。"""
        checks = [
            ("源A", "行情", self._check(cs._ERR, "[WinError 10061] 由于目标计算机积极拒绝，无法连接。")),
            ("源B", "新闻", self._check(cs._ERR, "[Errno 111] Connection refused")),
        ]
        with mock.patch.object(cs, "_checks", checks):
            results = cs.run_health_checks(max_timeout=5.0)
        hints = [r for r in results if r.get("hint")]
        assert len(hints) == 1
        assert "10061" in hints[0]["message"] or "代理" in hints[0]["message"]
        assert hints[0]["ok"] is False

    def test_no_hint_when_some_ok(self):
        """只要有源正常 → 不追加 hint（避免误报）。"""
        checks = [
            ("源A", "行情", self._check(cs._OK, "5ms 正常")),
            ("源B", "新闻", self._check(cs._ERR, "[WinError 10061] 拒绝")),
        ]
        with mock.patch.object(cs, "_checks", checks):
            results = cs.run_health_checks(max_timeout=5.0)
        assert not any(r.get("hint") for r in results)

    def test_no_hint_on_timeout_only(self):
        """全部超时（非连接被拒）→ 不追加 hint。"""
        checks = [("源A", "行情", lambda: (cs._ERR, 0.0, "超时（预算 12s）"))]
        with mock.patch.object(cs, "_checks", checks):
            results = cs.run_health_checks(max_timeout=5.0)
        assert not any(r.get("hint") for r in results)
        assert results[0]["message"].startswith("超时")
