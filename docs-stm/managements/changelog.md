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
