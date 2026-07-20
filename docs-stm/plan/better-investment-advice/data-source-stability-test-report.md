# Rf & 885005 数据源稳定性测试报告

> **版本**: v1.0 · **创建日期**: 2026-07-20  
> **归档日期**: 2026-07-20（原位于 `docs-stm/tmp/`，已迁移至正式目录）  
> **测试执行**: 2026-07-20  
> **执行说明**: 本报告记录 PRE-01（Rf 国债收益率）和 PRE-02（偏股基金指数 885005）的专项测试结果。

---

## 一、PRE-01: Rf 国债收益率 API 测试

### 1.1 测试目标

- 原定接口：`datacenter-web.eastmoney.com RPTBOND_BOND_YIELD_AND_SPREAD`
- 储备源：`worldgovernmentbonds.com`
- 替代源（测试中发现）：`bond_zh_us_rate`（akshare 封装的 Sina 财经数据）
- 决策标准：API 可用→P1-01/P1-02 按计划；API 不可用→P1-03 手动配置兜底

### 1.2 东方财富 datacenter API 测试

**测试时间**：2026-07-20

测试了 `datacenter-web.eastmoney.com/api/data/v1/get` 接口，使用大量不同 report name：

| reportName | 结果 | 备注 |
|-----------|:----:|------|
| `RPTBOND_BOND_YIELD_AND_SPREAD` | ❌ 参数配置不对 | 原始规划假设值 |
| `RPTBOND_YIELD` | ❌ 参数配置不对 | |
| `RPT_BOND_YIELD_CURVE` | ❌ 参数配置不对 | |
| `RPT_BOND_BS_INFO` | ✅ 成功 | 但返回债券基础信息，非收益率 |
| `RPT_ECONOMY_CPI` / `GDP` / `PMI` | ✅ 成功 | API 本身可用，但无债券收益率报告名 |
| 其余 25+ 个 bond/yield 相关 report name | ❌ 全部参数配置不对 | |

**结论**：东方财富 datacenter API **不再提供债券收益率数据**，该 API 端点在原规划中为错误假设。

### 1.3 worldgovernmentbonds.com 测试

- HTML 可获取（HTTP 200, ~46KB）
- **表格渲染为 JS 动态生成**，仅原始 HTML 无法解析出收益率数据
- 无 REST API 端点（尝试 4 个 URL 全部 404）
- **结论**：不可直接抓取

### 1.4 akshare 替代源测试

| 函数 | 数据 | 范围 | 结论 |
|------|:----:|:----:|:----:|
| `bond_zh_us_rate` 💡 | 中国 10Y 收益率 1.7404% | **2002~2026-07-17**（6129 条） | **✅ 主源** |
| `bond_china_yield` | 中国国债收益率曲线 | 2020-02 ~ 2021-01（246 条） | ⚠️ 历史备份 |
| `bond_treasury_index_cbond` | 国债指数价格 | 2008~至今（4634 条） | ⚠️ 价格非收益率 |

#### 1.4.1 `bond_zh_us_rate` 连续 50 次稳定性测试

| 测试项 | 结果 |
|--------|:----:|
| 连续 50 次请求成功率 | **50/50 = 100%** |
| 平均响应时间 | **2.734s** |
| 最小/最大响应时间 | 2.318s / 3.416s |
| 95% 分位响应时间 | 3.390s |
| 数据结构一致性 | ✅ 100%（13 列稳定，字段名一致） |
| 最新值一致性 | ✅ 100%（全部返回 China10Y=1.7404%） |
| 网络错误 | **0 次** |
| 限频触发 | **0 次** |

**结论**：`bond_zh_us_rate` 稳定可用，作为 Phase 1 的 Rf 主数据源。

### 1.5 数据质量对比

| 源 | 中国 10Y 最新值 | 历史覆盖 | 数据类型 |
|-----------|:--------------:|:--------:|---------|
| `bond_zh_us_rate` (Sina) | **1.7404%** (2026-07-17) | 2002~至今 | 收益率 % |
| `bond_china_yield` (ChinaBond) | 3.1185% (2021-01-22) | 2020~2021 | 收益率 % |
| `bond_treasury_index_cbond` (ChinaBond) | 指数值 | 2008~至今 | 指数价格 |

---

## 二、PRE-02: 偏股基金指数 885005 可用性测试

### 2.1 测试目标

- 接口：akshare / 东方财富基金指数 / 新浪/腾讯备用链路
- 决策标准：可获取→P3-07 使用三列对比表；不可获取→降级为沪深300+自定义基金池

### 2.2 测试结果

| 数据源 | 测试方式 | 结果 | 备注 |
|--------|---------|:----:|------|
| akshare `index_zh_a_hist` | symbol="885005" | ❌ | NoneType error — 非有效 index code |
| akshare `stock_zh_index_daily` | symbol="885005" | ❌ | Sina: "Invalid service name" |
| akshare `stock_zh_index_daily_em` | symbol="885005" | ❌ | 0 rows |
| akshare `stock_zh_index_spot_em` | search 885005 | ❌ | 未找到 |
| akshare `index_all_cni` | 1422 CSI 索引 | ❌ | 885005 不在其中 |
| 东财 push2 API | 市场码 0~19 | ❌ | 全部无数据 |
| 东财 push2his K-line | market=0/1/9 | ❌ | rc=100, data=null |
| 东财基金 index API | `FundIndex` | ❌ | ErrCode=4 (404) |
| 东财基金 performance API | `IndexPerformance` | ❌ | ErrCode=4 (404) |
| 腾讯财经 API | zs885005/sz885005/sh885005 | ❌ | v_pv_none_match |
| 腾讯 K-line API | zs885005 | ❌ | param error |
| 中证指数 (CSI) API | 930950/932055/931255 | ❌ | 全部不可用 |
| 新浪备用链路 | sz885005/sh885005 | ❌ | Invalid service name |

### 2.3 根因分析

885005（中证偏股基金指数）实际上是 **Wind（万得）金融终端** 的代码，并非自由公开 API 可获取的数据。中证指数公司发布了替代指数：
- **930950**（中证偏股型基金指数）— 但同样未在公开 API 中提供
- **932055**（中证主动偏股基金指数）— 同上

**结论**：885005 及 CSI 替代指数均无法通过免费公开 API 获取。

---

## 三、决策结论

### PRE-01-D 决策门

| 决策项 | 结论 |
|--------|:----:|
| 东方财富 datacenter API 可用且稳定 | ❌ **API 已不可用** |
| `bond_zh_us_rate` (akshare/Sina) 可用 | ✅ **稳定可用**（50/50, 100%) |
| **决策路径** | **激活 P1-03 手动配置兜底 + `bond_zh_us_rate` 作为自动化主源** |

**影响范围**：
- P1-01（东方财富 API fetcher, 12h）→ **取消**
- P1-02（备用源 fetcher, 8h）→ **取消**
- P1-03（手动配置, 2h）→ **保留**，降为 Rf 的 **手动兜底**，主源改为 `bond_zh_us_rate`
- P1-15（Rf 测试, 8h）→ **缩减**，只需集成测试 `bond_zh_us_rate` 调用
- 合计释放 **~20h** 开发工时，建议重分配给 P1-11（功能开关）、P1-12（断路包装器）、P1-04（数据质量增强）

### PRE-02-D 决策门

| 决策项 | 结论 |
|--------|:----:|
| 885005 可获取 | ❌ **不可获取**（Wind 专用代码） |
| CSI 替代（930950 等）可获取 | ❌ **不可获取** |
| **决策路径** | **降级为沪深300+自定义基金池** |

**影响范围**：
- P3-07：不扩展 `index.py` 增加 885005 → 只实现降级说明
- PRE-02-D：prompt 分支实现"偏股基金指数暂不可用，以下对比仅基于沪深300"
- P3-10（竞争语境完整版）: 使用沪深300+自定义池，不再依赖 885005

---

## 四、测试环境

| 项目 | 值 |
|------|:---|
| 执行主机 | Windows 11 |
| Python 版本 | 3.13 |
| akshare 版本 | 最新 |
| 请求库 | requests + akshare |
