# 行业分类/概念板块数据源接入 — 实施计划

创建日期：2026-06-28
类型：feat（新增数据源）

---

## 问题描述

当前系统在以下场景中需要行业/概念分类信息，但仅有静态关键词映射表（约 300+ 关键词 → 12 个板块）：

1. **穿透模块板块列**：`penetration.py` 的 `classify_sector()` 基于名称关键词匹配，覆盖有限
2. **新闻关键词富化**：`news_correlation.py` 的 "industry" 类型只是未被匹配到的剩余关键词，无实际行业信息
3. **LLM 分析上下文**：全球政经/智囊团分析缺少持仓资产的行业归属和概念热点信息

目标：接入东方财富 push2 API 的三级行业分类和概念板块归属，为每只股票/基金提供官方行业标签，7 天 TTL 缓存，持仓变更时自动刷新。

---

## API 调研

### 东方财富 push2 行业分类

```
GET https://push2.eastmoney.com/api/qt/stock/get
  ?secid=1.{code}
  &fields=f57,f58,f127,f128,f140,f141
```

| 字段 | 含义 | 说明 |
|------|------|------|
| f57 | 股票代码 | 6 位数字 |
| f58 | 股票名称 | 中文简称 |
| f127 | 行业ID | 东方财富三级行业编码 |
| f128 | 行业名称 | 如"电力设备" |
| f140 | 概念ID列表 | 逗号分隔的概念板块ID |
| f141 | 概念名称列表 | 逗号分隔的概念名称 |

**secid 前缀规则：**
- `1.{code}` — 沪市/深市股票（600000-603999, 000001-003999, 300000-301999）
- `0.{code}` — 深市主板（000001-001999 等旧格式）

### 备用方案

当 push2 API 不可用时，回退到东方财富个股页面解析：

```
GET https://push2.eastmoney.com/api/qt/stock/get
  ?secid=1.{code}
  &fields=f57,f58,f128
```

仅获取 f128（行业名称），不获取概念板块（f140/f141 在备用方案中不可用）。

---

## 实施单元

### U1: 新 Provider `src/providers/eastmoney_industry.py`

**Goal**: 封装东方财富 push2 API 的行业分类和概念板块数据获取。

**Files**:
- Create: `src/providers/eastmoney_industry.py`

**Approach**:
1. `fetch_industry(code: str) -> dict | None`
   - 调用 push2 API，提取 f128（行业名称）和 f127（行业ID）
   - 返回 `{"industry": "电力设备", "industry_id": "xxxx"}`
   - API 失败时返回 None

2. `fetch_concepts(code: str) -> list[dict] | None`
   - 调用 push2 API，提取 f141（概念名称列表）
   - 返回 `[{"name": "CPO光模块", "id": "BKxxxx"}, ...]`
   - API 失败或无概念时返回 None 或 []

3. `fetch_industry_and_concepts(code: str) -> dict | None`
   - 合并调用，一次 API 请求获取行业 + 概念
   - 返回 `{"code": "600900", "industry": "电力设备", "concepts": ["CPO光模块", "人工智能"]}`

4. 使用 `httpx.Client(timeout=10)`，复用已有的 `_HEADERS` 模式
5. 无需新依赖（httpx 已在 requirements.txt 中）

**Test scenarios**:
- 模拟 API 正常返回 → 正确解析行业和概念
- 模拟 API 返回空概念列表 → 正确返回空列表
- 模拟 API 超时/异常 → 返回 None，不抛出异常
- 模拟备用链路成功 → 正确解析行业名称

**Verification**: `python -c "from src.providers.eastmoney_industry import fetch_industry_and_concepts; print(fetch_industry_and_concepts('600900'))"` 看到行业和概念数据

---

### U2: 缓存集成

**Goal**: 新增 `industry_*` 缓存类型，7 天 TTL，纳入自动清理。

**Files**:
- Modify: `src/cache.py`
- Modify: `src/config.py`
- Modify: `src/main.py`

**Approach**:
1. **cache.py** `_CACHE_TTL_DEFAULTS`:
   ```python
   "industry": CACHE_WEEKLY,  # 7 天 — 行业分类不频繁变化
   ```

2. **cache.py** `prefix_type_map`:
   ```python
   "industry": "industry",
   ```

3. **cache.py** `cleanup_expired()`:
   - `industry` 前缀已自动覆盖（prefix_type_map 匹配）

4. **config.py** `_DEFAULT_CONFIG.cache_ttl`:
   ```python
   "industry": 604800,  # 7 天
   ```

5. **main.py** `_cmd_update_basic_cache()`:
   - 新增 `clear_by_prefix("industry_")` 清除行业缓存
   - 归入菜单 [1]（基础类数据，类似基金持仓/业绩）

6. **README.md / requirements.md** 更新：
   - 缓存文件清单新增 `industry_{code}.json`
   - TTL 表新增 `industry` 行
   - 菜单 [1] 清除范围新增 `industry_*`
   - 新增缓存覆盖矩阵

**Test scenarios**:
- `get_ttl("industry")` 返回 604800
- `clear_by_prefix("industry_")` 正确清除 industry_ 开头的缓存
- 配置覆盖 `cache_ttl.industry = 3600` 后 `get_ttl("industry")` 返回 3600

---

### U3: Fetcher 路由

**Goal**: 在 `fetcher.py` 中添加行业数据获取路由，支持批量预热。

**Files**:
- Modify: `src/fetcher.py`

**Approach**:
1. 新增 `_INDUSTRY_CACHE_PREFIX = "industry_"` 常量
2. 新增 `fetch_industry_data(code: str) -> dict | None`:
   - 使用 `_fetch_with_fallback()` 模式
   - Chain: `["eastmoney_industry"]`
   - 缓存键: `industry_{code}`
   - TTL: `CACHE_WEEKLY`（可通过 cache_ttl.industry 覆盖）
   - 转写函数将 provider 原始输出转为统一格式
3. 新增 `_INDUSTRY_PROVIDERS` 注册表
4. 新增 `batch_fetch_industry_data(codes: list[str]) -> dict[str, dict]`:
   - 对一组代码进行批量行业数据获取
   - 使用 ThreadPoolExecutor(max_workers=3) 并发
   - 返回 {code: industry_data} 字典
   - 适用于持仓变更时的批量预热

**Test scenarios**:
- 缓存命中时返回缓存数据
- 缓存未命中时调用 provider 并写入缓存
- 批量获取正确处理多个代码

---

### U4: 新闻关联富化增强

**Goal**: 将行业/概念数据注入新闻关键词富化，新增 "concept" 类型。

**Files**:
- Modify: `src/report/news_correlation.py`
- Modify: `src/report/penetration.py`（穿透数据输出 industry 字段）

**Approach**:
1. 在 `build_news_data()` 中，获取持仓和穿透资产后，调用 `fetch_industry_data()` 或 `batch_fetch_industry_data()` 获取行业/概念
2. 将行业名称和概念名称加入 `_build_keyword_lookup()` 的 lookup 表中，type 为 `"concept"`
3. `_enrich_keywords_for_item()` 新增 `"concept"` 类型处理：
   - 显示格式：`"CPO光模块[概念]"`
   - 类型排序：holding(0) → penetration(1) → concept(2) → industry(3)
4. `_format_enriched_keywords()` 自动适配 concept 类型
5. HTML 模板新增 `source-tag-concept` 样式（橙色/金色背景区分）
6. Excel 富化文本自动包含 `[概念]` 标记

**Integration timing**:
- `build_news_data()` 在关键词匹配→LLM增强→富化之前插入行业数据获取
- 仅在 `holdings` 或 `penetrated_assets` 非空时触发

**Test scenarios**:
- concept 类型关键词被正确识别和富化
- concept 类型显示格式为 `"XXX[概念]"`
- type 排序正确：holding > penetration > concept > industry
- 穿透资产也有 concept 富化
- 行业/概念缓存命中时正常工作

---

### U5: 穿透模块板块分类增强

**Goal**: 在 `compute_penetration_top10()` 和 `write_penetration_sheet()` 中使用 API 行业数据补充静态关键词匹配。

**Files**:
- Modify: `src/report/penetration.py`

**Approach**:
1. 在 `compute_penetration_top10()` 中，对穿透结果集调用 `batch_fetch_industry_data()`
2. 每个穿透条目新增 `"sector_from_api"` 字段
3. `classify_sector()` 新增参数 `prefer_api_data=False`：
   - `True` 时优先使用 API 行业数据（若不可用则回退关键词匹配）
4. 写入穿透页签时，板块列优先显示 API 行业数据
5. 若 API 数据可用，在板块列显示 `"消费 (API)"` 或 `"科技 (API)"` 以区分来源
6. 缓存机制避免重复 API 调用（同一代码多次出现时只取一次）

**Test scenarios**:
- API 行业数据可用时板块列显示 API 结果
- API 不可用时回退关键词匹配
- 同一代码多次出现只调用一次 API
- 空代码/无效代码安全处理

---

### U6: 测试覆盖

**Goal**: 为所有新增功能编写可自测的单元测试。

**Files**:
- Create: `src/test_eastmoney_industry.py`
- Modify: `src/test_news_correlation.py`（新增 concept 类型测试）
- Modify: `src/test_penetration.py`（新增 API 行业数据测试）

**Test categories**:
1. **Provider 测试** (`test_eastmoney_industry.py`):
   - API 正常返回 → 正确解析行业和概念
   - API 返回空概念/无行业 → 返回空/None
   - API 超时异常 → 返回 None
   - 股票代码前缀处理正确

2. **缓存测试**:
   - `get_ttl("industry")` 默认值正确
   - `clear_by_prefix("industry_")` 正常清除

3. **富化测试** (`test_news_correlation.py`):
   - concept 类型关键词富化
   - concept 排序在 penetration 之后、industry 之前
   - concept 显示格式正确
   - 混合类型富化顺序正确

4. **穿透增强测试** (`test_penetration.py`):
   - `classify_sector()` 配合 API 数据的行为
   - 回退逻辑正确

---

### U7: 文档更新

**Goal**: 更新所有管理文档，确保新增功能被完整记录。

**Files**:
- Modify: `docs-stm/managements/requirements.md`
- Create: `docs-stm/technical.md`（新技术文档）
- Modify: `docs-stm/managements/testplan.md`
- Modify: `docs-stm/README.md`
- Modify: `docs-stm/managements/changelog.md`
- Modify: `docs-stm/managements/review-findings.md`

**更新内容**:

**requirements.md**:
- 数据源表：行业分类/概念板块从"规划中"改为"✅ 已实现"
- 缓存文件清单：新增 `industry_{code}.json` 行
- TTL 表：新增 `industry` 行（7 天）
- 手动刷新表：菜单 [1] 新增 `industry_*`
- 模块 6 关键词富化：新增 concept（概念）类型说明
- 穿透模块：新增 API 行业数据说明

**technical.md**（新文件）:
- 技术架构总览
- 数据源汇总（含行业/概念）
- 各模块技术要点
- 目录结构
- 缓存策略完整说明

**testplan.md**:
- v0.2.11 测试重点行
- 新增 eastmoney_industry provider 覆盖要求

**README.md**:
- 版本 v0.2.11
- 数据源表行业分类改为 ✅ 已实现
- 缓存文件表新增 `industry_{code}.json`
- 模块 6 描述新增概念类型
- **新增缓存覆盖矩阵**（菜单 1/2 对全部缓存类型的覆盖说明）
- TTL 表新增 industry

**changelog.md**:
- [0.2.11] 版本
- Added: 行业/概念数据源、provider、缓存、富化增强、穿透增强
- Changed: 菜单 [1] 缓存清除范围
- Tests: 新增测试文件+用例

---

## 数据流

```
持仓文件 (.xlsx)
    ↓
read_holdings()
    ↓
compute_penetration_top10()   ────→  batch_fetch_industry_data(codes)
    ↓                                         ↓
穿透数据（含穿透资产代码集）          industry_{code}.json 缓存
    ↓                                         ↓
build_news_data()  ─────────────→  fetch_industry_data() / cache hit
    ↓                                         
_build_keyword_lookup(holdings + penetration + industry/concept)
    ↓
_enrich_keywords_for_item() → holding | penetration | concept | industry
    ↓
write_news_sheet() / HTML 模板
```

---

## 文件清单汇总

| 操作 | 文件 | 说明 |
|------|------|------|
| 创建 | `src/providers/eastmoney_industry.py` | 东方财富行业/概念 Provider |
| 创建 | `src/test_eastmoney_industry.py` | Provider 单元测试 |
| 创建 | `docs-stm/technical.md` | 技术文档 |
| 创建 | `docs-stm/plan/2026-06-28-002-industry-concept-data-source-plan.md` | 本实施计划 |
| 修改 | `src/cache.py` | 新增 industry 缓存类型/TTL/前缀映射 |
| 修改 | `src/config.py` | 新增 cache_ttl.industry 默认配置 |
| 修改 | `src/fetcher.py` | 新增行业数据获取路由 |
| 修改 | `src/main.py` | 菜单 [1] 新增 industry 缓存清除 |
| 修改 | `src/report/news_correlation.py` | 新增 concept 类型富化 |
| 修改 | `src/report/penetration.py` | 增强板块分类 API 支持 |
| 修改 | `src/test_news_correlation.py` | 新增 concept 测试 |
| 修改 | `src/test_penetration.py` | 新增 API 行业测试 |
| 修改 | `docs-stm/managements/requirements.md` | 需求同步 |
| 修改 | `docs-stm/managements/testplan.md` | 测试计划同步 |
| 修改 | `docs-stm/README.md` | 用户文档同步 + 缓存覆盖矩阵 |
| 修改 | `docs-stm/managements/changelog.md` | 变更日志 |
| 修改 | `docs-stm/managements/review-findings.md` | 自审记录 |
