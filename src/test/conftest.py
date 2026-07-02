"""conftest.py — 全局 pytest 配置与标记注册。

标记分组（支持 -m 选择运行）：
  - scenario: 业务场景集成测试（S1-S20），执行较慢
  - llm: LLM 相关测试（需 API key 配置）
  - datetime: 日期/时间/交易时段测试（T1-T16）
  - edge: 边缘/异常场景测试
  - smoke: 冒烟测试（快速验证核心功能）
  - data: 数据正确性验证测试

用法：
  cd D:/codebase/zoo/investor-util
  pytest src/test/ -m "smoke"                                    # 仅冒烟
  pytest src/test/ -m "not llm"                                  # 排除 LLM
  pytest src/test/ -m "smoke or edge"                            # 冒烟 + 边缘
  pytest src/test/                                             # 全量运行
"""

from __future__ import annotations


def pytest_configure(config):
    """注册自定义标记，避免 pytest 警告。"""
    config.addinivalue_line("markers", "scenario: 业务场景集成测试（S1-S20）")
    config.addinivalue_line("markers", "llm: LLM 相关测试（需 API key）")
    config.addinivalue_line("markers", "datetime: 日期/时间/交易时段测试（T1-T16）")
    config.addinivalue_line("markers", "edge: 边缘/异常场景测试")
    config.addinivalue_line("markers", "smoke: 冒烟测试（快速验证核心功能）")
    config.addinivalue_line("markers", "data: 数据正确性验证测试")
