# 首次运行引导实施（plan-9）

> **📦 已归档**：plan-9（首次运行引导）实施细节已于 2026-08-03 完成（v0.9.7 发布）并归档至本目录，与设计文档 `plan-first-run-wizard.md` 同目录。
> 原计划：`docs-stm/plan/plan-implement-2-3-9.md` §4（该实施总纲已按内容拆分：plan-2/3 归入 `correlation-drawdown/`，plan-9 归入本目录）。

## Context（背景）

plan-9 是"分析功能基础增强"批次的第三项，作为**总体架构视角**的独立实施条目（与前两项共享 P0 门禁/测试隔离约定，但不涉及 `analysis/` 层新计算模块）。

- **plan-9 首次运行引导** — 首次运行检测缺失资源并交互式引导

## plan-9 首次运行引导

### 4.1 新建 `src/python/startup_wizard.py`（镜像 `report/privacy_notice.py` 范式）

- 配置标记键 `_startup_wizard_shown`（同 `_privacy_notice_shown`），`is_first_run()` / `mark_wizard_shown()` / `show_startup_wizard_if_needed()`
- 检测函数 `_detect_startup_state(config)` → dict：`holdings_ok`（`holdings_dir` 下存在 xlsx，经 `reader.list_xlsx_files`）、`llm_key_ok`（`llm_key.json` 存在 **或** `llm_providers.json` 有 providers，读取复用 `_load_llm_providers`/`get_llm_config`）、`llm_degraded`（provider=claude 但无 key）
- 交互式引导流程（TUI 内执行，仿隐私提示边框）：
  ```
  config.json → init_config 已自动创建，无需处理（打印提示即可）
  ├── llm_key.json 缺失 → 提示 跳过/输入 Key（输入则经 _atomic_write 原子写 flat llm_key.json：provider/api_key/model/endpoint，C3）
  ├── holdings/ 为空 → 提示放置持仓文件（引导到 how-to-start.md 持仓格式章节）
  ├── LLM=claude 无 key → 降级提示（报告对应页签将显示占位）
  └── 全部就绪 → 打印 "一切就绪，开始生成报告！"
  ```
- **非交互检测**：`sys.stdin.isatty()` 为 False、环境变量 `CI`/`NON_INTERACTIVE` 存在、或 CLI 传 `--non-interactive` → **跳过交互**，仅日志记录，不阻塞（设计文档风险项）

### 4.2 接线

- `tui/tui.py` `main()`（L143 隐私提示旁）：`show_startup_wizard_if_needed()` 包 try/except
- `cli/cli.py`：`_build_parser`（L31）新增 `--non-interactive` 参数；`main()`（L326）`init_config` 后按 `args.non_interactive` 调 `show_startup_wizard_if_needed()`
- 现有 `tui_menu.print_header()`（L85）"首次使用指引" 保留（非阻塞提示），两者不冲突

## 测试计划

> 全部新测试**必须标注 marker**（conftest 已注册）；edge 用例放 `*_edge.py`；LLM/网络调用全 mock；pipeline 测试重定向 output_dir 到 tmp。

### 新增
| 文件 | marker | 覆盖 |
|---|---|---|
| `src/test/unit/startup/test_startup_wizard.py` | `[unit, unit_ui]` | 状态检测、首次标记、交互 mock、非交互跳过 |

## 文档维护（CLAUDE.md 强制项）

- `docs-stm/managements/plan.md`：plan-9 标记完成
- `folders.md`：目录树新增 `startup_wizard.py` 及测试文件
- `testplan.md` / `test-coverage.md`：登记新测试项
- `changelog.md`：`[0.9.7-dev]` 下 1 条 `### Feat` 条目（首次运行引导）

## 验证（P0 门禁）

1. 单测：`python -m pytest src/test/unit/startup/test_startup_wizard.py -v --tb=short`
2. 失败用例提取：`python scripts/extract-test-failures.py`
3. 提交前门禁：`python scripts/test_runner.py --mode dev-verify` + `python scripts/check-history-traces.py --ci`
4. 手动烟测：真实首次运行（清空 config/holdings）验证引导展示与 `--non-interactive` 跳过
5. `ruff format --check`（非阻塞，可 `ruff format` 自动修复）
