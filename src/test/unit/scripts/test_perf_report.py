"""测试：端到端性能基准 — perf-report.py

覆盖：
  - `_generate_holdings`：股票按请求量取样、场外基金全量追加；样本池覆盖 Phase3 目标量
  - `_sample_of`：按账户口径分列（港股非 6 位代码仍计为股票，不按代码位数误判）
  - `_verdict`：达标/超标边界（≤ 目标值即达标）
  - 报告文案：测试时间随运行时刻动态生成（解析回读、与当前时刻比对）；
    持仓规模按实际数量派生（文案 = 传入样本规模，不写死）
  - LLM mock：patch 目标为包属性（与 `_llm_news` 函数内 import 解析点一致），
    mock 返回值结构与收集器消费契约同构

测试通过脚本 import 方式直接复用，不运行真实 CLI 进程、不执行真实性能基准。
"""

from __future__ import annotations

import importlib.util
import inspect
import re
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # investor-util 仓库根目录
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
    pytest.mark.usefixtures("offline_external_sources"),
]


def _load_script(name: str):
    """按文件名加载 scripts/ 下的脚本（规避 import 路径限制）。"""
    fpath = _SCRIPTS_DIR / name
    mod_name = name.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # 注册进 sys.modules：`@dataclass` 解析类命名空间时按 cls.__module__ 回查模块
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def perf_report():
    return _load_script("perf-report.py")


@pytest.fixture()
def report_path(tmp_path, monkeypatch, perf_report):
    """把报告输出重定向到临时目录，测试不得写入 docs/tmp。"""
    path = tmp_path / "perf.md"
    monkeypatch.setattr(perf_report, "_PERF_REPORT_PATH", str(path))
    return path


def _timings() -> dict:
    return {
        "data_generation": 0.5,
        "phase1_basic_excel": 12.0,
        "phase2_both_html_excel": 25.0,
        "phase3_stress_large": 40.0,
    }


class TestGenerateHoldings:
    """样本规模：请求量 → 实际生成量的关系（含样本池上限）。"""

    def test_stock_count_plus_all_funds(self, perf_report):
        count = perf_report._PHASE1_STOCK_COUNT
        holdings = perf_report._generate_holdings(count)
        stock_part = holdings[: len(perf_report.SAMPLE_STOCKS[:count])]
        assert len(holdings) == count + len(perf_report.SAMPLE_FUNDS)
        assert all(h.account == "证券账户" for h in stock_part)
        assert all(h.account == "基金账户" for h in holdings[len(stock_part) :])

    def test_phase3_target_covered_by_sample_pool(self, perf_report):
        """Phase3 请求量必须被样本池覆盖（否则 [:N] 静默截断、文案与实际不符）。"""
        assert len(perf_report.SAMPLE_STOCKS) >= perf_report._PHASE3_STOCK_COUNT
        holdings = perf_report._generate_holdings(perf_report._PHASE3_STOCK_COUNT)
        sample = perf_report._sample_of(holdings)
        assert sample.stocks == perf_report._PHASE3_STOCK_COUNT
        assert sample.holdings == perf_report._PHASE3_STOCK_COUNT + len(perf_report.SAMPLE_FUNDS)

    def test_request_over_pool_is_clamped_to_pool(self, perf_report):
        """请求量超过样本池 → 以池大小为上限（文档化的实际语义）。"""
        over = len(perf_report.SAMPLE_STOCKS) + 10
        holdings = perf_report._generate_holdings(over)
        assert len(holdings) == len(perf_report.SAMPLE_STOCKS) + len(perf_report.SAMPLE_FUNDS)

    def test_stock_and_fund_names_distinct(self, perf_report):
        holdings = perf_report._generate_holdings(perf_report._PHASE1_STOCK_COUNT)
        names = [h.name for h in holdings]
        assert len(names) == len(set(names)), "样本名重复会让去重/覆盖类逻辑测不到"


class TestSampleOf:
    """样本规模统计：账户口径分类（代码位数会把港股误计为基金）。"""

    def test_counts_by_account_not_code_length(self, perf_report):
        holdings = perf_report._generate_holdings(perf_report._PHASE3_STOCK_COUNT)
        hk_stocks = [h for h in holdings if len(h.code) != 6]
        assert hk_stocks, "样本池应含港股（非 6 位代码），否则该分类分支测不到"
        sample = perf_report._sample_of(holdings)
        assert sample.stocks == perf_report._PHASE3_STOCK_COUNT
        assert all(h.account == "证券账户" for h in hk_stocks)

    def test_partition_is_complete(self, perf_report):
        holdings = perf_report._generate_holdings(perf_report._PHASE1_STOCK_COUNT)
        sample = perf_report._sample_of(holdings)
        assert sample.stocks + sample.funds == sample.holdings
        assert sample.funds == len(perf_report.SAMPLE_FUNDS)


class TestVerdict:
    """达标判定边界。"""

    def test_at_target_is_pass(self, perf_report):
        assert "✅" in perf_report._verdict(60.0, 60.0)

    def test_under_and_over_target(self, perf_report):
        assert "✅" in perf_report._verdict(0.0, 60.0)
        assert "❌" in perf_report._verdict(60.01, 60.0)


class TestTestTimeText:
    """测试时间文案：按时刻动态生成。"""

    def test_formats_given_moment(self, perf_report):
        assert perf_report._test_time_text(datetime(2026, 7, 20, 8, 30, 15)) == "2026-07-20 08:30:15"

    def test_defaults_to_now(self, perf_report):
        text = perf_report._test_time_text()
        reported = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        assert abs((datetime.now() - reported).total_seconds()) < 60


class TestWritePerfReport:
    """报告文案：测试时间随运行更新、持仓规模按实际数量派生。"""

    def test_report_time_tracks_run_time(self, perf_report, report_path):
        perf_report.write_perf_report(_timings(), _sample(perf_report, 20, 3), _sample(perf_report, 50, 3))
        text = Path(report_path).read_text(encoding="utf-8")
        matched = re.search(r"\*\*测试时间\*\*: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", text)
        assert matched, f"测试时间行缺失或格式非动态: {text!r}"
        reported = datetime.strptime(matched.group(1), "%Y-%m-%d %H:%M:%S")
        assert abs((datetime.now() - reported).total_seconds()) < 60

    def test_size_copy_derived_from_samples(self, perf_report, report_path):
        phase1 = _sample(perf_report, 20, 3)
        phase3 = _sample(perf_report, 50, 3)
        perf_report.write_perf_report(_timings(), phase1, phase3)
        text = Path(report_path).read_text(encoding="utf-8")
        expected_phase1 = f"Phase1/2: {phase1.holdings} 品种（{phase1.stocks} 股票 + {phase1.funds} 场外基金）"
        expected_phase3 = f"Phase3: {phase3.holdings} 品种（{phase3.stocks} 股票 + {phase3.funds} 场外基金）"
        assert expected_phase1 in text, "Phase1/2 规模文案与实际不符"
        assert expected_phase3 in text, "Phase3 规模文案与实际不符"
        assert f"{phase3.holdings}品种压力测试" in text
        # 结论文案（basic/压力测试段）同样按实际数量出
        assert f"{phase1.holdings} 品种（{phase1.stocks} 股票 + {phase1.funds} 场外基金）basic" in text
        assert f"{phase3.holdings} 品种（{phase3.stocks} 股票 + {phase3.funds} 场外基金）basic Excel" in text

    def test_size_copy_reflects_smaller_actual_sample(self, perf_report, report_path):
        """样本变小 → 文案随之变小（文案不写死的直接证据）。"""
        phase1 = _sample(perf_report, 7, 2)
        phase3 = _sample(perf_report, 9, 1)
        perf_report.write_perf_report(_timings(), phase1, phase3)
        text = Path(report_path).read_text(encoding="utf-8")
        assert f"Phase1/2: {phase1.holdings} 品种" in text
        assert f"Phase3: {phase3.holdings} 品种" in text
        assert "20 品种" not in text
        assert "50 品种" not in text

    def test_verdict_column_follows_basic_time(self, perf_report, report_path):
        timings = dict(_timings(), phase1_basic_excel=100.0)
        perf_report.write_perf_report(timings, _sample(perf_report, 20, 3), _sample(perf_report, 50, 3))
        text = Path(report_path).read_text(encoding="utf-8")
        assert "❌ 超标" in text

    def test_writes_to_configured_path(self, perf_report, report_path):
        ret = perf_report.write_perf_report(_timings(), _sample(perf_report, 20, 3), _sample(perf_report, 50, 3))
        assert ret == str(report_path)
        assert report_path.exists()


class TestLlmMock:
    """LLM mock：patch 目标 = 包属性；返回值结构与收集器契约同构。"""

    def test_patch_target_is_package_attribute(self, perf_report):
        """调用点在函数内 `from src.python.llm import generate_all_llm` 读包属性。"""
        import src.python.report._llm_news as news_mod

        source = inspect.getsource(news_mod._submit_llm_future)
        assert "from src.python.llm import generate_all_llm" in source

        assert perf_report._LLM_MOCK_TARGET == "src.python.llm.generate_all_llm"
        # 指向子模块属性的写法不会覆盖该读取点
        assert not perf_report._LLM_MOCK_TARGET.startswith("src.python.llm.generators_orchestrator")

    def test_patch_shadows_call_site_read(self, perf_report):
        """patch 目标生效后，与调用点同款的包属性读取拿到 mock。"""
        from unittest.mock import sentinel

        with patch(perf_report._LLM_MOCK_TARGET, sentinel.perf_llm) as mocked:
            from src.python.llm import generate_all_llm as resolved_at_call_time

            assert resolved_at_call_time is mocked
            assert mocked is sentinel.perf_llm

    def test_mock_value_matches_collector_contract(self, perf_report):
        """mock 返回值经真实收集器解析：4 模块内容 + 无辩论信息、无异常登记。"""
        from src.python.report._llm_news import _collect_llm_future_result

        class _FakeFuture:
            def result(self):
                return perf_report._LLM_MOCK_VALUE

        reporter = MagicMock()
        llm_content, debate_info = _collect_llm_future_result(_FakeFuture(), reporter)
        assert len(llm_content) == 4
        assert all(isinstance(c, str) and c for c in llm_content)
        assert debate_info is None
        reporter.add_error.assert_not_called()


def _sample(module, stocks: int, funds: int):
    """构造样本规模（总品种数由分量派生，不写死）。"""
    return module.PerfSample(holdings=stocks + funds, stocks=stocks, funds=funds)
