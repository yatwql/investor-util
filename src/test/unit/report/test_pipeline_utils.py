"""报告管线 LLM/新闻并行辅助函数单元测试。

覆盖 `_llm_news.py` 的并行收集与结果汇总辅助函数：
  - `_collect_llm_future_result` — LLM Future 结果解包（正常 / 异常）
  - `_collect_news_future_result` — 新闻 Future 结果解包（正常 / 异常）
  - `_report_llm_module_results` — 模块级 LLM 结果汇总日志（全部成功 / 部分失败）
"""

from __future__ import annotations

from concurrent.futures import Future

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestPipelineUtils:
    """报告管线辅助函数测试。"""

    def test_report_llm_module_results_all_success(self):
        """全部成功 → ok 消息。"""
        from src.python.report._llm_news import _report_llm_module_results

        results = ("<p>A</p>", "<p>B</p>", "<p>C</p>", "<p>D</p>")
        cached = (True, True, True, True)
        logged: list[str] = []

        class _MockReporter:
            def ok(self, msg: str) -> None:
                logged.append(("ok", msg))
            def info(self, msg: str) -> None:
                logged.append(("info", msg))
            def warn(self, msg: str) -> None:
                logged.append(("warn", msg))
            def add_error(self, msg: str) -> None:
                logged.append(("error", msg))

        _report_llm_module_results(results, cached, _MockReporter())
        assert any("缓存" in str(m) for m in logged)

    def test_report_llm_module_results_mixed(self):
        """部分失败 → 打印失败列表。"""
        from src.python.report._llm_news import _report_llm_module_results

        results = (None, "<p>B</p>", None, "<p>D</p>")
        cached = (False, True, False, True)
        logged: list[str] = []

        class _MockReporter:
            def ok(self, msg: str) -> None:
                logged.append(("ok", msg))
            def info(self, msg: str) -> None:
                logged.append(("info", msg))
            def warn(self, msg: str) -> None:
                logged.append(("warn", msg))
            def add_error(self, msg: str) -> None:
                logged.append(("error", msg))

        _report_llm_module_results(results, cached, _MockReporter())
        assert any(t[0] in ("error", "warn") for t in logged)

    def test_collect_llm_future_result_success(self):
        """正常结果 → 正确解包（返回 (llm_content, debate_info)）。"""
        from src.python.report._llm_news import _collect_llm_future_result

        fut = Future()
        content = ("<p>A</p>", None, "<p>C</p>", None)
        fut.set_result(content + (True, False, True, False) + ({"mode": "procon"},))

        class _MockReporter:
            def ok(self, *a): pass
            def info(self, *a): pass
            def warn(self, *a): pass
            def add_error(self, *a): pass
            def error(self, *a): pass

        llm_content, debate_info = _collect_llm_future_result(fut, _MockReporter())
        assert llm_content[:4] == content
        assert debate_info == {"mode": "procon"}

    def test_collect_llm_future_result_exception(self):
        """异常 → 返回 (全 None, None)。"""
        from src.python.report._llm_news import _collect_llm_future_result

        fut = Future()
        fut.set_exception(ValueError("test error"))

        class _MockReporter:
            def ok(self, *a): pass
            def info(self, *a): pass
            def warn(self, *a): pass
            def add_error(self, *a): pass
            def error(self, *a): pass

        llm_content, debate_info = _collect_llm_future_result(fut, _MockReporter())
        assert all(c is None for c in llm_content)
        assert debate_info is None

    def test_collect_news_future_result_success(self):
        """正常结果 → 返回 (data, meta, ok)。"""
        from src.python.report._llm_news import _collect_news_future_result

        fut = Future()
        fut.set_result(([{"title": "新闻1"}], {"total": 1}))

        class _MockReporter:
            def ok(self, *a): pass
            def warn(self, *a): pass
            def add_error(self, *a): pass

        data, meta, ok = _collect_news_future_result(fut, _MockReporter())
        assert len(data) == 1
        assert meta == {"total": 1}
        assert ok is True

    def test_collect_news_future_result_exception(self):
        """异常 → 返回 ([], {}, False)。"""
        from src.python.report._llm_news import _collect_news_future_result

        fut = Future()
        fut.set_exception(RuntimeError("test error"))

        class _MockReporter:
            def ok(self, *a): pass
            def warn(self, *a): pass
            def add_error(self, *a): pass

        data, meta, ok = _collect_news_future_result(fut, _MockReporter())
        assert data == []
        assert meta == {}
        assert ok is False
