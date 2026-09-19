# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.11.2-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### 修复 full 路径 HTML 漏接市场情绪契约（2026-09-18，rf-402）

**背景**（用户反馈）：「同花顺，市场情绪没开启么？我看数据可用性矩阵没提到它」。排查确认**开关与 key 均无问题**（`features.json` 已开 `market_sentiment`、hithink key 就绪、`data/cache/sentiment_*` 本次已由同花顺接口刷新），而是 full 路径的 HTML 端接线遗漏。

**现象**：同一次运行的两份产物自相矛盾——xlsx「15.数据源可用性矩阵」有 `市场情绪 | ✅ 正常 | 同花顺金融数据 ×2`、说明表「✅ 已使用」；HTML 两者皆无（矩阵缺该行、说明表「○ 未使用」），情绪区块也不渲染。

**根因**：`report/_report_generation.py::_generate_report_full` 未取数/未注入 `market_sentiment_data`，且 `_generate_full_html_report` 无该形参、其 `write_html_report` 调用未传参；Excel 侧靠 `report/excel_generator.py` 的「就地兜底」在 **HTML 落盘之后**才触发取数（`logs/app.log`：HTML 20.126 → 情绪取数 20.419/20.799 → Excel 21.032）。矩阵只列**本次取用过的类别**，故取数前生成的 HTML 自然缺行。

**变更**：
- 编排层在写 HTML 之前取数并注入 `pipeline_data`（位置与 both 路径一致：`record_prosperity_diagnosis` 之后、`# ── 6. HTML 报告 ──` 之前），并透传 `prep` 以带出穿透标的（与该路径 Excel 的穿透口径一致）
- `_generate_full_html_report` 新增 `market_sentiment_data` 形参并透传 `write_html_report`（HTML 与 Excel 从此同源同序）
- Excel 就地兜底保留（basic 路径不经编排层；注释「full/both 由编排层注入」自此属实）
- 回归用例 2 例（`test_market_sentiment_wiring.py::TestFullPathInjection`：编排注入 / HTML 生成器透传），已实测对修复前代码两者均失败

**验证**：修复前后各跑一次两例（修复前 `assert None is {...}` / `TypeError: unexpected keyword argument` 失败，修复后通过）；`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` 四个 `--ci` 脚本全 [OK]。

### 文案与实现对齐：市场情绪块的描述口径 + 报告组开关计数（2026-09-19，rf-403、rf-404）

**触发**：用户追问「情绪价值会出现在报告的哪个部分？我没看到」。实测确认区块已正常出现（HTML 行动建议章 ⑦ 号内嵌块 / Excel「7.行动建议」页签），只是当日 0 命中——而两份手册恰好把这种情况写反了，所以先修文档。

**两类文案与实现不符**：
- **位置**：`features.py` 的 `market_sentiment` 开关描述写「**新增独立章**」（初稿形态），实际是行动建议章内嵌块——该偏离在设计文档归档里已记录，只是开关描述未随之更新；它恰是功能开关面板/菜单里展示给用户的文字
- **零命中行为**：`data_source_matrix.py` 说明表、`how-to-config.md`、`datasource.md` 三处写「**无命中时该区块不显示/不渲染**」，而实现是**零命中仍渲染**（标题 + 市场概览 + 「（当日无持仓/穿透标的命中龙虎榜或连板梯队）」+ 口径脚注）——两句话叠加，正好把“功能正常、只是无事件”误读成“没开启”
- **报告组开关计数**（rf-400 同类漏改）：`how-to-use-tui-menu.md`（共 29 项 / 报告组 8 项 + 两处清单漏 `market_sentiment`）、`how-to-config.md`（子模块枚举漏）、`folders.md`（28 项 / 8 项）——实况 **30 项（⚗5 / 常规 16 / 报告组 9）**

**变更**：四处描述口径按实现改正（并把“怎么排查是否已取到数”写进手册：矩阵「市场情绪」行 + 说明表「本次使用」+ `logs/app.log` 的 `[market_sentiment] 命中 N 条`）；四处计数/清单按 `feature_switch_registry` 实况更正并补 `market_sentiment`。

**验证**：`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；四个 `--ci` 脚本全 [OK]。

### 文档与实现全量核对：4 类共 28 处不一致修订（2026-09-19，rf-405~rf-408）

**触发**：用户要求「核对管理文档和用户文档，比对程序和配置文件，查看有没有不一致的地方，要修订」。

**核对口径**：以注册表（`feature_switch_registry` / 章节注册表 `_REPORT_SECTION_DEFAULT` / 数据模块缓存注册表）、`data/config/config.json` + `_DEFAULT_CONFIG`、文件系统、`pytest --collect-only`（`scripts/collect-test-coverage.py`）为事实源，逐条比对 11 份用户文档（README + manuals 10）+ 10 份管理文档。审计脚本（`docs-stm/tmp/audit_phase{1..7}.py`，gitignore）按「提取代码侧事实 → 反向扫文档断言」两面跑。

**修订四类**：
- **统计快照过期（rf-405，12 处）**：`test-coverage.md` 的 unit/standard/all/report/unit 父标记/unit_report/功能域「报告生成」与实测差 2（rf-402 新增的回归用例未回填）；`folders.md` 的主程序与测试代码行数、测试用例数、managements/项目文档行数未随代码与文档变动刷新（含「源代码合计」联动）
- **目录树漏登 9 个文件（rf-406）**：`folders.md` 未随新增文件同步（`fetcher/financial_indicator.py` + 8 个测试文件）→ 按所属子包位置补条目并附职责说明（取自各文件 docstring）；补后重核「实际有而树内缺 0 / 树内有而磁盘无 0」
- **TUI `[S]` 面板编号表与分组实况脱节（rf-407）**：实验块只列 4 项（缺 ⚗ 景气度框架诊断）、常规块 10-25 未随实验组扩容后移、报告块未编号、三处「第 23 项」位置引用失准、`how-to-use-web-mode.md` 实验清单缺项——而编号本是 `handlers_config.py` 从分组与注册表顺序**派生**（设计上非硬编码）→ 按实况重编（实验 6-10 / 常规 11-26 / 报告 27-35）
- **零星数值/表述（rf-408，3 处）**：`requirements.md` 页签编号 1~19 与默认顺序 19 项（实况 17 个报告章节）；`technical.md` 功能语义命名表中 `market_temperature` 标为默认关（实况默认开）；`testplan.md` 「白名单 7 组」→「7 个可编辑面（功能开关面拆两块）」

**核对为一致（未改）**：30 项开关分组计数与清单、报告章节表（17 项）与 Excel sheet 名、13 份版本头（`check-version-consistency`）、`how-to-config.md` 标量默认值表与 `_DEFAULT_CONFIG`、缓存 TTL 表与 LLM 默认 `max_tokens`/`timeout`、CLI 7 个子命令、`providers/` 与数据源清单路由、测试标记与 conftest；另有 2 类扫描报警经核实为误报（`market_temperature_data` 契约名被前缀匹配、`how-to-config.md` 中非开关表被当成开关表），未改。

**验证**：`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；四个 `--ci` 脚本全 [OK]。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.1（2026-09-15 ~ 2026-09-18）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
