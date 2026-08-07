# 投资复盘助手 — 实现计划
> 文档版本：0.10.12-dev
> **编号源**：`plan-next = 26`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-25，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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
