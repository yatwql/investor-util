# 环境耗时对照文档自动更新（`--update-docs`）

## Context

上一轮为 `test_runner.py` 新增了 `--mode bench --machine-info`：跑 14 模式并打印环境属性表 + 耗时表，但**结果是打印输出、需手工粘贴**进 `test-coverage.md` 的「环境耗时对照」，且脚本表格结构与文档表格列不一致（脚本环境表 13 行/合并 OS 与系统版本；文档 14 行分列）。用户希望**跑完自动更新文档**。

**用户已定方向**：① 并排表格·按主机名增列（新机器自动加列，同机覆盖刷新）；② 显式 `--update-docs` 标志（隐含 `--machine-info`，默认永不写文档）。

## 方案

### 1. test-coverage.md 加标记 + 预改名

两张表各包一对 HTML 注释标记（独占一行、紧贴表格、中间不夹空行）：

- 环境属性表：`<!-- env-table:start -->` … `<!-- env-table:end -->`
- 耗时对照表：`<!-- duration-table:start -->` … `<!-- duration-table:end -->`

同时把两张表表头 `当前开发机（2026-08-05 实测）` 预改为 `dragonball（2026-08-05 实测）`——脚本按主机名子串匹配列，预改名后首次 `--update-docs` 即命中同名列原地刷新，不产生孤儿列。

### 2. scripts/test_runner.py

**`parse_args()`**：新增 `--update-docs`（action="store_true"）；`parse_args` 内 `if args.update_docs: args.machine_info = True`（便于单测直接验证隐含逻辑）。`_HELP_TEXT` 用法块 + 选项块各加一行。

**环境表统一 14 行**（修正 stdout 与文档不一致，供渲染与文档写入共用单一事实源）：
- 新增 `_ENV_ATTR_LABELS`（14 项：操作系统/系统版本/架构/主机名/CPU 型号/物理核数/逻辑线程/内存/磁盘类型/文件系统/Python 版本/并行级别/worker 数/采集日期）
- 新增 `_env_value(label, info) -> str | None`（未知属性返回 None；系统版本单列）
- 重构 `_render_env_table` 遍历 14 标签。现有测试 `test_render_env_table_has_all_rows` 断言的 13 个标签全部保留 → 不破坏，仅需补 `"系统版本"` 断言。

**文档写入器**（纯函数，置于 `_print_machine_report` 之后）：
- `_DOC_ENV_TABLE_MARKERS` / `_DOC_DURATION_TABLE_MARKERS` / `_DOC_COVERAGE_PATH`（用现有 `_PROJECT_ROOT`）
- `_duration_mode_cells(results) -> dict[str, str]`：按 `_MODE_TABLE_ORDER` 聚合 `~{N}s` 单元格；组合行 `verify,regression` = 顺序耗时之和，格式 `~{N}s（verify+regression 顺序之和）`；超时/未测模式缺席
- `_format_approx_duration(seconds)`：≥60s 显示 `~{M}min`，否则 `~{N}s`（慢机器可读性；对齐文档旧列风格）
- `_find_machine_column(header_row, hostname) -> int|None`：表头 token 网格子串匹配主机名（天然豁免旧笔记本列）
- `_new_separator_cell(last_sep)`：由最后数据列分隔标记推断 `:---:`（居中）/`:---`（左对齐），一个函数覆盖两张表
- `_update_machine_table(table_lines, header_cell, row_value: Callable[[str], str|None])`：token 网格增/改列。同名列 → 只改表头（刷新日期）+该列数据格；新列 → 表头插入、分隔行补对齐标记、每数据行插一格（未测/None 留空格）。未改动列字节原样保留
- `_table_region_pattern` / `_extract_table_region` / `_replace_table_region`：`re.subn(count=1)` 定位/替换标记间区域，marker 缺失或非表格结构抛 `ValueError`（沿用 `check-version-consistency.py` 的 `re.subn` 习语）
- `_update_test_coverage_doc(doc_text, machine_info, results) -> str`：纯函数总入口，先环境表后耗时表
- `_update_test_coverage_doc_file(machine_info, results)`：读文件 → 调纯函数 → 仅内容变化才 `write_text`；缺标记/异常打印 `[ERR]` 返回，绝不破坏既有文档
- 需在 import 区新增 `from typing import Callable`

**`main()` 接线**：
- 特性横幅：`if args.update_docs: print("  [..] 文档更新: 开启（…）")`
- 正常路径：`_print_machine_report` 之后、`sys.exit(overall)` 之前，`if args.update_docs and machine_info is not None: _update_test_coverage_doc_file(...)`
- `KeyboardInterrupt` 路径：`results` 非空时也写文档（部分结果走 None 保留未测单元格），否则不写

### 3. 测试

**新建 `src/test/unit/scripts/test_test_runner_doc_writer.py`**（pytestmark `[unit, unit_scripts]`，复用 `_load_script` 加载模式），约 16 项：
1. 环境表同名列原地更新 + 日期刷新 + 列数不变
2. 操作系统/系统版本分行、14 行齐全
3. 环境表新机器列追加（表头 + 14 格 + 分隔行 `:---`）
4. 未知行标签（如自定义行）该列保留原值
5. 耗时表同名列更新 `~{N}s`、未测模式保留
6. 耗时表新列追加、未测留空格、分隔行 `:---:`
7. 组合行 `verify,regression` 格式 + 取整/下限
8. 部分结果（仅 unit/regression/verify）其余模式保留不清空
9. start marker 缺失 → `ValueError`，文本不改写
10. end marker 缺失 → `ValueError`
11. round-trip 幂等（二次相同输入输出不变）
12. 标记区外文本逐字节不变
13. `_update_test_coverage_doc_file` 仅内容变化才写盘（monkeypatch 路径到 tmp_path）
14. `parse_args` `--update-docs` 隐含 `--machine-info`
15. `_env_value` 格式与未知回退
16. `_duration_mode_cells` 跳过超时/live、无 verify 时无组合行

现有 `test_test_runner_machine_info.py`：`test_render_env_table_has_all_rows` 标签元组补 `"系统版本"`。

### 4. 文档同步（同一提交）

- `test-coverage.md`：两对 marker、表头预改名、第 27/35 行注追加 `--update-docs` 说明、计数行按 `collect-test-coverage.py` 实测回填（unit/standard/verify/dev-verify/all/unit_scripts）、第 141 行 unit_scripts 描述补"环境耗时对照文档自动更新"
- `scripts-reference.md`：用法块 + 注追加 `--update-docs`
- `changelog.md`：`[0.10.6-dev]` 下新增条目
- `folders.md`：目录树新增 `test_test_runner_doc_writer.py` 行（`test_test_runner_machine_info.py` 前缀 `└──`→`├──`）、辅助脚本行数 += test_runner 新增行数、测试代码文件数 283→284、测试用例数按 collect 实测更新

## 关键文件

- `scripts/test_runner.py`（核心：写入器 + 接线 + 环境表 14 行）
- `src/test/unit/scripts/test_test_runner_doc_writer.py`（新建，16 项测试）
- `src/test/unit/scripts/test_test_runner_machine_info.py`（补 1 断言）
- `docs-stm/managements/test-coverage.md` / `scripts-reference.md` / `changelog.md` / `folders.md`

## 实施顺序（TDD）

1. 新建测试文件 + 补断言 → 跑新文件预期失败（红）
2. 实现 `_ENV_ATTR_LABELS`/`_env_value` + 重构 `_render_env_table`（绿）
3. 实现 `_duration_mode_cells`/`_format_approx_duration`
4. 实现文档写入器整段
5. 接线 parse_args/`_HELP_TEXT`/main() 三处
6. 文档同步（marker/预改名/notes/changelog/folders/计数回填）
7. 门禁验证 + 提交

## 验证

```bash
.venv/bin/python -m py_compile scripts/test_runner.py src/test/unit/scripts/test_test_runner_doc_writer.py
.venv/bin/python -m pytest src/test/unit/scripts/test_test_runner_doc_writer.py src/test/unit/scripts/test_test_runner_machine_info.py -q
.venv/bin/python scripts/test_runner.py --mode dev-verify            # P0 门禁
.venv/bin/python scripts/check-code-traces.py --ci                   # P0 门禁
.venv/bin/python scripts/check-doc-traces.py --ci                    # P0 门禁
.venv/bin/python scripts/check-task-numbering.py --ci                # P0 门禁
.venv/bin/python scripts/collect-test-coverage.py                    # 取计数回填文档
# 手动冒烟：--mode smoke --update-docs 观察 [OK] 更新提示 + test-coverage.md 表格列刷新/新增
```

`check-test-markers.py --ci` 已知 5 处 pre-existing 失败（`test_live_*/test_cli_integration.py`），与本改动无关。语义命名：新标识符全部语义名，无任务代号/字母+数字，注释中文。
