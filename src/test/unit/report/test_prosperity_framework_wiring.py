"""景气度框架诊断接线测试（实验性功能 `prosperity_framework`）。

覆盖：
  - 编排辅助 `compute_prosperity_framework_data`：开关关闭 → None（零行为变化）；
    开启 → 契约可组装（穿透/基本面/历史注入后六维尽量可计分）
  - Excel：行动建议页签在契约存在时追加「景气度框架诊断」块；None 时不出现
  - HTML：行动建议章 partial 在 context 含契约时渲染该块；缺省时不渲染
运行：pytest src/test/unit/report/test_prosperity_framework_wiring.py -v
"""

from __future__ import annotations

import pytest

from src.python.report.market_value import DetailRow

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _details() -> list[DetailRow]:
    return [
        DetailRow(account="A", name="中际旭创", code="300308", market_value=300_000.0, cost=250_000.0),
        DetailRow(account="A", name="贵州茅台", code="600519", market_value=100_000.0, cost=90_000.0),
    ]


def _contract() -> dict:
    return {
        "available": True,
        "reason": "",
        "total_score": 55,
        "scored_weight": 70,
        "max_score": 100,
        "total_score_pct": 79,
        "rating": "partial_fit",
        "rating_label": "较契合",
        "dimensions": [
            {
                "key": "boom_cycle",
                "name": "景气方向/通胀属性",
                "score": 18,
                "max_score": 25,
                "status": "scored",
                "evidence": ["命中景气关键词的权重 60.00%"],
                "unverified": [],
            },
            {
                "key": "roe_elasticity",
                "name": "ROE 低位弹性",
                "score": 0,
                "max_score": 20,
                "status": "unverified",
                "evidence": [],
                "unverified": ["未取到个股 ROE（功能开关 `financial_indicator` 默认关）→ 该维不计分"],
            },
        ],
        "holdings_view": [
            {
                "code": "300308",
                "name": "中际旭创",
                "weight_pct": 75.0,
                "sector": "科技",
                "roe": None,
                "notes": ["ROE 需核实（未取到基本面）"],
            }
        ],
        "concentration_pct": 100.0,
        "turnover_proxy_pct": None,
        "unverified": ["ROE 低位弹性：未取到个股 ROE（功能开关 `financial_indicator` 默认关）→ 该维不计分"],
        "partial_notes": [],
        "notes": ["本评分衡量组合与景气度框架的契合度，非组合优劣判断，亦非投资建议；标注「需核实」的项请自行核实。"],
    }


class TestOrchestrationHelper:
    def test_switch_off_returns_none(self, monkeypatch):
        """开关关闭 → 返回 None（调用方不注入契约，报告零行为变化）。"""
        from src.python.report import _report_aux_metrics

        monkeypatch.setattr("src.python.config.features.is_feature_enabled", lambda _k: False)
        out = _report_aux_metrics.compute_prosperity_framework_data([], _details(), {}, {}, None)
        assert out is None

    def test_switch_on_builds_contract(self, monkeypatch):
        """开关开启 → 组装契约（穿透/流动性/快照失败均降级为未验证，不抛异常）。"""
        from src.python.report import _report_aux_metrics

        monkeypatch.setattr("src.python.config.features.is_feature_enabled", lambda _k: True)
        monkeypatch.setattr(
            "src.python.analysis.liquidity.check_liquidity",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("no cache")),
        )
        out = _report_aux_metrics.compute_prosperity_framework_data([], _details(), {"penetrated_assets": []}, {}, None)
        assert out is not None and out["available"] is True
        assert out["scored_weight"] < 100  # 缺输入 → 部分维度未验证

    def test_uses_penetrated_assets_from_prep(self, monkeypatch):
        """prep 提供穿透重仓 → 维度①按穿透口径计分（证据含「穿透后」）。"""
        from src.python.report import _report_aux_metrics

        monkeypatch.setattr("src.python.config.features.is_feature_enabled", lambda _k: True)
        monkeypatch.setattr("src.python.analysis.liquidity.check_liquidity", lambda *_a, **_k: [])
        out = _report_aux_metrics.compute_prosperity_framework_data(
            [],
            _details(),
            {"penetrated_assets": [{"name": "中际旭创", "sector": "科技", "concepts": ["光通信"], "ratio_pct": 100.0}]},
            {},
            None,
        )
        boom = next(d for d in out["dimensions"] if d["key"] == "boom_cycle")
        assert any("穿透底层" in e and "两视角叠加" in e for e in boom["evidence"])


class TestExcelRendering:
    def _write(self, prosperity):
        from openpyxl import Workbook

        from src.python.report.action_sheet import write_action_sheet

        wb = Workbook()
        ws = wb.active
        action = {
            "available": True,
            "summary": "s",
            "rebalance_signals": [],
            "discipline_signals": [],
            "rebalance_advice": [],
            "attribution": None,
        }
        write_action_sheet(ws, action, prosperity_framework_data=prosperity)
        return ws

    def _flat(self, ws) -> str:
        return "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value is not None)

    def test_block_rendered_when_contract_present(self):
        text = self._flat(self._write(_contract()))
        assert "景气度框架诊断（实验性）" in text
        assert "较契合" in text
        assert "ROE 低位弹性" in text
        assert "非投资建议" in text

    def test_block_absent_when_contract_none(self):
        text = self._flat(self._write(None))
        assert "景气度框架诊断" not in text


class TestHtmlRendering:
    def _render(self, prosperity):
        from src.python.report.html_jinja_env import _ENV
        from src.python.report.html_writer import _build_section_nav_groups

        order = [{"key": "action", "name": "行动建议", "number": 1, "type": "action"}]
        numbers = {"action": 1}
        sv = {"action": True}

        def _sv(key, _d=sv):
            return bool(_d.get(key, False))

        groups = _build_section_nav_groups(order, _sv, numbers)
        html = _ENV.get_template("report_template.html").render(
            now="2026-09-16 12:00:00",
            today="2026-09-16",
            trading_day="2026-09-16",
            total_mv=0,
            total_cost=0,
            total_profit=0,
            total_profit_rate=0,
            total_today_profit=0,
            today_profit_rate=0,
            categories={},
            update_status=None,
            a_indices=[],
            us_indices=[],
            accounts={},
            account_totals={},
            cat_data=[],
            penetration=None,
            perf_data=[],
            news_data=None,
            news_llm_meta=None,
            has_llm_analysis=False,
            manager_analysis=None,
            overlap_matrix=None,
            position_relationship_data={},
            concentration_analysis=None,
            style_analysis=None,
            llm_enabled=True,
            global_macro=None,
            expert_review=None,
            health_check=None,
            penetration_deep=None,
            llm_session_usage=None,
            module_labels={},
            module_disabled={},
            llm_module_info=[],
            llm_endpoint="",
            cache_stats=None,
            section_order=order,
            section_numbers=numbers,
            section_visible_dict=sv,
            chart_datasets={},
            enable_interactive_charts=False,
            action_data={
                "available": True,
                "summary": "s",
                "rebalance_signals": [],
                "discipline_signals": [],
                "rebalance_advice": [],
                "attribution": None,
            },
            prosperity_framework_data=prosperity,
            section_visible=_sv,
            section_groups=groups,
            llm_supported_sections=frozenset(),
        )
        return html

    def test_block_rendered_when_contract_present(self):
        html = self._render(_contract())
        assert "⑥ 景气度框架诊断（实验性）" in html
        assert "较重" not in html  # 防误断言
        assert "较契合" in html
        assert "ROE 低位弹性" in html

    def test_block_absent_when_contract_none(self):
        html = self._render(None)
        # 模板内保留 HTML 注释，但渲染块本身（含「（实验性）」小标题）不得出现
        assert "⑥ 景气度框架诊断（实验性）" not in html


class TestResilienceIsolation:
    """韧性防线：实验性诊断的任何异常都不得影响主报告（缺陷回归）。"""

    def test_helper_returns_none_when_build_raises(self, monkeypatch):
        """构建函数抛异常 → 组装辅助返回 None（不冒泡），主报告流程不受影响。"""
        from src.python.report import _report_aux_metrics

        monkeypatch.setattr("src.python.config.features.is_feature_enabled", lambda _k: True)
        monkeypatch.setattr("src.python.analysis.liquidity.check_liquidity", lambda *_a, **_k: [])

        def _boom(*_a, **_k):
            raise AttributeError("'SnapshotData' object has no attribute 'get'")

        monkeypatch.setattr("src.python.analysis.prosperity_framework.build_prosperity_framework_data", _boom)
        assert _report_aux_metrics.compute_prosperity_framework_data([], _details(), {}, {}, None) is None

    def test_broken_snapshots_do_not_break_contract(self, monkeypatch):
        """快照形态异常（对象非 dict 形态）→ 契约仍可构建（集中度维度降级）。"""
        from src.python.report import _report_aux_metrics

        monkeypatch.setattr("src.python.config.features.is_feature_enabled", lambda _k: True)
        monkeypatch.setattr("src.python.analysis.liquidity.check_liquidity", lambda *_a, **_k: [])
        monkeypatch.setattr("src.python.report.history_snapshot.load_all", lambda *_a, **_k: [object(), object()])
        out = _report_aux_metrics.compute_prosperity_framework_data([], _details(), {}, {}, None)
        assert out is not None and out["available"] is True
        assert out["turnover_proxy_pct"] is None

    def test_dimension_failure_isolated_to_that_dimension(self, monkeypatch):
        """单维计算异常 → 该维 unverified，其余维度与契约不受影响。"""
        from src.python.analysis import prosperity_framework as pf

        monkeypatch.setattr(pf, "_score_liquidity", lambda _s: (_ for _ in ()).throw(RuntimeError("boom")))
        data = pf.build_prosperity_framework_data(_details(), penetration_data=None)
        liquidity = next(d for d in data["dimensions"] if d["key"] == "liquidity")
        assert liquidity["status"] == "unverified"
        assert any("计算异常" in u for u in liquidity["unverified"])
        boom = next(d for d in data["dimensions"] if d["key"] == "boom_cycle")
        assert boom["status"] == "scored"

    def test_real_snapshotdata_runs_end_to_end(self, monkeypatch):
        """真实 SnapshotData 对象经组装辅助全链路（缺陷现场复现 → 不得失败）。"""
        from src.python.report import _report_aux_metrics
        from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

        def _snap(codes):
            holdings = tuple(
                SnapshotHolding(code=c, name=c, shares=100.0, cost_price=10.0, market_value=1000.0) for c in codes
            )
            return SnapshotData(
                accounts=(AccountSnapshot(account_name="证券", holdings=holdings),),
                total_value=1_000_000.0,
                total_cost=800_000.0,
                total_pnl=200_000.0,
                total_pnl_pct=25.0,
                timestamp="2026-09-16T15:00:00",
                fingerprint="fp",
            )

        monkeypatch.setattr("src.python.config.features.is_feature_enabled", lambda _k: True)
        monkeypatch.setattr("src.python.analysis.liquidity.check_liquidity", lambda *_a, **_k: [])
        monkeypatch.setattr(
            "src.python.report.history_snapshot.load_all",
            lambda *_a, **_k: [_snap(["600519", "300308"]), _snap(["600519", "601398"])],
        )
        out = _report_aux_metrics.compute_prosperity_framework_data([], _details(), {}, {}, None)
        assert out is not None and out["turnover_proxy_pct"] == 66.67


class TestHtmlCallSiteSeam:
    """接缝守卫：**每条** HTML 生成调用链都必须把契约传到模板（缺陷回归）。

    现场（用户报障「行动建议后没加内容」）：`_generate_full_html_report`（菜单 L 走的
    full 路径）未接收/转发 `prosperity_framework_data`，而 both 路径已转发 —— 只在
    一条路径上补参数就会漏掉另一条。故以「源码级调用点全覆盖」方式守卫：
    新增其它 HTML 调用链时，若忘记转发，本用例立即失败。
    """

    def _source(self) -> str:
        from pathlib import Path

        # 输出包装层已从编排模块拆出，两文件都要扫——否则守卫只盯旧文件、漏掉真正的调用点
        return "\n".join(
            Path(f).read_text(encoding="utf-8")
            for f in ("src/python/report/_report_generation.py", "src/python/report/_report_output.py")
        )

    def test_every_write_html_report_call_passes_contract(self):
        """报告输出模块中每处 write_html_report(...) 调用都须带该参数。"""
        import re

        src = self._source()
        calls = re.findall(r"write_html_report\(\s*\n(.*?)\n\s*\)", src, re.S)
        assert len(calls) >= 2, f"预期至少两处 HTML 调用点（both/full），实际 {len(calls)}"
        missing = [c.strip().splitlines()[0] for c in calls if "prosperity_framework_data" not in c]
        assert not missing, f"以下 HTML 调用点未转发 prosperity_framework_data: {missing}"

    def test_full_html_wrapper_signature_and_forwarding(self):
        """`_generate_full_html_report` 须声明该参数（并在函数体内转发）。"""
        import inspect

        from src.python.report import _report_generation

        sig = inspect.signature(_report_generation._generate_full_html_report)
        assert "prosperity_framework_data" in sig.parameters
        body = inspect.getsource(_report_generation._generate_full_html_report)
        assert "prosperity_framework_data=prosperity_framework_data" in body, "包装函数须把参数转发给 write_html_report"

    def test_full_path_call_site_passes_contract(self):
        """full 路径的包装调用点须从 pipeline_data 取契约传入。"""
        import inspect

        from src.python.report import _report_generation

        src = inspect.getsource(_report_generation._generate_report_full)
        assert 'prosperity_framework_data=(pipeline_data or {}).get("prosperity_framework_data")' in src
