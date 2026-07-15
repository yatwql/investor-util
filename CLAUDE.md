# CLAUDE.md

## Project

个人投资分析报告生成小助手：读取持仓 Excel → 生成 Excel/HTML 报告（含行情、穿透、基金业绩、财经新闻热点与持仓关联分析、LLM 全球政经局势/智囊团深度复盘）。

## Conventions

- **默认工作分支**：`dev`（日常开发、提交均在此分支）
- **发布分支**：`master`（仅从 dev 合并，打版本标签后发布）
- **语言**：中文（UI、报错、报告内容）
- **日志**：`logging` → `logs/app.log` + console（INFO / WARNING / ERROR）
- **测试**：`src/test/test_*.py`，执行 `pytest src/test/`
  - **提交前门禁（P0）**：必须通过 `python scripts/test_runner.py --mode regression`（业务场景快速验证），否则不得 commit
  - **合入门禁（P1）**：合并到 master 前必须通过 `python scripts/test_runner.py --mode verify`（场景+核心模块），否则不得 merge
  - **发布门禁（P2）**：发布版本前必须通过 `python scripts/test_runner.py --mode all`（全量测试），否则不得 release
- **缺陷自测**：发现并修复缺陷时，**必须**为该缺陷编写可自测的回归测试用例，避免再次回退。新增功能时，**必须**同步编写测试用例覆盖。测试用例应直接验证缺陷场景的具体断言，而非仅测正常路径。
- **测试标记强制**：所有新增/修改的测试用例（测试类或测试方法）**必须**标注对应的 pytest marker（如 `@pytest.mark.unit_providers`、`@pytest.mark.scenario_basic` 等），marker 定义见 `src/test/conftest.py` 的 `pytest_configure`。新增 marker 需同步注册到 `conftest.py` 和维护文档。
- **边缘测试文件隔离**：edge 场景测试（`@pytest.mark.edge`）**必须**放置在 `*_edge.py` 文件中，不得与普通测试混搭在同一文件。`conftest.py` 的 `pytest_collection_modifyitems` 会在收集期自动校验此约束。
- **测试隔离**：运行测试时**不得**修改用户的配置文件（`data/config/`）、持仓文件（`data/holdings/`）等敏感数据。`src/test/conftest.py` 中的 `_isolate_sensitive_paths` autouse fixture 会自动将 `config.json` 和缓存目录重定向到临时目录。测试用例应使用 mock 或临时文件隔离，避免污染真实数据。
- **自审记录**：自查发现的所有问题 **必须** 先记录到 `docs-stm/managements/review-findings.md`，标注状态（待处理/已完成）。待办区允许非空（有未修复问题属正常）。修复后 **立即** 从 review-findings.md 中移除该条详细说明（仅保留摘要行），变更记录移至 `docs-stm/managements/changelog.md`。
- **目录结构同步**：新增/重命名任何非排除文件或目录时，**必须**同步更新 `docs-stm/managements/folders.md` 中的目录树，并确保每个文件都有简短说明。排除项：`.git/`、`.claude/`、`.venv/`、`.pytest_cache/`、`data/cache/`、`docs-stm/tmp/`、`logs/`、`reports/`。目录树使用 `├──`/`└──` 层级符号，`__init__.py` 标注为"包标记（空文件）"或"子包标记（空文件）"。`test-reports/` 是自动生成目录，只需在目录树中保留一行描述，不展开子目录。
- **管理文档**：`docs-stm/managements/`（plan.md, requirements.md, technical.md, llm-technical.md, testplan.md, review-findings.md, changelog.md, test-coverage.md, folders.md）
- **用户文档**：`README.md`（总入口）+ `docs-stm/manuals/`（分册：how-to-start.md, how-to-menu.md,how-to-config.md, how-to-config-llm.md, how-to-use-registry.md, datasource.md, reports-instruction.md, faq.md, how-to-test-my-code.md）
- **文件归属三原则**：
  - **中间计划文件**（设计方案、迭代计划、架构决策）→ `docs-stm/plan/`
  - **运行时临时文件**（除log以外的临时输出、调试产物、缓存转储）→ `docs-stm/tmp/`
  - **`.claude/` 全局目录** — 只存放 Claude Code 工具自动管理的运行时数据（sessions/tasks/file-history 等），**禁止主动写入**任何文件（包括记忆/memory/、计划/plans/、临时数据等）
- **自检清单（文件写入前必答）**：
  1. 这个文件是项目源码/配置/文档？→ 放仓库对应路径
  2. 是中间计划？→ `docs-stm/plan/`
  3. 是运行时临时产物？→ `docs-stm/tmp/`
  4. 以上都不是，想放 `.claude/`？→ **停，不允许，重新分类**
- **违规补救**：发现 `.claude/` 下出现本应放在 `docs-stm/` 的文件时，**必须立即迁移**，不留存待办
- **注意**：`EnterPlanMode` 等工具自动写入 `.claude/plans/` 的行为不可控，使用后**必须手动迁移**到 `docs-stm/plan/`
- **版本号一致**：发布版本时，先修改 `src/python/constants.py`（`APP_VERSION`），然后运行 `python scripts/check-version-consistency.py`，按 [ERR] 提示逐个同步其余文件，直到全部 [OK] 再提交。受检文件：`README.md`、`pyproject.toml`、4 份管理文档头部、`how-to-test-my-code.md`、`changelog.md`。任何版本号变更均应全局覆盖，避免遗漏。
- **版本标签**：发布版本时，完成版本号更新并提交后，**必须**执行 `git tag v{版本号}` 打标签并 `git push origin --tags`，确保每次发布都可追溯。
- **UI 输出前缀**：`[..]`（进行中）、`[OK]`（成功，绿色）、`[!]`（部分失败/告警，黄色）、`[ERR]`（错误，红色）。终端不支持颜色时自动降级。
- **架构遵从**：所有模块必须遵守 `docs-stm/managements/technical.md` 中「#2-核心架构原则与设计决策」（代码类型判定中心化 C1、Provider Chain 必经 C6、缓存统一管理 C2/C3、报告配置化 C7/C14、数据降级治理体系）和「#9-架构设计约束」（C1~C15 含会话级复用缓存 C4、测试标记强制 C11、边缘测试文件隔离 C12 等），新增/修改代码不得违反。

## 持仓文件格式

每 worksheet = 一个账户；固定 4 列（名称、代码、持仓份额、每份成本），列名不可配置。

## 技术要点

- **缓存**：`data/cache/` JSON 文件，`src/python/cache.py` 统一管理，按前缀匹配 TTL
- **LLM**：`src/python/llm/` 支持 `provider: "claude"`（含 DeepSeek Anthropic 兼容端点）和 `"openai"`
