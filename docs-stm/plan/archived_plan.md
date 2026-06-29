# 投资分析报告小工具 — 历史迭代记录

> 归档时间：2026-06-28
> 原始文件：`docs-stm/managements/plan.md`
> 归档原因：Iter 1.0~3.7 已完成，保留历史迭代详情供回溯参考，plan.md 已精简为当前架构决策。

---

## Iter 1.1 — 项目骨架 + 配置管理

**Goal**：搭建项目目录结构、依赖锁定、启动脚本、配置读写。

**Files**：
- `src/__init__.py`
- `src/config.py`
- `src/logger.py` — 日志初始化模块
- `requirements.txt`
- `scripts/launch.ps1`
- `scripts/launch.sh`
- `data/cache/`（目录占位）

**Approach**：
- `logger.py`：用标准库 `logging` 初始化，日志文件输出到 `logs/app.log`，控制台同时输出
  - 日志级别：INFO 正常流程、WARNING API切换/数据跳过、ERROR 失败但不崩溃
- 过程文件和临时文件统一存放在 `docs-stm/tmp/` 下
- `config.py` 读写 `data/config/config.json`，保存 holdings_dir（默认 `data/holdings/`）、holdings_filename（默认 `个人投资持仓信息.xlsx`）、output_dir（默认 `reports/`）
- 提供 `get_config()`、`set_config(key, value)` 接口
- 注意：列名映射不在配置范围内——xlsx 列名固定为"名称/代码/持仓份额/每份成本"
- 启动脚本自动创建 `logs/` 和 `docs-stm/tmp/` 目录
- 启动脚本（`launch.ps1` / `launch.sh`）依次执行：
  1. 检查 Python 是否安装，未安装则报错退出
  2. 检查 `.venv` 虚拟环境是否存在，不存在则创建
  3. 激活虚拟环境
  4. `pip install -r requirements.txt`（静默安装）
  5. 检查 `data/holdings/` 和 `data/cache/` 目录，不存在则创建
  6. 启动 `python src/main.py`

**Test scenarios**：
- 默认配置不存在时返回预设默认值
- 写入配置后再次读取，值与写入一致
- 手动修改 JSON 文件后程序能正确读取

---

## Iter 1.2 — 持仓 Excel 读取器 + TUI 菜单框架

**Goal**：解析持仓 xlsx 为结构化数据；TUI 菜单可交互导航。

**Files**：
- `src/main.py` — 入口 + TUI 循环
- `src/models.py` — 持仓数据结构（dataclass）
- `src/reader.py` — xlsx 解析器

**Approach**：
- `models.py`：`Holding` dataclass（account, name, code, shares, cost_price）
- `reader.py`：用 `openpyxl` 读取 xlsx，遍历所有页签，每个页签 = 一个账户，页签名作为 `account` 字段
- 固定 4 列：名称（str）、代码（str）、持仓份额（float）、每份成本（float）
- 自动跳过空行（名称列为空的视为无效行）
- `main.py`：`input()` 循环菜单，检测目录/文件有效性，E/H/B 先输出占位提示

**xlsx 输入格式（固定，不需要列名映射）**：

| 列 | 列名 | 类型 | 说明 |
|---|---|---|---|
| A | 名称 | str | 资产全称 |
| B | 代码 | str | 6 位代码（股票/基金统一长度） |
| C | 持仓份额 | float | 持仓数量，>0 |
| D | 每份成本 | float | 成本单价，>0 |

账户不通过列区分，而是通过**页签名**区分。示例：页签"证券账户"下的所有行 = 证券账户的持仓。

---

## Iter 1.3 — 数据源接入 + 缓存管理

**Goal**：对接金融 API 获取价格/净值；缓存层管理 API 响应生命周期。

**Files**：
- `src/fetcher.py` — 数据获取主入口
- `src/providers/tencent.py` — 腾讯财经 API
- `src/providers/eastmoney.py` — 东方财富 API
- `src/providers/tiantian.py` — 天天基金 API
- `src/providers/sina.py` — 新浪财经 API
- `src/providers/__init__.py`
- `src/cache.py` — 缓存管理

**Approach**：
- **cache.py**：泛用 JSON 缓存，支持 `get(key, max_age_seconds)` / `set(key, data)`，过期返回 None
- **API 路由与备用链路**：

| 用途 | 主链路 | 备用链路 |
|---|---|---|
| 场内行情（实时/收盘） | 腾讯 `qt.gtimg.cn/?q={code}` | 东方财富 `push2.eastmoney.com` |
| 场外基金净值 | 东方财富 `fundf.eastmoney.com` | 天天基金 `fundgz.1234567.com.cn` |
| 基金持仓数据 | 天天基金 `fundf10.eastmoney.com` | — |
| 基金业绩排名 | 天天基金 | — |
| 财经新闻 | 新浪财经 `finance.sina.com.cn` | — |

- **fetcher.py**：根据资产类型路由到对应 provider，先读缓存 → 未命中则调 API → 写入缓存
- 主链路超时或返回异常 → 自动切换备用链路

---

## Iter 1.4 — 汇总模块 + 市值核算 + Excel 输出引擎

**Goal**：实现 Excel 报表核心生成能力（汇总 + 市值核算两个页签）。

**Files**：
- `src/report/excel_writer.py` — Excel 生成引擎
- `src/report/summary.py` — 汇总模块
- `src/report/market_value.py` — 市值核算模块
- `src/report/styles.py` — Excel 样式常量

---

## Iter 1.5 — 打磨验证

**Goal**：错误处理、边界情况打磨，Iter 1 全流程走通。

---

## Iter 2 — 分类汇总 + 资产穿透 TOP10 + 基金业绩分析 ✅ 已完成

**Goal**：补全剩余 3 个 Excel 页签。

**Files**：
- `src/report/category.py` — 分类汇总
- `src/report/penetration.py` — 资产穿透 TOP10
- `src/report/fund_performance.py` — 基金业绩分析

---

## Iter 3.1 — HTML 报告引擎基础

**Goal**：搭建 HTML 报告生成引擎 + Jinja2 模板框架。

**Files**：
- `src/report/html_writer.py` — HTML 生成引擎
- `src/tmpl/report_template.html` — Jinja2 模板文件
- `requirements.txt` — 增加 Jinja2 依赖

---

## Iter 3.2 — 财经新闻关联模块 ✅ 已完成

**Goal**：实现财经新闻关联模块，在 HTML 报告中新增第 6 个模块。

**Files**：
- `src/providers/sina_news.py` — 新浪新闻 API + 关键词关联
- `src/report/news_correlation.py` — 财经新闻关联（Excel + HTML）
- `src/tmpl/report_template.html` — 更新模板，新增新闻模块区域

---

## Iter 3.3 — 模板占位模块 + 打磨

**Goal**：补齐全球政经局势/智囊团深度复盘 的模板占位，缓存管理，文件选择器增强，异常处理增强。

**Files**：
- `src/tmpl/report_template.html` — 更新模板，新增两个占位模块区域
- `src/report/html_writer.py` — 传递 `llm_enabled=False` 标记
- `src/report/penetration.py` — 增加板块分类
- `src/cache.py` — 新增 `cleanup_expired()` / `get_cache_stats()` / `get_cache_dir()`
- `src/reader.py` — 新增 `get_xlsx_info()` 文件信息查询
- `src/main.py` — 新增菜单 [3][4]；文件选择器增强；错误友好提示
- `src/report/excel_writer.py` — `save_workbook` 增加 PermissionError 保护

---

## Iter 3.4 — LLM 智能分析接入 ✅ 已完成

> **注：** 此迭代使用 `data/config/llm.json` 单文件存储 LLM 配置。v0.2.15 已拆分为双文件。

**Goal**：替换模板占位为 LLM 生成内容。

**Files**：
- `src/llm_client.py` —（新建）LLM API 客户端
- `src/config.py` — 新增 `get_llm_config()`
- `src/report/html_writer.py` — `enable_llm` 参数
- `src/tmpl/report_template.html` — 条件渲染 LLM 区域
- `data/config/config.json` — 增加 `llm_config_file` 字段

---

## Iter 3.5 — LLM 全局优化 ✅ 已完成

**Goal**：LLM 调用性能优化、System Prompt 外部可配置、智囊团升级为5位专家、提示词紧凑化。

**Files**：
- `src/llm_client.py` — `generate_all_llm()` 并行批处理、全局 `_HTTP_POOL` 连接池、智囊团 System Prompt
- `src/config.py` — LLM 配置内存缓存
- `src/main.py` — 穿透TOP10统一计算复用

---

## Iter 3.6 — 全面性能优化与代码清理 ✅ 已完成

**Goal**：多维度性能优化（并行化、Token 压缩、缓存增强）、死代码全面清理。

**Files**（修改）：
- `src/main.py` — 菜单 [1]/[2] ThreadPoolExecutor 并行化；`_busy` 防重入
- `src/llm_client.py` — Prompt 压缩、Token 追踪、超时提升
- `src/report/llm_content.py` — 参数精简
- `src/cache.py` — 死代码移除
- `src/config.py` — mtime 缓存 + 配置校验
- `src/providers/news_aggregator.py` — 新闻 15 分钟缓存 + 并行获取
- `src/providers/sina_news.py` — 移除死函数
- `src/providers/tiantian.py` — 移除死函数

---

## Iter 3.7 — 类型与空安全审计 ✅ 已完成

**Goal**：全量代码类型一致性审计 + API JSON null 防御性编程。

**Files**：
- `src/report/html_writer.py` — a_indices/us_indices dict 修复
- `src/report/fund_performance.py` — API null 兜底
- `src/report/summary.py` — dict 类型保留
