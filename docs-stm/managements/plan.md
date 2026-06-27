# 投资分析报告小工具 — 实现计划

创建日期：2026-06-26
类型：feat（新项目构建）

---

## 问题描述

个人投资者需要基于持仓数据和市场行情，生成包含市值核算、资产穿透、基金分析等内容的投资分析报告。当前无现成工具，需从零构建 Python TUI 应用，对接中国金融数据源，输出 Excel 和 HTML 格式报告。

---

## 需求

完整需求详见 [`docs-stm/managements/requirements.md`](requirements.md)。

---

## 关键技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| TUI 框架 | 原生 `input()` 循环 | 零依赖，开发最快，满足菜单需求 |
| Excel 库 | `openpyxl` | 原生支持 .xlsx 读写、颜色/字体格式设置 |
| HTTP 客户端 | `httpx` | 同步/异步、连接复用，比 requests 现代 |
| 数据解析 | 手动解析，不使用 pandas | 减少依赖，数据量小，自定义校验更可控 |
| 配置持久化 | `data/config/config.json` | JSON 简单可靠，无需额外依赖 |
| AI 模块 7、8 | 模板占位文本 | 先跑通基础功能，后续按需接入 LLM |
| 报告模板 | 程序生成（Excel openpyxl / HTML Jinja2） | Excel 和 HTML 报告均程序化生成，在对应迭代阶段设计和讨论 |

---

## 模板策略

报告输出程序化生成，不依赖独立模板文件：
- **Excel 报告**：使用 openpyxl 直接生成页签、样式、公式和数据，详见 `src/report/` 各模块
- **HTML 报告**：使用 Jinja2 模板引擎渲染，模板在 Iter 3 设计

各迭代到达需要模板的模块时，再与你交互讨论具体模板设计。当前阶段不预定义模板内容。

---

## 迭代计划

### Iter 1.1 — 项目骨架 + 配置管理

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

**Verification**：运行 `python -c "from src.config import get_config; print(get_config())"` 看到默认配置

---

### Iter 1.2 — 持仓 Excel 读取器 + TUI 菜单框架

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

**Test scenarios**：
- 给定标准格式 xlsx 解析出正确条数和字段值
- 目录不存在时提示先配置目录
- 目录下有多个 xlsx 时列出文件供选择
- TUI 输入非法选项时提示重新输入
- X 选项正常退出程序
- xlsx 中某行缺字段或数值为负 → 跳过该行并给出提示

**Verification**：运行 `python src/main.py`，菜单正常显示，选 E 看到"该功能尚未实现"提示

---

### Iter 1.3 — 数据源接入 + 缓存管理

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

**Test scenarios**：
- 缓存存在且未过期 → 直接返回缓存数据
- 缓存过期 → 调 API 获取并更新缓存
- 腾讯 API 超时 → 自动切换新浪备用链路
- 股票代码格式处理（sh600000 / 600000 兼容）
- 缓存文件写入失败时优雅降级（静默继续不抛异常）
- API 返回异常数据格式 → 跳过该条并记录日志

**Verification**：`python -c "from src.fetcher import get_price; print(get_price('sh600000'))"` 打出最新价

---

### Iter 1.4 — 汇总模块 + 市值核算 + Excel 输出引擎

**Goal**：实现 Excel 报表核心生成能力（汇总 + 市值核算两个页签）。

**Files**：
- `src/report/excel_writer.py` — Excel 生成引擎
- `src/report/__init__.py`
- `src/report/summary.py` — 汇总模块
- `src/report/market_value.py` — 市值核算模块
- `src/report/styles.py` — Excel 样式常量

**Approach**：
- **excel_writer.py**：使用 openpyxl 直接创建 Workbook，设置页签、列宽、样式和数据
- **styles.py**：RED_FONT（正数红色）、GREEN_FONT（负数绿色）、标题样式、表头样式
- **模板讨论**：进入 Iter 1.4 时与你交互确定 Excel 模板的具体内容和样式需求
- **summary.py**：日期时间 + 指数 + 总市值/成本/盈亏/本日盈亏
- **market_value.py**：15 列明细（账户/名称/代码/最新价/净值日期/昨日价/取价方式/溢价率/份额/市值/成本/盈亏/收益率/本日盈亏/取价渠道）+ 分账户小计 + 总计
  - 场内本日盈亏 = (实时价 - 昨收盘) × 份额；场外非当日更新标 0
  - 盈亏正数红色、负数绿色
- 将 E 和 B 选项接入实际生成逻辑

**Test scenarios**：
- 空的 workbook 能正常生成合法 xlsx
- 汇总页签数字格式正确（保留 2 位小数、千分位）
- 市值核算页签 15 列标题顺序正确
- 分账户小计正确聚合该账户所有持仓
- 盈亏正数红色，负数绿色
- 本日盈亏 = 0 显示 0
- 无持仓数据时不崩溃，输出空表或提示信息

**Verification**：TUI 选 E → 生成 `{output_dir}/个人投资分析报告.xlsx`，打开确认 2 个页签内容正确

---

### Iter 1.5 — 打磨验证

**Goal**：错误处理、边界情况打磨，Iter 1 全流程走通。

**Approach**：
- 空目录/无文件 → 引导用户配置
- 网络异常 → 友好提示"获取数据失败，请检查网络"，不崩溃
- API 返回异常数据 → 跳过该条并日志记录
- 持仓文件格式异常 → 提示具体错误行
- 配置数据防呆校验

**Test scenarios**：
- 删掉 data/holdings 目录后选 E → 提示配置目录
- 断网后选 E → 提示网络异常，用已有缓存数据或显示"--"
- xlsx 某行缺字段 → 跳过并提示
- 报告输出目录无写入权限 → 提示文件写入失败

**Verification**：无网络环境下仍能启动、选 E 不崩溃

---

### Iter 2 — 分类汇总 + 资产穿透 TOP10 + 基金业绩分析 ✅ 已完成

**Goal**：补全剩余 3 个 Excel 页签。

**Files**：
- `src/report/category.py` — 分类汇总
- `src/report/penetration.py` — 资产穿透 TOP10
- `src/report/fund_performance.py` — 基金业绩分析

**Approach**：
- **分类汇总**：按资产属性（股票/债券/基金/现金）分组，再按投资分类（主动/被动/固收等）分组，计算各类小计
- **穿透 TOP10**：每只基金拆解为前 10 持仓，合并相同标的，合并直接持有股票，按市值降序取全仓前 10
- **基金业绩分析**：调天天基金 API 获取同类排名和区间收益，按规则打标签（优秀/良好/稳定/偏差）

**Test scenarios**：
- 分类汇总各分组计数正确
- 穿透：基金 A 持茅台 10% + 基金 B 持茅台 5% + 直接持有茅台 → 合并市值正确
- 基金业绩标签语义检查（不从标签文本中泄露基金类型词）

---

### Iter 3.1 — HTML 报告引擎基础

**Goal**：搭建 HTML 报告生成引擎 + Jinja2 模板框架，将 5 个已有 Excel 模块渲染为 HTML。

**Files**：
- `src/report/html_writer.py` — HTML 生成引擎
- `src/tmpl/report_template.html` — Jinja2 模板文件（迭代开始时与用户讨论样式）
- `requirements.txt` — 增加 Jinja2 依赖

**Approach**：
- `html_writer.py`：用 Jinja2 渲染 HTML 模板，从现有模块（汇总/市值核算/分类汇总/穿透TOP10/基金业绩）提取数据
- HTML 模板基于 Jinja2，模板文件 `src/tmpl/report_template.html`，在迭代开始时与用户讨论样式
- 使用与 Excel 报告相同的数据结构（DetailRow / holdings / details），复用现有计算逻辑
- 报告输出路径通过 `output_dir` 配置（默认 `reports/`），支持菜单 R 配置
- `main.py` 的 H 和 B 选项接入真实 HTML 生成

**Test scenarios**：
- HTML 在浏览器中正常渲染，中文字符不乱码
- 5 个模块内容与 Excel 页签一致
- 报告标题、表格、数字格式正确
- H 和 B 选项正确触发 HTML 生成

**Verification**：TUI 选 H → 生成 `{output_dir}/个人投资分析报告.html`，浏览器打开确认内容完整

---

### Iter 3.2 — 财经新闻关联模块 ✅ 已完成

**Goal**：实现财经新闻关联模块，在 HTML 报告中新增第 6 个模块，同时支持 Excel 增补页签。

**Files**：
- `src/providers/sina_news.py` — 新浪新闻 API + 关键词关联
- `src/report/news_correlation.py` — 财经新闻关联（Excel + HTML）
- `src/tmpl/report_template.html` — 更新模板，新增新闻模块区域

**Approach**：
- 调用新浪财经 API 获取 TOP 新闻（`feed.mix.sina.com.cn`），支持多个分类
- 新闻标题 + 简介与持仓名称做关键词匹配，按匹配数降序排列
- **财经新闻**：通过菜单 N/B/L 触发
- 输出 TOP N 条关联新闻（N 通过 `news_top_count` 配置，默认 100），标注匹配到的关键词（默认缓存 1 天）
- HTML 报告新增"财经新闻热点与持仓关联分析"模块（模块 6）
- Excel 通过菜单 N 生成增补页签（模块 6）
- 默认缓存 1 天

**Test scenarios**：
- API 返回正常 → 正确解析新闻列表
- 有关联的持仓名称 → 标题正确匹配
- 无关联匹配 → 显示提示信息
- API 不可用 → 显示"获取新闻失败"提示，不崩溃

**Verification**：TUI 选 N → Excel 含新闻页签；选 H/B/L → HTML 含新闻模块

---

### Iter 3.3 — 模板占位模块 + 打磨

**Goal**：补齐模块 7/8 的模板占位，全流程打磨。

**Files**：
- `src/report/templates/__init__.py`
- `src/report/templates/global_macro.py` — 全球政经（模板占位）
- `src/report/templates/expert_review.py` — 智囊团复盘（模板占位）
- `src/tmpl/report_template.html` — 更新模板，新增两个占位模块区域
- `src/report/html_writer.py` — 集成所有 8 个模块

**Approach**：
- 模块 7（全球政经局势）：输出固定占位文本，预留 LLM 接口
- 模块 8（智囊团深度复盘）：输出固定占位文本，预留 LLM 接口
- 占位文本格式：显示"本节内容待生成"提示 + 模块接口说明
- 错误处理增强：网络异常、模板渲染失败、数据缺失等场景

**Test scenarios**：
- 模板占位模块显示"本节内容待生成"提示
- 全 6+2 模块 HTML 页面渲染正常（6 个现行模块 + 2 个占位）
- 网络异常时友好提示

**Verification**：TUI 选 H/B/L → HTML 报告包含 6 个现行模块 + 2 个占位模块

---

### Iter 3.4 — LLM 智能分析接入

**Goal**：替换模板占位为 LLM 生成内容，实现智能持仓分析。

**Files**：
- `src/report/templates/__init__.py`
- `src/report/templates/global_macro.py` — 全球政经（LLM 生成）
- `src/report/templates/expert_review.py` — 智囊团复盘（LLM 生成）
- `src/report/templates/llm_client.py` — LLM API 客户端
- `.env` 或 `data/config/` — API Key 管理

**Approach**：
- 接入 LLM API（如 Claude API / OpenAI API），生成模块 7 和 8 内容
- 模块 7（全球政经局势）：基于当前市场数据、指数表现、持仓结构，LLM 撰写宏观分析
- 模块 8（智囊团深度复盘）：基于持仓明细和盈亏数据，LLM 生成优化建议和风险预警
- API Key 通过环境变量或配置文件管理，不在代码中硬编码
- 费用控制：LLM 调用结果缓存，按日更新
- API Key 未配置时优雅降级，继续输出占位文本

**风险**：

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| API Key 未配置 | LLM 模块不可用 | 降级输出占位文本，提示用户配置 |
| LLM API 超时 | 报告生成延迟 | 设置超时兜底，失败时继续输出占位文本 |
| Token 费用超预期 | 成本增加 | 缓存 LLM 结果；限制输入上下文大小 |

**Test scenarios**：
- API Key 已配置 → LLM 生成内容正常
- API Key 未配置 → 降级输出占位文本
- LLM 输出格式异常 → 解析兜底，不中断报告生成
- 多次调用间缓存生效，不重复扣费

**Verification**：TUI 选 H/B/L → HTML 报告中全球政经和智囊团复盘由 LLM 生成真实内容（API Key 已配时）

---

## 系统影响

- `data/holdings/`、`data/cache/`、`data/config/` 在首次运行时需保证存在
- `data/config/config.json` 在程序生命周期外持久保存，含 `output_dir` 字段控制报告输出位置
- 程序依赖外部中国金融 API，网络不可用时会降级运行（使用缓存数据或显示"--"）
- 持仓库多 xlsx 文件时，用户通过 TUI 选择

---

## 风险

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 腾讯/东方财富 API 变更或封禁 | 行情获取失败 | 备用链路自动切换；缓存支撑当日使用 |
| 持仓 xlsx 格式与预期不一致 | 解析失败或数据错误 | 固定列名解析 + 字段校验 + 友好提示 |
| 基金穿透计算量大 | 报告生成变慢 | 穿透结果缓存每日更新 |
| LLM API Key 未配置 / 超时 | 模块 7/8 不可用 | 降级输出占位文本，不阻塞报告生成 |
| LLM Token 费用超预期 | 成本增加 | 缓存 LLM 结果；限制输入上下文；每日最多 2 次调用 |

---

## 验证

每次迭代完成后：
1. 运行 `python src/main.py`，确认 TUI 正常导航
2. 选择对应功能生成报告文件
3. 打开输出目录（默认 `reports/`，可通过菜单 R 配置）下的 `个人投资分析报告.xlsx` 或 `个人投资分析报告.html` 确认内容完整
4. 模拟异常场景（断网、空目录、格式错误）确认程序不崩溃
