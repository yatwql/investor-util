# 场景-测试文件覆盖率映射（详细版）

> 本文件由 `scripts/validate_coverage_map.py` 验证。
> 新增 S/T 场景或修改测试文件后，运行 `python scripts/validate_coverage_map.py` 确认映射准确。

覆盖状态标识：
- ✅ 已覆盖 — 有对应测试文件/类
- ◐ 部分覆盖 — 有覆盖但不够完整
- ❌ 未覆盖 — 尚无测试

---

## §1.3 业务场景 S1-S20

| 场景 | 覆盖状态 | 测试文件/类 | 说明 |
|:-----|:---------|:------------|:-----|
| **S1: 纯股票组合** | ✅ 已覆盖 | `test_integration.py::TestScenarioS1` | 穿透 TOP10 等于直接持股 |
| **S2: 纯基金组合** | ✅ 已覆盖 | `test_integration.py::TestScenarioS2` | 穿透计算+LLM 正常生成 |
| **S3: 混合多账户** | ✅ 已覆盖 | `test_integration.py::TestScenarioS3` | 分账户小计/总计/分组 |
| **S4: 新持仓无缓存** | ✅ 已覆盖 | `test_integration.py::TestScenarioS4` | 全部 API 获取 |
| **S5: 缓存全命中** | ✅ 已覆盖 | `test_integration.py::TestScenarioS5` | 第二次全缓存 |
| **S6: 纯债基金组合** | ✅ 已覆盖 | `test_integration_scenarios.py::TestScenarioS6` | 穿透无股权覆盖 |
| **S7: 断网降级过期缓存** | ✅ 已覆盖 | `test_integration_scenarios.py::TestScenarioS7` | 网络中断+过期缓存 |
| **S8: 单账户单持仓** | ✅ 已覆盖 | `test_integration_scenarios.py::TestScenarioS8` | 单行报告 |
| **S9: 零成本持仓** | ✅ 已覆盖 | `test_integration_scenarios.py::TestScenarioS9` | cost_price=0 |
| **S10: 极端值** | ✅ 已覆盖 | `test_integration_scenarios.py::TestScenarioS10` | 极大持仓份额 |
| **S11: LLM 混合缓存+真实调用** | ✅ 已覆盖 | `test_llm_scenarios.py::TestS11MixedCacheAndRealCall` | 2缓存+1成功+1失败+1禁用 |
| **S12: LLM 全部失败（5 种原因）** | ✅ 已覆盖 | `test_llm_scenarios.py::TestS12AllFailures` | 5种失败原因映射 |
| **S13: Extended Thinking 混合** | ✅ 已覆盖 | `test_llm_scenarios.py::TestS13ThinkingMixed` | 2有+2无 Thinking |
| **S14: LLM 不启用** | ✅ 已覆盖 | `test_llm_scenarios.py::TestS14LlmDisabled` | 无 LLM 章节/用量页 |
| **S15: 禁用+缓存混合** | ✅ 已覆盖 | `test_llm_scenarios.py::TestS15DisabledPriority` | 禁用优先于缓存 |
| **S16: 断网下 LLM 降级** | ✅ 已覆盖 | `test_llm_scenarios.py::TestS16NetworkDown` | 全部 NETWORK_ERROR |
| **S17: LLM 部分缓存超期** | ✅ 已覆盖 | `test_llm_scenarios.py::TestS17PartialCacheExpiry` | 过期重新调用 |
| **S18: LLM 全缓存+无调用** | ✅ 已覆盖 | `test_llm_scenarios.py::TestS17aFullCache` | call_count=0 |
| **S19: news_correlation 启用+5 模块** | ✅ 已覆盖 | `test_llm_scenarios.py::TestS11MixedCacheAndRealCall`（含 news_correlation） | 5模块明细 |
| **S20: 无 LLM 用量不渲染** | ✅ 已覆盖 | `test_llm_scenarios.py::TestS14LlmDisabled` | 无页签/章节 |

## §1.6 日期/时间场景 T1-T16

| 场景 | 覆盖状态 | 测试文件/类 | 说明 |
|:-----|:---------|:------------|:-----|
| **T1: 交易日盘中** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestGetTtlMarketAware` | short TTL 30s |
| **T2: 交易日盘前** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestGetTtlMarketAware` | long TTL |
| **T3: 午间休市** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestIsMiddayBreak` | 7项边界 |
| **T4: 交易日盘后** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestGetTtlMarketAware` | long TTL |
| **T5: 非交易日** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestGetTtlMarketAware` | weekend long TTL |
| **T6: 长假边界** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestLastTradingDayExtended`、`TestGetTradingCalendarCache` | 国庆假期/缓存行为 |
| **T7: 国内场外基金** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestClassifyHoldings`、`TestCountTradingDaysBack` | 分类+净值日期标签 |
| **T8: QDII 场外基金** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestClassifyHoldings` | QDII 名称识别 |
| **T9: 场内 ETF/LOF** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestClassifyHoldings` | 名称/代码识别 |
| **T10: 股票持仓** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestClassifyHoldings` | 6/0/3 开头代码 |
| **T11: 混合持仓** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestClassifyHoldings`::test_mixed_holdings_separated_correctly | 四种类型互不干扰 |
| **T12: 盘中转盘后** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestGetTtlTransition` | TTL 变化断言 |
| **T13: 时段切换缝隙** | ◐ 部分覆盖 | `test_market_hours.py`（边界测试） | 分钟级边界已有，缺少切换瞬间竞态 |
| **T14: 首次启动+非交易日** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestFirstLaunchNonTradingDay` | 无缓存降级 |
| **T15: 盘中断网** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestFetchMarketDataMarketAware` | fetch 链路 TTL |
| **T16: 盘后断网** | ✅ 已覆盖 | `test_datetime_scenarios.py::TestFetchMarketDataMarketAware` | fetch 链路 TTL |

## §1.5 异常场景覆盖

| 场景 | 覆盖状态 | 测试文件/类 | 说明 |
|:-----|:---------|:------------|:-----|
| 断网降级 | ✅ 已覆盖 | `test_integration_scenarios.py::TestScenarioS7` | 过期缓存降级集成 |
| 熔断器状态 | ✅ 已覆盖 | `test_circuit_breaker_recovery.py`（15项） | 全生命周期 |
| Provider 回退 | ✅ 已覆盖 | `test_chain.py::TestFetchWithFallback` | 主→备→过期缓存 |
| 大文件 gzip 缓存 | ✅ 已覆盖 | `test_cache.py` gzip 相关测试 | >100KB 自动压缩 |
| 空持仓+LLM | ✅ 已覆盖 | `test_llm_scenarios.py::TestEmptyHoldingsWithLlm` | 不崩溃+占位 |
| 非交易日+LLM | ◐ 部分覆盖 | `test_datetime_scenarios.py` + `test_integration.py`（S7） | 需补充 LLM 内容含交易日标记验证 |
| 多账户混合+LLM 多轮 | ◐ 部分覆盖 | `test_integration.py::TestScenarioS3` + `TestScenarioS5` | 覆盖多账户和多轮，但未验证指纹一致性 |
| market_hours UTC 时区 | ✅ 已覆盖 | `test_market_hours.py::TestUtcTimezoneConsistency` | 9项跨时区 |
| 原子写入断电 | ✅ 已覆盖 | `test_config_atomic.py`（11项） | tempfile+os.replace |
| today_profit 场外非 T 日 | ✅ 已覆盖 | `test_market_value_edge.py` + `test_market_value.py` | nav_date≠T→0 |
| 溢价率占位符 | ✅ 已覆盖 | `test_market_value_edge.py` | `--`占位 |
| 净值数据空窗期 | ✅ 已覆盖 | `test_market_value_edge.py::TestCountTradingDaysBack`、`TestDeterminePriceTypeNavGap` | 3个月空窗→官方净值(日期) |
| 多时区 QDII 净值一致性 | ✅ 已覆盖 | `test_qdii_timezone.py::TestQdiiNavDateConsistency` | 美东/港股 QDII T-1/T-2 |
| 交易时段切换瞬间取价 | ✅ 已覆盖 | `test_market_value_edge.py::TestDeterminePriceTypeSessionSwitch` | 11:29:59/11:30:00/14:59:59/15:00:00 |
| 交易时段 cache TTL 短/长切换 | ✅ 已覆盖 | `test_cache.py::TestGetTTLMarketHourAware` | market_open 30s vs 闭市长 TTL |
