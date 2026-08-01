# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：0.9.5-dev
> 审查范围：全代码库（src/python/ + src/test/ + scripts/）
> 审查基准：technical.md §8 架构设计约束（C1~C19）+ §1.4 核心架构决策 + 代码质量最佳实践
> 审查日期：2026-07-29

---

## 当前待处理问题

### P2 - 代码质量（低优先级，增量改进）

#### P2A — 文件过长（>500 行，建议拆分）

| # | 文件 | 行数 | 拆分建议 |
|---|------|------|----------|
| **rf-75** | `core/registry.py` | 617 | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责 |
| **rf-76** | `llm/fact_checker.py` | 623 | 核心校验逻辑与辅助函数分离（注：长函数已拆分，文件级别未拆） |
| **rf-77** | `tui/handlers_config.py` | 553 | JSON 文本编辑函数提取到 `config/` 子模块 |
| **rf-78** | `fetcher/batch.py` | 549 | BatchDispatcher 本身内聚，可维持现状 |
| **rf-79** | `core/code_utils.py` | 541 | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出 |
| **rf-80** | `report/data_status.py` | 528 | DegradationTracker 单类偏大 |
| **rf-81** | `report/html_renderers.py` | 521 | 所有 HTML render 函数揉合一体 |
| **rf-85** | `fetcher/fund.py` | 394 | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 472 | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 447 | Excel 编排器 |

### P3 — 测试覆盖缺口（建议补齐）

| # | 位置 | 问题 |
|---|------|------|

---

## 已修复（摘要）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-101 | `test_runner.py` 打印子进程捕获输出时，GBK 控制台遇 U+FFFD 替换字符抛 UnicodeEncodeError，Phase A 后 runner 崩溃致 Phase B 不执行（dev-verify 门禁跑不全） | `sys.stdout.reconfigure(errors="replace")` 模块级兜底，异常时静默跳过 | `changelog.md` → Fix |
| rf-100 | `test_fetcher_index.py::test_tencent_success` mock 目标笔误：mock `tencent.fetch_price`，实际调用 `fetch_index_price`——有外网时真调成功侥幸通过，无外网环境失败 | mock 目标对齐 `fetch_index_price` + 新增 `assert_called()` 回归守卫 | `changelog.md` → Fix / Test |
| rf-99 | TUI [S] 菜单泄漏旧设计遗留辩论三模块：`debate_pro`/`debate_con`/`debate_synthesis` 显示为 6/7/8 开关，切换仅写入 `enabled_llm` 但无生成路径消费（僵尸开关） | 菜单层过滤：`tui_menu.py` 新增 `LLM_MENU_HIDDEN_KEYS` + `filter_menu_llm_modules()`，[S] 面板与模型路由显示同步过滤；注册表条目保留（缓存 TTL/前缀清理依赖） | `changelog.md` → Fix |
| rf-96 | 辩论虚构过滤按"行"删除，HTML 单行输出被一个误判 token 整段清空（TOP2/TOP3/Smart 误判 → 白脸 6412 字符过滤后 0 字符 → 回退普通模式） | 过滤粒度改"行内句段"级；`raw_filter_fn` 钩子使过滤在 markdown_to_html 前作用于原始 Markdown；`TOP\d` 与 `smart`/`money` 白名单降低误报 | `changelog.md` → 辩论虚构过滤修复 |
| rf-97 | `set_config` 读-改-写无锁，并发下 get_config 读失败静默回退默认配置覆盖写，丢失已有配置项（P2 verify 门禁暴露：并发测试 final.get("base")=None） | `_config_lock` 改 RLock；`set_config` 整个 RMW 纳入锁内串行化；`get_config(_strict=True)` 文件存在但读失败时抛异常中止写而非静默覆盖；新增损坏文件回归测试 | `changelog.md` → Fix |
| rf-98 | LLM 空内容误报"内容被过滤"（DeepSeek V4 兼容端点为强制推理模型，thinking 耗尽 max_tokens 预算时响应仅含 thinking block 无 text；安抚重试无效） | `_extract_content` 无 text block 时区分根因：`stop_reason=max_tokens` 记录"思考耗尽预算"日志，其他记录"可能被过滤"；统一返回 `None` 走 provider 切换；health_check max_tokens 4096→8192 + expert_review/health_check effort high→medium（实测 mt=8192 正常产出） | `changelog.md` → Fix |
| rf-90 | `_build_prompt_appendix` 无专用测试 | 新增 `TestBuildPromptAppendix` 4 用例（空持仓/单品种/多品种排序/零市值）+ `TestBuildExpertReviewPromptSkipScenarios` 3 用例 | `changelog.md` → Test |
| rf-91 | `fact_checker` 数值混淆（601939 11.0%→2.0%） | 自动修正 v3：返回 correction 二元组 + apply_numerical_corrections + tolerance_overrides | `changelog.md` → 事实校验 v3 |
| rf-92 | LLM 持仓排名幻觉（040046/561910 声称"最大持仓"）| 统一注入架构：`_build_prompt_appendix` 在 `_run_standard_mode` 自动注入 TOP3/速查表/白名单 | `changelog.md` → Prompt 防御统一注入 |
| rf-93 | 辩论 synthesis 重复白脸/黑脸观点 + 情景分析 | `_SYSTEM_DEBATE_SYNTHESIS` 重写：禁止重述论点、禁止插入情景分析 | `changelog.md` → 辩论模式 synthesis 修复 |
| rf-94 | `_build_debate_synthesis_prompt` HTML误标为markdown | ` ```markdown` → ` ```` | `changelog.md` → 同上 |
| rf-95 | `_SYSTEM_EXPERT_REVIEW` 情景分析双重指令 + 辩论 pro/con 情景重复 | 从 system prompt 移除情景段移至 user prompt 单一注入；`skip_scenarios` 参数使辩论模式跳过情景分析 | `changelog.md` → Fix |

---

## 归档

### 归档档案

- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
