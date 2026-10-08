"""基准指数映射（benchmark_index_resolver）单元测试 — 三阶优先级与降级。

覆盖（对应验收条目）：
  - 配置覆盖最高优先（合法指数代码才生效，非法值回落）
  - 持仓业绩基准文本 → 宽基池反查（含成本降序的权重优先）
  - 全不命中 → 宽基默认 sh000300；getter 异常不外溢
  - 池内非法指数代码不参与匹配（代码判定经 code_utils，禁自建前缀表）

运行：
  cd <项目根目录>
  pytest src/test/unit/analysis/test_benchmark_index_resolver.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis.benchmark_index_resolver import (
    DEFAULT_BENCHMARK_INDEX,
    DEFAULT_BENCHMARK_NAME,
    SOURCE_CONFIG,
    SOURCE_DEFAULT,
    SOURCE_HOLDINGS,
    resolve_benchmark_index,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

_POOL = {"sh000300": "沪深300", "sh000905": "中证500"}


class TestResolveBenchmarkIndex:
    """三阶优先级：配置覆盖 → 持仓基准文本 → 宽基默认。"""

    def test_config_override_wins_over_holdings_text(self) -> None:
        """配置覆盖为最高优先：即使持仓文本可匹配也以配置为准。"""
        result = resolve_benchmark_index(
            [{"code": "002943", "name": "广发多因子", "cost": 100.0}],
            override="sh000905",
            comparison_indices=_POOL,
            benchmark_text_getter=lambda code: "沪深300指数收益率×90%",
        )
        assert result == {"code": "sh000905", "name": "中证500", "source": SOURCE_CONFIG}

    def test_invalid_override_falls_through_to_holdings(self) -> None:
        """非法覆盖值（非指数代码）告警忽略，回落持仓文本级。"""
        result = resolve_benchmark_index(
            [{"code": "002943", "name": "广发多因子", "cost": 100.0}],
            override="600900",  # A 股代码不是指数
            comparison_indices=_POOL,
            benchmark_text_getter=lambda code: "沪深300指数收益率×90%",
        )
        assert result == {"code": "sh000300", "name": "沪深300", "source": SOURCE_HOLDINGS}

    def test_holdings_benchmark_text_matches_pool(self) -> None:
        """持仓业绩基准文本含池显示名 → 反查命中（sh000905）。"""
        result = resolve_benchmark_index(
            [{"code": "011506", "name": "某指数基金", "cost": 100.0}],
            comparison_indices=_POOL,
            benchmark_text_getter=lambda code: "中证500指数收益率×95% + 活期存款利率×5%",
        )
        assert result == {"code": "sh000905", "name": "中证500", "source": SOURCE_HOLDINGS}

    def test_largest_holding_text_decides(self) -> None:
        """按成本降序逐只匹配：权重最大的持仓文本优先。"""
        holdings = [
            {"code": "BIG", "name": "重仓", "cost": 90000.0},
            {"code": "SMALL", "name": "轻仓", "cost": 1000.0},
        ]
        texts = {"BIG": "中证500指数收益率×80%", "SMALL": "沪深300指数收益率×80%"}
        result = resolve_benchmark_index(
            holdings,
            comparison_indices=_POOL,
            benchmark_text_getter=lambda code: texts.get(code),
        )
        assert result["code"] == "sh000905" and result["source"] == SOURCE_HOLDINGS

    def test_no_match_defaults_to_wide_index(self) -> None:
        """文本全不命中池 → 宽基默认（source=default）。"""
        result = resolve_benchmark_index(
            [{"code": "X", "name": "定制指数", "cost": 1.0}],
            comparison_indices=_POOL,
            benchmark_text_getter=lambda code: "某某定制策略指数",
        )
        assert result == {"code": DEFAULT_BENCHMARK_INDEX, "name": "沪深300", "source": SOURCE_DEFAULT}

    def test_getter_exception_does_not_propagate(self) -> None:
        """基准文本查询抛异常 → 跳过该代码按默认回落，不外溢。"""

        def _boom(code: str) -> str:
            raise RuntimeError("benchmark unavailable")

        result = resolve_benchmark_index(
            [{"code": "002943", "name": "x", "cost": 1.0}],
            comparison_indices=_POOL,
            benchmark_text_getter=_boom,
        )
        assert result["source"] == SOURCE_DEFAULT and result["code"] == DEFAULT_BENCHMARK_INDEX

    def test_empty_holdings_default(self) -> None:
        """空持仓清单 → 直接默认级（不触发查询）。"""
        result = resolve_benchmark_index(
            [],
            comparison_indices=_POOL,
            benchmark_text_getter=lambda code: pytest.fail("空持仓不应查询基准文本"),
        )
        assert result["source"] == SOURCE_DEFAULT

    def test_pool_non_index_code_skipped(self) -> None:
        """池内非指数代码（如纯数字证券码）不参与匹配，只能落默认。"""
        result = resolve_benchmark_index(
            [{"code": "X", "name": "y", "cost": 1.0}],
            comparison_indices={"999999": "非指数池项"},
            benchmark_text_getter=lambda code: "非指数池项指数",
        )
        assert result["code"] == DEFAULT_BENCHMARK_INDEX
        assert result["source"] == SOURCE_DEFAULT

    def test_default_name_falls_back_to_constant_when_pool_empty(self) -> None:
        """池为空时默认名回落常量（沪深300），不产出空名。"""
        result = resolve_benchmark_index(
            [{"code": "X", "name": "y", "cost": 1.0}],
            comparison_indices={},
            benchmark_text_getter=lambda code: None,
        )
        assert result == {
            "code": DEFAULT_BENCHMARK_INDEX,
            "name": DEFAULT_BENCHMARK_NAME,
            "source": SOURCE_DEFAULT,
        }
