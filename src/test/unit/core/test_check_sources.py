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
            ("src_a", "快源A", "测试", lambda: (cs._OK, 5.0, "5ms 正常")),
            ("src_b", "快源B", "测试", lambda: (cs._OK, 8.0, "8ms 正常")),
            ("src_c", "慢源C", "测试", lambda: (time.sleep(30), (cs._OK, 1.0, "1ms 正常"))[1]),
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
            ("src_a", "快源A", "测试", lambda: (cs._OK, 5.0, "5ms 正常")),
            ("src_b", "快源B", "测试", lambda: (cs._OK, 8.0, "8ms 正常")),
        ]
        with mock.patch.object(cs, "_checks", checks):
            results = cs.run_health_checks(max_timeout=5.0)
        assert len(results) == 2
        assert all(r["ok"] for r in results)
        assert not any(r["message"].startswith("超时") for r in results)

    def test_check_exception_marked_not_ok(self):
        """检查函数抛异常时标记 ok=False 并带错误信息（不崩溃）。"""
        checks = [("src_err", "异常源", "测试", lambda: (_ for _ in ()).throw(RuntimeError("boom")))]
        with mock.patch.object(cs, "_checks", checks):
            results = cs.run_health_checks(max_timeout=5.0)
        assert results[0]["name"] == "异常源"
        assert results[0]["ok"] is False
        assert "boom" in results[0]["message"]

    def test_boundary_no_duplicate_and_result_wins(self):
        """正常完成下同 name 不重复，真实结果保留。"""
        checks = [("src_a", "快源A", "测试", lambda: (cs._OK, 5.0, "5ms 正常"))]
        with mock.patch.object(cs, "_checks", checks):
            results = cs.run_health_checks(max_timeout=5.0)
        names = [r["name"] for r in results]
        assert names.count("快源A") == 1
        assert results[0]["ok"] is True


class TestProbeReachability:
    """探针可达性判定回归（3xx 误报 / 不跟随重定向 / 主备双端点）。

    回归背景：探针若用 `http://` 端点且不跟随重定向，上游迁 https 后的 301/302 会被记成
    301/302，探针既不跟随又把 3xx 计失败 → 健康历史里天天基金/腾讯K线/财联社
    长期 ok=0/fail=10（用户报「高频连接失败」），而生产路径（https + follow）
    一直正常。
    """

    def _client(self, *, status_code: int, text: str = ""):
        resp = mock.Mock()
        resp.status_code = status_code
        resp.text = text
        client = mock.Mock()
        client.get.return_value = resp
        client.__enter__ = mock.Mock(return_value=client)
        client.__exit__ = mock.Mock(return_value=False)
        return client

    def test_redirect_counts_as_reachable(self):
        """3xx 应计「可达」（带备注），不再算告警/失败。"""
        for code in (301, 302, 307):
            with mock.patch.object(cs, "make_http_client", return_value=self._client(status_code=code)):
                symbol, _elapsed, message = cs._check_http("https://example.com/x")
            assert symbol == cs._OK, f"HTTP {code} 应视为可达"
            assert "重定向" in message

    def test_follow_redirects_passed_to_client(self):
        """默认把 follow_redirects=True 传给客户端（跟随后 3xx 实际不应出现）。"""
        with mock.patch.object(cs, "make_http_client", return_value=self._client(status_code=200)) as mk:
            cs._check_http("https://example.com/x")
        assert mk.call_args.kwargs.get("follow_redirects") is True

    def test_other_status_still_warns(self):
        """4xx/5xx 仍计告警（防「3xx 放宽」过度放宽）。"""
        for code in (403, 404, 500):
            with mock.patch.object(cs, "make_http_client", return_value=self._client(status_code=code)):
                symbol, _elapsed, message = cs._check_http("https://example.com/x")
            assert symbol == cs._WARN
            assert f"HTTP {code}" in message

    def test_check_any_backup_takes_over_with_note(self):
        """主源不可达、备源可达 → 整体可用，并标注主源降级。"""
        calls: list[str] = []

        def fake_check(url, **_kwargs):
            calls.append(url)
            if "primary" in url:
                return cs._ERR, 5.0, "connection reset"
            return cs._OK, 12.0, "12ms 正常"

        with mock.patch.object(cs, "_check_http", side_effect=fake_check):
            symbol, _elapsed, message = cs._check_any(
                [("push2 主源", "https://primary"), ("行情页备源", "https://backup/x")]
            )
        assert symbol == cs._OK
        assert calls == ["https://primary", "https://backup/x"]
        assert "主源不可达" in message and "行情页备源" in message

    def test_check_any_all_fail_reports_labeled_reason(self):
        """全部端点不可达 → 失败，且原因带端点标签（便于定位）。"""
        with mock.patch.object(cs, "_check_http", return_value=(cs._ERR, 3.0, "Server disconnected")):
            symbol, _elapsed, message = cs._check_any(
                [("push2 主源", "https://primary"), ("行情页备源", "https://backup/x")]
            )
        assert symbol == cs._ERR
        assert "行情页备源" in message

    def test_all_probe_urls_use_https(self):
        """静态守卫：探针 URL 一律 https（http→https 重定向是历史误报根因）。"""
        import inspect

        source = inspect.getsource(cs)
        assert '"http://' not in source, "探针不应再使用 http:// 端点"

    def test_industry_probe_has_backup_endpoint(self):
        """行业分类探针必须是主+备双端点（push2 在部分环境不可达，行情页备源交付数据）。"""
        entry = next(c for c in cs._checks if c[0] == "eastmoney_industry")
        urls: list[str] = []

        def fake_check(url, **_kwargs):
            urls.append(url)
            if len(urls) == 1:
                return cs._ERR, 5.0, "Server disconnected"
            return cs._OK, 9.0, "9ms 正常"

        with mock.patch.object(cs, "_check_http", side_effect=fake_check):
            symbol, _elapsed, _message = entry[3]()
        assert symbol == cs._OK, "主源不可达时应有备源接管"
        assert len(urls) == 2, "应依次探测主源与备源"
        assert urls[0] != urls[1], "两个端点不应相同"


class TestResultRowRenderingConsistency:
    """结果行符号与统计口径一致（回归：超时行被计入告警却渲染成红色错误）。"""

    def _run_cli(self, capsys, raw: list[dict]) -> tuple[int, str]:
        with mock.patch.object(cs, "run_health_checks", return_value=raw):
            with pytest.raises(SystemExit) as exc:
                cs.run_check_sources()
        return exc.value.code, capsys.readouterr().out

    def test_budget_timeout_row_rendered_as_warn(self, capsys):
        """预算超时（消息「超时（预算 Ns）」）→ 行符号为告警、统计计入告警、退出码 1。

        曾出现：统计分支判「timeout / 超时」两种措辞，符号分支只判 "timeout"，
        于是 `超时（预算 15s）` 被计入 warn_count 却渲染成 `_ERR`（红色错误）——
        同一行自相矛盾（统计行说告警、行首说错误），退出码也按失败处理。
        """
        raw = [
            {"name": "快源A", "label": "行情", "ok": True, "latency_ms": 5.0, "message": "5ms 正常"},
            {"name": "慢源C", "label": "历史行情", "ok": False, "latency_ms": 0.0, "message": "超时（预算 15s）"},
        ]
        code, out = self._run_cli(capsys, raw)

        row = next(line for line in out.splitlines() if "慢源C" in line)
        assert row.lstrip().startswith(cs._WARN), f"超时行应以告警符号渲染，实际：{row}"
        assert f"{cs._WARN} 1" in out, "统计行应把超时计为告警"
        assert f"{cs._ERR} 0" in out, "超时不应计为失败"
        assert code == 1, "超时是告警级 → 退出码 1 而非失败级 2"

    def test_real_failure_still_rendered_as_error(self, capsys):
        """真实失败（非超时措辞）仍渲染为错误并退出码 2（防上一条修复过度放宽）。"""
        raw = [{"name": "源A", "label": "行情", "ok": False, "latency_ms": 3.0, "message": "HTTP 301"}]
        code, out = self._run_cli(capsys, raw)

        row = next(line for line in out.splitlines() if "源A" in line)
        assert row.lstrip().startswith(cs._ERR)
        assert code == 2


class TestProxyHint:
    """全部数据源被拒时追加代理诊断提示（回归：另一台电脑 WinError 10061 全灭）。"""

    def _check(self, symbol: str, msg: str):
        return lambda: (symbol, 5.0, msg)

    def test_all_refused_appends_hint(self):
        """全部失败且多数为连接被拒（WinError 10061 / Errno 111）→ 追加 hint 项。"""
        checks = [
            ("src_a", "源A", "行情", self._check(cs._ERR, "[WinError 10061] 由于目标计算机积极拒绝，无法连接。")),
            ("src_b", "源B", "新闻", self._check(cs._ERR, "[Errno 111] Connection refused")),
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
            ("src_a", "源A", "行情", self._check(cs._OK, "5ms 正常")),
            ("src_b", "源B", "新闻", self._check(cs._ERR, "[WinError 10061] 拒绝")),
        ]
        with mock.patch.object(cs, "_checks", checks):
            results = cs.run_health_checks(max_timeout=5.0)
        assert not any(r.get("hint") for r in results)

    def test_no_hint_on_timeout_only(self):
        """全部超时（非连接被拒）→ 不追加 hint。"""
        checks = [("src_a", "源A", "行情", lambda: (cs._ERR, 0.0, "超时（预算 12s）"))]
        with mock.patch.object(cs, "_checks", checks):
            results = cs.run_health_checks(max_timeout=5.0)
        assert not any(r.get("hint") for r in results)
        assert results[0]["message"].startswith("超时")


class TestFinancialReportProbes:
    """财报域两个源纳入健康检查（rf-439）。

    回归背景：`_checks` 原先只探 10 个源（行情/基金/行业/新闻/K 线），**DataSinking 与
    巨潮资讯都不探测**——财报域整链失败时用户跑 `check-sources` 得到「10/10 全绿」，
    实际两个源都不可用，故障现场无可见线索（只能翻 logs/app.log）。
    """

    def test_both_report_sources_registered(self):
        ids = {source_id for source_id, _name, _label, _fn in cs._checks}
        assert {"datasink", "cninfo"} <= ids

    def test_datasink_probe_ok_with_metadata(self, monkeypatch):
        from src.python.providers import datasink

        monkeypatch.setattr(datasink, "fetch_report_documents", lambda *_a, **_k: [{"id": 1}])
        symbol, _latency, message = cs._check_datasink()
        assert symbol == cs._OK
        assert "1 篇" in message

    def test_datasink_probe_warns_when_metadata_empty(self, monkeypatch):
        from src.python.providers import datasink

        monkeypatch.setattr(datasink, "fetch_report_documents", lambda *_a, **_k: None)
        symbol, _latency, message = cs._check_datasink()
        assert symbol == cs._WARN
        assert "未取到元数据" in message

    def test_probe_exception_is_err_and_does_not_raise(self, monkeypatch):
        from src.python.providers import datasink

        def _boom(*_a, **_k):
            raise RuntimeError("probe exploded")

        monkeypatch.setattr(datasink, "fetch_report_documents", _boom)
        symbol, _latency, message = cs._check_datasink()
        assert symbol == cs._ERR
        assert "probe exploded" in message

    def test_cninfo_probe_ok_when_orgid_resolved(self, monkeypatch):
        from src.python.providers import cninfo

        monkeypatch.setattr(cninfo, "resolve_org_id", lambda code: f"{code},gssh0600900")
        symbol, _latency, message = cs._check_cninfo()
        assert symbol == cs._OK
        assert "orgId" in message

    def test_cninfo_probe_warns_when_orgid_missing(self, monkeypatch):
        from src.python.providers import cninfo

        monkeypatch.setattr(cninfo, "resolve_org_id", lambda _code: None)
        symbol, _latency, message = cs._check_cninfo()
        assert symbol == cs._WARN
        assert "未解析到 orgId" in message

    def test_missing_credential_marks_skip_without_probing(self, monkeypatch):
        """缺 key 的源产出 ⏭️ 跳过态，且**不发起探测**（配置级问题不是源故障）。"""
        probed: list[int] = []

        def _probe():
            probed.append(1)
            return cs._OK, 1.0, "不应被调用"

        monkeypatch.setattr(cs, "_checks", [("datasink", "DataSinking 财报", "财报全文", _probe)])
        monkeypatch.setattr(cs, "credential_ready_enabled", lambda: True)
        monkeypatch.setattr(cs, "missing_credential", lambda sid: object() if sid == "datasink" else None)
        monkeypatch.setattr(cs, "credential_hint", lambda _spec: "缺凭据：请设置 DATASINK_API_KEY")

        results = cs.run_health_checks(max_timeout=2.0)

        assert probed == []
        assert len(results) == 1
        assert results[0]["skipped"] is True
        assert results[0]["ok"] is False
        assert "DATASINK_API_KEY" in results[0]["message"]
