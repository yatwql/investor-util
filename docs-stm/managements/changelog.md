# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.12-dev] - 2026-08-03

### Refactor

- **plan 迭代设计文档归档清理** — ① `plan-11-dark-mode-plan.md` 归档至 `archive/v0.9.x/html-dark-mode/`（原 `archive/v0.9.x/dark-mode/` 目录更名 `html-dark-mode/`）；② `plan-whatif-backtest.md` 归档至 `archive/v0.9.x/whatif-backtest/`；③ `plan-advanced-analysis.md` 归档至 `archive/v0.9.x/abandoned-design/` 并更名 `plan-4-brinson-attribution-abandoned.md`（记录放弃设计决策依据——除已放弃的 plan-4 Brinson 归因外均已实现）；④ `plan-engineering.md` 删除（任务均已实现）。外部引用同步（plan.md / plan-web-ui.md / folders.md 目录树与统计）
- **因子暴露分析设计沉淀至正式文档** — `technical.md` §4.8 因子暴露分析新增「候选因子代理指数」表（6 个 CSI 指数 + probe 实测状态）与「数据新鲜度判定标准」（threshold/stale 双维度 + 5f/3f/infeasible 分级）；`probe-csi-factor-indices.py` 与 `whatif.py` 注释/文档字符串由 archive 路径改引正式文档（technical.md §4.8 / §4.13）
- **check-doc-traces.py 打磨（文档痕迹检查收口）** — 明确两条核心规则：① 文档正文不得带历史痕迹与历史变更（changelog / plan / review-findings 例外），只反映最新状态；② 除上述三例外文档外，管理/用户文档正文不得引用归档文件（folders.md 目录树可引用 archive 目录及文件名）。归档引用模式收紧——运行时产物归档描述（"归档至 `YYYYMMDD/` 日期子目录"、"归档到 `reports/`"等）豁免；工具说明豁免加固（含"不得/禁止"前缀）；`scripts-reference.md` 同步说明

---

## [0.9.11] - 2026-08-03

### Feat

- HTML 报告暗色模式（plan-11）：主报告与调仓 What-if 报告均可切换深/浅色，右上角浮动按钮，主题偏好 localStorage 持久化（首次默认浅色）；页面级颜色统一为 CSS 变量，Chart.js 图表随主题重绘，打印自动切浅色
- 组合演进纳入报告可选环节配置（plan-12）：新增独立开关 `enable_portfolio_evolution`（默认开启），控制 #19 组合演进章节显示/隐藏；与 `enable_fund_deep_analysis`、`enable_history` 相互独立。持仓快照不受影响、始终自动记录，开关仅影响报告展示。菜单 `P` 新增第 4 项切换

### Refactor

- **首次运行引导/隐私声明已读标志迁移至机器本地状态（config.json 去个性化）** — `_startup_wizard_shown`、`_privacy_notice_shown` 自 `data/config/config.json` 迁移至 `data/state/local_state.json`（git 忽略的机器本地目录），避免 config.json 跨机同步时各机器个性化差异。新增 `config/_local_state.py`（`get_flag`/`set_flag`/`_migrate_legacy_keys` 惰性迁移）与 `del_config()` 删键能力（磁盘文本 span 定位删除键行 + 末位成员尾随逗号清理，保留注释）；startup_wizard/privacy_notice/tui_menu 三处调用点改读 local_state
- **报告可见性类型 `b_series` 更名 `fund_deep_analysis`（语义化）** — `core/registry.py` `_REPORT_SECTION_DEFAULT` 的 6 处 `type: "b_series"` 改为 `type: "fund_deep_analysis"`，`board_flags` / `orchestrator._read_section_flags` 字典键同步改名；`config/features.py` 的 `b_series_fund_manager` / `b_series_fund_overlap` / `b_series_fund_concentration` / `b_series_fund_style` 四个遗留开关一并更名 `fund_deep_analysis_*`（无消费方，统一语义）。4 个测试文件断言与 4 个活动文档（technical / requirements / how-to-config / reports-instruction）同步；归档历史文档保持原名不追溯
- **代码/文档历史痕迹清理 + 痕迹检查脚本打磨（提交门禁配套）** — ① 代码/测试注释移除历史迭代叙述（"旧设计遗留"的辩论三模块改为当前状态描述、"此前误扫全局临时目录"历史说明、版本更名/来源叙述/SDK 路由描述清理）；② `check-code-traces.py` 新增 HIGH 模式 `旧设计|旧架构|历史遗留`，堵住"旧设计遗留"类盲区；③ 管理/用户文档正文移除历史变更痕迹与归档文件引用（所需内容复制合并进正文，允许冗余）、同步最新状态（config 旧键自动迁移、akshare 锁定版本、菜单 P 四开关、LLM HTTP 直连路由、组合演进章节等）；④ `check-doc-traces.py` 新增 HIGH 模式 `旧设计|旧架构|历史遗留|旧版|老版|未升级版`；⑤ 测试统计快照刷新——test-coverage.md 各模式/功能域/子标记计数对齐 `collect-test-coverage.py` 实时收集（unit 4027、all 4345），folders.md 文件数/行数/用例数与实际一致，testplan.md 菜单选项 16→17（新增调仓 What-if W）

### Test

- 新增 `test_local_state.py`（标志读写 + 旧键惰性迁移 9 例）、`test_config.py` 增 `TestDelConfig`（删键 5 例，含末位键尾随逗号清理）；conftest `_isolate_sensitive_paths` 隔离 `local_state.json` 路径；修正 `test_menu_key_coverage` 期望键集合补 `W`（调仓 What-if 菜单）

---

## 归档

- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.10（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
