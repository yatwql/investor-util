# CLAUDE.md

## Project

Python TUI 投资分析工具：读取持仓 Excel → 生成 Excel/HTML 报告（含行情、穿透、基金业绩、新闻关联、LLM 宏观/复盘分析）。

## Conventions

- **语言**：中文（UI、报错、报告内容）
- **日志**：`logging` → `logs/app.log` + console（INFO / WARNING / ERROR）
- **测试**：unittest 毗邻源文件（`src/test_*.py`），执行 `pytest src/`
- **管理文档**：`docs-stm/managements/`（plan.md, requirements.md, testplan.md, changelog.md）
- **中间文件**：计划/设计文档 → `docs-stm/plan/`；临时/过程文件 → `docs-stm/tmp/`。禁止放在全局 `.claude/` 目录下
- **UI 输出前缀**：`[..]`（进行中）、`[OK]`（成功）、`[!]`（部分失败）、`[ERR]`（错误）

## 持仓文件格式

每 worksheet = 一个账户；固定 4 列（名称、代码、持仓份额、每份成本），列名不可配置。

## 技术要点

- **缓存**：`data/cache/` JSON 文件，`src/cache.py` 统一管理，按前缀匹配 TTL
- **数据源**：腾讯/东方财富（价格）、天天基金（净值/排名/持仓）、新浪/东方财富/财联社（新闻）
- **LLM**：`llm_client.py` 支持 `provider: "claude"`（含 DeepSeek Anthropic 兼容端点）和 `"openai"`
