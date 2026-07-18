# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.7.1-dev] - 未发布

### Added
- **Gemini Extended Thinking 支持**：`call_gemini()` 新增 `llm_config` 参数，根据 `thinking_enabled_{模块}`/`thinking_budget_{模块}` 配置向 `generationConfig.thinkingConfig.thinkingBudget` 注入推理预算。`api_base.py` 模型兼容列表新增 `gemini-2-5-` 前缀（仅 Gemini 2.5 系列支持）

### Changed
- **LLM 配置修复**：DeepSeek endpoint 补全路径 `.../anthropic` → `.../anthropic/v1/messages`（缺少 `/v1/messages` 导致 404）；模型名 `DeepSeek-V4-Flash` → `deepseek-v4-flash`（API 要求全小写）
- **Gemini URL 构造修复**：`call_gemini()` 传入 `endpoint` 时正确拼接 `/v1beta/models/{model}:generateContent` 路径，不再只取基础地址

### Fixed
- **基金历史净值获取全部为空（P0 修复）**：天天基金 `_parse_nav_trend()` 只认 `YYYYMMDD` 和 `YYYY-MM-DD` 格式，但东方财富 pingzhongdata 接口的 `x` 字段已改为**毫秒时间戳**（13 位），所有条目被 `continue` 跳过 → 返回 0 条。新增毫秒时间戳→日期转换分支
- **天天基金 HTTP 客户端健壮性**：`_request_pingzhong_data()` 缺少 `follow_redirects=True` 和 `raise_for_status()`，与同文件的 `_request_fund_html()` 不一致。补充后避免静默失败
- **JS 变量声明格式兼容**：`_parse_nav_trend()` 正则从仅匹配 `var` 扩展为匹配 `var`/`let`/`const`/`window.` 前缀
- **东方财富备用链路 HTTP 健壮性**：`fetch_fund_nav_history()` 补充 `follow_redirects=True` 和 `raise_for_status()`
- **LLM 用量页模型名显示"未指定"**：`format_session_usage()` 过滤 `models` 列表中 `"未指定"` 占位值，避免显示 `"deepseek-v4-flash / 未指定"`
- **LLM 用量页 Endpoint 缺失**：`_write_llm_summary_section()` 将 Endpoint 行移至汇总区的 `pairs` 列表，使其始终显示
- **A 股指数腾讯链路失败**：`_fetch_indices_from_tencent()` 使用 `tencent.fetch_price()` 获取指数行情，但该函数的前置类型守卫（`is_a_share_code`/`is_exchange_fund_code`）将 `sz399001`（深证成指）和 `sz399006`（创业板指）过滤为"不支持的类型"。改用 `tencent.fetch_index_price()` 修复，此函数无类型限制，专为指数设计
- **akshare 超时无重试**：`_run_with_timeout()` 新增自动重试机制（网络错误时 1 次重试 + 1s 间隔）；`get_profit_forecast()` 超时从 15s 放宽至 30s（全量数据获取）；`_fetch_all_dividends()` 新增超时保护（60s，此前完全无保护可能永久阻塞）
- **移除"机构覆盖"列遗留的引用**：`html_renderers.py` 仍从 `html_builders` 导入已删除的 `_load_profit_forecast`，导致 `ImportError` 报告生成崩溃；同步清理 `html_writer.py` 中向 `build_perf_data_status` 传 `profit_success` 的死参数，移除测试文件中对应 `patch` 和用例

### Docs
- **项目统计信息**：`folders.md` 新增统计表（项目概览：源代码 128 文件 31,570 行，测试代码 155 文件 49,674 行/3,211 用例，文档 67 文件 31,523 行）；`test-coverage.md` 测试项数同步更新至 v0.7.1-dev 最新数据（`all` 模式 3211 项）

---

## [0.7.0] - 2026-07-18

### Added
- **增强多链 Provider 状态显示（TUI + CLI）**：新增 `get_circuit_status()` 公共函数暴露熔断器状态查询；TUI 菜单 `[4]` / `show_config` 时多链模式展示各 Provider 后端类型、模型名、优先级、熔断状态（带绿✓/红⚠图标）；CLI `cache --stats` 同步输出 LLM Provider 状态详情
- **文档**: changelog.md v0.6.10 变更记录迁移至归档文件

---

> v0.6.x 及更早版本变更记录已归档：
>
> - [`v0.6.x`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
> - [`v0.5.x`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
> - [`v0.4.x`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
> - [`v0.3.x`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
> - [`v0.2.x`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
> - [`v0.1.x`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
