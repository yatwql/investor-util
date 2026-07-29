"""LLM 客户端模块单元测试 — 已拆分为子模块。

本文件的所有测试类已按主题拆分到以下子文件：

  - test_llm_analysis.py              — LLM 新闻关联分析
  - test_llm_api.py                   — API 调用、熔断器、回退、content_filter
  - test_llm_content.py               — LLM 内容 Excel 写入
  - test_llm_generators.py            — generate_all_llm、缓存预检、llm_config 传递
  - test_llm_placeholder.py           — 占位文本常量
  - test_llm_placeholder_distinction_edge.py — 占位文本区分（edge）
  - test_llm_prompts.py               — 提示词构建
  - test_llm_session.py               — 会话统计
  - test_llm_utils.py                 — 工具函数（markdown、指纹、TTL、thinking 等）

请直接运行对应子文件：
  python -m pytest src/test/unit/llm/test_llm_<模块名>.py -v
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]
