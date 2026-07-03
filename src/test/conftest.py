"""conftest.py — 全局 pytest 配置与标记注册。

标记分组（支持 -m 选择运行）：
  - scenario: 全部业务场景（S1-S20 + T1-T16）
    - scenario_basic: 基础业务链路（S1-S5）
    - scenario_resilience: 异常容错场景（S6-S10）
    - scenario_llm: LLM 场景组合（S11-S20）
    - scenario_datetime: 日期/时间场景（T1-T16）
  - llm: LLM 相关测试（unit_llm 336 + scenario_llm 24，均为 mock，无需 API key）
  - edge: 边缘/异常场景测试（~93 项，含 9 个 _edge.py 文件）
  - smoke: 冒烟测试（6 文件 × 4 项 = 24 项，~2s）
  - data: 数据正确性验证测试（65 项）

⚠ 以下注释中的测试项数可能随版本更新而变化，参见 test_runner.py 获取精确统计。

用法：
  cd D:/codebase/zoo/investor-util
  pytest src/test/ -m "smoke"                                    # 仅冒烟
  pytest src/test/ -m "not llm"                                  # 排除 LLM
  pytest src/test/ -m "scenario"                                 # 全部场景 S1-S20 + T1-T16
  pytest src/test/ -m "scenario_basic"                           # 仅基础链路 S1-S5
  pytest src/test/ -m "scenario_llm or scenario_datetime"        # LLM + 日期时间场景
  pytest src/test/                                             # 全量运行
"""

from __future__ import annotations


def pytest_configure(config):
    """注册自定义标记，避免 pytest 警告。"""
    config.addinivalue_line("markers", "scenario: 业务场景集成测试（S1-S20 + T1-T16）")
    config.addinivalue_line("markers", "scenario_basic: 基础业务链路（S1-S5）")
    config.addinivalue_line("markers", "scenario_resilience: 异常容错场景（S6-S10）")
    config.addinivalue_line("markers", "scenario_llm: LLM 场景组合（S11-S20）")
    config.addinivalue_line("markers", "scenario_datetime: 日期/时间场景（T1-T16）")
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
    config.addinivalue_line("markers", "llm: LLM 相关测试（unit_llm 336 + scenario_llm 24，均为 mock，无需 API key）")
    config.addinivalue_line("markers", "edge: 边缘/异常场景测试")
    config.addinivalue_line("markers", "smoke: 冒烟测试（快速验证核心功能）")
    config.addinivalue_line("markers", "data: 数据正确性验证测试")
    config.addinivalue_line("markers", "integration: 集成测试—模块间契约/全链路/缓存一致性")
    config.addinivalue_line("markers", "integration_contract: 模块间接口契约验证")
    config.addinivalue_line("markers", "integration_isolation: 错误隔离业务语义验证")
    config.addinivalue_line("markers", "integration_news_pipeline: 新闻流水线全链路")
    config.addinivalue_line("markers", "integration_cache: 跨模块缓存一致性验证")
    config.addinivalue_line("markers", "integration_tui: TUI → Handler 路由集成测试")
