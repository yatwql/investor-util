# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.8]**（2026-10-09）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.9-dev] - 开发中（未发布）

- **功能**：**景气度框架诊断转正入常规组（plan-49 / plan-71 判定执行）**——转正判据（plan-71 定稿）逐项达成：① 六维数据覆盖 6/6（2026-10-10 报告全维非「需核实」）；② 真实复盘认可（24 次运行评分稳定 55/100「部分契合」，10-09 降级运行折算 26/80 语义正确；用户认可评分口径，`concentration_target_pct` 保持 50%——实测前十大集中度 88.55% 使该维压至 4/15，属有效风险提示不调高掩盖）；③ 覆盖 24 天真实使用、跨月快照、真实调仓（159222 止盈后清仓）与真实数据降级；前置降级矩阵 6 场景全绿（09-16）、批内十守护 / dev-verify / verify 全绿。执行：`features.py` 移实验组入常规组、`default False → True`（声明位与评分口径不变）；[S] 面板重排（实验 8-11 / 常规 12-22，prosperity 落 13）；requirements R-PF-01、technical §4.20、五份手册、testplan、README/CLI 示例（改用仍在实验组的 `factor_catalog`）同步；新增转正锁定用例；plan-49 / plan-71 完成并归档。

- **功能**：**收益归因升级「大类 → 品种」两级贡献分解（plan-89 完成）**——大类层按 `core/code_utils.classify_holding_tier` 单源分类（原报告分类页签 `_categorize_holding` 逻辑上移共用，分类判定唯一事实来源）聚合为权益/固收/现金（未知二元组兑底「其他」），与品种 TOP5 共用 Σ|盈亏| 分母（Σ大类 ≡ Σ品种，结构断言锁定）；HTML/Excel 归因子块与智囊团提示词段落三处同源呈现（大类行在前），口径脚注句单源（`ATTRIBUTION_NOTE`，成本口径，非严格区间收益归因）；`holdings_details` 契约新增 `account` 字段（orchestrator 与 `_action_holdings_details` 双路径，单源分类需渠道判定）；零新数据源（纯本地，无 plan-4 归档所列 3 项缺口）；requirements R-ACT-06、testplan载体、technical 契约与语义命名表、reports-instruction 同步；新增单元用例 6 项 + 扩展渲染断言 2 项
- **功能**：**CLI 任务完成/失败通知（plan-100 完成）**——新增 `core/completion_notify` 三通道通知（webhook POST JSON / SMTP 邮件 / notify-send 桌面）：失败（退出码非 0）必发、成功需 `notify.on_success=true`，无 `notify` 节或全通道未配置静默跳过（默认关，符合「配置文件不必须存在」惯例）；载荷含报告类型/退出码/产物路径（命名单源 `LATEST_XLSX_NAME`/`LATEST_HTML_NAME` + 结果标志推导）/错误数（全量）与明细（截断 20 条）/数据状态跟踪器降级摘要（最新在前、按源去重 10 条，CLI 收集层与 `get_tracker().get_log()` 解耦）；单通道失败隔离、永不抛出、绝不改变退出码（尽力而为，单次尝试无重试）；webhook URL 异常消息落日志前掩码只记域名（凭据不落日志纪律）、HTTP 走 `make_http_client`（客户端统一）、日志 logger `invest`（日志统一）；config 模板新增通知节（dict+JSONC 双处），需求 R-OUT-14、testplan 批 13、technical 语义命名表、how-to-config「R. 任务完成通知」、CLI 手册 13.4 同步；新增单元用例 20 项 + CLI 接线用例 3 项
- **功能**：**持仓相关性滚动趋势（plan-87 完成）**——相关性区块新增滚动子块：60/120 日端点窗**组合平均相关性**折线 + **重点品对**（静态 |r| 降序前 3 对）滚动 r 折线与最新值表，回答「分散化是否随时间失效」；`analysis/correlation.py::compute_rolling_correlations` 纯计算（端点窗 = min(窗口, 该对可得重叠期数)，历史不足**按可得区间截断**并经 `notes` 单源标注口径，`coverage.full_window_from` 记录完整窗起始，60/120 同轴端点网格），静态末点均值与静态矩阵配对均值同源（容差断言锁口径）；数据底座 `FETCH_DAYS` 90→260（覆盖最长滚动窗）+ **增量链路短缓存自动全量补齐**（`chain_incremental`：缓存历史 < 请求窗口时 start_from 置 None 全量刷新——否则滚动趋势恒被 90 日短缓存截断，滚动层失败仅降级本层）；序列复用 `report/downsample` 周/月聚合（在编排层调用，避免分析层反向依赖报告层，分层依赖约束）；HTML（`position_structure_section` 日期映射对齐防御，不传 null 保极值轴）与 Excel（滚动摘要 + 口径句进说明区）同源消费同一滚动契约；需求 R-COR-01、testplan 批 14、technical 契约 11→12 键与语义命名表、reports-instruction 三处同步；新增相关单元用例 26 项（分析 8 + 边缘 3 + 渲染/接线 9 + Excel 4 + chain 回归 2）

- **计划**：**plan-70 窗口期满重判（2026-10-10 执行）**——读数：experiment_stats `decision_reflection` 启用 17 → 24（判据①不成立）、`fold_ledger()` 已结算 2 <10（判据②成立；已结算 outcome 均 flat、`directional_total=0`、`sample_sufficient=false`），但 2026-10-08 单批 8 条 pending（`horizon_bars=5`）预计 10-15 前后集中结算、如期 settled=10 恰好达标 → 有达标趋势；按 10-09 裁定三元条件（判据②成立 **且** 无达标趋势才撤销）**本轮不撤销、不转正**，终判顺延至该批结算后——用户确认 10-15 后执行终判（settled ≥10 → 据 doctor 账本概览评估转正，正式命中率另需 `directional_total ≥ 20`；仍 <10 且无新增结算 → 按原文撤销）。

- **配置**：**LLM Provider 链精简（用户指定）**——`data/config/llm_providers.json` 移除 `kimi-main` / `kimi-code` 两条条目，链路只剩 `deepseek-main`（主，priority 20）+ `opencode-go`（备，priority 30）；`opencode-go` 的 `pacing.min_interval` 1s → 5s（订阅端点收紧节流）。改前备份 `llm_providers.json.bak-20261010`（git 忽略）。

- **文档**：**管理与用户文档核对修复（rf-656 / rf-657）**——① `how-to-config-llm.md` / `faq.md` 的 429 口径按 rf-647 / rf-653 后实现改写（429 归 `quota` 终态、首试即 600s 长冷却熔断零退避重试，503 才按 `max_retries` 退避），并补登缺项：全局键 `llm_full_fail_retry_delay`（8 → 9 项）、`{module}` 后缀清单与 `enabled_llm` 三处 JSON 示例补 `self_review` / `holding_change`、`how-to-config.md` cache_ttl 表补 `llm_holding_change`（2h 内容寻址）；② `folders.md` 版本演进对照「当前开发版」列按 2026-10-10 工作区重跑（主程序 345 / 91,291、测试 508 / 147,773、用例 9,412、代码合计 945 / 260,418、仓库 1,174 / 336,261，增长比与口径附注同步：严格口径 9,359、收集 9,882 / 9,902、行数比 147,773 / 91,291）；③ review-findings 的 rf-654 归位「已解决问题」区。

- **修复/分析**：**事实校验器四类语境缺口（rf-655）**——① **回放/回测语境未豁免**：调仓纪律回放的模拟指标（规则A/买入持有 的区间收益、最大回撤、夏普）与持仓实际收益率不同源，句中无 6 位代码时被全局最近邻兜底归因到无关品种并自动「修正」（实盘：回放句「区间收益 -5.35% 优于买入持有 -7.16%」的 -7.16% 被改为 096001 的 9.2%，把正确数据改错且与回放面板自相矛盾）；② **回撤紧邻窗口被远端收益词击穿**：「收益 -5.35%、最大回撤 10.28%」中 10.28 因前 15 字符窗口含「收益」被排除回撤语境；③ **历史（已清仓）代码未纳入有效集**：LLM 提示词含【环比变化】清仓行与统一附录【持仓变动复盘】块，引用已清仓代码（如 159222）属合法历史语境，却被误报「不在当前持仓中」；④ **近并列排名无差距注记**：市值差仅 0.05% 的两只品种排名随快照时点翻转，告警未提示该脆弱性。修复：① `_REPLAY_KEYWORDS` + `_is_replay_context` 整句跳过；② `_is_drawdown_context` 增紧邻优先（≤8 字符内回撤词优先于远端收益词）；③ `extract_historical_codes` 从 `pipeline_data` 动态提取历史代码并入 `extra_valid_codes`；④ `_near_tie_note` 在市值差 <1% 时附加差距注记（不改变严重级别）。回归 16 项。

- **UI/报告**：**行动建议章正文默认折叠**——正文大块包进 `details.section-fold`（与财经新闻关联、组合演进等已折叠各章同构）：提示条携带行动摘要与「点击展开/收起」指引，默认收起，锚点/打印展开由 fold.js 对全部折叠块统一生效；「回到顶部」与降级占位（无持仓数据）留在折叠块外常显。需求 R-OUT-12 覆盖清单同步（含此前漏登的持仓变动复盘/调仓纪律回放），新增 `TestActionSectionFold` 5 项结构回归。

- **功能/数据**：**市场温度第一因子升级为估值分位（plan-116 完成）**——新增指数估值历史源 `fetcher/index_valuation.py`（akshare 乐咕 `stock_index_pe_lg`/`stock_index_pb_lg`，沪深300 月频 PE/PB 2005 起；1 周缓存 + 30 天旧缓存兑底；**可选源不计入共享 `akshare` 熔断键**防乐咕故障连坐无风险利率）；`bond_yield` 扩展 10Y 国债收益率全历史序列（`bond_yield_history` 独立键，ERP 因子数据底座）；`build_erp_series` 按日期 asof 对齐（修复尾部 zip 会把历史 PE 与近期 rf 错位配对的缺陷）；三因子第一项 = PE/PB/ERP 各自历史分位等权（样本下限 60），估值序列不可得 → 旧缓存兑底 → 回落点位分位（=升级前行为，温度行永不消失；实测当日两口径分差 7.6 分、同档）；契约新增 `valuation_percentile`/`valuation_components`/`first_factor` 三键，Excel/HTML 三因子行首项按口径动态展示「估值分位/价格分位」，免责声明同步。**回看窗口 750 → 2000 交易日**（实测腾讯/东财源上限 ≈8 年），并修复**链路文件缓存窗口锁死缺陷**（增量合并从缓存末日补数把短窗口永久钉死——修前请求 2000 天实测只返 91 根；现短于请求窗口且存在文件缓存时自动清缓存全量重取）。新增测试 33 项（单元计数 9,475 → 9,508），文档同步（技术契约注记 16 键/数据源表/缓存表/目录树、datasource 两册、folders）

- **修复/分析**：**市场温度波动率分量方向反转**——`_vol_component` 由「越高越热」改为「越高越冷」：A 股高波动多现于恐慌下跌（股灾/贸易战/急跌）而非狂热顶部，旧口径同向会把恐慌期温度硬抬高（波动分量最高 +20 分），可能把「低估」推成「合理」；回归用例锁定「其余因子相同、波动越高温度越低」及低估区反向陷阱（`test_volatility_direction_reversed`）。契约/权重/免责声明/三档刻度均不变；PE/PB 估值分位化 + 股债性价比 + 回看窗口拉长已立项 plan-116（同版本内完成，见上条）

- **重构/配置**：**量化指标 7 个逐项开关合并为单开关 `metrics_enabled`（plan-115）**——菜单 `[S]` 18-24 号 `metrics_*` 七项并为「量化指标显示」一项（指标始终全量计算、开关只管显示；注册表 34→28 项、常规组 16→10，面板编号与各手册表格/计数同步）；雷达图改为单开关口径（关闭 → 全轴 N/A，**降级 3 轴路径此前不过滤已补齐**）；`circuit_breaker_wrapper` 两份逐项 flag_map 收敛为单常量；**修复 `_ff_was_off` 只读不写**（rf-654：开关「开回时重置断路器」的契约从未生效，关闭前的残留失败计数会跨周期累计）；旧 `metrics_*` 键按无消费者告警。**补齐测试**：熔断 FF 联动 6 项（此前零覆盖）+ 降级路径过滤 + 旧键告警回归；生效面维持现状（不扩到 LLM 指标表/正文）。

- **修复/数据**：**场外净值缓存新鲜度门禁按基金类型分域（rf-652）**——`_price_cache_fresh` 新增 `name` 形参并按 `is_qdii_extended` 细化阈值：QDII 官方净值合法 T-1（不变），国内场外 T 日当晚披露、盘后要求 T；两处调用点传入持仓名（`fetcher/price.py` 强刷路径 `expected_name`、`report/market_value.py` CACHE_ONLY 路径 `h.name`），与 `price_update_status` 口径同源。修前实测 5 只国内场外缓存停在 T-1 被误判新鲜、报告「价格更新状态」8/13（东财已返回 T），修后盘后强刷取到 T。回归 4 项。
- **技术债/文档+配置**：**过去 72h 实现核查三项修复（rf-653）**——① rf-647 的 429 行为变更（归 `quota` 终态、首试即 600s 长冷却熔断、零退避重试）同步入 `llm-technical.md`（§4.2 与 403 的配合、§6.1 容错层次新增「全链延迟重试」、§6.2 重试表、§6.3 失败原因表补 `FAIL_REASON_QUOTA_EXCEEDED`、§12.2 全局键）、`requirements.md`（R-LLM-10 与 `max_retries` 说明）、`technical.md`（LLM 降级与 C26）、`developer-guide.md`；② `llm_full_fail_retry_delay` 补入 `_DEFAULT_LLM_SETTINGS`/模板/已知键集（原 `skeleton` 直接读取却未登记，用户设置会被判「未知配置项」），加「默认集 ⊆ 已知键集」结构回归；③ `_factor_zoo` 根路径收敛为包 `__init__.py` 的 `PROJECT_ROOT` 单一来源（原 catalog/metrics/stages 三处各算 `parents[2]`）。

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1 ~ v0.12.8（2026-10-03 ~ 2026-10-09）
- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.12 + v0.12.0（2026-09-15 ~ 2026-10-03）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12)
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
