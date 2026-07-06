"""conftest.py — 全局 pytest 配置与标记注册 + edge 文件隔离校验。

标记分组（支持 -m 选择运行）：
  - scenario: 全部业务场景（S0a-S0d + S1-S33 + T1-T21）
  - llm: LLM 相关测试（全部 mock，无需 API key）
  - edge: 边缘/异常场景测试 — 必须放在 *_edge.py 文件中
  - smoke / data / integration（详见各 marker 说明）

用法：
  cd D:/codebase/zoo/investor-util
  pytest src/test/ -m "smoke"                                    # 仅冒烟
  pytest src/test/ -m "not llm"                                  # 排除 LLM
  pytest src/test/ -m "scenario"                                 # 全部场景
  pytest src/test/                                             # 全量运行
"""

from __future__ import annotations

import pytest


def pytest_configure(config):
    """注册自定义标记，避免 pytest 警告。"""
    config.addinivalue_line("markers", "scenario: 业务场景集成测试（S0a-S0d + S1-S33 + T1-T21）")
    config.addinivalue_line("markers", "scenario_basic: 基础业务链路（S1-S5 + S0a-S0d + S21-S28 + S29-S33）")
    config.addinivalue_line("markers", "scenario_resilience: 异常容错场景（S6-S10）")
    config.addinivalue_line("markers", "scenario_llm: LLM 场景组合（S11-S20）")
    config.addinivalue_line("markers", "scenario_datetime: 日期/时间场景（T1-T21）")
    config.addinivalue_line("markers", "scenario_stock: 场景 S1 — 纯股票组合")
    config.addinivalue_line("markers", "scenario_fund: 场景 S2 — 纯基金组合")
    config.addinivalue_line("markers", "scenario_mixed_accounts: 场景 S3 — 混合多账户")
    config.addinivalue_line("markers", "scenario_new_holdings: 场景 S4 — 新持仓无缓存")
    config.addinivalue_line("markers", "scenario_cache_hit: 场景 S5 — 缓存全命中")
    config.addinivalue_line("markers", "scenario_bond: 场景 S6 — 纯债券基金组合")
    config.addinivalue_line("markers", "scenario_network_down: 场景 S7 — 网络中断降级")
    config.addinivalue_line("markers", "scenario_single_holding: 场景 S8 — 单账户单持仓")
    config.addinivalue_line("markers", "scenario_zero_cost: 场景 S9 — 零成本持仓")
    config.addinivalue_line("markers", "scenario_extreme: 场景 S10 — 极端值")
    config.addinivalue_line("markers", "unit: 单元测试总标记")
    config.addinivalue_line("markers", "unit_providers: 数据源提供商单元测试")
    config.addinivalue_line("markers", "unit_fetcher: 数据获取调度单元测试")
    config.addinivalue_line("markers", "unit_llm: LLM 模块单元测试")
    config.addinivalue_line("markers", "unit_news: 新闻模块单元测试")
    config.addinivalue_line("markers", "unit_report: 报告生成单元测试")
    config.addinivalue_line("markers", "unit_config: 配置管理单元测试")
    config.addinivalue_line("markers", "unit_core: 核心基础设施单元测试")
    config.addinivalue_line("markers", "unit_ui: TUI/UI 交互单元测试")
    config.addinivalue_line("markers", "llm: LLM 相关测试（全部 mock，无需 API key）")
    config.addinivalue_line("markers", "edge: 边缘/异常场景测试 — 必须放在 *_edge.py 文件中，不得与普通测试混搭")
    config.addinivalue_line("markers", "smoke: 冒烟测试（快速验证核心功能）")
    config.addinivalue_line("markers", "data: 数据正确性验证测试")
    config.addinivalue_line("markers", "integration: 集成测试—模块间契约/全链路/缓存一致性")
    config.addinivalue_line("markers", "integration_contract: 模块间接口契约验证")
    config.addinivalue_line("markers", "integration_isolation: 错误隔离业务语义验证")
    config.addinivalue_line("markers", "integration_news_pipeline: 新闻流水线全链路")
    config.addinivalue_line("markers", "integration_cache: 跨模块缓存一致性验证")
    config.addinivalue_line("markers", "integration_tui: TUI → Handler 路由集成测试")


def pytest_collection_modifyitems(config, items):
    """收集期校验 edge 标记与文件名的匹配约束。

    规则（§1.9 边缘测试文件隔离规范）：
      1. 任何带 @pytest.mark.edge 的测试，其所属文件必须以 _edge.py 结尾
      2. 任何 *_edge.py 文件中的测试，必须带有 @pytest.mark.edge 标记
      3. 违规项报错停止，不允许静默跳过
    """
    for item in items:
        fspath = str(item.fspath)
        has_edge_marker = item.get_closest_marker("edge") is not None
        is_edge_file = fspath.endswith("_edge.py")

        if has_edge_marker and not is_edge_file:
            raise pytest.UsageError(
                f"[!] 边缘测试文件隔离违规：\n"
                f"    测试项 {item.name} 带有 @pytest.mark.edge 标记，\n"
                f"    但所在文件 {fspath} 不以 _edge.py 结尾。\n"
                f"    请将该测试移至对应的 *_edge.py 文件，或移除 edge 标记。"
            )
        if is_edge_file and not has_edge_marker:
            raise pytest.UsageError(
                f"[!] 边缘测试文件隔离违规：\n"
                f"    文件 {fspath} 以 _edge.py 结尾，\n"
                f"    但其测试项 {item.name} 缺少 @pytest.mark.edge 标记。\n"
                f"    请为该测试添加 @pytest.mark.edge，或移出 _edge.py 文件。"
            )
