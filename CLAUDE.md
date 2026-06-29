# CLAUDE.md

## Project

Python TUI 投资分析工具：读取持仓 Excel → 生成 Excel/HTML 报告（含行情、穿透、基金业绩、新闻关联、LLM 宏观/复盘分析）。

## Conventions

- **语言**：中文（UI、报错、报告内容）
- **日志**：`logging` → `logs/app.log` + console（INFO / WARNING / ERROR）
- **测试**：`src/test/test_*.py`，执行 `pytest src/test/`
- **缺陷自测**：发现并修复缺陷时，**必须**为该缺陷编写可自测的回归测试用例，避免再次回退。新增功能时，**必须**同步编写测试用例覆盖。测试用例应直接验证缺陷场景的具体断言，而非仅测正常路径。
- **管理文档**：`docs-stm/managements/`（plan.md, requirements.md, testplan.md, changelog.md）
- **用户文档**：`README.md`（项目根目录）
- **中间文件**：中间过程及设计文件 → `docs-stm/plan/`；除日志以外的临时文件 → `docs-stm/tmp/`。禁止放在全局 `.claude/` 目录下
- **UI 输出前缀**：`[..]`（进行中）、`[OK]`（成功）、`[!]`（部分失败）、`[ERR]`（错误）

## 持仓文件格式

每 worksheet = 一个账户；固定 4 列（名称、代码、持仓份额、每份成本），列名不可配置。

## 技术要点

- **缓存**：`data/cache/` JSON 文件，`src/python/cache.py` 统一管理，按前缀匹配 TTL
- **数据源**：腾讯/东方财富（价格）、天天基金（净值/排名/持仓）、新浪/东方财富/财联社（新闻）
- **LLM**：`src/python/llm_client.py` 支持 `provider: "claude"`（含 DeepSeek Anthropic 兼容端点）和 `"openai"`
