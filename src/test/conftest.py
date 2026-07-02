"""conftest.py — 全局 pytest 配置与标记注册。

标记分组（支持 -m 选择运行）：
  - scenario: 全部业务场景（S1-S20 + T1-T16）
    - scenario_basic: 基础业务链路（S1-S5）
    - scenario_extended: 扩展业务场景（S6-S10）
    - scenario_llm: LLM 场景组合（S11-S20）
    - scenario_datetime: 日期/时间场景（T1-T16）
  - integration: 集成/端到端流程测试（模块间接口契约）
  - llm: LLM 相关测试（需 API key 配置）
  - edge: 边缘/异常场景测试
  - smoke: 冒烟测试（快速验证核心功能）
  - data: 数据正确性验证测试

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
    config.addinivalue_line("markers", "scenario_extended: 扩展业务场景（S6-S10）")
    config.addinivalue_line("markers", "scenario_llm: LLM 场景组合（S11-S20）")
    config.addinivalue_line("markers", "scenario_datetime: 日期/时间场景（T1-T16）")
    config.addinivalue_line("markers", "unit: 单元测试总标记")
    config.addinivalue_line("markers", "unit_providers: 数据源提供商单元测试")
    config.addinivalue_line("markers", "unit_fetcher: 数据获取调度单元测试")
    config.addinivalue_line("markers", "unit_llm: LLM 模块单元测试")
    config.addinivalue_line("markers", "unit_news: 新闻模块单元测试")
    config.addinivalue_line("markers", "unit_report: 报告生成单元测试")
    config.addinivalue_line("markers", "unit_config: 配置管理单元测试")
    config.addinivalue_line("markers", "unit_core: 核心基础设施单元测试")
    config.addinivalue_line("markers", "unit_ui: TUI/UI 交互单元测试")
    config.addinivalue_line("markers", "integration: 集成/端到端流程测试（模块间接口契约）")
    config.addinivalue_line("markers", "llm: LLM 相关测试（需 API key）")
    config.addinivalue_line("markers", "edge: 边缘/异常场景测试")
    config.addinivalue_line("markers", "smoke: 冒烟测试（快速验证核心功能）")
    config.addinivalue_line("markers", "data: 数据正确性验证测试")
