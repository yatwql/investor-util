# 投资复盘助手 — 实现计划
> 文档版本：0.10.13-dev
> **编号源**：`plan-next = 29`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-28，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：投资功能优化 + 章节归并（目标 19 章）**已全部完成并发布**（P1 轮 1~11 + 阶段 D~G 轮 12~20，plan-17~plan-24，changelog v0.10.1/v0.10.3/v0.10.4）。详细设计、实施轮次、推荐实施顺序与发布门禁记录见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)（含设计文档索引：`plan-investment-features.md` 设计层 §4 章节归并方案与 §4.4 架构合规自查表 + `plan-investment-iteration.md` 实施层 21 轮每轮量化验收 + 已完成项摘要表 + 推荐实施顺序 ①~⑧ + P0 发布门禁记录）。本文档当前仅收录**未完成计划项**（P4 实验功能）与归档引用。

> **命名纪律（强制）**：重构/新增的变量名、函数名、注释与文档表述必须与新章节语义相关（如 `position_relationship`/`portfolio_history_drawdown`/`style_factor`/`action`），**绝对禁止用任务编号命名**（F 系列、plan-N、rf-N 等）。任务编号仅在本表作链接锚点，不进入实现层。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪 · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

**当前无 P0~P3 待办**（v0.10.x 已完成事项记录已整体归档至 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)：P0 发布门禁、推荐实施顺序 ①~⑧、P1~P3 已完成项详细段落）。

### P4 — 实验功能

> 实验性功能，缺省关闭，需通过配置项或 features.json 显式启用。启用不影响现有功能稳定性。**当前实验项**：日志可视化、轻量 Web UI（独立于本迭代，选做，无排期）。

#### `plan-10` 日志可视化（[`plan-web-ui.md §2`](../archive/v0.10.x/web-ui/plan-web-ui.md#2-日志可视化)）

结构化日志查看（`--view-logs` 命令 + 报告尾部数据源状态表）。**预估：1d**

#### `plan-8` 轻量 Web UI（[`plan-web-ui.md §1`](../archive/v0.10.x/web-ui/plan-web-ui.md#1-轻量-web-ui)）

Flask/FastAPI + 上传页面 + 触发管线 + 结果预览/下载。MVP 不做多用户/LLM 在线修改/实时日志流。**运维与安全成本最高，单人工具需谨慎，选做。**

> 详细评估与实施拆分见 [`plan-web-ui-implementation.md`](../archive/v0.10.x/web-ui/plan-web-ui-implementation.md)（收益/风险/架构约束符合性/`src/python/web/` 模块拆分/安全设计/API/测试/实施阶段）。

| 阶段 | 工作量 |
|------|:------:|
| MVP 核心 | 3d |
| 功能补齐 | 1.5d |
| 体验打磨 | 1d |

> **实施进度（2026-08-06）**：阶段1（MVP 核心）**已落地**——`src/python/web/` 全量创建（server/app/handlers/upload/progress/runs + templates/static），依赖接入 `flask==3.1.2`（pyproject + requirements.txt），`launch.sh`/`launch.ps1` 增 `web` 入口参数；上传→生成→轮询→预览/下载全链路贯通（复用 `generate_report` 管线，零改动 report/ 层），上传安全（§6.1：uuid 重命名/扩展名白名单/PK 魔数/10MB/行数上限/原子落盘/TTL）与预览防穿越（§6.2）就位；`unit_web` marker 注册 + 5 个测试文件（upload/upload_edge/progress/runs/handlers，54 用例）全绿，P0 门禁通过。**阶段2（功能补齐）已落地**（同日）——索引页按 `get_config()` 回填表单默认（历史走势跟随配置 + 强制 LLM 开关）、进度编号步骤 + 当前阶段展示、状态区（数据源健康 `/api/health` 含 `?fresh=1` 重测 + 历史运行记录 `/api/runs/history`）、错误处理完善（exit_code 映射展示 / 严重态产物裁剪 rf-254 / FILE_EXPIRED 重置 / 重新生成按钮）；web 目录 64 用例全绿，P0 门禁通过。**阶段3（体验打磨 + 用户文档）已落地**（同日）——样式打磨（design-quality：上传区拖拽高亮/渐变进度条/卡片悬浮阴影/状态区分栏/语义色）、加载态与轮询节流（提交/生成中按钮禁用 + 文案、页面不可见暂停轮询、AbortSignal 超时）、375px 移动端响应式（表单纵向堆叠/状态区单列/`prefers-reduced-motion` 减动效）、a11y（文件输入 sr-only 键盘可达、progressbar aria、aria-live）、用户文档（how-to-start 方式四 Web 模式 + faq 端口冲突/无法访问/进度卡住/产物 404 高频问题 + README 功能提点）；web 目录 64 用例全绿，P0 门禁通过。**三阶段全部完成**，设计文档已归档至 [`archive/v0.10.x/web-ui/`](../archive/v0.10.x/web-ui/plan-web-ui-implementation.md)。复用基础已确认存在——`report/orchestrator.py` 的 `prepare_report_data` 与 `generate_report(holdings, config, reporter, report_type, fetch_history, force_llm, output_dir, ...)` 接口签名未变，Web 层直接调用管线。工作量估算：阶段1/2/3 实际完成（约 5.5d），仍为 P4 选做、无排期。

#### `plan-25` Web 持仓输入模式：试算隔离 vs 正式共享（[`plan-web-holdings-input-modes.md`](../archive/v0.10.x/web-holdings-input-modes/plan-web-holdings-input-modes.md)）

Web 上传持仓跑 full/both 会污染共享快照目录（rf-261）。方案已确认（2026-08-07 探讨收敛），按**使用意图**分两模式，`data/cache`/`data/state` 保持共享不动：

- **① 临时试算（web 默认）**：上传保持 uuid 临时态（现状），快照写入独立子目录 `data/history/snapshots/web/`（`history_snapshot.save/load` 增 namespace 子目录参数），TUI/CLI 读主目录自然排除 web 试算快照 → 组合演进/快照差异不受污染。
- **② 正式更新（共享，显式选择）**：两种输入——上传覆盖 `data/holdings/{holdings_filename}`（先备份旧文件），或**不上传直接用存量持仓文件**（web 成为完整报告生成入口，符合"最少输入"定位）；快照入共享主目录，演进/对比真实生效。

**实现要点**：`capture_snapshot` 增试算/正式判定（web 默认试算 → namespace="web"）；`history_snapshot` 的 save/load_latest/load_all/prune 支持 namespace 子目录；`portfolio_evolution`/`_snapshot` 读主目录；web `_handle_create_run` 增模式参数（trial/formal + use-existing），前端表单增模式选择；测试覆盖两种模式快照归属；用户文档（how-to-start Web 模式 + how-to-config）。**预估：2d**。

> **实施进度（2026-08-07）**：**六阶段全部落地**——① 存储层 `history_snapshot` namespace 子目录（save/load_latest/load_all/list_all/prune + 白名单校验）；② 消费层 `capture_snapshot`/`build_evolution_data`/`build_snapshot_diff` + 两个 `_inject_*` 透传 `snapshot_namespace`；③ 编排层 `generate_report` + `_report_generation` 双路径透传；④ web 入口 `holdings_update.py`（单槽 `.bak` 备份 + 原子提升）+ `_handle_create_run` mode/use_existing 解析与组合校验（正式+用存量禁止 file_id→400）+ `_web_input_mode_snapshot_domain` 模式→快照域映射；⑤ 前端生成用途/输入来源单选 + 覆盖警示 + 确认勾选（index.html/main.js/style.css），resetFlow 区分正式-用存量；⑥ 文档与门禁——语义表登记 `snapshot_namespace`/`web_input_mode`/`use_existing`/`holdings_update`，folders/三手册/changelog 同步，`_pipeline.py` 标注遗留不承载活代码。smoke-web.py 10 断言全通过，dev-verify 1970 + 4 checks --ci 全 [OK]。**已实现**（P4 选做、无排期，仍列为实验功能）。设计文档已归档至 [`archive/v0.10.x/web-holdings-input-modes/`](../archive/v0.10.x/web-holdings-input-modes/plan-web-holdings-input-modes.md)。

#### `plan-26` Web 配置编辑：完整镜像 TUI 可编辑配置全集（[`web-config-edit.md`](../plan/web-config-edit.md)）

Web 模式支持修改与 TUI **完全一致**的配置项全集。已确认决策（用户拍板，勿推翻）：① 先写设计文档 ② 完整镜像 TUI ③ 写前 `.bak` 备份。**设计已定稿**（2026-08-07，设计文档位于 `docs-stm/plan/web-config-edit.md`）：

- **7 组全集**：自由文本路径（holdings_dir / holdings_filename / output_dir）、报告章节开关 5 项、增强子模块开关 6 项、匿名化枚举（off/code_display/full_anonymous/summary）、对比指数池（增/删/重置默认）、LLM 分析章节开关 5 项（enabled_llm，隐藏三模块不展示）、辩论实验功能开关 3 项（features.json）。
- **后端**：新模块 `web/config_edit.py`——`config_edit_whitelist` 白名单（点分键→类型/枚举→目标文件→写入原语）+ `GET/POST /api/config/edit`（POST 复用 `_is_same_origin()` 守卫）；写共享配置前 `config_backup_file` 单槽 `.bak`（mkstemp + `os.replace` 原子写）。
- **写入语义（逐条等价 TUI）**：config.json→`set_config`（嵌套 dict 读合并整块写；匿名化走 `set_anonymization_mode`）；llm_settings.json→共享 `write_llm_settings`（自 tui 抽取，TUI 改委托）；features.json→`save_feature_overrides`。
- **一致性修正**：两个状态面板（tui_menu / web handlers）匿名化读路径改顶层 `anonymization.mode`（原误读不存在的 `features.anonymization.mode`，恒显示关闭）。
- **前端**：index.html 新增「配置编辑」card（7 组控件）+ main.js 即改即存 + error_code 分支，选项与 TUI 完全一致。
- **语义命名**：`config_edit` / `config_edit_whitelist` / `config_backup`（technical.md 语义表已随实现登记，反向校验通过）。
- **预估**：2d（对齐 plan-25）。

> **实施进度（2026-08-07）**：六阶段全量完成——①共享层抽取 `write_llm_settings`（`config/_llm_settings.py` 公开原语，TUI 改委托，行为零变化）；②后端核心 `web/config_edit.py`（白名单 + 面板读取 + 应用编辑 + 备份）+ `handlers.py` 路由 `GET/POST /api/config/edit` 与同源守卫；③匿名化读路径修正（tui_menu `_show_privacy_and_security_status` + web `_build_system_info` 读顶层 `anonymization.mode`）；④前端配置面板（index.html 「③ 配置编辑」card + main.js 即改即存 + error_code 分支 + style.css 样式）；⑤测试补齐（`test_config_edit.py` 35 用例 + `test_config_edit_edge.py` 42 用例 + `smoke-web.py` 扩展至 11 项断言）；⑥文档与门禁——changelog/how-to-config/faq/folders 同步 + technical.md 语义表登记 3 行。附带修复：smoke-web `_DEFAULT_CONFIG` 顺序污染（finally 还原，config 测试在 web 后运行 7 失败 → 恢复 282 全绿）。**已实现**。

#### `plan-27` 前端资产统一归入 `src/static/`：Web UI 与报告模板（基础设施重构）

将分散在 Python 包内的非 Python 前端资产统一归入 `src/static/`（报告图表 bundle 已有目录），`src/python/` 仅保留纯 Python 代码：

- **Web UI 前端**（`index.html`/`main.js`/`style.css`）：`src/python/web/{templates,static}/` → `src/static/web/`；`app.py` 的 Flask `template_folder`/`static_folder` 改为 `PROJECT_ROOT` 派生，`/static/main.js` 与 `render_template("index.html")` 契约不变。
- **报告 Jinja 模板**（`report_template.html`/`whatif_template.html`/`partials/`）：`src/python/tmpl/` → `src/static/tmpl/`；`html_jinja_env.py` `_TEMPLATE_DIR` 改用 `PROJECT_ROOT` 派生（单加载点）。
- **净效果**：`src/static/` = 报告图表 bundle + Web UI 前端 + 报告模板三合一；5 个按路径读模板的测试路径同步。

> **实施进度（2026-08-07）**：代码归入 + 加载点改造（app.py / html_jinja_env）+ 5 测试路径同步完成；`smoke-web.py` 10/10 + report/web/llm 单测 2395 passed；folders 目录树/统计表同步，changelog 登记；`src/static/README.md` 资产说明滞后登记 rf-266，已修复（README 扩展为三类资产说明，rf-266 移入已修复区）。**已实现**（基础设施重构，随 P4 实验功能批次，无独立排期）。

#### `plan-28` 三模式使用指南体系：TUI/CLI/Web 各一份 + 文档索引统一（用户文档）

plan-8/25/26/27 实现后，用户文档从「单份菜单手册 + 定时任务手册」演进为**三种模式各一份分册**——Web 模式使用指南、CLI 模式使用指南（含定时任务）、TUI 菜单手册，并统一 README / CLAUDE.md / folders 索引。

- **三份模式分册**：`how-to-use-web-mode.md`（新建，Web 全流程——启动访问/首页 6 分区/上传→生成→预览下载/配置编辑面板/运行状态/安全注意）、`how-to-use-cli-mode.md`（新建，命令结构/全局参数/report·cache·whatif·check-sources 子命令/使用示例/退出码/最佳实践）、`how-to-menu.md` → `how-to-use-tui-menu.md`（重命名，标题改「TUI 菜单操作手册」）。
- **定时任务并入 CLI 指南**：`how-to-schedule.md` 内容并入 cli-mode.md §11「定时任务」（Windows schtasks + PowerShell 包装 + 防重入 / Linux crontab + flock / 排障），原文档删除，活跃引用（README/faq/how-to-start/tui-menu）统一改指。
- **索引统一**：README 启动方式三节 + 功能特性三模式条目 + 用户指南表指向各分册；CLAUDE.md 用户文档列表顺序与 README 索引一致；folders.md 目录树去重 + 统计表刷新（用户文档 14/6,204，manuals 13/5,998）。
- **测试覆盖统计刷新**：`bench --update-docs` 回填 dragonball 列耗时（2026-08-07），`collect-test-coverage.py` 计数核对无变化（all 5445 / unit 5136）。
- **预估**：无排期（纯文档配套，随 Web 功能批次）。

> **实施进度（2026-08-07）**：三模式分册全部落地 + 定时任务并入 + README/CLAUDE.md/folders 索引统一 + test-coverage 耗时刷新 + changelog 登记；P0 门禁（dev-verify 2005 + 4 checks `--ci`）全 [OK]。**已实现**（纯文档任务，无运行时代码变更）。

---

## 归档

- [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md) — v0.10.x 已完成项（plan-17~plan-25，含设计文档索引：投资功能优化/章节归并 + 任务编号门禁 + Web 持仓输入模式）
- [`archived_plan.0.9.x.md`](../archive/v0.9.x/archived_plan.0.9.x.md) — v0.9.x 已完成项（含设计文档索引）
- [`archived_plan.0.8.x.md`](../archive/v0.8.x/archived_plan.0.8.x.md) — v0.8.0 ~ v0.8.10（含设计文档索引 + 已完成项）
- [`archived_plan.0.7.x.md`](../archive/v0.7.x/archived_plan.0.7.x.md)
- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md)
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md)
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md)
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md)
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md)
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md)
