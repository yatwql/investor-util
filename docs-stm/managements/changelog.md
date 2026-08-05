# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.7] - 2026-08-05

### 测试可移植性修复：指标熔断持久化路径断言兼容 Windows 路径分隔符

- **动机**：`test_circuit_breaker_wrapper.py` 的 `test_default_path_under_state_dir` 用硬编码正斜杠子串 `data/state/metrics_breaker.json` 对实际路径做 `in` 匹配——Linux 下 `tmp_path` 为正斜杠路径恰好命中，Windows 下为反斜杠路径断言落空，导致 Windows 平台 dev-verify 单点失败。
- **修复**：断言前将实际路径分隔符统一规范化为 `/`（`path.replace(os.sep, "/")`）再匹配，正向/负向两条断言同时修正；源码（`os.path.join`）与 conftest 隔离（`tmp_path / ...`）本就 OS 感知，无需改动。
- **测试**：`test_circuit_breaker_wrapper.py` 10 项全通过；额外以 Windows 反斜杠路径字面量模拟验证规范化逻辑通过。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；提交前跑 dev-verify 全量验证。

### 语义命名索引双向校验（check-semantic-index.py + 功能语义命名表存量修正 + 架构约束参照）

- **动机**：「功能语义命名表」（技术设计文档中「代码标识符 = 文档中文描述」的唯一现状基准）此前是「记录性活索引」而非自动约束——`check-code-traces.py` 只做负面禁止（禁任务代号/魔法编号），**不校验正面一致性**：新增 `report_submodules.*` 开关键可绕过登记、功能删除后表行可残留僵尸条目、合并章 sheet key 无人核实。预演审计实证漂移：`cost_lots` 未登记（表内成本流水此前由 `fund_flow`/`dividend_flow` 覆盖）、`dividend_flow`/`holding_diagnosis` 为僵尸条目。
- **存量修正（技术设计文档）**：表与代码对齐——`cost_lots` 补登记（`report_submodules.cost_lots`，默认关）、移除僵尸条目 `dividend_flow`/`holding_diagnosis`（并入说明注明其并入归属）、合并章 sheet key 三枚（`position_relationship`/`portfolio_history_drawdown`/`style_factor`）核实均存在于 `registry._REPORT_SECTION_DEFAULT`；表体包裹 `<!-- semantic-index:start/end -->` HTML 标记供脚本定位（与 check-version-consistency / test_runner 文档写入器同款标记习语）。
- **新增 `check-semantic-index.py`**（独立脚本，正面校验，与 check-code-traces 负面禁止互补）：正向——`_config_defaults.py` 中 `report_submodules` 各键须在「功能语义命名表」中登记（表外键报错）；反向——表中每个语义 slug 在 `src/python` 至少一处非注释代码引用（防僵尸条目，tokenize 剔除注释）；合并章——注声明 sheet key 须在 registry 中存在。退出码 0/2，`--ci` 只输出违规。
- **纪律升级为架构约束参照**：技术设计文档「架构设计约束」章节开头新增「约束外参照（语义命名纪律）」——除该章节编号约束外，语义命名纪律以「功能语义命名表」为唯一现状基准、由双脚本强制；表所在章节的纪律行同步指向该参照。**不新增约束编号**：语义命名纪律以「约束外参照」形式并入，避免扩充约束编号集合，从而无需波及 check-code-traces 的约束代号边界匹配与其边界测试。
- **门禁接入**：CLAUDE.md 提交前（P0）/发布前（P2）门禁、testplan.md 回归门禁清单增补 `check-semantic-index.py --ci`；scripts-reference.md 一览表 + 详细章节、folders.md 目录树与统计同步。
- **测试**：`test_check_semantic_index.py` 24 项（标记区间提取/表行解析/合并章 key 解析/权威源 ast/注释剔除/反向存在性/run_checks 三向/真实仓库冒烟），全部通过；新增脚本自身通过 check-code-traces --ci 自检。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；提交前跑 dev-verify 全量验证。

### 文档内容修正（菜单 P 章节组 / enable_action 配置入口 / 场内场外识别描述 / 注册表使用说明）

- **菜单 P 章节组修正**：`faq.md` 菜单 P 可配置章节组由「三个」修正为「四个」（基金深度分析/市场新闻/历史走势/组合演进），并补充「组合演进」对应 `enable_portfolio_evolution` 开关；`how-to-config.md` 同步修正——`enable_action` 无菜单入口（需手动编辑 `config.json`），菜单 P 仅配置其余 4 个章节组可见性。
- **场内/场外识别描述修正**：`reports-instruction.md` 移除「F 开头标记场外基金」的错误描述，改为程序自动识别规则（账户渠道/名称关键词/代码前缀三要素联合判定，QDII 单独分类，识别结果以取价方式列颜色区分），与实际 `market_value.py` 分类逻辑一致。
- **注册表使用说明修正（`how-to-use-registry.md`）**：① 注册表结构表移除已并入「持仓关系矩阵」的缓存模块 `fund_overlap`（`_MODULE_REGISTRY` 中已删除），TTL 由「24h~7d」修正为「24h」；②「无需手动维护的派生产出」误称报表页签标题/Excel 标签随 `_MODULE_REGISTRY` 自动派生——实际由独立 `_REPORT_SECTION_DEFAULT` 注册表驱动，改为说明注释；③「计算模块注册表」交叉引用去掉裸 `§` 符号，改文字指引；④ 计算模块表 `量化指标` 名称对齐代码 `量化指标计算`。**同步清理**：`how-to-config.md` 缓存 TTL 表移除同源失效行 `fund_overlap`（模块已删除）。
- **测试**：纯文档修正，无代码变更。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### 调仓建议可行化层区分场内/场外渠道

- **动机**：调仓建议可行化层（`analysis/rebalance_advisor`）此前仅凭代码前缀 + 名称关键词判定证券类型，场外持有基金（LOF/开放式指数基金，如 `161725 招商中证白酒指数A`、`110022 易方达消费行业`）的 16/11 开头代码命中场内基金前缀，被误当场内处理（100 份取整 + 仅计佣金），漏计赎回费且份额取整过粗。
- **持仓明细携带渠道上下文**：`holdings_details` 契约（`orchestrator.prepare_report_data` 与 `_report_generation` both 路径 `_both_action_holdings_details`）新增 `channel` 字段，按账户关键词 `is_offsite_fund(account)` 判定填充（`"场外"`/`"场内"`）；`getattr` 兼容缺 `account` 的 detail 对象（测试 fixture 简化版）。
- **可行化层按渠道消费**：`_round_to_lot`/`estimate_fee` 新增 `channel` 参数——`channel="场外"` 强制整数份取整 + 计收赎回费；非场外回退既有证券类型判定（A 股印花税 / 场内基金仅佣金 / 100 份取整），避免用单一渠道覆盖 A 股印花税等差异化费率。显式 `channel` 优先，其次按 `account` 关键词判定，两者皆无保持向后兼容。候选构造（再平衡/纪律）携带渠道到可行化层。
- **测试**：`test_rebalance_advisor.py` 新增渠道感知 10 项（场外 LOF/开放式基金整数份 + 赎回费、场内 ETF 100 份 + 仅佣金、A 股渠道仍计印花税、显式 channel 优先于 account、账户关键词回退、无渠道回退代码判定）；`test_orchestrator.py` 新增契约 channel 字段 2 项（场内/场外账户各一）+ both 路径 channel 接线 1 项。
- **门禁**：dev-verify 1820 passed + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### 再平衡信号配置化阈值 + 静默期 + 回撤纪律峰值注入 + 日收益口径统一（第四批）

- **再平衡信号配置化阈值 + 静默期**：`analysis/simple_rebalance` 的再平衡阈值与静默期由硬编码改为配置化参数（`threshold`/`silence_days`/`silence_file`），与纪律层共用 `_silence.py` 静默机制；智囊团深度复盘「行动摘要」的 LLM 段**豁免静默期**（`prompts_core` 以 `silence_days=0` 调用），保证每次复盘完整呈现超限信号、不被静默窗口抑制；新增回归验证 LLM 段不写共享静默文件。
- **回撤纪律管线注入组合历史峰值市值**：组合级回撤纪律此前在生产路径**从未激活**——`build_action_data` 的两处调用（`orchestrator.prepare_report_data`、`_report_generation` both 路径）均未传 `portfolio_peak_mv`，而峰值只能从 `history_data.bars` 计算且晚于 action_data 构建。修复：新增 `metrics.compute_portfolio_peak_mv(bars)` 计算历史峰值；both 路径将 action_data 构建移至「3. 历史走势」之后并注入峰值；full 路径在 `_prepare_full_risk_metrics` 后重建 action_data 并覆盖 prep/pipeline_data；新增 `persist_silence` 参数使 `prepare_report_data` 的中间占位构建不读写纪律静默文件，保证峰值就绪后的最终构建为管线中纪律静默的唯一写入方（单品信号不被占位构建抢占静默而误抑制）。
- **日收益口径统一**：`metrics.compute_daily_returns` 成为 tail_risk 与组合走势表共用的单一口径源（prev 与 curr 市值均 >0 才计入，跳过缺失/占位/清仓的伪 -100% 单日）；`tail_risk` 与 `portfolio_history` 均委托之，VaR/最大单日跌幅/年化波动率与走势表日收益完全一致。
- **测试**：新增组合峰值市值计算 4 项、`persist_silence=False` 不读写静默文件 1 项、both/full 路径峰值注入接线 3 项（含历史走势关闭时峰值取 None 的降级路径）。
- **门禁**：dev-verify 1810 passed + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### 统一熔断网关 + 指标熔断状态文件落盘位置修正 + 菜单 [1] 基础缓存刷新补齐

- **统一熔断网关（三路聚合）**：`CircuitBreakerGateway` 将数据源熔断（DataSourceRegistry）、LLM 端点熔断、指标熔断（IndicatorBreaker）三路状态聚合到统一查询入口——`gateway.get("data_source"/"indicator"/"llm")`、`gateway.summary()`，并新增模块级 `get_indicator_breaker_status()`/`get_all_breaker_status()` 包装函数。`technical.md` §2.2「统一熔断网关」段落同步更新为三路聚合描述。
- **指标熔断状态文件落盘位置修正**：指标熔断器持久化文件从 `data/cache/metrics_breaker.json` 调整至 `data/state/metrics_breaker.json`（运行时状态目录），旧路径文件在首次加载时自动改写至新位置并删除旧文件，避免被缓存清理误扫。`technical.md` §2.2 持久化列与 `datasource-reliability.md` §4.1 同步更新。
- **菜单 [1] 更新基础类缓存补齐**：新增三项刷新——财经新闻（持仓关键词聚合预热 `news_` 缓存）、基金经理（逐基金刷新 `fund_manager_` 缓存）、基金风格扩展（A 股扩展数据预取到 registry 会话缓存）；同时补齐有基金路径此前缺失的行业分类、分红刷新。纯股票组合路径同样刷新新闻与风格扩展。`how-to-menu.md` 菜单 [1] 说明同步更新。
- **测试**：新增统一熔断网关 12 项、指标熔断持久化路径 3 项、菜单 [1] 扩展缓存刷新 19 项（新闻/基金经理/风格扩展 helper + 并行编排 + update_basic_cache 两分支接线 + 显示三行输出）。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]；提交前跑 dev-verify 全量验证。

### 基金业绩评级类型差异化阈值接线

- **动机**：`tiantian_ranking` 已定义四组类型差异化评级阈值（默认/债券/指数/QDII）与类型提示参数，但 `fetch_fund_rankings` 调用评级计算时未传类型，导致债券型/QDII 的宽松阈值与指数型的严格阈值**从未生效**，所有基金均按主动权益默认阈值评级。
- **接线**：新增 `_fund_type_hint_from_name(name)`——按基金名称推导阈值类型键（优先级：QDII/隐式海外 → 债券型 → 指数/ETF/联接 → 默认，与穿透分类 `classify_penetration` 一致）；`fetch_fund_rankings` 从 JS `fS_name` 提取名称后推导类型，透传至 `_calc_rating_from_entry`，并在返回结构 `type` 字段回填类型键（此前恒为 `""`）。调用链（fetcher 包装、报告、缓存刷新、候选比较）零签名变更。
- **行为影响**：债券型/QDII 在 10~15% 百分位区间由「良好」升至「优秀」，指数型在 25~30% 区间由「良好」降为「稳定」，评级与「类型」列展示的基金分类口径一致。
- **文档**：`requirements.md` §6.4.5 基金业绩分析补充类型差异化评级阈值表。
- **测试**：`test_tiantian.py` 新增类型推导 9 项 + `fetch_fund_rankings` 接线 6 项（mock `_request_pingzhong_data`，覆盖债券/指数/QDII/主动权益四类阈值生效与无排名数据回退）。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]；提交前跑 dev-verify 全量验证。

---

## 归档

- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.6（2026-08-04 ~ 2026-08-05）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
