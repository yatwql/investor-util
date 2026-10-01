# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.9]**（2026-09-30）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.10-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### 新增

- **LLM 合规声明集中注入**：新增 `llm/compliance.py`（`apply_compliance_guardrails` / `COMPLIANCE_CLOSING`）——在 system prompt 尾部幂等叠加「仅供复盘参考、不构成投资建议」约束，窄判定角色（如新闻关联）可经 `role` 追加专属条目；注入点为 `llm.api.call_llm` 单一漏斗，覆盖全部 LLM 模块（新增模块无需各自声明），已含声明的 prompt 不重复叠加，空 prompt 原样返回。缓存指纹由结构化数据计算（不含 prompt 文本），注入不改变缓存键（旧缓存产物仍由报告模板层免责声明兜底）。回归 8 例（幂等/角色追加项/空保护/call_llm 接线）。
- **CLI 收尾资源摘要行**：报告生成完成后输出两行运行资源摘要——LLM 成本（`print_llm_cost_summary`：调用次数 / 输入输出 token / 模型名）与缓存命中率（`print_cache_hit_summary`：命中/总数/百分比，0% 亦输出）。无 LLM 调用/无缓存读写时各自静默；常规模式进 logging，`--verbose` 同步到 stderr。二者为 `CliProgressReporter` 公开方法（与 `print_timing_summary` 同形），并在同一完成点接入；回归 6 例（含 0% 不静默、无观测静默、`_handle_report` 接线）。
- **akshare 新闻源内接口降级**：`providers/akshare_news.py::fetch_news` 在聚合点对财新（主）/ 央视（补充）两个接口各自隔离异常——单接口异常降级为仅另一接口结果并记 WARNING 日志（可观测，非静默降级），双接口均失败返回空列表而非抛出，由新闻聚合器按源记录失败。回归 4 例（主接口降级 / 补充接口降级 / 双失败空返回 / 降级日志）。

### 修复

- **cassette 回放的日期时移假红（既有缺陷）**：季报取数的回溯窗口按「当前日期」向前循环（`_recent_quarters`），而 cassette 录制内容固定在录制当日——时间跨过一个季度后，回放会先去请求**未录制**的新季度并报 `CassetteMissError`，导致 `test_cassette_replay.py` 三项与 P0 门禁变红（与上游是否漂移无关）。修复：新增 `providers/tiantian_holdings.py::quarter_walk_anchor` 时间锚点上下文（回放时把窗口锚定到 cassette 的 `recorded_at`）——① pytest 侧由 `conftest.py::_install_cassette_replay` 统一施加（取所声明 cassette 中最新的录制时点）；② CLI `cassettes --verify` 侧由 `fetcher/cassette_checks.py` 的 `_anchored_to_recording` 施加。**锚定后请求形状仍须与录制逐字一致，上游漂移照样报 miss**（信号不弱化，仅去掉时间依赖）；新增回归用例（冻结模块时钟到下一年，断言回放仍解析出录制内容；已实测：去掉锚定即变红）。

### 文档

- **管理/用户文档一致性核对（rf-479 ~ rf-509，31 项）**：全量核对 10 份管理文档 + 10 份用户手册 + `README.md` 的章节序号、层级、交叉引用与内容数字，逐项修复：
  - **章节序号/层级**：`requirements.md` §5.11 景气度框架诊断误落在报告输出需求章内 → 归位至 §5.10 之后（rf-479）；`technical.md` 链路同源重试节由 `### 2.2.1` 降为 §2.1 的无编号 `####`（rf-480）、`I.1.1` 降为 `#####`（rf-481）、§4.10 重复标题「整体流程」改为「标题去重判定流程」（rf-505）；`developer-guide.md` 与 `check-doc-drift.py` 守护清单 14/15 顺序纠正（rf-482 / rf-483）；`review-findings.md` P2 子块层级统一为 `###`（rf-484）；`how-to-start.md` 跳过层级的 `####` 降为 `###`（rf-485）；`how-to-config.md` 缓存 TTL 五个子类降为 `#####`（rf-486）
  - **交叉引用**：`how-to-use-web-mode.md` 配置指引章节号 P → Q（rf-487）；`reports-instruction.md` 功能开关章节号 §M → §N（rf-488 / rf-489）；`how-to-config.md` `default_menu_key` 合法键表更正（补 `T`、去 `C/F/O`，门控键由 `D` 更正为 `T`）（rf-490）；三处悬空设计文档引用改为指向 `folders.md` 目录树归档索引（rf-491）
  - **内容数字**：`requirements.md` R-FIN-12 / R-FIN-08 两行归位 §5.9 表（rf-492）；`technical.md` 「完整 16 项」补 `llm_usage` 强制末位说明（合计 17 个模块）（rf-493）；`testplan.md` 需求条数 276 → 278 并限定追溯口径（仅单段 ID；§7.2–§7.8.4 的 60 条双段子域 ID 不在范围）（rf-494 / rf-495）；`folders.md` CLAUDE.md 行数 75 → 86、文档增长列改行数比 45.8×、v0.11.x 归档区间更新至 v0.11.9 / plan-58 / rf-478（rf-496 / rf-497 / rf-498）；`testplan.md` §1.3 无规格块的 `SP1-SP10` 改标 `—`、规格表头 T1-T21 加指向 §1.7（rf-499 / rf-500）
  - **目录树/格式**：`folders.md` 两处 `└──` 误标（rf-501 / rf-502）、补收 `web-ui-verification-checklist.md` 条目（rf-503）；`reports-instruction.md` 目录行补 `>` 前缀（rf-504）；`llm-technical.md` 目录补附录 A/B/C（rf-506）；`developer-guide.md` 删除误粘括注、补 `check-requirement-trace.py` 速查行与专节（rf-507 / rf-508）
  - `test-coverage.md` 采集说明的 bench 读数标注为批次读数、指向模式表（rf-509）
  - `folders.md`「项目统计」同步实测行数（项目文档 / 管理文档）；「版本演进对照」按约定保持发布时点快照不变


---

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.9（2026-09-15 ~ 2026-09-30）
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
