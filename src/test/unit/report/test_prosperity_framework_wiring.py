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
        assert any("穿透后" in e for e in boom["evidence"])


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
