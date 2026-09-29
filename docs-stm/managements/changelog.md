# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.8]**（2026-09-29）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.9-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

---

### 交互优化：新增 [D] 配置目录信息子菜单（rf-471）

**背景**（用户要求）：持仓目录 / 持仓文件名 / 报告输出目录三个同属「路径配置」的入口平铺在主菜单占 3 个键位，而 `[D]` 已被系统自检占用，语义冲突。

**变更**：
- `tui_menu.MENU_ITEMS`：三项合并为 `[D] 配置目录信息`（20 → 18 项）；系统自检键 `D` → `T`（`FEATURE_GATED_ITEMS` 同步，仍受 `doctor_check` 门控）
- `handlers_config._cmd_config_dir_info()`：独立子菜单循环（`[C]` 持仓目录 / `[F]` 持仓文件名 / `[O]` 报告输出目录 / `[B]` 返回主菜单）——大小写归一、无效输入重提示、EOF/Ctrl+C 安全返回；子项在调用时取模块全局（便于打桩）
- 回归 +7 例（子菜单分发/大小写/返回/无效输入/EOF + 菜单键集与路由 D→`_cmd_config_dir_info`、T→`_cmd_run_doctor`）
- 文档同步：how-to-use-tui-menu / how-to-start / faq / how-to-config / how-to-config-llm / how-to-use-web-mode / how-to-use-cli-mode / requirements（R-TUI-02 18 项 + §3.2 菜单表 + R-DIAG-05）/ technical（§1.6.3 菜单体系）/ testplan / test-coverage / folders；代码内提示串（`handlers_log` docstring、`features.doctor_check` 说明）同步

### 文档：README 核心亮点与功能特性重梳（v0.11.x 全部特性）

**背景**（用户要求）：README 的亮点表与功能特性章节停留在较早版本，未覆盖 v0.11.x 落地的能力。

**变更**（`README.md` 全文重写，207 → 221 行）：
- 核心亮点表：7 条重排为「一次持仓三种用法 / 全量报告双格式 / 穿透到真实持仓 / 量化风控成体系 / 真正把 LLM 用成智囊团 / 数据可信度可追溯 / 决策闭环 / 调仓 What-if」
- 功能特性重分组：报告与行情 / 新闻与数据增强 / LLM 分析 / 投资分析与风控 / 基金评价 / 持仓基本面 / 调仓 What-if / 运维与可观测性 / 隐私与安全
- 补齐此前缺失：市场情绪、估值分位、市场温度、交易纪律、流动性、尾部风险、候选基金比较、财务指标与财报摘要、信号预消化、确定性信号沉淀、决策跨期反思闭环、正反辩论/条件推理/集中度问答、景气度框架诊断、系统自检、日志可视化、阶段计时、凭据不落产物、00 重叠区按名称消歧、ETF 联接穿透
- 修正过期内容：图表数与页签分组口径、「17 章」章节编号表述、技术设计文档描述去约束代号

---

### 缺陷修复：巨潮备源三处取数缺陷（rf-472）

**现象**（用户贴日志问「所以其实是拿不到信息的么？」）：报告里大量 `[financial_report] 全链路失败（无过期缓存可用）`，夹杂 `[cninfo] 连接挂起 40.0s… 判定主机不可达`。

**排查结论（实测）**：
- **主源 DataSinking 完全正常**：直连官方 API 实测 `GET /documents` **HTTP 200**（`total: 626044`）、`/documents/{id}/sections` **HTTP 200**；日志里的「返回空」是**正常业务结果**——那几份季报确实没有「管理层讨论与分析」章节
- **备源巨潮确实连不上**：`www/static.cninfo.com.cn` DNS 解析正常但 **TCP 握手超时**（对照：东财/新浪/datasink 全秒连）——属本机网络路径阻断，非服务下线

**三处缺陷**：
1. `_get_bytes` 与元数据接口共用 `_TIMEOUT = 20.0`，而公告 PDF 是完整年报原文（几十 MB）→ 慢链路下必然「挂起 → 失败」，**从未下成功过**，每次白等一个超时预算
2. `cninfo` 是**直连调用（不经 Provider Chain）**，无会话级熔断 → 主机不可达时同一轮报告里**每篇文档都重新发起、重新白等**（实测 601939 连试 4 次共 160s）
3. provider 返回 `None` 时链路只记笼统的「返回空」，无法区分「源故障」与「该文档确实没这一节」——本次排查即被误导

**变更**：
- `cninfo`：新增独立 `_PDF_TIMEOUT = 60.0`，公告 PDF 用它；新增「主机本会话不可达」短路（`_mark_host_unreachable` / `_is_host_unreachable`，挂起型失败后标记主机，后续请求不发 HTTP 直接失败；非超时失败不标记以免误伤）
- `providers/_utils`：新增**按线程隔离、消费即清**的失败原因载体 `set_last_reason` / `take_last_reason`
- `chain._try_provider_fetch`：provider 返回 `None` 时读取该原因并**替换笼统的「返回空」**，同时进 `FailureDiagnostics`（→ 报告数据源矩阵）
- `datasink` / `cninfo`：各失败分支逐条自陈原因（无凭据 / 凭据为空 / 配额用尽 / 401-403 / 429 / 404 探测（区分「无该章节」与「章节清单未解析」）/ 非 200 / 非 JSON / orgId 未解析 / 主机不可达 / 连接超时）
- 回归 +14 例；文档：`technical.md` §2.2.1、`datasource-reliability.md`、`testplan.md`

**效果**：慢链路下年报 PDF 能真正下下来；主机不可达时由 N × 超时降为 1 次；日志/矩阵如实区分「源故障」与「该文档无该章节」。

---

### 界面优化：新闻表手机窄屏改卡片式堆叠（rf-473）

**现象**（用户用手机打开 HTML 报告）：财经新闻热点与持仓关联分析表里，摘要、关联关键词、LLM 关联分析挤在一起，有些地方错位，容易错过信息。

**根因**：该表 7 列（含 LLM 关联分析列）并沿用全局 `table { min-width: 600px }`，手机（≤768px）横向压缩后各列互相挤压换行、列边界难辨，三块相关字段黏连。

**变更**：
- 新闻表加 `.news-table` 类作窄屏规则作用域
- `@media (max-width: 768px)`：**改为卡片式堆叠**——隐去表头、每行一张卡片；单元格转块级，`td[data-label]::before { content: attr(data-label) }` 生成字段名前缀；序号与可点击标题作卡片头（不显示字段名前缀）；取消 `min-width`
- 模板补 `news-table` / `news-seq` / `news-title` 类与各字段 `data-label`
- 回归 +5 例（类名作用域、逐字段 data-label 齐备、窄屏隐表头与堆叠规则、取消 min-width、卡片头规则）
- 文档：`reports-instruction.md` 补「新闻表窄屏卡片布局」说明

**效果**：手机上一屏一条新闻，各字段带名字段名各占一行，不再错位；宽屏表格形态不变。

---

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.8（2026-09-15 ~ 2026-09-29）
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
