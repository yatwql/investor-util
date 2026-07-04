# CLAUDE.md

## Project

个人投资分析报告生成小助手：读取持仓 Excel → 生成 Excel/HTML 报告（含行情、穿透、基金业绩、财经新闻热点与持仓关联分析、LLM 全球政经局势/智囊团深度复盘）。

## Conventions

- **默认分支**：`master`
- **语言**：中文（UI、报错、报告内容）
- **日志**：`logging` → `logs/app.log` + console（INFO / WARNING / ERROR）
- **测试**：`src/test/test_*.py`，执行 `pytest src/test/`
  - **提交前门禁（P0）**：必须通过 `python scripts/test_runner.py --mode regression`（222 项业务场景，~30s），否则不得 commit
  - **合入门禁（P1）**：合并到 master 前必须通过 `python scripts/test_runner.py --mode verify`（场景+核心模块 838 项，~49s），否则不得 merge
  - **发布门禁（P2）**：发布版本前必须通过 `python scripts/test_runner.py --mode all`（全量 2244 项，~待测），否则不得 release
- **缺陷自测**：发现并修复缺陷时，**必须**为该缺陷编写可自测的回归测试用例，避免再次回退。新增功能时，**必须**同步编写测试用例覆盖。测试用例应直接验证缺陷场景的具体断言，而非仅测正常路径。
- **测试标记强制**：所有新增/修改的测试用例（测试类或测试方法）**必须**标注对应的 pytest marker（如 `@pytest.mark.unit_providers`、`@pytest.mark.scenario_basic` 等），marker 定义见 `src/test/conftest.py` 的 `pytest_configure`。新增 marker 需同步注册到 `conftest.py` 和维护文档。
- **自审记录**：自查发现的所有问题 **必须** 先记录到 `docs-stm/managements/review-findings.md`，标注状态（待处理/已完成）。待办区允许非空（有未修复问题属正常）。修复后 **立即** 从 review-findings.md 中移除该条详细说明（仅保留摘要行），变更记录移至 `docs-stm/managements/changelog.md`。
- **目录结构同步**：新增/重命名任何非排除文件或目录时，**必须**同步更新 `docs-stm/manuals/datasource-and-folders.md` 中的目录树，并确保每个文件都有简短说明。排除项：`.git/`、`.claude/`、`.venv/`、`.pytest_cache/`、`data/cache/`、`docs-stm/tmp/`、`logs/`、`reports/`。目录树使用 `├──`/`└──` 层级符号，`__init__.py` 标注为"包标记（空文件）"或"子包标记（空文件）"。`docs-stm/test-reports/latest/` 的子目录（`unit/`、`scenario/`、`integration/`、`regression/`、`edge/`、`all/`）需逐行说明，汇总文件 `index.html` 需标注其作用；`archives/` 下一级仅需一行描述，`<YYYYMMDD>/` 子目录不展开。
- **管理文档**：`docs-stm/managements/`（plan.md, requirements.md, technical.md, testplan.md, review-findings.md, changelog.md,test-coverage.md）
- **用户文档**：`README.md`（总入口）+ `docs-stm/manuals/`（分册：how-to-start.md, how-to-config.md, how-to-config-llm.md, how-to-use-registry.md, datasource-and-folders.md, reports-instruction.md, faq.md,how-to-test-my-code.md）
- **中间文件**：中间过程及设计文件 → `docs-stm/plan/`；除日志以外的临时文件 → `docs-stm/tmp/`。禁止放在全局 `.claude/` 目录下
- **UI 输出前缀**：`[..]`（进行中）、`[OK]`（成功）、`[!]`（部分失败）、`[ERR]`（错误）

## 持仓文件格式

每 worksheet = 一个账户；固定 4 列（名称、代码、持仓份额、每份成本），列名不可配置。

## 技术要点

- **缓存**：`data/cache/` JSON 文件，`src/python/cache.py` 统一管理，按前缀匹配 TTL
- **数据源**：腾讯/东方财富（价格）、天天基金（净值/排名/持仓）、新浪/东方财富/财联社（新闻）
- **LLM**：`src/python/llm/` 支持 `provider: "claude"`（含 DeepSeek Anthropic 兼容端点）和 `"openai"`
