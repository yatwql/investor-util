# 投资复盘助手 — 质量控制与测试标准
> 文档版本：0.11.6-dev

---

## 0. 测试环境要求

| 环境项 | 要求 | 说明 |
|:-------|:-----|:-----|
| **Python** | >= 3.10 | f-strings / match-case / `timezone` 等语法特性要求 |
| **依赖安装** | `pip install -r requirements.txt` | 含 httpx / openpyxl / akshare（间接依赖 pandas）|
| **网络** | 全量测试均不需要（全 mock） | Provider 联通性由运行时回退/熔断治理，非门禁。另有 opt-in `live` 套件（`--mode live`）真实联网验证数据源可达性，默认排除、不入门禁 |
| **系统时区** | 不限 | `datetime.now(timezone(hours=8))` 保证 UTC+8 一致性 |
| **磁盘** | `data/cache/` `data/config/` `reports/` 读写权限 | 首次运行自动创建缺失目录 |
| **aktools/pandas** | akshare 需 pandas | 部分 test_*.py 间接依赖，CI 中需预装 |
| **pytest 插件** | `pytest-mock` 可选 | 项目中统一用 `unittest.mock.patch`，非强制 |

> 注：CI/CD 环境（GitHub Actions 等）中需额外注意 akshare 的 pandas 依赖和网络 mock 覆盖。

## 1. 测试分类

### 1.1 单元测试

**测试框架**：`pytest`（含 `unittest.mock.patch` + `pytest-mock`）

**覆盖要求：**

| 模块 | 覆盖目标 | 强制验证项 |
|:-----|:--------|:-----------|
| `core/models.py` | 100% 字段验证 | 有效值、边界值（0/负数/超长字符串）、类型错误 |
| `config/` 子包 | 100% 读写/异常 | 文件缺失、JSON 损坏、null 值覆盖、类型错误、权限拒绝、并发写入 |
| `core/reader.py` | 标准格式 + 7 种异常 | 空文件、缺列、多工作表、全空行、数值类型转换失败、zip 损坏、临时文件（~$前缀自动跳过） |
| `cache/` 子包 | 过期判断、读写、清理 | 原子写入、损坏恢复、TTL 边界（0s/1s/过期1s）、前缀匹配、并发 access、gzip 透明解压 |
| `providers/*.py` | mock HTTP + 异常 | 200 正常 / 空数据 / 超时 / 429 / 503 / JSON 格式错误 / HTML 而非 JSON / 空响应 / 字段缺失 / 编码异常 |
| `providers/tiantian_holdings.py` | 三跳阶梯次序 + 锚点解析 | **次序不变量**：第 1 跳命中即不请求主页面、第 2 跳请求失败即返 None 不落第 3 跳、第 3 跳仅在「第 2 跳无持仓且无目标 ETF 锚点」时到达、联接基金在第 2 跳即返回故第 3 跳**不可达**（回归锁定「兜底不得遮蔽联接基金」）；第 2 跳 `date=""`（报告期不从主页面取）；`parse_feeder_target_etf` 正反例——**常规 ETF 页的反向链接「查看相关ETF联接」必须被拒**（两重区分各测一遍）、锚点指向自身、目标非场内代码、无标签链接；`_extract_fund_name` 无括号标题返回空串 |
| `llm/` 包 | 全路径覆盖 | API 路由、Provider 回退、截断检测+自动重试、空内容安抚重试、熔断器、缓存命中/未命中、Extended Thinking 注入/降级、thinking 耗尽自动重试（关闭 thinking 同 provider 重试一次，仍失败才切换）、thinking 并发信号量（`llm_max_thinking_concurrency` 串行化，`TestThinkingConcurrencyLimit`）、指纹确定性 |
| `llm/` — 辩论模式 | 6 文件专项覆盖 | `test_debate_generators.py`（三段生成流程 pro→con→synthesis 控制）、`test_debate_prompts.py`（提示词模板/合成提示/集中度问答块）、`test_debate_token_budget.py`（Token 预算守卫 1×/2× 阈值）、`test_debate_edge.py`（边缘测试文件隔离 合规边缘场景 11 项）、`test_debate_conditional.py`（条件推理场景注入）、`test_debate_qa.py`（集中度问答阈值触发） |
| `report/*.py` | 正常 + 空数据 + 边界 | 单条持仓、最大 100 条持仓、零成本/零市值、全亏损、全盈利、混合账户 |
| `core/market_hours.py` | 所有时段边界 | 开盘/收盘/午休/周末/节假日/UTC 时区、config 覆盖、API 掉线回退 |
| `core/provider_registry.py` | 100% 熔断/缓存/策略 | Provider 注册/熔断（默认 3 次→冷却 300s→自动恢复，批量 API 如 eastmoney_industry 为 6 次→120s）、会话缓存 get/set/contains/clear/淘汰、策略选择(交易时段/熔断/QDII豁免)、链式熔断检测、并发安全、审计报告、phase_timeout 嵌套保护 |
| `tui/handlers_*.py` | 各菜单命令入口 | 正常路径 + 配置缺失 + 异常日志 |
| `tui/tui_menu.py` | 所有 20 选项 | 合法/非法输入、Ctrl+C、空目录选择、多文件导航、开关门控项 `[D]` 的裁剪与还原 |
| `analysis/correlation.py` | Pearson 相关矩阵计算+降级 | 已知答案（r=±1/缩放不变）、不显著配对、下三角布局、配对 |r| 降序、数据不足/单品种/无有效收益降级、名称回退、数据契约键、NaN/Inf/None 过滤、重复日期去重、日期缺口对齐、极大幅值钳位、多品种大矩阵 |
| `report/position_structure_sheet.py` | 重合度/相关性/集中度三区块 Excel 呈现 | 矩阵/配对/说明三区齐全、下三角+对角+上三角空、N/A 格、available=False/None 占位、配对 |r| 降序 |
| `report/report_template.html`（correlation 模块） | 相关性章节 HTML 呈现 | 汇总卡+相关度最高+热力矩阵+配对明细、单元格样式分支（强正/强负/不显著/N/A）、不足品种提示、available=False 降级占位、correlation_data=None 章节隐藏 |
| `analysis/portfolio_evolution.py` | 多快照趋势聚合计算 | 多账户合并、快照缺市值回退成本权重、HHI 计算、TOP 持仓变迁、快照数不足 available=False、历史快照容错跳过 |
| `report/evolution_sheet.py` + `report_template.html`（evolution 模块） | 组合演进双端呈现 | 汇总/总市值/HHI/TOP/账户流/说明顺序、多账户流表、单账户无流表、HHI 无效期记 "-"、available=False 占位、evolution_data=None 章节隐藏、enable_portfolio_evolution=False 章节隐藏（board 层）、3 图各带 .chart-caption（图下说明） |
| `analysis/whatif.py` | 双持仓成本口径 diff 计算 | 新增/清仓/加仓/减仓/不变识别、份额容差(<1e-3)、成本权重+HHI、汇总 delta+箭头、分类配置（_CATEGORY_ORDER 排序）、多账户合并、两侧空降级、单侧空=全清仓仍可算 |
| `analysis/whatif_backtest.py` | 生效日时序回测纯计算 | 生效日→请求天数折算/钳位/坏格式/未来日期、并集+LOCF+锚点对齐、归一化/收益率/回撤序列数值、5 指标对比、数据不足/两侧空/不可对齐 available=False、status 降级传播 |
| `report/whatif_operations.py` | whatif 共享层编排 | build_whatif_data→校验→写报告；未指定生效日不调用回测且无 backtest 键；指定生效日合并进 data；回测异常→ok=True 且 available=False；返回 None 不加键 |
| `report/whatif_sheet.py` | 调仓 What-if Excel 页签呈现 | 摘要(文件对比+变动统计+汇总+箭头)、分类配置权重%、变动明细行底色（新增绿/清仓红/加仓黄/减仓蓝/不变灰）、时序回测页签（指标表+净值/回撤序列+占位）、available=False/None 占位 |
| `report/whatif_writer.py` + `whatif_template.html` | 调仓 What-if 独立 HTML 页 | ①~⑦ 段齐全（未指定生效日④时序回测隐藏）、双环形图+回测 2 折线图各带 .chart-caption（图下说明）+#whatif-chart-data/#whatif-backtest-chart-data JSON（R9 最小化）、行动作行 class + badge、箭头类、available=False 占位 |
| `cli/cli.py`（whatif 子命令） | whatif argparse + 处理器 | --candidate 必填、--base 可选、--effective-date 解析并透传、_handle_whatif 委托（显式 base/config 默认/读取失败/目标失败/不可用数据不写报告）、main 透传 |

### 1.2 数据边界 Edge Case 强制清单（通用规范）

写任何函数/模块的测试时，必须从以下 edge case **类型**中选取适用的来覆盖（至少每函数 1 项）。
这是横切所有模块的**测试编写规范**，关注**输入值域的极端情况**。

| Edge Case 类型 | 示例 | 验证点 |
|:---------------|:-----|:-------|
| **零值边界** | 成本=0、市值=0、份额=0 | 不抛出 ZeroDivisionError，输出 `0.0` 或 `--` |
| **非有限数值** | 解析结果为 `float("nan")` / `float("±inf")`（上游脏值、除零派生） | **不抛异常**——`try: float(x) except` 与 `or 0.0` 对二者均**兜不住**（NaN 参与比较恒 False、`or` 不把 NaN 当假）；必须经 `core/num_utils.safe_num` 显式拦下，验证点见 `test_numeric_guard_regression.py` |
| **极大/极小值** | 市值超 1e12、成本=0.0001、份额=1e8 | 数值不溢出，`_fmt_wan()` 正确定标 |
| **空数据集** | 空持仓文件、空 API 响应、空缓存文件、空新闻列表 | 不崩溃，输出合理占位 |
| **单条/极限大** | 1 条持仓 vs 1000 条持仓 | 前者不空转，后者有时间保护（不超时） |
| **Unicode/全角** | 名称含全角括号、emoji、日文 | 不崩、JSON 序列化正常、Excel 不乱码 |
| **并发/竞态** | 两个线程同时 `cache.set()` 同 key | 不产生损坏文件 |
| **时区安全** | 系统时区非 UTC+8 时运行 | `datetime.now(timezone(hours=8))` 一致 |
| **版本兼容** | 缓存数据为旧版本占位符（`--` / `—`） | 正确降级读取不报错 |
| **特殊代码格式** | `600000`（无前缀）、`sh600000`、`600000.SH` | 统一处理 |
| **文件系统边界** | 缓存目录不存在、磁盘满、路径含空格/中文 | 自动创建目录、gzip 压缩回退 |

### 1.3 业务场景测试（Scenario Tests）

按真实用户行为组合设计的集成测试场景，通过分层 pytest 标记实现灵活选择。
标记定义、覆盖规模和典型耗时见 [`test-coverage.md`](./test-coverage.md) → 场景测试分组。

各场景的文件归属：

| 测试文件 | 覆盖场景 | 职责范围 |
|:---------|:---------|:---------|
| `scenario/basic/test_scenario_basic_flows.py` | S1-S5 | 基础业务链路：股票/基金/多账户/缓存首次/缓存命中 |
| `scenario/resilience/test_scenario_resilience_flows.py` | S6-S9 | 异常容错场景：纯债/断网/单账户/零成本 |
| `scenario/resilience/test_scenario_extreme.py` | S0c+S10 | 极限场景：超多持仓/极端份额/高精度净值/零值组合 |
| `scenario/llm/test_llm_mixed_cache.py` / `test_llm_extended_thinking.py` / `test_llm_disabled.py` / `test_llm_disabled_cache.py` / `test_llm_network_error.py` / `test_llm_partial_cache.py` | S11, S13-S17 | LLM 混合缓存/Thinking/禁用/禁用+缓存混合/断网降级/部分缓存超期 |
| `scenario/llm/test_llm_module_info.py` | S12, S20 | LLM 全部失败（5 种原因）/ 状态契约输出一致性（disabled/failed/success/cached） |
| `scenario/llm/test_llm_empty_holdings.py` | S18-S19 | LLM 全缓存无 API 调用 / 空持仓降级 |
| `scenario/basic/test_scenario_holdings_quality.py` | S0a/S0b/S0d | 持仓质量：清仓/同名多份额/特殊字符 |
| `scenario/basic/test_scenario_special_securities.py` | S21-S28 | 特殊品种：港股通/可转债/REITs/货币基金/科创板/北交所/商品ETF/跨境ETF/纯债 |
| `scenario/basic/test_scenario_operational_behavior.py` | S29-S33 | 操作行为：分红送转除权/定投成本摊薄/部分调仓/跨账户转仓/新股中签待上市 |
| `scenario/basic/test_scenario_penetration_basic.py` / `_advanced.py` / `_mixed.py` / `_edge.py` | SP1-SP10 | 穿透 TOP10 分类/合并/排序/交叉持股验证 |
| `scenario/basic/test_scenario_section_order.py` | — | 报告序号可配置：自定义/部分配置/未知 key 合并场景 |
| `scenario/basic/test_pipeline_smoke.py` / `test_pipeline_metrics_injection.py` / `test_pipeline_style_factor_regression.py` | — | 管线冒烟/指标注入/风格因子回归管线（数据契约 + 全失败 source_failed + 空持仓 insufficient） |
| `scenario/datetime/test_datetime_scenarios.py` | T1-T21 | 日期/时间场景：市场状态×产品类型×边界×Long Tail |
| `scenario/llm/test_llm_hallucination.py` | `scenario_llm` | LLM 幻觉率采样测试：10 组标准化持仓 × 事实校验器 × 幻觉率统计 |

**业务场景规格（S0a-S0d、S1-S34、D1-D3、T1-T21）：**

| 场景 | 前置场景 | 所属文件 | 前置条件 | 操作 | 验证点 |
|:-----|:---------|:---------|:---------|:-----|:-------|
| **S0a: 清仓持仓** | — | `test_scenario_holdings_quality.py` | 持仓含份额=0 的已清仓品种 | 菜单 E | 清仓品种不计入市值、盈亏、总计；分类表跳过空行 |
| **S0b: 同名多份额** | — | `test_scenario_holdings_quality.py` | 同一基金分多笔买入（A 类+C 类同一代码） | 菜单 B | 多份额合并计算、穿透不崩溃、分类各计各 |
| **S0c: 超多持仓** | — | `test_scenario_extreme.py` | 200 条持仓（覆盖各品种类型） | 菜单 L | 所有账户小计正确、总计正确、无性能问题（标记 `scenario_extreme`） |
| **S0d: 特殊字符** | — | `test_scenario_holdings_quality.py` | 名称含全角括号/空格/日文/emoji | 菜单 L | 分类正确、穿透正常、Excel/HTML 不崩溃 |
| **S1: 纯股票组合** | — | `test_scenario_basic_flows.py` | 持仓仅含 3 只 A 股，无基金 | 菜单 B | 穿透 TOP10 等于直接持股；基金业绩显示"无基金"；总计正确 |
| **S2: 纯基金组合** | — | `test_scenario_basic_flows.py` | 持仓仅含 5 只基金（ETF+主动+QDII） | 菜单 L | 穿透计算正确、分类表无"股票"行、LLM 正常生成 |
| **S3: 混合多账户** | — | `test_scenario_basic_flows.py` | 3 个账户：证券（股票+ETF）、支付宝（场外基金）、微信（债基） | 菜单 L | 分账户小计正确、总计 = 小计和、分类表按账户分组 |
| **S4: 新持仓无缓存** | — | `test_scenario_basic_flows.py` | 删除全部缓存后首次生成 | 菜单 L | 所有 API 正常获取、无缓存命中提示、生成时间 > 缓存命中场景 |
| **S5: 缓存全命中** | **S4** | `test_scenario_basic_flows.py` | 连续两次执行菜单 L，间隔 < TTL | 菜单 L × 2 | 第二次所有 LLM 显示"缓存命中"页脚、总费用为 0 |
| **S6: 纯债券基金组合** | — | `test_scenario_resilience_flows.py` | 持仓仅含债券基金（国债ETF + 场外债基） | 菜单 E | 穿透 TOP10 无股权覆盖或极小；债券基金正确分类 |
| **S7: 网络中断降级** | — | `test_scenario_resilience_flows.py` | 持仓缓存存在但网络断开 | 菜单 B | 价格从缓存读取（过期缓存降级）；报告完整不含空白页签 |
| **S8: 单账户单持仓** | — | `test_scenario_resilience_flows.py` | 仅一个账户一只持仓 | 菜单 E | 分类表仅一行、穿透 TOP10 仅该持仓、总计 = 该持仓市值 |
| **S9: 零成本持仓** | — | `test_scenario_resilience_flows.py` | 持仓成本=0（赠送/未记录买入价） | 菜单 B | 盈亏 = 市值 - 0、收益率不除零崩溃、显示合理占位 |
| **S10: 极端值** | — | `test_scenario_extreme.py` | 超大市值/极小份额/极多小数位 | 菜单 E | 正确定标至万元/亿元单位，不溢出、不崩溃（标记 `scenario_extreme`）|
| **S11: LLM 混合缓存+真实调用** | — | `test_llm_mixed_cache.py` | 4 模块（假设 news_correlation 关闭）：2 缓存 + 1 成功 + 1 失败 | 菜单 L × 2（部分缓存 TTL 内） | HTML 表各模块状态正确（蓝"缓存"、绿"成功"、红"失败"）；Excel 明细行颜色/费用/Thinking 正确；Summary 模块列表正确 |
| **S12: LLM 全部失败（5 种原因）** | — | `test_llm_module_info.py` | API Key 无效 / 网络断开 / 超时 / 熔断 / 配置缺失 | 菜单 L | 各模块分别显示 NOT_CONFIGURED / API_ERROR / NETWORK_ERROR / TIMEOUT / CIRCUIT_OPEN，颜色均为灰色/红色 |
| **S13: Extended Thinking 混合** | — | `test_llm_extended_thinking.py` | 2 模块启用 Thinking（global_macro + expert_review），2 模块未启用 | 菜单 L | Thinking 列 ✓ 仅出现在启用模块行，Excel/HTML/Summary 三种输出一致 |
| **S14: LLM 不启用** | — | `test_llm_disabled.py` | TUI 不按 L，直接生成报告 | 菜单 E / B 等（无 L） | 核心报告完整生成；无 LLM API 用量页签（Excel 无页签 19、HTML 无第 19 节）；LLM 分析章节整体不出现 |
| **S15: 禁用+缓存混合** | — | `test_llm_disabled_cache.py` | 1 模块 llm_settings 中 enable=false、1 模块缓存命中、1 模块成功 | 菜单 L | 禁用模块显示"已禁用"（灰色），禁用优先于缓存或 per_module 数据 |
| **S16: 断网下 LLM 降级** | — | `test_llm_network_error.py` | 网络断开 + 持仓缓存存在 | 菜单 L | 所有 LLM 模块降级为 NETWORK_ERROR 占位文本，不阻塞报告生成 |
| **S17: LLM 部分缓存超期** | — | `test_llm_partial_cache.py` | 2 模块缓存 TTL 内 + 2 模块缓存已过期 | 菜单 L | 过期模块重新调用 API（显示 Token 和费用），未过期模块显示缓存状态 |
| **S18: 全缓存无 API 调用** | — | `test_llm_empty_holdings.py` | 连续两次菜单 L（间隔 < TTL，全部模块命中缓存） | 菜单 L → 菜单 L | 第二次 LLM API 用量汇总"无新增 API 调用，数据全部来自缓存"，call_count=0 |
| **S19: 空持仓 LLM 降级** | — | `test_llm_empty_holdings.py` | 无持仓数据但按 L | 菜单 L（空目录） | LLM 调用跳过，输出空占位，报告不崩溃 |
| **S20: 三种输出格式一致性** | — | `test_llm_module_info.py` | 正常持仓 + 菜单 L | 菜单 L | Excel/HTML/Summary 三种输出对同一 module_info 的状态/颜色/费用一致 |
| **S21: 港股通** | — | `test_scenario_special_securities.py` | 持仓含港股通股票（00700.HK 腾讯控股） | 菜单 E | 港股通代码正确分类（hk_stock），无行情不崩溃 |
| **S22: 可转债** | — | `test_scenario_special_securities.py` | 持仓含可转债（如 127005 长证转债） | 菜单 E | 可转债正确分类（convertible_bond），名称含"转债"关键字识别 |
| **S23: REITs** | — | `test_scenario_special_securities.py` | 持仓含 REITs（如 508000 张江REIT） | 菜单 E | REITs 正确分类（reit），名称含"REIT"关键字，市值计算正常 |
| **S24: 货币基金** | — | `test_scenario_special_securities.py` | 持仓含场外货币基金/理财产品 | 菜单 E | 货币基金分类正确（money_market），净值恒为 1 |
| **S25: 科创板+北交所** | — | `test_scenario_special_securities.py` | 持仓含科创板（688xxx）和北交所（8xxxxx）股票 | 菜单 E | 代码前缀正确触发分类（star_market/bse），腾讯前缀补全 |
| **S26: 商品/黄金ETF** | — | `test_scenario_special_securities.py` | 持仓含黄金ETF/商品ETF | 菜单 E | 商品ETF 分类正确（commodity），溢价率计算正常 |
| **S27: 跨境ETF** | — | `test_scenario_special_securities.py` | 持仓含跨境 ETF（如 159941 纳指ETF） | 菜单 L | 分类为 QDII，净值日期 T-1，T-1 净值正确计算 |
| **S28: 纯债** | — | `test_scenario_special_securities.py` | 持仓含纯债/国债/企业债 | 菜单 E | 纯债分类正确（bond），名称含"债"关键字，市值计算正常 |
| **S29: 分红送转除权** | — | `test_scenario_operational_behavior.py` | 持仓含送转后份额翻倍/除权后收益率/纯送股零成本 | 菜单 E | 送转后份额翻倍、除权后收益率正确计算、纯送股profit_rate=None |
| **S30: 定投成本摊薄** | — | `test_scenario_operational_behavior.py` | 同一基金多批定投（批次按加权平均计算成本） | 菜单 E | 两批/三批不等额/定投亏损均加权平均正确；盈亏计算使用加权成本 |
| **S31: 部分调仓卖出** | — | `test_scenario_operational_behavior.py` | 持仓含卖出一半/90%/全部清仓 | 菜单 E | 卖出后剩余份额市值盈亏正确；全部清仓不崩溃 |
| **S32: 跨账户转仓** | — | `test_scenario_operational_behavior.py` | 同一代码出现在两个账户 | 菜单 E | 各账户独立计算明细、分类各自汇总、总计=账户和 |
| **S33: 新股中签待上市** | — | `test_scenario_operational_behavior.py` | 持仓含无行情新股尚未上市 | 菜单 E | 无行情降级 cost 正确显示、上市后正常计算、多只新股不干扰 |
| **S34: 组合历史走势基准指数对比** | — | 单元测试（见下方注） | 持仓含 A 股+基金，config.json 含 `benchmark_indices: {"sh000300": "沪深300"}` | 菜单 L | 组合走势 + 基准指数走势归一化正确；HTML 走势图显示组合曲线+基准虚线+图例；Excel portfolio_history_drawdown 页签含基准列；benchmark_indices 为空时走势正常不崩溃 |
| **D1: 辩论模式-正反辩论三段正常生成** | — | `test_debate_pipeline.py` | 含多品种持仓，Feature Flag `llm_debate_procon=true` | 菜单 L | pro（白脸）→ con（黑脸）→ synthesis（综合）三段完整生成；HTML 显示三色块+实验模式标签；Excel 显示"🧪 辩论模式"灰字注记；LLM 用量表正确归入"实验模式"行 |
| **D2: 辩论降级回退普通模式** | — | `test_debate_pipeline.py` | 正反辩论启用但 pro 或 con 返回 None | 菜单 L（模拟 LLM pro 失败） | 自动回退普通 expert_review；返回 8 元组（无 debate_info）；HTML 不显示辩论块，显示普通结果 |
| **D3: Token 预算触发生成截断** | — | `test_debate_token_budget.py` | 配置极低 `max_total_tokens_per_report`，持仓数据量大使 pro+con 超 1× 预算 | 菜单 L（模拟长篇输出） | 超过 1× 预算跳过 synthesis，返回 pro+con 拼接；超过 2× 跳过全部 debate 回退普通模式；日志输出 budget 告警 |

> LLM 相关的场景：S11/S13-S17 分布在 6 个子文件（`scenario/llm/test_llm_mixed_cache.py` / `test_llm_extended_thinking.py` / `test_llm_disabled.py` / `test_llm_disabled_cache.py` / `test_llm_network_error.py` / `test_llm_partial_cache.py`），S12（全部失败）与 S20（输出一致性）归入 `test_llm_module_info.py`，S18/S19 归入 `test_llm_empty_holdings.py`，幻觉率归入 `test_llm_hallucination.py`。
> S0a/S0b/S0d（持仓质量，不含 S0c）统一放在 `test_scenario_holdings_quality.py`；S0c（超多持仓）和 S10（极端值）放在 `test_scenario_extreme.py`。
> S21-S28（特殊品种）统一放在 `test_scenario_special_securities.py`。
> S29-S33（操作行为）统一放在 `test_scenario_operational_behavior.py`。
> S34（基准指数对比）覆盖在以下单元测试中（scenario 测试环境搭建成本较高，单元级验证已充分）：
> - `unit/report/test_benchmark.py` — normalize_benchmarks 算法 11 项 + 边缘 7 项
> - `unit/report/test_portfolio_history.py` — benchmark 集成调用 3 项（提供/空/异常）
> - `unit/fetcher/test_fetcher_index.py` — fetch_index_history 链路由/缓存/异常 3 项
> - `unit/fetcher/test_chain.py` — history_index 路由 5 项
> T 类场景统一放在 `test_datetime_scenarios.py` 并标注 `scenario_datetime`。
> 新增场景需要同时标注场景子标记（如 `scenario_basic`、`scenario_llm`）和通用 `scenario` 父标记，确保 `-m "scenario"` 能自动涵盖。
> D1-D3（辩论模式）统一放在 `test_debate_pipeline.py`（D1-D2）和 `test_debate_token_budget.py`（D3），归属集成测试组。

### 1.4 单元测试标记分组（Unit Test Markers）

单元测试按被测模块分组，通过 **父子双层 marker** 实现灵活筛选：

- **父标记 `unit`** 匹配全部 12 个已注册 `unit_*` 子标记（providers/fetcher/llm/news/report/config/core/cli/ui/analysis/scripts/web，其中 `unit_web` 为 Web 入口层），用于全量单元测试运行（`-m "unit"`）
- **子标记**如 `unit_providers`、`unit_fetcher`、`unit_llm` 等支持单独运行指定模块的测试（`-m "unit_providers"`）
- 新增单元测试文件时，必须为其测试类标注子标记和父标记，缺一不可

**跨类标记**（如 `llm`、`edge`、`smoke`、`data`、`cassette`、`live`）不依附于父子层级，可跨越单元/场景分类独立筛选。其中 `cassette` 声明用例所需的已录制真实响应（离线回放），`live` 为 opt-in 真实网络套件（默认跳过、不入门禁，仅 `--run-live` 或 `-m live` 运行）。

各标记的定义、覆盖规模和典型耗时见 [`test-coverage.md`](./test-coverage.md) → 单元测试分组 / 跨类标记。

### 1.5 集成测试

与 §1.3（端到端用户场景）的分工：**§1.5 聚焦模块间的接口契约和管道行为** — 组件 A 的输出是组件 B 的合法输入、错误在模块边界正确隔离、数据流跨模块一致。

> **与 §1.6 异常场景的关系：** §1.5 = 集成测试目标（"应该测什么"），§1.6 = 当前覆盖状态跟踪（"现在实测了什么"）。
> 重叠条目（如断网降级、Provider 回退）在 §1.5 标注目标状态，在 §1.6 标注实测状态，两者不矛盾。

| 集成维度 | 已验证 | 测试位置 |
|:---------|:------:|:---------|
| **数据流完整链路**：持仓 xlsx → 数据获取 → 缓存 → Excel/HTML 输出 | ✅ | `test_scenario_basic_flows.py` S1-S5 |
| **Provider 回退链路端到端**：腾讯不可用 → 东方财富 → 过期缓存 | ✅ | `test_chain.py` |
| **缓存与 API 协同**：缓存命中不调 API，缓存缺失调 API 并写入 | ✅ | `test_cache_core.py` / `test_cache_format.py` |
| **原子写入恢复**：磁盘满/断电后缓存和配置文件完整性 | ✅ | `test_config_atomic.py`（配置层）+ `core/test_atomic_write.py`（原语：新建/覆盖/父目录创建/临时文件不残留/失败返回 False 且不抛并保留原内容/Windows 占用回退 rename） |
| **模块间接口契约**：reader 输出 → market_value 输入 → penetration 输入 → ... 类型链正确 | ✅ | `test_module_contract.py` |
| **错误隔离**：penetration/LLM/news_correlation 任一模块失败，不阻塞其他模块写入 | ✅ | `test_excel_generator.py` `test_sheet_exception_others_still_called` |
| **LLM 输出→报告渲染**：Markdown → HTML/Jinja2 → 条件段落的渲染链路 | ✅ | `test_llm_module_info.py` / `test_llm_disabled.py` 等 |
| **新闻流水线集成**：fetch_all → aggregate → deduplicate → correlate_with_holdings → write_to_report | ✅ | `test_news_pipeline.py` |
| **多模块缓存一致性**：price 刷新后，market_value / fund_performance 使用同一缓存源 | ✅ | `test_cache_consistency.py` |
| **TUI → Handler 路由集成**：菜单按键 → handler dispatch → 正确模块被调用 | ✅ | `test_tui_routing.py` |
| **辩论管线集成**：orchestrator 辩论路由 _debate_wrapper → _debate_info_container → 8/9 元组返回 → HTML/Excel 渲染 | ✅ | `test_debate_pipeline.py` |
| **Provider 降级链路**：断网/超时/异常响应 → 回退/熔断/降级占位（真实联通性由运行时治理，非门禁） | ✅ | `test_scenario_resilience_flows.py`（S7）/ T15/T16 / provider edge |
| **联接基金穿透跨接缝**：取数层解析目标 ETF → fetcher 层以目标持仓代理 → 报告层登记来源并标注报告期 | ✅ | `test_fund.py` `TestWithFeederPenetration` + `test_penetration.py` / `test_penetration_sheet.py` |
| **缓存预检接缝**：批量取数缓存命中时任务不执行，穿透仍须生效（幂等后处理在两处接缝调用） | ✅ | `test_fund.py` `TestFetchFundHoldingsBatch.test_penetration_applied_on_cache_hit` |

### 1.6 异常场景全覆盖

> **与 §1.5 集成测试的关系：** §1.6 跟踪已有测试的覆盖状态（✅/🟡/🔴/❌），§1.5 列出集成测试目标。
> 同一异常场景（如断网降级）可能同时出现在两处：§1.5 标识为集成目标，§1.6 标识实测状态。

| 场景 | 预期行为 | 现有测试 |
|:-----|:---------|:--------:|
| 持仓目录不存在 | TUI 提示配置目录，不崩溃 | ✅ |
| 持仓目录为空 | TUI 提示配置目录，不崩溃 | ✅ |
| 持仓 xlsx 格式异常 | 提示具体错误行，跳过异常行 | ✅ |
| 网络断开 | 提示网络异常，使用缓存数据或显示"--" | ✅ |
| API 超时 | 自动切换备用链路；全部失败则跳过该数据 | ✅ |
| API 返回异常数据 | 跳过该条，日志记录 | ✅ |
| 缓存文件损坏 | 删除损坏缓存，重新获取 | ✅ |
| 报告输出目录无写入权限 | 提示文件写入失败 | ✅ |
| 股票代码前缀缺失 | 自动补全 | ✅ |
| 并发取价竞争 | 每种资产正确获取独立价格 | ✅ |
| LLM API 超时（120s 上限） | 降级返回 None，报告输出占位文本 | ✅ |
| LLM 缓存 HTML vs Markdown 共存 | 新缓存 HTML，老缓存自然过期 | ✅ |
| 空持仓下菜单 L | 跳过 LLM 调用，输出空占位 | ✅ |
| config.json 配置值异常 | 输出警告，使用代码默认值 | ✅ |
| JSON null 自动兜底 | 不崩溃，降级为空列表 | ✅ |
| market_hours UTC 时区 | `datetime.now(timezone(hours=8))` 一致 | ✅ `test_market_hours_edge.py`（UTC/JST/PST 时区） |
| config 原子写入断电 | `tempfile.mkstemp` + `os.replace` | ✅ `test_config_atomic_edge.py`（模拟断电/部分写入） |
| Provider 回退链路 | 主 provider 失败 → fallback provider | ✅ `test_chain_edge.py`（超时/429/503/全失败） |
| 熔断器冷却恢复 | 熔断后 60s 半开探测 | ✅ `test_circuit_breaker_edge.py`（60s 边界/59s 仍开/多端点） |
| 缓存 > 100KB gzip 压缩 | 自动 `.json.gz` 存储 + 透明解压 | ✅ `test_cache_edge.py`（gzip 边界 100KB/损坏删除） |
| LLM content_filter 空返回安抚重试 | 追加安抚指令重试一次 | ✅ `test_llm_api_edge.py`（恢复重试/仍空不回退） |
| **辩论虚构代码过滤** | 行级检测 LLM 输出的含字母虚构代码，移出该整行 | ✅ `test_debate_edge.py` `test_filter_removes_hallucinated` |
| **辩论 Provider 全不可用** | pro 失败返回 (None, None, None)，回退普通模式 | ✅ `test_debate_edge.py` `test_pro_failure_returns_none` |
| **辩论 synthesis 超时** | pro+con 成功但 synthesis 失败 → 返回 pro+con 拼接 | ✅ `test_debate_edge.py` `test_synthesis_timeout_returns_pro_con` |
| **辩论配置段缺失** | llm_settings.json 无 debate 段 → 使用全缺省配置 | ✅ `test_debate_edge.py` `test_missing_config_section` |
| **辩论 Token 预算 1× 超限** | pro+con 总和超过 1× 预算 → 跳过 synthesis | ✅ `test_debate_token_budget.py` `test_budget_exceeded_skips_synthesis` |
| **辩论 Token 预算 2× 超限** | pro 单独超过 2× 预算 → 跳过全部 debate | ✅ `test_debate_token_budget.py` `test_budget_2x_skips_all` |
| **相关性 NaN 虚假相关** | NaN 收益不得产生虚假 r=1.0/p=0.0 显著相关 | ✅ `test_correlation_edge.py` `TestNaNReturnRegression`（单 NaN 过滤贴近干净数据 / 全 NaN 序列剔除降级 / NaN 混入常数序列仍受守卫） |
| **相关性全 NaN 品种剔除** | 全 NaN 序列整条剔除，跌破 MIN_HOLDINGS → available=False | ✅ `test_correlation_edge.py` `test_all_nan_series_dropped` |
| **相关性日期缺口对齐** | 缺失中间日期/重复日期 → 仅用交集对齐不崩溃 | ✅ `test_correlation_edge.py` `TestDateHandling` |

### 1.7 日期/时间数据获取场景测试（T1-T21）

> **pytest marker**：`scenario_datetime`（含 `scenario` 父标记），`-m "scenario_datetime"` 可独立选择运行（项数见 [`test-coverage.md`](./test-coverage.md) → 场景测试分组）。

按市场状态、产品类型、时间边界三重维度组合，验证各数据源在不同时段的正确性和降级表现。其中 T1-T6 按市场状态划分（盘中/盘前/午休/盘后/非交易日/长假），T7-T11 按产品类型划分（场外基金/QDII/ETF/股票/混合），T12-T16 按边界条件划分（时段切换/缝隙/首次启动/断网），T17-T21 按数据异常/特殊日历划分（净值空窗/汇率故障/跨年/调休/港股通假期）。

**市场状态组合：**

| 场景 | 前置条件 | 操作 | 预期结果 |
|------|----------|------|----------|
| **T1: 交易日盘中**（09:30-11:30 / 13:00-15:00） | 网络正常、无缓存 | 菜单 E/B | 实时价格使用短 TTL（30s）；场外基金净值昨收；涨幅基于昨收计算；IOPV/溢价率实时更新 |
| **T2: 交易日盘前**（09:30 前） | 网络正常 | 菜单 E | 昨日收盘价可用，实时价不可用；最后交易日为上一交易日；场外基金净值日期为 T-1 |
| **T3: 交易日午间休市**（11:30-13:00） | 网络正常 | 菜单 E | 行情续用上午盘中高频缓存；基金净值不可用（发布在盘后）|
| **T4: 交易日盘后**（15:00 后） | 网络正常 | 菜单 E/B | 收盘价固化；场外基金净值渐次发布（15:00-20:00）；净值日期为 T；盘中缓存已清理 |
| **T5: 非交易日**（周末/节假日） | 网络正常 | 菜单 E | 使用最近交易日收盘价；净值日期停留在最近交易日；指数显示最近交易日数据 |
| **T6: 长假前后**（春节/国庆假期） | 假期前最后交易日生成报告 + 假期中再生成 | 菜单 E × 2 | 假期中所有价格降级为过期缓存；缓存 TTL 判断正常（非"过期"错误）；假期后首个交易日恢复正常 |

**产品类型差异化：**

| 场景 | 前置条件 | 操作 | 预期结果 |
|------|----------|------|----------|
| **T7: 国内场外基金** | 含多只国内场外基金 | 菜单 L | 净值日期标记 T 日（15:00 后）或 T-1（15:00 前）；本日盈亏仅当净值日期=T 时计算 |
| **T8: QDII 场外基金** | 含 QDII 基金（美股/港股方向） | 菜单 L | 净值日期通常 T-2（跨境延迟）；估值净值与官方净值差异字段标记正确；市值按数据源返回的净值（已为人民币计值）× 份额直接计算，不做汇率折算 |
| **T9: 场内 ETF/LOF** | 含 ETF/LOF 持仓 | 菜单 E | 盘中实时价更新；盘后收盘价固化；IOPV/溢价率计算；振幅/换手率字段正确 |
| **T10: 股票持仓** | 含 A 股股票 | 菜单 E | 实时价（盘中）/ 昨收（盘前盘后）；PE/PB/总市值等基本面字段盘后才更新 |
| **T11: 混合持仓** | 同时含场外+场内+股票 | 菜单 B | 各类型行情获取互不干扰；市值核算中价格来源标识正确；报告完整无遗漏 |

**边界与异常 Edge Case：**

| 场景 | 前置条件 | 操作 | 预期结果 |
|------|----------|------|----------|
| **T12: 盘中转盘后** | 盘中生成报告 B | 盘中生成后再盘后生成 | 盘中实时价 → 盘后收盘价；盘中缓存已过期 → 盘后新缓存写入 TTL 正确 |
| **T13: 交易时段切换缝隙** | 11:29:59 / 14:59:59 附近 | 时间条件模拟 | 午休/收盘切换前夕的缓存/数据行为正确，不出现竞态或错误缓存残留 |
| **T14: 第一次启动+非交易日** | 完全无缓存 + 非交易日 | 首次运行菜单 E | 全降级路径正确：指数→过期缓存→"--"；价格→昨收/净值→"--"；报告完整无崩溃 |
| **T15: 盘中断网** | 盘中网络断开 | 菜单 L | 价格从缓存读取（过期缓存降级）；LLM 全部失败降级；报告完整 |
| **T16: 盘后断网** | 盘后网络断开 + 有当日缓存 | 菜单 E | 收盘价从缓存读取（当日缓存未过期）；全流程正常 |

**数据异常与特殊日历（T17-T21）：**

| 场景 | 前置条件 | 操作 | 预期结果 |
|------|----------|------|----------|
| **T17: 跨月/跨年报告** | 12 月 31 日和 1 月 2 日分别生成 | `get_last_trading_day` 调用 | 跨年行情数据连续性正确，get_last_trading_day 返回正确日期 |
| **T18: 季末/年末效应** | 基金季末调仓日前后净值跳变 | 菜单 E | 大额净值变动时 today_profit 计算正确、profit_rate 无除零异常 |
| **T19: 场外品种净值日期非 T 日** | QDII/场外基金净值为 T-1 或 T-2（跨境延迟、非交易日运行等） | 菜单 L（含 QDII 持仓） | 本日盈亏为 0（仅净值日期 = 最近交易日才计当日盈亏）、市值照常核算、不崩溃 |
| **T20: 节假日调休** | 调休工作日（周日上班）vs 调休放假（周六休息） | _is_trading_day 判断 | 交易日历包含调休规则时 is_trading_day 正确识别工作日/休息日 |
| **T21: 港股通假期差异** | A 股开市但港股通因香港假期关闭 | 菜单 E（含港股通持仓） | QDII 净值延迟 T-1，price_type 正确标记，today_profit=0 |

> **pytest marker 对照：** §1.3 场景 → `scenario_basic`/`scenario_resilience`/`scenario_llm`；
> §1.7 场景 → `scenario_datetime`。全量场景用 `-m "scenario"`。
> 每场景的测试类参考见 [`test-coverage.md`](./test-coverage.md) → 场景测试分组表。


> edge 异常场景测试另有专项覆盖（`_edge.py` 文件），见 [`test-coverage.md`](./test-coverage.md) → 跨类标记。

### 1.8 边缘测试文件隔离规范（强制）

所有 `@pytest.mark.edge` 标记的测试**必须**遵守以下文件级约束：

| 规则 | 说明 |
|:-----|:------|
| **文件独立** | edge 测试必须放置在 `*_edge.py` 文件中，禁止与普通（non-edge）测试混搭在同一 `.py` 文件 |
| **标记唯一** | `*_edge.py` 文件中的所有测试类/方法**必须**标注 `@pytest.mark.edge`，但允许同时标注其他合法标记（如 `@pytest.mark.unit_report`） |
| **自动校验** | `conftest.py` 的 `pytest_collection_modifyitems` 在收集期自动检查：任何含有 `@pytest.mark.edge` 的测试项，其所属文件必须以 `_edge.py` 结尾；反之，`*_edge.py` 文件中的所有测试项必须有 `@pytest.mark.edge` 标记。违规项将报错停止 |

**例外：** 基类/混入类（Mixin）中定义的辅助方法不受此限，但调用这些方法的子类测试方法仍需遵守。

此规范在 `scripts/check-test-markers.py` 中另有 AST 级别的静态扫描补充验证。

---

## 2. 数据正确性验证

| 验证项 | 方法 | 现有测试 |
|:-------|:-----|:--------:|
| 市值 = 最新价 × 份额 | `test_holdings_detail_sheet.py`（市值/成本/盈亏列计算断言） | ✅ |
| 盈亏 = 市值 - 成本 | `test_holdings_detail_sheet.py`（盈亏列计算 + 着色断言） | ✅ |
| 分账户小计 = 该账户持仓合计数 | `test_category.py`（账户小计聚合一致性） | ✅ |
| 总计 = 各账户小计之和 | `test_category.py`（三维度聚合一致：账户小计之和 = 总计） | ✅ |
| 穿透 TOP10 合并逻辑 | 构造两个基金持相同股票 + 直接持有 | ✅ |
| 本日盈亏计算 | 给定时价、昨收、份额 | ✅ |
| 收益率 = 盈亏 / 成本（成本 > 0） | 验证边界值 cost=0 | ✅ |
| 溢价率 = (市价 - 净值) / 净值 | QDII ETF 验证，仅 QDII 基金显示 | ✅ `test_data_integrity.py` `_compute_premium()` |
| 本日盈亏 — 场外非 T 日更新 | 场外基金 nav_date ≠ T → today_profit = 0 | ✅ `test_data_integrity.py` `TestTodayProfitOffsiteNavDate` |
| 穿透市值占比归一化 | TOP10 占比总和 ≤ 100% | ✅ `test_data_integrity.py` `TestPenetrationTop10RatioNormalization` |
| **三维度分类聚合一致**：资产属性/投资分类/账户的小计各自 = 总计 | 三类分类各自独立聚合，交叉验证无遗漏/无重复 | ✅ `test_data_integrity.py` |
| **穿透行业占比归一化**：各行业占比之和 ≤ 100% | 穿透行业分布验证 | ✅ `test_data_integrity.py` |
| **指数行情数值合理**：上证≈3000、沪深300≈4000、恒指≈20000、标普≈5000 | 数量级确认，非精确值 | ✅ `test_data_integrity.py` |
| **非人民币计价品种市值核算**：按数据源价格 × 份额直接计市值（程序不做汇率折算） | 构造 QDII / 港股通持仓，验证市值与币种敞口分类 | ✅ `test_data_integrity.py` + `test_market_value.py` |
| **QDII 估值净值 vs 官方净值关系**：估值净值 ≥ 0，官方净值延迟 T-2 | 双列数值关系合理性断言 | ✅ `test_data_integrity.py` |
| **基金业绩排名数据合理性**：排名/收益率在 0-100% 范围内 | 天天基金排名数值验证 | ✅ `test_data_integrity.py` |

---

### 2.1 需求 ID ↔ 验证载体映射

`requirements.md` 的**每条需求 ID**（34 域 / 276 条）在测试侧均有确定载体，**全量已补全**。由 `scripts/check-requirement-trace.py --ci` 断言：映射表格式齐备 + ID 均存在于需求侧 + ID 唯一 + **全域全覆盖** + 载体文件真实存在。新增需求条目时须同步在表内补行（门禁会拦截漏映射）。

| 需求 ID | 验证载体（`测试文件::用例`，粗粒度时仅列文件） | 补全批次 |
|:--|:--|:--:|
<!-- requirement-trace:start -->
| R-CCH-01 | `src/test/unit/core/test_cache_core.py` + `src/test/unit/cache/test_cache_io.py` | 批 1 |
| R-CCH-02 | `src/test/unit/core/test_cache_format.py::test_small_file_not_gzipped` / `::test_large_file_auto_gzipped` / `::test_read_gzipped_file`；边界 `test_cache_edge.py::test_exact_100kb_boundary_not_gzip` | 批 1 |
| R-CCH-03 | `src/test/unit/core/test_cache_core.py::test_key_with_slash_replaced` / `::test_key_with_backslash_replaced` / `::test_key_with_dotdot_replaced` | 批 1 |
| R-CCH-04 | `src/test/unit/core/test_atomic_write.py` + `src/test/unit/cache/test_cache_io.py::test_write_atomic_json` / `::test_write_atomic_gzip` | 批 1 |
| R-CCH-05 | `src/test/unit/core/test_cache_core.py::test_corrupted_json_deletes_file` / `::test_corrupted_json_io_error_returns_none`；`test_cache_edge.py::test_gz_corrupted_file_deleted_on_read`；`test_cache_cleanup.py::test_corrupted_file_deleted_in_cleanup` | 批 1 |
| R-CCH-06 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/core/test_provider_registry.py` | 批 1 |
| R-CCH-07 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/core/test_data_freshness.py` | 批 1 |
| R-CCH-08 | `src/test/unit/news/test_news_aggregator.py` + `src/test/integration/test_news_pipeline.py` | 批 1 |
| R-CCH-09 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/providers/test_eastmoney_industry.py` | 批 1 |
| R-CCH-10 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/providers/test_tiantian.py` | 批 1 |
| R-CCH-11 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/providers/test_eastmoney.py` | 批 1 |
| R-CCH-12 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/providers/test_tiantian_holdings_edge.py` | 批 1 |
| R-CCH-13 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/providers/test_eastmoney_industry.py` | 批 1 |
| R-CCH-14 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/handlers/test_handlers_cache.py::test_with_valid_codes` | 批 1 |
| R-CCH-15 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/core/test_data_freshness.py` | 批 1 |
| R-CCH-16 | `src/test/unit/llm/test_llm_api.py`（缓存命中/未命中）+ `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` | 批 1 |
| R-CCH-17 | 同 R-CCH-16（LLM 新闻关联分析走同一缓存层） | 批 1 |
| R-CCH-18 | 同 R-CCH-16（LLM 全球政经局势走同一缓存层） | 批 1 |
| R-CCH-19 | 同 R-CCH-16（LLM 持仓体检走同一缓存层） | 批 1 |
| R-CCH-20 | 同 R-CCH-16（LLM 穿透深度分析走同一缓存层） | 批 1 |
| R-CCH-21 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/providers/test_tiantian.py` | 批 1 |
| R-CCH-22 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/providers/test_akshare_extras.py` | 批 1 |
| R-CCH-23 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/providers/test_akshare_extras.py` | 批 1 |
| R-CCH-24 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/providers/test_tiantian.py` | 批 1 |
| R-CCH-25 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/providers/test_akshare_extras.py` | 批 1 |
| R-CCH-26 | `src/test/unit/cache/test_holdings_tracker.py` + `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` | 批 1 |
| R-CCH-27 | `src/test/unit/core/test_market_hours.py` + `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` | 批 1 |
| R-CCH-28 | `src/test/unit/llm/test_debate_generators.py`（pro 阶段生成流程） | 批 1 |
| R-CCH-29 | `src/test/unit/llm/test_debate_generators.py`（con 阶段生成流程） | 批 1 |
| R-CCH-30 | `src/test/unit/llm/test_debate_generators.py`（synthesis 阶段生成流程） | 批 1 |
| R-CCH-31 | `src/test/unit/core/test_registry.py::test_cache_groups_known_values` / `::test_cache_prefix_modules_have_groups` + `src/test/unit/core/test_cache_cleanup.py::test_prefix_grouping` | 批 1 |
| R-CCH-32 | `src/test/unit/core/test_registry.py::test_cache_groups_known_values` / `::test_cache_prefix_modules_have_groups` + `src/test/unit/core/test_cache_cleanup.py::test_multiple_prefixes_use_different_ttl` | 批 1 |
| R-CCH-33 | `src/test/unit/core/test_registry.py::test_cache_groups_known_values` / `::test_cache_prefix_modules_have_groups` + `src/test/unit/core/test_cache_cleanup.py::test_unknown_prefix_uses_default_ttl` | 批 1 |
| R-CCH-34 | `src/test/unit/llm/test_fingerprint.py` + `src/test/unit/cache/test_holdings_tracker.py::test_same_holdings_same_fingerprint` / `::test_different_code_different_fingerprint` | 批 1 |
| R-CCH-35 | `src/test/unit/core/test_cache_edge.py::test_market_open_uses_short_ttl` / `::test_market_closed_uses_static_ttl` / `::test_market_open_clamps_min_30`（交易时段感知短 TTL + 指数指纹缓存键） | 批 1 |
| R-CCH-36 | `src/test/unit/handlers/test_handlers_cache.py::test_with_valid_codes` + `src/test/unit/core/test_cache_cleanup.py`（分红前缀清理） | 批 1 |
| R-CCH-37 | `src/test/unit/news/test_news_aggregator.py::test_cache_hit` / `::test_cache_miss` / `::test_default_sources`（缓存键含源+关键词摘要） | 批 1 |
| R-CCH-38 | `src/test/unit/cache/test_holdings_tracker.py::test_different_shares_different_fingerprint` / `::test_different_cost_different_fingerprint` / `::test_different_account_different_fingerprint` / `::test_fingerprint_mismatch_new_codes` | 批 1 |
| R-ERR-01 | `src/test/unit/fetcher/test_chain.py` + `src/test/scenario/resilience/test_scenario_resilience_flows.py` | 批 2 |
| R-ERR-02 | `src/test/unit/core/test_cache_core.py::test_corrupted_json_deletes_file`（同 R-CCH-05） | 批 2 |
| R-ERR-03 | `src/test/unit/config/test_config.py` + `src/test/unit/core/test_data_freshness.py` | 批 2 |
| R-ERR-04 | `src/test/unit/fetcher/test_batch.py` | 批 2 |
| R-ERR-05 | `src/test/unit/report/test_data_status.py` | 批 2 |
| R-ERR-06 | `src/test/unit/config/test_local_state.py` | 批 2 |
| R-ERR-07 | `src/test/scenario/llm/test_llm_disabled.py` + `src/test/unit/report/test_llm_module_info.py` | 批 2 |
| R-ERR-08 | `src/test/scenario/llm/test_llm_disabled.py` + `src/test/unit/report/test_section_visibility.py` | 批 2 |
| R-ERR-09 | `src/test/unit/llm/test_llm_placeholder.py` + `src/test/unit/llm/test_llm_placeholder_distinction_edge.py` | 批 2 |
| R-ERR-10 | `src/test/unit/report/test_html_fund_deep_renderers.py` + `src/test/unit/report/test_excel_fund_deep_analysis.py` | 批 2 |
| R-ERR-11 | `src/test/unit/report/test_news_degradation_edge.py` | 批 2 |
| R-ERR-12 | `src/test/unit/report/test_portfolio_history.py` | 批 2 |
| R-ERR-13 | `src/test/unit/report/test_portfolio_history.py` | 批 2 |
| R-ERR-14 | `src/test/unit/report/test_portfolio_history.py` + `src/test/unit/config/test_config.py` | 批 2 |
| R-ERR-15 | `src/test/unit/analysis/test_snapshot_diff_edge.py` | 批 2 |
| R-ERR-16 | `src/test/unit/analysis/test_snapshot_diff_edge.py` | 批 2 |
| R-DIAG-01 | `src/test/unit/cli/test_cli.py` + `src/test/unit/core/test_log_reader.py` | 批 2 |
| R-DIAG-02 | `src/test/unit/ui/test_handlers_log.py` + `src/test/unit/ui/test_tui_menu.py` | 批 2 |
| R-DIAG-03 | `src/test/unit/web/test_handlers.py` + `src/test/unit/web/test_health_credential.py` | 批 2 |
| R-DIAG-04 | `src/test/unit/cli/test_cli.py` + `src/test/unit/core/test_doctor.py` | 批 2 |
| R-DIAG-05 | `src/test/unit/ui/test_tui_menu.py` + `src/test/unit/config/test_features.py` | 批 2 |
| R-DIAG-06 | `src/test/unit/web/test_handlers.py` + `src/test/unit/core/test_doctor.py` | 批 2 |
| R-DIAG-07 | `src/test/unit/core/test_doctor.py` + `src/test/unit/config/test_features.py` | 批 2 |
| R-BRK-01 | `src/test/unit/core/test_provider_registry.py` | 批 2 |
| R-BRK-02 | `src/test/unit/core/test_provider_registry.py` + `src/test/unit/fetcher/test_fetcher_industry.py` | 批 2 |
| R-BRK-03 | `src/test/unit/core/test_provider_registry.py` | 批 2 |
| R-BRK-04 | `src/test/unit/llm/test_circuit_breaker_recovery.py` + `src/test/unit/llm/test_circuit_breaker_edge.py` | 批 2 |
| R-BRK-05 | `src/test/unit/core/test_provider_registry.py` | 批 2 |
| R-BRK-06 | `src/test/unit/core/test_circuit_breaker_gateway.py` + `src/test/unit/llm/test_circuit_breaker_recovery.py` | 批 2 |
| R-BRK-07 | `src/test/unit/core/test_circuit_breaker_gateway.py` + `src/test/unit/config/test_local_state.py` | 批 2 |
| R-BRK-08 | `src/test/unit/core/test_circuit_breaker_gateway.py`（网关统一双熔断器）+ `src/test/unit/core/test_provider_registry.py` | 批 2 |
| R-CRD-01 | `src/test/unit/core/test_datasource_credential.py` | 批 2 |
| R-CRD-02 | `src/test/unit/core/test_datasource_credential.py` + `src/test/unit/core/test_datasource_credential_edge.py` | 批 2 |
| R-CRD-03 | `src/test/unit/core/test_datasource_credential.py` | 批 2 |
| R-CRD-04 | `src/test/unit/fetcher/test_credential_gate.py` | 批 2 |
| R-CRD-05 | `src/test/unit/core/test_check_sources_credential.py` | 批 2 |
| R-CRD-06 | `src/test/unit/core/test_doctor_credential.py` | 批 2 |
| R-CRD-07 | `src/test/unit/core/test_datasource_credential.py` + `src/test/unit/llm/test_log_sanitize.py` | 批 2 |
| R-CRD-08 | `src/test/unit/config/test_features.py` + `src/test/unit/core/test_datasource_credential.py` | 批 2 |
| R-FIN-01 | `src/test/unit/report/test_financial_indicator.py` + `src/test/unit/fetcher/test_financial_indicator.py` | 批 3 |
| R-FIN-02 | `src/test/unit/providers/test_akshare_financial.py` | 批 3 |
| R-FIN-03 | `src/test/unit/fetcher/test_financial_indicator.py` + `src/test/unit/fetcher/test_chain.py` | 批 3 |
| R-FIN-04 | `src/test/unit/core/test_code_utils.py` | 批 3 |
| R-FIN-13 | `src/test/unit/report/test_financial_indicator.py` | 批 3 |
| R-FIN-05 | `src/test/unit/analysis/test_financial_indicator_edge.py` + `src/test/unit/fetcher/test_financial_indicator.py` | 批 3 |
| R-FIN-15 | `src/test/unit/analysis/test_financial_indicator.py` | 批 3 |
| R-FIN-14 | `src/test/unit/analysis/test_financial_statement_derive.py` | 批 3 |
| R-FIN-06 | `src/test/unit/fetcher/test_financial_indicator.py` + `src/test/unit/providers/test_datasink.py` | 批 3 |
| R-FIN-07 | `src/test/unit/analysis/test_financial_indicator_extract.py` + `src/test/unit/analysis/test_financial_indicator_extract_edge.py` | 批 3 |
| R-FIN-09 | `src/test/unit/report/test_financial_indicator.py` + `src/test/unit/report/test_html_report_structure.py` | 批 3 |
| R-FIN-10 | `src/test/unit/report/test_financial_indicator.py` | 批 3 |
| R-FIN-11 | `src/test/unit/fetcher/test_financial_indicator.py` | 批 3 |
| R-FIN-12 | `src/test/integration/test_module_contract.py` + `src/test/unit/report/test_pipeline_data_builder.py` | 批 3 |
| R-FIN-08 | `src/test/unit/fetcher/test_financial_report.py` + `src/test/unit/analysis/test_financial_indicator_extract.py` | 批 3 |
| R-FRD-01 | `src/test/unit/report/test_financial_report_digest.py` | 批 3 |
| R-FRD-02 | `src/test/unit/core/test_datasource_credential.py` + `src/test/unit/providers/test_datasink.py` | 批 3 |
| R-FRD-03 | `src/test/unit/fetcher/test_financial_report.py` | 批 3 |
| R-FRD-04 | `src/test/unit/providers/test_datasink.py` | 批 3 |
| R-FRD-05 | `src/test/unit/report/test_financial_report_digest.py` + `src/test/unit/fetcher/test_report_backup_source.py` | 批 3 |
| R-FRD-06 | `src/test/unit/fetcher/test_financial_report.py` | 批 3 |
| R-FRD-07 | `src/test/unit/core/test_registry.py::test_cache_ttl_defaults_known_values` + `src/test/unit/fetcher/test_report_backup_source.py` | 批 3 |
| R-NWS-01 | `src/test/unit/news/test_news_aggregator.py` | 批 3 |
| R-NWS-02 | `src/test/unit/news/test_news_correlator.py` | 批 3 |
| R-NWS-03 | `src/test/unit/news/test_news_keywords.py` | 批 3 |
| R-NWS-04 | `src/test/unit/report/test_news_correlation.py` | 批 3 |
| R-NWS-05 | `src/test/unit/news/test_news_sources.py` | 批 3 |
| R-NWS-06 | `src/test/unit/news/test_news_correlator.py` + `src/test/unit/report/test_news_correlation.py` | 批 3 |
| R-DATA-01 | `src/test/unit/fetcher/test_chain.py` + `src/test/scenario/resilience/test_scenario_resilience_flows.py` | 批 3 |
| R-DATA-02 | `src/test/unit/fetcher/test_batch.py` | 批 3 |
| R-DATA-03 | `src/test/unit/core/test_provider_registry.py` | 批 3 |
| R-DATA-04 | `src/test/unit/core/test_cache_edge.py::test_market_open_uses_short_ttl` / `::test_market_closed_uses_static_ttl` | 批 3 |
| R-DATA-05 | `src/test/unit/core/test_data_freshness.py` | 批 3 |
| R-DATA-06 | `src/test/unit/core/test_code_utils_classification.py` + `src/test/unit/fetcher/test_fund.py` | 批 3 |
| R-DATA-07 | `src/test/unit/core/test_retry.py` + `src/test/unit/core/test_throttle.py` + `src/test/unit/providers/test_cninfo.py` + `src/test/unit/llm/test_llm_api_base.py` | 批 4 |
| R-IDX-01 | `src/test/unit/fetcher/test_fetcher_index.py` + `src/test/unit/providers/test_tencent.py` | 批 3 |
| R-IDX-02 | `src/test/unit/fetcher/test_fetcher_index.py` + `src/test/unit/providers/test_sina.py` | 批 3 |
| R-IDX-03 | `src/test/unit/fetcher/test_fetcher_index.py` + `src/test/unit/fetcher/test_chain.py` | 批 3 |
| R-OUT-01 | `src/test/unit/report/test_orchestrator.py` | 批 4 |
| R-OUT-02 | `src/test/unit/report/test_excel_writer.py` | 批 4 |
| R-OUT-03 | `src/test/unit/report/test_excel_generator.py` | 批 4 |
| R-OUT-04 | `src/test/unit/report/test_html_writer.py` | 批 4 |
| R-OUT-05 | `src/test/unit/report/test_excel_report_structure.py` | 批 4 |
| R-OUT-06 | `src/test/unit/report/test_html_report_structure.py` | 批 4 |
| R-OUT-07 | `src/test/unit/report/test_orchestrator.py` + `src/test/unit/config/test_config.py` | 批 4 |
| R-OUT-08 | `src/test/unit/report/test_excel_report_structure.py` | 批 4 |
| R-OUT-09 | `src/test/unit/report/test_section_visibility.py` | 批 4 |
| R-OUT-10 | `src/test/unit/report/test_html_report_structure.py` + `src/test/unit/report/test_feature_interactive.py` | 批 4 |
| R-OUT-11 | `src/test/unit/report/test_theme_js.py` + `src/test/unit/report/test_feature_interactive.py` | 批 4 |
| R-PERF-01 | `src/test/unit/news/test_news_aggregator.py` | 批 4 |
| R-PERF-02 | `src/test/unit/llm/test_generate_all_llm.py` | 批 4 |
| R-PERF-03 | `src/test/unit/fetcher/test_batch.py` | 批 4 |
| R-PERF-04 | `src/test/unit/config/test_config.py` | 批 4 |
| R-PERF-05 | `src/test/unit/llm/test_llm_prompt_builders.py` | 批 4 |
| R-PERF-06 | `src/test/unit/core/test_provider_registry.py` | 批 4 |
| R-PERF-07 | `src/test/unit/fetcher/test_fetcher_index.py` + `src/test/unit/report/test_portfolio_history.py` | 批 4 |
| R-PERF-08 | `src/test/unit/core/test_phase_timeout.py` | 批 4 |
| R-PERF-09 | `src/test/unit/report/test_progress.py` + `src/test/unit/config/test_local_state.py` | 批 4 |
| R-PERF-10 | `src/test/unit/core/test_check_sources.py` + `src/test/unit/config/test_local_state.py` | 批 4 |
| R-WIF-01 | `src/test/unit/cli/test_cli.py` + `src/test/integration/test_cli_integration.py` | 批 4 |
| R-WIF-02 | `src/test/unit/analysis/test_whatif.py` | 批 4 |
| R-WIF-03 | `src/test/unit/analysis/test_whatif.py` | 批 4 |
| R-WIF-04 | `src/test/unit/analysis/test_whatif.py` | 批 4 |
| R-WIF-05 | `src/test/unit/report/test_whatif_writer.py` + `src/test/unit/report/test_whatif_sheet.py` + `src/test/unit/report/test_whatif_html.py` | 批 4 |
| R-WIF-06 | `src/test/unit/analysis/test_whatif.py` + `src/test/unit/report/test_whatif_operations.py` | 批 4 |
| R-WIF-07 | `src/test/unit/report/test_whatif_sheet.py` + `src/test/unit/cli/test_cli_edge.py` | 批 4 |
| R-WIF-08 | `src/test/unit/handlers/test_handlers_whatif.py` | 批 4 |
| R-WIF-09 | `src/test/unit/analysis/test_whatif_backtest.py` | 批 4 |
| R-WIF-10 | `src/test/unit/analysis/test_whatif_backtest.py` | 批 4 |
| R-WIF-11 | `src/test/unit/analysis/test_whatif_backtest_edge.py` + `src/test/unit/report/test_whatif_sheet.py` | 批 4 |
| R-ACT-01 | `src/test/unit/report/test_action_sheet.py` + `src/test/unit/config/test_features.py` | 批 4 |
| R-ACT-02 | `src/test/unit/report/test_action_sheet.py` + `src/test/integration/test_module_contract.py` | 批 4 |
| R-ACT-03 | `src/test/unit/analysis/test_rebalance.py` | 批 4 |
| R-ACT-04 | `src/test/unit/report/test_action_sheet.py` + `src/test/unit/analysis/test_return_attribution.py` | 批 4 |
| R-ACT-05 | `src/test/unit/report/test_action_html.py` + `src/test/unit/report/test_section_visibility.py` | 批 4 |
| R-RBL-01 | `src/test/unit/analysis/test_rebalance.py` | 批 4 |
| R-RBL-02 | `src/test/unit/analysis/test_rebalance.py` | 批 4 |
| R-RBL-03 | `src/test/unit/analysis/test_rebalance.py` + `src/test/unit/config/test_config.py` | 批 4 |
| R-RBL-04 | `src/test/unit/analysis/test_rebalance.py` | 批 4 |
| R-RBL-05 | `src/test/unit/analysis/test_rebalance_edge.py` + `src/test/unit/config/test_local_state.py` | 批 4 |
| R-RBL-06 | `src/test/unit/analysis/test_rebalance.py` | 批 4 |
| R-RBL-07 | `src/test/unit/analysis/test_rebalance.py` + `src/test/unit/analysis/test_rebalance_edge.py` | 批 4 |
| R-RBL-08 | `src/test/unit/analysis/test_rebalance_advisor.py` | 批 4 |
| R-VAL-01 | `src/test/unit/analysis/test_valuation_percentile.py` | 批 4 |
| R-VAL-02 | `src/test/unit/analysis/test_valuation_percentile.py` | 批 4 |
| R-VAL-04 | `src/test/unit/analysis/test_valuation_percentile.py` + `src/test/unit/report/test_valuation_temperature_wiring.py` | 批 4 |
| R-VAL-03 | `src/test/unit/analysis/test_valuation_percentile.py` + `src/test/unit/analysis/test_valuation_percentile_edge.py` | 批 4 |
| R-TAIL-01 | `src/test/unit/analysis/test_tail_risk.py` | 批 4 |
| R-TAIL-02 | `src/test/unit/analysis/test_tail_risk.py` | 批 4 |
| R-TAIL-03 | `src/test/unit/analysis/test_tail_risk_edge.py` | 批 4 |
| R-TAIL-04 | `src/test/unit/report/test_tail_risk_wiring.py` | 批 4 |
| R-EVO-01 | `src/test/unit/analysis/test_portfolio_evolution.py` | 批 4 |
| R-EVO-02 | `src/test/unit/analysis/test_portfolio_evolution.py` | 批 4 |
| R-EVO-03 | `src/test/unit/report/test_evolution_sheet.py` + `src/test/unit/report/test_evolution_html.py` | 批 4 |
| R-EVO-04 | `src/test/unit/config/test_features.py` + `src/test/unit/report/test_section_visibility.py` | 批 4 |
| R-SNP-01 | `src/test/unit/report/test_history_snapshot_namespace.py` | 批 4 |
| R-SNP-02 | `src/test/unit/handlers/test_handlers_cache.py` + `src/test/unit/report/test_history_snapshot_namespace.py` | 批 4 |
| R-SNP-03 | `src/test/unit/report/test_history_snapshot_namespace.py` | 批 4 |
| R-SNP-04 | `src/test/unit/report/test_history_snapshot_namespace.py` | 批 4 |
| R-SNP-05 | `src/test/unit/analysis/test_snapshot_diff.py` | 批 4 |
| R-SNP-06 | `src/test/unit/analysis/test_snapshot_diff_edge.py` | 批 4 |
| R-CFL-01 | `src/test/unit/analysis/test_cost_flow.py` | 批 4 |
| R-CFL-02 | `src/test/unit/analysis/test_cost_flow.py` | 批 4 |
| R-CFL-03 | `src/test/unit/analysis/test_cost_flow.py` + `src/test/unit/config/test_features.py` | 批 4 |
| R-CFL-04 | `src/test/unit/report/test_category.py` + `src/test/unit/analysis/test_cost_flow.py` | 批 4 |
| R-DIFF-01 | `src/test/unit/analysis/test_snapshot_diff.py` | 批 4 |
| R-DIFF-02 | `src/test/unit/analysis/test_snapshot_diff.py` | 批 4 |
| R-DIFF-03 | `src/test/unit/analysis/test_snapshot_diff_edge.py` | 批 4 |
| R-DIFF-04 | `src/test/unit/report/test_evolution_sheet.py` + `src/test/unit/report/test_evolution_html.py` | 批 4 |
| R-LLM-01 | `src/test/unit/ui/test_tui_menu.py` | 批 5 |
| R-LLM-02 | `src/test/unit/config/test_features.py` + `src/test/unit/llm/test_generate_all_llm.py` | 批 5 |
| R-LLM-03 | `src/test/unit/llm/test_llm_api_multi.py` + `src/test/unit/llm/test_llm_utils.py` | 批 5 |
| R-LLM-04 | `src/test/unit/llm/test_llm_fallback.py` | 批 5 |
| R-LLM-05 | `src/test/unit/report/test_llm_module_info.py` + `src/test/unit/llm/test_cost_tracker.py` | 批 5 |
| R-LLM-06 | `src/test/unit/llm/test_llm_chain_strategies.py` + `src/test/unit/llm/test_strategy.py` | 批 5 |
| R-LLM-07 | `src/test/unit/config/test_llm_settings.py` + `src/test/unit/config/test_config_llm_multi.py` | 批 5 |
| R-LLM-09 | `src/test/unit/llm/test_prompts_signals.py` | 批 5 |
| R-LLM-10 | `src/test/unit/llm/test_llm_pacing.py`（策略解析/容错/注册/零开销直通/间隔/抖动/并发上限/异常释放/403 不重试）+ `src/test/unit/config/test_config_llm_multi.py`（pacing 透传/缺省不注入/非对象忽略） | 批 5 |
| R-LLM-08 | `src/test/unit/llm/test_llm_api.py` + `src/test/unit/report/test_llm_module_info.py` | 批 5 |
| R-PF-01 | `src/test/unit/config/test_features.py` + `src/test/unit/report/test_section_visibility.py` | 批 5 |
| R-PF-02 | `src/test/unit/analysis/test_prosperity_framework.py` | 批 5 |
| R-PF-03 | `src/test/unit/analysis/test_prosperity_framework.py` | 批 5 |
| R-PF-09 | `src/test/unit/report/test_fund_roe_estimate.py` + `src/test/unit/analysis/test_prosperity_framework.py` | 批 5 |
| R-PF-04 | `src/test/unit/analysis/test_prosperity_framework.py` + `src/test/unit/analysis/test_prosperity_framework_edge.py` | 批 5 |
| R-PF-05 | `src/test/unit/analysis/test_prosperity_framework.py` | 批 5 |
| R-PF-06 | `src/test/unit/report/test_prosperity_framework_wiring.py` | 批 5 |
| R-PF-07 | `src/test/unit/analysis/test_prosperity_framework.py` | 批 5 |
| R-PF-08 | `src/test/unit/config/test_config.py` + `src/test/scenario/basic/test_scenario_prosperity_framework.py` | 批 5 |
| R-CTX-01 | `src/test/unit/config/test_config.py` + `src/test/unit/report/test_benchmark.py` | 批 5 |
| R-CTX-02 | `src/test/unit/report/test_benchmark.py` | 批 5 |
| R-CTX-03 | `src/test/unit/report/test_benchmark.py` | 批 5 |
| R-CTX-04 | `src/test/unit/report/test_benchmark.py` | 批 5 |
| R-CTX-05 | `src/test/unit/llm/test_llm_prompt_builders.py` + `src/test/unit/report/test_benchmark_edge.py` | 批 5 |
| R-CTX-06 | `src/test/unit/llm/test_prompts_core.py` | 批 5 |
| R-CTX-07 | `src/test/unit/ui/test_tui_handlers.py` + `src/test/unit/handlers/test_handlers_config.py` | 批 5 |
| R-WEB-01 | `src/test/unit/web/test_server.py` | 批 6 |
| R-WEB-02 | `src/test/unit/web/test_upload.py` + `src/test/unit/web/test_upload_edge.py` | 批 6 |
| R-WEB-03 | `src/test/unit/web/test_handlers.py` | 批 6 |
| R-WEB-04 | `src/test/unit/web/test_progress.py` | 批 6 |
| R-WEB-05 | `src/test/unit/web/test_handlers.py` + `src/test/unit/web/test_web_static_serving.py` | 批 6 |
| R-WEB-06 | `src/test/unit/web/test_runs.py` | 批 6 |
| R-WEB-07 | `src/test/unit/web/test_upload.py` + `src/test/unit/web/test_runs.py` | 批 6 |
| R-WEB-08 | `src/test/unit/web/test_config_edit.py` + `src/test/unit/web/test_config_edit_edge.py` | 批 6 |
| R-WEB-09 | `src/test/unit/web/test_holdings_update.py` + `src/test/unit/web/test_holdings_update_edge.py` | 批 6 |
| R-TUI-01 | `src/test/unit/ui/test_tui_menu.py` | 批 6 |
| R-TUI-02 | `src/test/unit/ui/test_tui_menu.py` + `src/test/unit/ui/test_tui_keys.py` | 批 6 |
| R-TUI-06 | `src/test/unit/ui/test_tui_menu.py` + `src/test/unit/config/test_config.py` | 批 6 |
| R-TUI-03 | `src/test/unit/ui/test_tui_handlers.py` | 批 6 |
| R-TUI-04 | `src/test/unit/ui/test_tui_handlers.py` + `src/test/unit/ui/test_tui_edge.py` | 批 6 |
| R-TUI-05 | `src/test/unit/report/test_progress.py` | 批 6 |
| R-ENV-01 | `src/test/unit/cli/test_cli.py`（CLI 入口）+ 手工验收（testplan §4 环境项） | 批 6 |
| R-ENV-02 | `src/test/unit/scripts/test_script_encoding.py`（脚本编码）+ 手工验收（testplan §4 启动脚本项） | 批 6 |
| R-ENV-03 | `src/test/unit/scripts/test_script_encoding.py` + 手工验收（testplan §4 启动脚本项） | 批 6 |
| R-ENV-04 | `src/test/unit/web/test_smoke_web.py` + 手工验收（testplan §4 Web 启动项） | 批 6 |
| R-ENV-05 | `src/test/unit/scripts/test_script_encoding.py` + `src/test/unit/cli/test_cli.py` | 批 6 |
| R-HLD-01 | `src/test/unit/core/test_reader.py` | 批 6 |
| R-HLD-02 | `src/test/unit/core/test_reader.py` + `src/test/unit/core/test_models.py` | 批 6 |
| R-HLD-03 | `src/test/unit/core/test_reader.py` | 批 6 |
| R-HLD-04 | `src/test/unit/core/test_reader.py` | 批 6 |
| R-HLD-05 | `src/test/unit/core/test_code_utils.py` | 批 6 |
| R-DIS-01 | `src/test/unit/analysis/test_trade_discipline.py` | 批 6 |
| R-DIS-02 | `src/test/unit/analysis/test_trade_discipline.py` | 批 6 |
| R-DIS-03 | `src/test/unit/analysis/test_trade_discipline.py` | 批 6 |
| R-DIS-04 | `src/test/unit/analysis/test_trade_discipline.py` | 批 6 |
| R-DIS-05 | `src/test/unit/analysis/test_trade_discipline.py` + `src/test/unit/config/test_config.py` | 批 6 |
| R-LIQ-01 | `src/test/unit/analysis/test_liquidity.py` | 批 6 |
| R-LIQ-02 | `src/test/unit/analysis/test_liquidity_otc.py` | 批 6 |
| R-LIQ-03 | `src/test/unit/analysis/test_liquidity_otc.py` + `src/test/unit/core/test_code_utils.py` | 批 6 |
| R-LIQ-04 | `src/test/unit/analysis/test_liquidity.py` | 批 6 |
| R-LIQ-05 | `src/test/unit/llm/test_llm_prompt_builders.py` | 批 6 |
| R-LIQ-06 | `src/test/unit/analysis/test_liquidity.py` | 批 6 |
| R-LIQ-07 | `src/test/unit/analysis/test_liquidity_otc.py` | 批 6 |
| R-LIQ-08 | `src/test/unit/analysis/test_liquidity.py` + `src/test/unit/analysis/test_liquidity_edge.py` | 批 6 |
| R-FX-01 | `src/test/unit/analysis/test_fx_exposure.py` | 批 6 |
| R-FX-02 | `src/test/unit/analysis/test_fx_exposure.py` | 批 6 |
| R-FX-03 | `src/test/unit/analysis/test_fx_exposure.py` | 批 6 |
| R-FX-04 | `src/test/unit/analysis/test_fx_exposure.py` | 批 6 |
| R-FX-05 | `src/test/unit/llm/test_llm_prompt_builders.py` | 批 6 |
| R-CON-01 | `src/test/scenario/llm/test_llm_disabled.py` | 批 6 |
| R-CON-02 | `src/test/unit/config/test_config_edge.py` | 批 6 |
| R-CON-03 | `src/test/unit/core/test_reader.py` | 批 6 |
| R-CON-04 | `src/test/unit/core/test_filesystem_edge.py` | 批 6 |
| R-CON-05 | `src/test/scenario/basic/test_scenario_basic_flows.py` | 批 6 |
| R-CON-06 | `src/test/integration/test_error_isolation.py` | 批 6 |
| R-CON-07 | `src/test/unit/fetcher/test_chain.py` + `src/test/scenario/resilience/test_chain_resilience.py` | 批 6 |
| R-CON-08 | `src/test/unit/report/test_data_status.py` | 批 6 |
| R-ADP-01 | `src/test/unit/fetcher/test_source_adapter.py` | 批 6 |
| R-ADP-02 | `src/test/unit/fetcher/test_source_adapter.py` | 批 6 |
| R-ADP-03 | `src/test/unit/fetcher/test_source_adapter.py` + `src/test/unit/fetcher/test_quote_adapter_parity.py` | 批 6 |
| R-ADP-04 | `src/test/unit/fetcher/test_chain.py` + `src/test/unit/fetcher/test_quote_adapter_parity.py` | 批 6 |
| R-ADP-05 | `src/test/unit/fetcher/test_quote_adapter_parity.py` | 批 6 |
| R-ADP-06 | `src/test/unit/fetcher/test_source_adapter_edge.py` + `src/test/unit/config/test_features.py` | 批 6 |
| R-ADP-07 | `src/test/unit/fetcher/test_source_adapter.py` | 批 6 |
| R-ADP-08 | `src/test/unit/config/test_features.py` | 批 6 |
| R-HST-01 | `src/test/unit/fetcher/test_fetcher_price.py` + `src/test/unit/providers/test_tencent.py` | 批 6 |
| R-HST-02 | `src/test/unit/providers/test_tiantian.py` + `src/test/unit/providers/test_eastmoney.py` | 批 6 |
| R-HST-03 | `src/test/unit/fetcher/test_fetcher_index.py` | 批 6 |
| R-HST-04 | `src/test/unit/fetcher/test_fetcher_index.py` | 批 6 |
| R-HST-05 | `src/test/unit/config/test_config.py` + `src/test/unit/report/test_portfolio_history.py` | 批 6 |
| R-HST-06 | `src/test/unit/fetcher/test_fund.py` | 批 6 |
| R-HST-07 | `src/test/unit/fetcher/test_fetcher_index.py` | 批 6 |
<!-- requirement-trace:end -->
---

## 3. UI/UX 验证

| 验证项 | 标准 | 现有测试 |
|:-------|:-----|:--------:|
| **TUI 菜单** | 20 选项完整、中文字符正常、按键响应正确 | ✅ |
| **TUI 进度反馈** | 长时间操作有进度条/动画，不出现"假死"感 | ✅ |
| **TUI Ctrl+C 中断** | 中断不留下半渲染状态，可安全重试 | ✅ |
| **TUI 错误提示友好** | 异常堆栈不暴露给用户，包装为中文提示 | ✅ | `test_tui_edge.py` |
| **Excel 页签结构** | 页签编号排序（1.~19.，LLM API 用量强制末位）、冻结首行、列宽自适应 | ✅ |
| **Excel 盈亏着色** | 正数绿/红色（RGB 正绿/红），覆盖所有盈亏列（本日盈亏/持仓盈亏/收益率） | ✅ |
| **Excel LLM 状态颜色** | 蓝底=缓存、绿底=成功、红底=失败、灰底=禁用+各色图标 | ✅ |
| **Excel 取价方式标识** | 蓝色字体标注（实时价/收盘价/官方净值） | ✅ |
| **Excel 评级颜色** | 5 级评级对应深绿/绿/黄/橙/红，与 HTML 一致 | ✅ |
| **Excel 数字格式** | 收益率列 % 格式，金额列千分位，小数位数统一 | ✅ | `test_excel_format_edge.py` |
| **HTML 渲染** | 浏览器渲染正常、中文无乱码、章节锚点导航 | ✅ |
| **HTML 响应式布局** | 移动端和桌面端均排版正常 | ✅ |
| **HTML LLM 条件渲染** | 无 LLM 时整节消失，有 LLM 时显示状态颜色标签 | ✅ |
| **HTML 评级色** | 深绿/绿/黄/橙/红与 Excel 一致 | ✅ |
| **HTML 打印样式** | 打印时隐藏导航、展开全部内容、黑白友好 | ✅ | `test_html_template.py` `TestHtmlTemplatePrintStyles` |
| **日志输出** | `logs/app.log` 含 INFO/WARNING/ERROR 三级，无敏感信息（API Key 脱敏） | ✅ | `test_log_sanitize.py` |
| **LLM 占位文本区分** | "未配置"/"已禁用"/"生成失败"三种文本用户可辨别 | ✅ | `test_llm_placeholder_distinction_edge.py` |
| **LLM 缓存提示** | 缓存命中显示灰字"本次使用LLM缓存" | ✅ |
| **报告文件管理** | 按日期归档、文件名含时间戳、不覆盖旧报告，自动清理 180 天前归档 | ✅ |
| **首次运行引导** | 配置缺失时提示操作步骤而非直接报错 | ✅ | `test_config_firstrun_edge.py` |
| **Web 配置编辑** | 配置面板 8 块可编辑项（7 个可编辑面，功能开关面拆成「实验性功能」「常规开关」两块）与 TUI 全集一致、即改即存、写前 `.bak` 备份、非法键 400 / 非同一来源 403、极端输入不落盘 | ✅ | `test_config_edit.py` / `test_config_edit_edge.py` / `smoke-web.py` 配置编辑检查（11 项断言） |

---

## 4. 回归测试清单

每次代码变更后按优先级执行。**§1.5 集成测试**的自动化用例是回归套件的一部分，写入 `src/test/`，由 `pytest` 统一执行；
**§4 回归清单**全部为自动化门禁，每项均对应 `src/test/` 中的自动化测试（见备注列），由 `test-runner.py` 各 `--mode` 统一执行。

三级自动化验证流水线的定义、工作流和统计数据见 `developer-guide.md` → § 测试模式详解，门禁等级定义见同文档 → 回归测试级别。

| 优先级 | 回归范围 | 触发条件 | 备注（自动化覆盖） |
|:------:|:---------|:---------|:-----|
| **P0** | `.venv/bin/python scripts/test-runner.py --mode dev-verify` 通过（项数见 [`test-coverage.md`](./test-coverage.md) → 模式对应测试量） | **任何代码变更** | 提交前极速验证 |
| **P0** | 已修复 Bug 的回归用例 | Bug 修复（MUST 补充） | 验证缺陷场景的断言 |
| **P0** | 测试隔离验证：`.venv/bin/python -m pytest --co` 无冲突 | 新增/修改 test_*.py | 避免 patch 残留污染 |
| **P1** | 报告生成完整性（菜单 E/B/L 全链路） | config / report / html / llm 变更 | `scenario_basic` 管线冒烟/指标注入 + 场景测试（Excel 页签完整、不崩溃） |
| **P1** | Excel 报告视觉质量 | 颜色/格式/样式相关变更 | `test_excel_writer.py` / `test_summary.py`（盈亏着色、评级色、LLM 状态色、冻结首行） |
| **P1** | 报告章节合并（同页签多区块 + 多契约 OR 可见性 + 块级开关） | 注册表条目 / 章节键 / 页签写入器 / HTML 模板或 partial / board_flags 变更 | `test_holdings_detail_sheet.py` / `test_position_structure_sheet.py` / `test_fundamental_snapshot_sheet.py`（各合并章：章名与区块小节标题同页签、区块行值与独立写入**逐格等价**、契约 None 的块级门控）+ `test_section_visibility.py`（`data_flag_any` 多契约 OR：单契约就绪即可见、两者皆无隐藏）+ `test_section_type_flag_consistency.py`（注册表 type ↔ 两侧 board_flags ↔ 写入器装配键一致，防旧 type/旧模块键残留）+ `test_report_chapter_consistency.py`（Excel 页签与 HTML 章节两侧可见集合一致）+ `test_fund_performance_manager_block.py`（经理变更块随基金深度分析门控）。**回归防线**：合并章若漏改任一侧可见性、装配键或 board_flags，两侧一致性/一致性守卫用例立刻失败（实施期即由此捕获 `rf-367`） |
| **P1** | 景气度框架诊断（实验性功能） | 分析框架/评分口径/关键词配置/行动建议章渲染变更 | `test_prosperity_framework.py`（六维计分、缺数据降级为未验证且不计分、总分口径与评级边界、配置覆盖）+ `test_prosperity_framework_edge.py`（空/None/零/异常类型/全防御/未知板块/极端集中度/负收益）+ `test_prosperity_framework_wiring.py`（开关关 → 契约缺席且双端无块；开 → 契约注入、Excel/HTML 块与契约一致）+ `test_fund_roe_estimate.py`（②维基金层扩展：重仓股 ROE 加权推演、报告期陈旧闸门、非 A 股过滤、known_roe 免重取）+ `test_liquidity_otc.py` 与 `test_code_utils.py::TestOtcRedemptionDaysDefault`（④维场外类型默认档：货币/短债 T+1、纯债 T+2、其他 T+3、QDII T+7，非实测标注与配置口径优先）。**回归防线**：开关关闭时报告必须逐字节不变；缺数据维度若被算成得分（臆造）立即失败 |
| **P1** | HTML 报告渲染结构 | html_writer / template 变更 | `test_html_report_structure.py`（中文不乱码、章节锚点、LLM 条件消失/出现） |
| **P1** | 缓存刷新/清理/统计（菜单 [1][2][3][4]） | cache / handlers / registry 变更 | `test_handlers_cache.py` / `test_tui_handlers.py`（刷新/清理/统计不崩溃） |
| **P1** | Provider 降级链路 | providers / fetcher 变更 | 熔断/回退/断网降级测试（S7/T15/T16 + provider edge 用例）；实际联通性由运行时 Provider Chain 回退 + 熔断治理，非门禁 |
| **P1** | 基金持仓取数阶梯次序与联接基金穿透 | providers / fetcher / report 的持仓取数路径变更 | `test_tiantian.py` `TestFetchFundHoldingsLadder`（次序不变量：第 1 跳命中不发主页面请求、联接基金不可达第 3 跳）+ `test_fund_edge.py`（批量接缝幂等/异常不外抛）+ `test_penetration.py`（穿透来源登记）。**次序回归防线**：把无年份兜底提回与年份域并列，联接基金会被最早可得报告遮蔽，本组用例立刻失败 |
| **P1** | 数据源**真实响应体**解析路径（cassette 离线回放） | providers / fetcher 的解析或归一路径变更 | `test_cassette_replay.py`（对上仓库录制的真实响应体做精确值断言，离线）；人工核验入口 `cassettes --verify`（解析器吃不下已录制响应体即报 `[ERR]` 并退出码 2）。上游字段改名/加前后缀/返回 HTML 错误页这类回归**只有真实响应体测得出**，手工构造的假响应测不出 |
| **P1** | 真实历史估值分位（TTM 口径） | `analysis/valuation_percentile`（`compute_real_valuation`/`ttm_eps_by_period`/`disclosure_date`）、`report/orchestrator`（`_fetch_valuation_for_code`）、`report/penetration_sheet` 估值文案变更 | `test_valuation_percentile.py`（TTM 四类差分/披露生效日/落盘对齐**无前视**/PB 时点/亏损剔除/分位与档位/各类降级）+ `test_valuation_percentile_edge.py`（脏值/非正与不可解析价格/生效日边界/空序列）+ `test_valuation_temperature_wiring.py`（真实分位优先与口径标注、无基本面回落代理、取数异常收敛）。**关键回归**：生效日之前的历史价格**不得**参与估值序列（前视偏差是本口径最大的正确性风险）；数据底座未就绪时估值列文案与免责语须**逐字回原样**且不取数。另有提示词侧 `test_prompts_signals.py`（五路信号：基本面分布与方向、叙事-数字背离双向命中与「无背离不得出现要求行」、信号块指纹随内容变化） |
| **P1** | 财务指标取数（主源 + 全文解析备用支路） | `providers/akshare_financial`、`analysis/financial_indicator_extract`、`fetcher/financial_indicator_adapters`、`fetcher/chain`（`financial_indicator` 链）变更 | `test_akshare_financial.py`（宽表归一/百分数换算/同名指标优先/降级）+ `test_financial_indicator_extract.py`（真实年报夹具逐字段复现：营收 862.42 亿、归母净利 345.03 亿、经营现金流 605.63 亿、EPS 1.4101、ROE 15.90%、同比 2.07%/6.17%；另有行文变体/单位换算/精度切分/扣非排除）+ `test_financial_indicator_extract_edge.py`（取值窗口边界/异常幅度/越界比率/零基数同比/截断正文）+ `test_financial_indicator.py`（链路顺序与降级、解析适配器逐章节试取与源身份注入、多期序列主源/退化单期/缓存/非 A 股不发请求/价格映射）+ 报告消费层 `test_financial_indicator.py`（契约键与 C19 登记、降级保留失败清单、质量档/趋势/PE·PB 装配、开关访问器、C7 注册与导航分组与模板 include、编排接缝开关关闭返 None 与现价贯通、穿透代码透传）+ `test_fundamental_snapshot_sheet.py`（页签数值格式与「—」占位、不可用原因与失败清单）+ 派生层 `test_financial_indicator.py`/`test_financial_indicator_edge.py`（四维阈值阶梯/缺维跳过/脏值不计分/分档边界/零基数与期数不足趋势/非正现价）。**隔离防线**：akshare 接口与 `financial_report.fetch_symbol_report` 均 mock，禁真实网络与真实密钥 |
| **P1** | 市场情绪章内区块（纯装配只按代码命中/零命中仍出契约/开关门禁与异常兜底/双端渲染载体） | `analysis/market_sentiment.py`、`report/market_sentiment.py`、`report/action_sheet.py`、`report/_report_aux_metrics.py` | `unit/analysis/test_market_sentiment.py`、`unit/report/test_market_sentiment.py`、`unit/report/test_market_sentiment_wiring.py` | — |
| **P1** | 行情/历史日 K 第三链路 + 交易日历官方兜底（适配器别名归一、`date_ms` 解析、增量起点、链路顺序、akshare 失败后官方序列兜底） | `providers/hithink.py`、`fetcher/quote_adapters.py`、`fetcher/chain.py`、`core/trading_calendar.py` | `unit/providers/test_hithink.py`（行情/K线）、`unit/fetcher/test_quote_adapter_hithink.py`、`unit/core/test_trading_calendar.py` | — |
| **P1** | 财务指标第三链路（同花顺官方报表派生：口径与报告期归一、多期回退与主源优先、凭据跳过） | `analysis/financial_statement_derive.py`、`fetcher/financial_indicator_adapters.py`、`fetcher/financial_indicator.py` | `unit/analysis/test_financial_statement_derive.py`、`unit/fetcher/test_financial_indicator_hithink.py` | — |
| **P1** | 基金持仓两源链（天天基金主 → 同花顺官方备；载荷归一 + 联接基金目标 ETF 信号，需 key 源由凭据预检跳过） | `fetcher/fund.py`、`providers/hithink.py`、`fetcher/chain.py` | `unit/fetcher/test_fund.py`（归一/链路顺序/备源接管）、`unit/providers/test_hithink.py`（候选解析/联接信号/取数入口） | — |
| **P1** | 财报摘要取数（DataSinking 密钥/限速/配额/降级） | `providers/datasink`、`fetcher/financial_report`、`report/financial_report_digest`、`core/datasource_credential` 变更 | `test_datasink.py`（符号映射/套餐限速派生/日配额护栏/HTTP 401·429·非 200/取数原语）+ `test_financial_report.py`（标的收集/年报优先/多章节拼接/截断）+ `test_financial_report_digest.py`（降级契约/失败清单）+ `test_datasource_credential.py`（密钥文件节结构/就绪判定/环境变量优先）。**隔离防线**：密钥文件与 `data/state/datasink_quota.json` 均由 conftest 重定向到 tmp；免费档无批量端点、限速落在 provider 逐请求前 |
| **P2** | 断网环境下自动降级 | 网络/超时/重试相关变更 | `test_scenario_resilience_flows.py::TestScenarioNetworkDown`（S7）+ T15/T16 |
| **P2** | 清理缓存后全新运行 | provider / fetcher / cache 变更 | `test_scenario_basic_flows.py::TestScenarioNewHoldings`（S4） |
| **P2** | 旧缓存格式兼容性验证 | cache.py / models.py 变更 | `test_cache_format.py`（gz→JSON 回退、透明读取） |
| **P2** | 跨缓存池污染验证 | 缓存 Key/TTL 策略变更 | `test_cache_cleanup.py`（多前缀独立 TTL + `TestClearByGroup` 按组精确清理） |
| **P3** | 非 UTC+8 时区运行 | 日期/时间/时区相关变更 | `test_datetime_scenarios.py`（时区边界，`datetime.now(timezone(hours=8))` 一致） |
| **P3** | 长假期前后跨日运行 | TTL / market_hours 变更 | `test_datetime_scenarios.py`（T17-T21 长假/跨年/跨日） |

## 5. 测试数据与 Mock 策略

### 5.1 通用 Mock 约定

```python
# 所有 mock 使用 unittest.mock.patch，统一路径规则：
#   模块级导入 → patch("src.python.<module>.<symbol>")
#   函数体内导入 → patch("<package>.<symbol>")   # 第三方库用顶层包名
#   内部 import → patch("src.python.<module>.<symbol>")
```

### 5.2 Mock HTTP 请求

所有 `providers/*.py` 测试通过 mock `httpx.Client` 规避真实网络：

```python
# 通过 http_client.py 工厂创建的 client
@patch("src.python.providers.tencent.httpx.Client")
def test_fetch_price_normal(self, mock_client_cls):
    mock_instance = mock_client_cls.return_value.__enter__.return_value
    mock_instance.get.return_value.status_code = 200
    mock_instance.get.return_value.text = 'v_sh600900="1~长江电力~600900~28.50~..."'
    result = fetch_price("600900")
    self.assertIsNotNone(result)
```

> 注意：provider 通过 `core/http_client.py` 创建 client（`with get_httpx_client() as client:`），
> 应 mock `httpx.Client` 类的构造，而非直接 mock 模块函数。

**真实响应体回归优先用 cassette 回放**（见 `technical.md` §2.6）。手工构造的假响应测的是
「我以为上游长什么样」，字段改名、加前后缀、换分隔符、返回 HTML 错误页这类回归它在结构上测不出；
对已完成记录的数据源（行情/K 线/基金净值/基金持仓），改用 `@pytest.mark.cassette("名称")` 声明所需
夹具，运行期离线回放真实响应体、不发起网络请求。刷新夹具是显式联网动作：
`test-runner --mode live --record-cassettes`（需 `--run-live` 同开，且仅录进 cassette 不入门禁）。

### 5.3 Mock LLM API

```python
# LLM API 调用统一 mock 入口
@patch("src.python.llm.api._call_single_provider")
def test_generate_global_macro_cached(self, mock_call):
    mock_call.return_value = ("分析内容...", {"input_tokens": 100})
    # 预热缓存
    result = generate_global_macro(...)    # 第一次调用 API
    result = generate_global_macro(...)    # 第二次命中缓存→不调 API
    assert mock_call.call_count == 1
```

### 5.4 Mock 交易日历 & 市场时段

```python
# 交易日历 — akshare 在 _get_trading_calendar 内部以 "import akshare as ak" 导入
# 不能在模块级 patch "src.python...ak"，需直接 patch 函数：
@patch("akshare.tool_trade_date_hist_sina")
def test_trading_calendar(self, mock_ak):
    mock_ak.return_value = pd.DataFrame(...)

# 市场时段 — market_hours 中 datetime.now 通过模块级引用
# 标准写法（替代对全部代码搜索 datetime.now 的 patch 路径）：
@patch("src.python.market_hours.datetime")
def test_is_market_open_morning(self, mock_dt):
    mock_dt.now.return_value = datetime(2026, 7, 2, 10, 30)  # 盘中

# 更简单的做法（日期不敏感的测试）：
@patch("src.python.cache._is_market_open")
def test_get_ttl_closed(self, mock_open):
    mock_open.return_value = False  # 盘后/非交易日 → long TTL
```

### 5.5 Mock 配置文件

```python
# config.json — get_config() 在不同函数体内导入
# 标准路径（取决于函数内 import 位置）：
@patch("src.python.cache.get_config")   # get_ttl() 内部 import
@patch("src.python.config.get_config")  # 模块级 import

# llm_key.json — 同理：
@patch("src.python.llm.api.load_llm_key")
```

### 5.6 测试数据构造

| 数据类型 | 构造方式 | 说明 |
|:---------|:---------|:-----|
| **持仓数据** | 内存 `Holding(...)` 对象 | 不依赖磁盘 xlsx |
| **API 响应** | `httpx.Response(status_code, text=...)` 或 dict→JSON | 返回结构模拟真实 API |
| **缓存数据** | `cache.set(key, value)` 到临时目录 | 不操作真实 `data/cache/` |
| **交易日历** | 固定 `datetime.date` 列表 | 避免 akshare API 依赖 |
| **市场时段** | `@patch("src.python.market_hours.datetime")` | 覆盖开盘/午休/收盘/周末/节假日 |
| **基金净值** | `{"NAV": 1.5, "NAVdate": "2026-07-01"}` 字典 | 模拟东方财富返回值 |
| **天天基金 JS** | 模拟 `var data = { ... }` 格式的 JavaScript 变量 | 模拟 pingzhongdata 响应 |
| **新闻** | `{"title": "...", "content": "..."}` 列表 | 模拟各新闻源返回 |

### 5.7 门禁场景的自动化覆盖

以下场景全部由自动化测试覆盖（通过 mock 精确模拟条件），不存在人工门禁：

| 场景 | 自动化覆盖 | 模拟方式 |
|:-----|:-----------|:---------|
| Provider API 联通性 | 熔断/回退/断网降级用例（S7/T15/T16 + provider edge） | mock httpx 响应模拟异常/超时；实际联通性由运行时 Provider Chain 回退 + 熔断治理，非门禁 |
| Excel 报告视觉检查 | `test_excel_writer.py` / `test_summary.py` | 断言单元格样式（着色/评级色/冻结首行） |
| HTML 报告浏览器渲染 | `test_html_report_structure.py` | 断言渲染结构（中文/锚点/LLM 条件/响应式） |
| 断网降级 | `test_scenario_resilience_flows.py::TestScenarioNetworkDown`（S7）+ T15/T16 | mock 网络异常 → 断言降级占位/过期缓存读取 |
| 旧缓存格式兼容 | `test_cache_format.py` | 构造旧格式 JSON/gzip → 断言当前版本透明读取 |

### 5.8 测试隔离要求

- 测试不操作真实 `data/cache/` 和 `data/state/`，所有缓存/状态操作使用 `tempfile.mkdtemp` 临时目录
- **后台线程兜底隔离**：用例级 monkeypatch 只能约束用例存活期，**后台批量线程**（如 `fetcher/industry.py` 经 `BatchDispatcher` 派发的取数）可能活过 teardown——此时路径补丁已还原，线程内新建的 tracker 会落到真实 `data/state/` 写盘。`conftest.py::_install_session_state_fallback_isolation` 在会话开始即把降级状态文件默认路径改为会话级临时目录（用例内仍被 `tmp_path` 覆盖，teardown 后回落到兜底值），新增此类后台写入方时须同步纳入
- 测试不写磁盘配置，`config.json` 通过 `os.environ` 或 `tempfile` 隔离
- 网络测试全部 mock，不发起真实 HTTP 请求
- 测试间互不依赖，每个 `setUp` 清理状态
- 每新增 test_*.py 后运行 `.venv/bin/python -m pytest --co` 验证无 patch 残留污染
- 不修改全局变量/环境变量（必须修改时用 `with patch.dict(os.environ, ...)`）

---

## 6. 验收标准

每个迭代完成后必须满足以下条件方可进入下一迭代：

### 6.1 功能完整性

1. **功能完成**：当前迭代的所有计划功能已实现（对应 `plan.md` 条目全部标注完成）
2. **文档同步**：新增/重命名/删除的文件或目录已同步更新 `folders.md` 目录树
3. **自审记录**：自查问题已写入 `review-findings.md`，修复后已同步到 `changelog.md`

### 6.2 自动化测试门禁

4. **全量 pytest 通过**：`.venv/bin/python -m pytest src/test/` 全部通过（0 failed, 0 error）
5. **无测试污染**：`.venv/bin/python -m pytest --co` 验证无跨文件 patch 残留冲突
6. **测试数量不降级**：新增功能后 `.venv/bin/python -m pytest --collect-only | tail -1` 报告的总测试数 ≥ 变更前（有删除须在 changelog.md 中说明理由）
7. **测试用例 MUST**：新增功能必有对应测试用例，Bug 修复必有对应回归用例（验证缺陷场景的具体断言，非仅正常路径）
8. **`test-coverage.md` 场景表更新**：新场景（S/Txx）必须在场景测试分组表补充条目

### 6.3 回归检查门禁

> 详细回归项定义（含触发条件和备注）见 **§4 回归测试清单**，此处仅列门禁约束。

9. **P0 全通** — 不可提交代码：`.venv/bin/python scripts/test-runner.py --mode dev-verify`（项数见 [`test-coverage.md`](./test-coverage.md) → 模式对应测试量；其 preflight 已内置 `check-task-numbering.py --ci`）+ `.venv/bin/python scripts/check-code-traces.py --ci`（代码注释历史痕迹检查）+ `.venv/bin/python scripts/check-doc-traces.py --ci`（文档历史痕迹检查）+ `.venv/bin/python scripts/check-task-numbering.py --ci`（任务编号全局一致性检查）+ `.venv/bin/python scripts/check-semantic-index.py --ci`（语义命名索引正反向校验）+ `.venv/bin/python scripts/check-doc-drift.py --ci`（文档与实现一致性：章节/开关/默认值/面板编号/目录树/统计表/归档索引/管理文档分区纪律/Thinking 支持矩阵）+ `.venv/bin/python scripts/check-test-redundancy.py --ci`（测试用例冗余与无效：死用例/无断言/完全重复/自证用例）+ `.venv/bin/python scripts/check-requirement-trace.py --ci`（需求 ID ↔ 验证载体追溯）+ Bug 回归用例 + 测试隔离验证（`.venv/bin/python -m pytest --co`）
10. **P1 全通** — 不可合并 master：`.venv/bin/python scripts/test-runner.py --mode verify` + §4 中 P1 级各自动化回归项全部通过（报告完整性 / Excel 视觉 / HTML 渲染 / 缓存刷新 / Provider 降级）
11. **P2 已执行** — 可合入但不可发布：`.venv/bin/python scripts/test-runner.py --mode verify,regression` + `.venv/bin/python scripts/check-code-traces.py --ci`（代码注释历史痕迹检查）+ `.venv/bin/python scripts/check-doc-traces.py --ci`（文档历史痕迹检查）+ `.venv/bin/python scripts/check-task-numbering.py --ci`（任务编号全局一致性检查）+ `.venv/bin/python scripts/check-semantic-index.py --ci`（语义命名索引正反向校验）+ `.venv/bin/python scripts/check-doc-drift.py --ci`（文档与实现一致性：章节/开关/默认值/面板编号/目录树/统计表/归档索引/管理文档分区纪律/Thinking 支持矩阵）+ `.venv/bin/python scripts/check-test-redundancy.py --ci`（测试用例冗余与无效：死用例/无断言/完全重复/自证用例）+ `.venv/bin/python scripts/check-requirement-trace.py --ci`（需求 ID ↔ 验证载体追溯）+ §4 中 P2 级各自动化回归项全部通过（断网降级 S7 / 全新运行 S4 / 旧缓存格式 / 跨缓存池污染，均已在 `verify,regression` 内覆盖）+ **发布手动验证**（建议，非自动门禁）：`.venv/bin/python scripts/test-runner.py --mode perf,security`（端到端性能基准 + 安全基线，独立标记不进自动门禁，手工/发布前运行）
    > 注：P2 的 `verify` 在 `dev → merge → tag master` 常规流程中与 P1 重复。保留冗余是为了覆盖**直接从 dev 打 tag 发布**（未过 P1 合入门禁）的场景。若团队有严格 merge 屏障且从不直接发布 dev，P2 可简化为 `--mode regression`（仅场景测试，~6min），节省约 1min 单元测试重复时间。

### 6.4 补充自动化门禁

12. **异常场景全覆盖**：§1.6 异常场景清单全部 ✅（每项异常场景均有对应自动化用例，edge/resilience 标记），不允许存在仅靠人工确认的 🔴/🟡 项
13. **报告文件视觉结构**：Excel 和 HTML 输出无格式错乱（盈亏着色、评级色、冻结首行、中文不乱码）→ `test_excel_writer.py` / `test_summary.py` / `test_html_report_structure.py`
14. **TUI 菜单功能**：所有菜单选项（[E]/[B]/[L]/[W]/[C]/[F]/[O]/[1]/[2]/[3]/[4]/[P]/[I]/[A]/[S]/[R]/[V]/[H]/[D]/[X]，其中 [D] 系统自检受 `doctor_check` 开关门控）响应正确、无崩溃 → `test_tui_menu.py`（20 项计数/键唯一/索引）+ `test_tui_handlers.py` + `test_handlers_*.py`
15. **whatif CLI**：`--candidate` 必填、`--base` 可选、缺失报参数错误、`--effective-date` 解析，生成/归档行为 → `test_cli.py::test_whatif_*` + `test_whatif_operations.py` / `test_whatif_sheet.py` / `test_whatif_html.py` / `test_whatif_writer.py`
16. **whatif 生效日时序回测**：① 过去生效日→出「时序回测」页签/区 → `test_effective_date_merges_backtest` + `test_backtest_sheet_full` + `test_backtest_section_rendered`；② 缺省→维持现状（无回测）→ `test_no_effective_date_no_backtest_call` + `test_full_rendering_sections_without_backtest`；③ 未来/非法日期→降级占位、主报告正常 → `test_compute_backtest_days_invalid_format` / `test_compute_backtest_days_future_or_today_none` + `test_effective_date_exception_degrades` + `test_backtest_sheet_unavailable_reason_placeholder`；④ 断网/空缓存→回测不可用但报告仍生成 → `test_unavailable_returns_reason` / `test_unavailable_without_reason_falls_back` + `test_effective_date_bt_none_no_key`

---

## 7. 测试记录

测试记录和发现的问题记录在 `docs-stm/managements/changelog.md` 中。
审查发现的问题（无论是否已修复）记录在 `docs-stm/managements/review-findings.md`。

---

## 8. 新增测试指南

> 新增测试用例的操作流程（确定文件位置 / 命名规范 / 必须更新的文件 / 验证步骤 / 膨胀阈值）详见 [`developer-guide.md` → 新增测试指南](developer-guide.md#新增测试指南)。
