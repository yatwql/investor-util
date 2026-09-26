"""景气度框架诊断场景冒烟（实验性功能 `prosperity_framework`）。

覆盖真实故障场景（logs/app.log 2026-09-16「生成 full 报告失败」）的端到端回归：
  - 功能开启 + 生产形态快照（`SnapshotData` 冻结 dataclass）→ 报告生成**不得失败**
  - 契约进入 pipeline_data；关闭开关时契约缺席（零行为变化）

约束（对齐测试隔离纪律）：
  - 最小持仓（2 品种），行情/指数/历史/LLM 全部 mock，不触网
  - 输出目录重定向到 tmp_path，不污染 reports/
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.python.core.models import Holding

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic, pytest.mark.usefixtures("offline_external_sources")]

_SAMPLE_HOLDINGS = [
    Holding(account="证券", name="长江电力", code="600900", shares=100, cost_price=10.0),
    Holding(account="证券", name="贵州茅台", code="600519", shares=50, cost_price=200.0),
]


def _detail(code: str, name: str, mv: float):
    from src.python.report.market_value import DetailRow

    return DetailRow(
        account="证券", name=name, code=code, shares=100.0, cost=mv * 0.9, market_value=mv, profit=mv * 0.1
    )


def _snapshots():
    """生产形态快照（冻结 dataclass）——故障现场返回的正是这种类型。"""
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

    return [_snap(["600900", "600519"]), _snap(["600900", "600519"])]


class TestProsperityFrameworkPipeline:
    """Excel 编排路径（basic）就地带出契约——原缺陷即发生在此调用链上的 full 路径。"""

    def _write_report(self, tmp_path, monkeypatch, *, enabled: bool, snapshots=None):
        """驱动 generate_excel_report（真实快照形态 + 隔离输出目录），返回捕获的契约。"""
        from src.python.report.excel_generator import generate_excel_report
        from src.python.report.market_value import DetailRow
        from src.python.report import _report_aux_metrics

        details = [
            DetailRow(
                account="证券",
                name="长江电力",
                code="600900",
                shares=100.0,
                cost=1_000.0,
                market_value=1_100.0,
                price=11.0,
            ),
            DetailRow(
                account="证券",
                name="贵州茅台",
                code="600519",
                shares=50.0,
                cost=9_000.0,
                market_value=10_000.0,
                price=200.0,
            ),
        ]
        monkeypatch.setattr("src.python.config.features.is_feature_enabled", lambda _k: enabled)
        monkeypatch.setattr("src.python.analysis.liquidity.check_liquidity", lambda *_a, **_k: [])
        monkeypatch.setattr(
            "src.python.report.history_snapshot.load_all",
            lambda *_a, **_k: _snapshots() if snapshots is None else snapshots,
        )

        captured: dict = {}
        real_build = _report_aux_metrics.compute_prosperity_framework_data

        def _spy(*args, **kwargs):
            out = real_build(*args, **kwargs)
            captured["data"] = out
            return out

        monkeypatch.setattr(_report_aux_metrics, "compute_prosperity_framework_data", _spy)

        with (
            patch("src.python.fetcher.index.fetch_indices", return_value={}),
            patch("src.python.fetcher.index.fetch_us_indices", return_value={}),
            patch("src.python.report.penetration.fetch_fund_holdings_batch", return_value={}),
            patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}),
            patch("src.python.config.get_llm_config", return_value={"provider": None, "enabled_llm": {}}),
        ):
            generate_excel_report(
                _SAMPLE_HOLDINGS,
                output_dir=str(tmp_path),
                details=details,
                enable_action=True,
            )
        produced = sorted(p.name for p in Path(tmp_path).glob("*.xlsx"))
        return captured.get("data"), produced

    def test_feature_enabled_with_snapshotdata_succeeds(self, monkeypatch, tmp_path):
        """功能开启 + 生产形态快照 → 报告生成成功，契约可算换手代理（缺陷回归）。"""
        data, produced = self._write_report(tmp_path, monkeypatch, enabled=True)
        assert produced, "报告应生成成功（原缺陷：整份 full 报告失败）"
        assert data is not None and data["available"] is True
        assert data["turnover_proxy_pct"] is not None, "生产形态快照必须被正确解析"

    def test_feature_disabled_leaves_contract_absent(self, monkeypatch, tmp_path):
        """功能关闭 → 契约缺席（零行为变化）。"""
        data, produced = self._write_report(tmp_path, monkeypatch, enabled=False)
        assert produced
        assert data is None

    def test_broken_snapshots_do_not_break_report(self, monkeypatch, tmp_path):
        """快照形态异常 → 报告仍生成成功（诊断降级，不拖垮主报告）。"""
        data, produced = self._write_report(tmp_path, monkeypatch, enabled=True, snapshots=[object(), object()])
        assert produced, "诊断失败不得中断报告生成"
        assert data is not None and data["available"] is True
        assert data["turnover_proxy_pct"] is None

    def test_build_exception_does_not_break_report(self, monkeypatch, tmp_path):
        """诊断内部异常 → 报告仍生成成功（装配辅助内部兜底）。"""
        from src.python.report import _report_aux_metrics

        monkeypatch.setattr(
            _report_aux_metrics,
            "compute_prosperity_framework_data",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("simulated build failure")),
        )
        data, produced = self._write_report(tmp_path, monkeypatch, enabled=True)
        assert produced, "装配异常不得中断报告生成"
        assert data is None
