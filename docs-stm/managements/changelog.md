# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.7]**（2026-09-27）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.8-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

---

### 缺陷修复：传输级失败不再被吞成「返回空」（rf-461）

**现象**（用户贴日志报「备用也不好用」）：`launch` 生成的报告里持仓基本面章区块② 数据不可用；日志显示 `[datasink] 请求失败 /documents/48002/sections: _ssl.c:1012: The handshake operation timed out`，紧接着链路却记 `datasink 返回空，尝试下一链路` → `全链路失败（无过期缓存可用）`。

**根因**：`providers/datasink.py::_request` 把**传输级异常**（TLS 握手超时/断连）与**代码级空结果**一律 `return None`，而链路的传输级判据**只认异常**（`chain._try_provider_fetch`）——后果：同源重试不触发、熔断与可用性统计不计（主源持续不可用也不会被熔断，每篇白等 20s 超时）、诊断文案把 SSL 超时报成「返回空」。且 datasink 连**连接级重试**都没有（cninfo/tencent/eastmoney_industry 均有），一次握手被丢即整篇丢失——而 cninfo 的注释已实测「首个连接常被丢弃，重试即成功」。`hithink._request`、`_utils.run_with_timeout`（akshare 路径）同源。

**变更**：
- `datasink._request` / `hithink._request`：新增 `_get_with_transient_retry`（每次尝试前取限速许可 + `core/retry` 统一原语的连接级重试：3 次、线性 1s/2s），**重试耗尽后上抛**；代码级结果（401/403/404/非 200/非 JSON/业务 code≠0）仍返回 None 不计熔断
- 直连调用点护栏（不因上抛中断报告）：`financial_report._fetch_index` → 转巨潮备源；`_fetch_sections` → 返回 None 回退偏好名直取；`financial_indicator.fetch_indicator_series` / `fetch_hithink_indicator_series` → 转下一兜底
- `_utils.run_with_timeout` 新增 `raise_on_failure`（默认 False 维持既有 None 契约；链路消费方 `akshare_financial` 开启上抛）
- 文档：`technical.md` §2.2.1 新增「传输级失败必须上抛给链路」契约 + datasink 降级段落修正；`datasource-reliability.md` datasink/hithink 降级与重试条目重写；`requirements.md` R-DATA-07 补「两类失败分界」

**回归**：+9 例（datasink/hithink：重试耗尽上抛并断言尝试次数与退避序列、首次握手失败重试即成功、非瞬时异常不重试；`run_with_timeout` 两种模式；`akshare_financial` 上抛且断言 `raise_on_failure=True`；编排层三处护栏）。**效果**：主线持续不可用时现在会被熔断（不再每篇白等 20s×3 超时 + 刷屏），且报告失败清单/日志如实给出「连接超时」。

> **已评估未改（登记待办）**：`providers/cninfo.py` 重试耗尽后仍返回 None（同为「传输级降级成返回值」），但其直连调用点有多处，改动面更大，本轮仅取「已有连接级重试」的可靠性收益，专项处理时一并加护栏。

### 文档核对：传输级失败语义的四处口径同步（rf-461 配套）

**背景**（用户要求核对管理文档与用户文档）：rf-461 改变了「传输级失败如何呈现」的可观测行为，逐份比对后发现 **5 处文档仍描述旧口径**或缺失新能力说明：

**变更**：
- `manuals/faq.md`：「数据源 API 失效或数据获取失败怎么办」补同源重试/熔断口径；新增问答「日志里出现『连接失败 …，1.0s 后重试』『连续失败，本会话后续请求跳过』是什么意思」——解释两类保护机制 + 四步排查（直连验证域名/设代理/换网络/查日志），这是用户侧**新出现的日志**，必须能自查
- `manuals/datasource.md`：DataSinking 新增「重试与失败分类」条目（3 次线性退避 + 两类失败分界）；同花顺限流条目补连接级重试；链路总述段补「降级前先同源重试」与熔断只计传输级
- `managements/testplan.md`：R-DATA-07 载体补 6 份测试文件（datasink/hithink/akshare_financial/financial_report/financial_indicator ×2）
- `managements/folders.md`：目录树 `datasink.py`/`hithink.py`/`_utils.py` 与 `test_datasink.py`/`test_hithink.py` 注释补连接级重试与上抛契约
- `managements/test-coverage.md`：`unit_providers`/`unit_fetcher` 描述补新增覆盖口径

**核对无偏差项**：`technical.md` §2.2.1 与 datasink 段落、`requirements.md` R-DATA-07、`datasource-reliability.md` datasink/hithink 条目已于 rf-461 修复同批改完；版本一致性 13/13；归档索引与分区纪律齐备。

### 缺陷修复：挂起型失败不再重试（避免把等待放大 3 倍，rf-462）

**现象**（用户报「现在运行测试，怎么那么久了」）：套件本机耗时不升（单元 101s、`verify,regression` 31.3s，与改动前 30.5s 持平），但**取数失败路径**变慢——挂起型连接（主机不可达/连接被丢）也被重试 3 次：单请求 3 × 20s + 3s 退避 ≈ 63s（链路再同源重试 1 次 ≈ 83s）；用不可路由地址实测复现：2s 预算 → 6.0s / 3 次尝试。巨潮（cninfo）更早就有 3 次盲重试（63s/请求，既有问题）。

**根因**：连接级重试（rf-461 引入）只按「是否瞬时异常」判据重试，未区分**快速失败**（连接被拒/重置 → 重试有效）与**挂起**（等到超时 → 重试只会线性放大等待）。

**变更**：
- `providers/_utils.py` 新增共享判据 `build_transient_retry_judge(elapsed, timeout)`（`HANG_ELAPSED_RATIO = 0.5`）：瞬时异常**且**本次尝试耗时 < 超时预算一半 → 可重试；否则判「主机不可达」不重试，并记 WARNING「连接挂起 Ns（≥超时预算一半），判定主机不可达，不再重试」
- `datasink` / `hithink` / `cninfo` 三处连接级重试改用该判据（判据单源，三者口径一致）
- 回归 +3 例（假时钟模拟挂起耗时：断言仅 1 次尝试、**无退避等待**（`sleep` 被换成 `pytest.fail`）、留下「连接挂起」日志）

**效果**：挂起型失败单请求从 63s 降到 20s（一次超时），且现在**计入熔断** → 连续 3 次后本会话跳过，整轮报告不再逐篇白等；“首个连接被丢、重试即成功”的偶发抖动仍照旧重试。

### CI 加固：安装依赖步加重试与超时（rf-463）

**现象**：`test (3.12)` job 在「安装依赖」步失败（测试步未执行），同 run 内 3.11/3.13 安装成功，且上一提交同样装在 3.12 上全绿——本次未改任何依赖声明。

**根因面**：安装步需从源码构建 akshare 的 Linux 依赖（`py-mini-racer`（编 V8）与 `jsonpath` 均只有 sdist），是全流水线最脆弱的一环，下载/编译抖动即整 job 失败；GitHub 日志端点需授权，免授权只能拿到「exit code 1」，定位受限。

**变更**：`.github/workflows/ci.yml` 四个 job 的安装步统一加 `--retries 5 --timeout 60`（pip 自升级同步），降低网络/下载抖动导致的假失败。

**备注**：本轮 GitHub API 触发未授权限流，重跑结果待确认；若再现则评估 wheels 缓存或重依赖可选化。

### 缺陷修复：LLM 关闭时「LLM API 用量」章不再渲染（rf-464）

**现象**（用户报「章节数由 17 降至 12 章；llm api 用量还没有序号了，又摆在最前面」）：用 `scripts/cli.sh` 无参数跑报告，章节数降至 12 章；且「LLM API 用量」章标题序号为空、被排到所有章节之前。

**根因**：`src/static/tmpl/report_template.html` 的 `sec-llm_usage` 容器**漏加可见性守卫**（其余 4 个 LLM 章由 `section_visible("global_macro")` 统一包住）。`both`/`basic`（LLM 关闭）下该章照样输出，但它不在 `_compute_section_visibility` 的 `visible_numbers` 中 → `section_numbers['llm_usage']` 为 Undefined，标题渲染成「、LLM API 用量」；容器 `.container{display:flex}` 靠 `style="order:N"` 排序，空值输出为非法的 `order: ;` 被 CSS 忽略 → `order` 回退 0 → 排到所有 `order:1..N` 之前。L 模式下该章有数据（编号 17、末位），故长期未暴露。

**变更**：
- `src/static/tmpl/report_template.html`：`sec-llm_usage` 补 `{% if section_visible("llm_usage") %} … {% endif %}` 守卫，LLM 关闭时整章不渲染（与其余 LLM 章口径一致）
- 回归 +2 例（不可见时不渲染且无 `order: ;`；可见时渲染且 `order` 为末位序号），`test_all_invisible` 改写为「只渲染 4 个 always 章容器」的结构断言
- `managements/folders.md` 统计表行数同步

**说明**：17→12 章本身**非渲染缺陷**——CLI 包装脚本 `cli.sh`/`cli.ps1` 无参数默认 `report --type both`（Excel+HTML、不含 LLM）为既定行为，本次未改；需要全部章节（L 模式）请用 `report --type full` 或 `scripts/llm.sh`。

### 测试修复：风格因子场景 fixture 不再写死绝对日期（rf-465）

**现象**：`dev-verify` 出现 1 个既有失败 `test_pipeline_style_factor_regression.py::TestComputeFactorExposureData::test_contract_available_with_full_data`（`available=False`，日志「因子 价值/成长/质量已停更（末根 K 线距今 87 个交易日）」）。

**根因**：**非网络/数据源问题**——该用例 mock 了全部外网（`fetch_index_history` 走合成 K 线 + `offline_external_sources` 离线桩）。真因是 fixture 的时间炸弹：`_klines()` 默认 `start="2026-03-01"`（末根 K 线 2026-05-29），而停更判定用真实 `datetime.now()`（2026-09-29），阈值 86 交易日；离线桩将交易日历置空 → `count_trading_days_elapsed` 回退「仅排周末」近似计数 = 87 > 86 → 三因子全被判停更剔除。真实交易日历口径为 85，仅差 1 个交易日，即该用例本就随时间必然变红。

**变更**：
- `_klines` 改为 `end: date | None = None`，默认以「今天」为末根（`last = end or date.today()`，向前推 `n-1` 天），合成 K 线始终新鲜
- 回归 +1 例 `TestMockKlinesFreshness::test_klines_anchored_to_today_and_not_stale`（断言末根日期 == 今天且距今天数 ≤ 停更阈值）
- 数据快照同步：`managements/folders.md`（测试代码行数 + 用例数 7,938→7,941）、`managements/test-coverage.md`（`scenario_basic` 152→153、报告生成/`unit_report` 1,983→1,985）

---

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.7（2026-09-15 ~ 2026-09-27）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
