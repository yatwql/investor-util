# 辅助脚本参考

> 项目 `scripts/` 目录下的所有工具脚本用法速查。

---

## 一览

| 脚本 | 分类 | 一句话 |
|:-----|:-----|:-------|
| `test_runner.py` | 测试 | pytest 标记模式封装驱动，支持 15+ 种 `--mode` |
| `extract-test-failures.py` | 测试 | 从 pytest-html 报告提取失败用例详情 |
| `check-test-markers.py` | 测试 | AST 静态扫描验证测试标记合规性 |
| `llm_hallucination_sampler.py` | 测试 | 10 组标准持仓 × LLM 幻觉率采样 |
| `calibrate-dedup-threshold.py` | 测试 | 新闻去重阈值校准分析 |
| `check-version-consistency.py` | 质量 | 版本号全局一致性检查（发布前必跑） |
| `perf_report.py` | 诊断 | 端到端报告生成管线性能基准（独立脚本，mock 外部数据源） |
| `perf_view.py` | 诊断 | 性能历史趋势查看（读取 perf_history.jsonl → 跨版本耗时对比） |
| `diagnose_gemini_proxy.py` | 诊断 | Gemini API 代理连通性诊断 |
| `launch.sh` / `launch.ps1` | 启动 | Linux/macOS / Windows 一键启动脚本 |
| `check-sources` | 诊断 | cli.py 子命令：数据源联通性检测 |

---

## 测试类

### `test_runner.py` — 测试模式驱动

pytest 的 `-m` 标记表达式封装层，按 `--mode` 选择预定义组合。

```bash
# 查看所有可用 mode
python scripts/test_runner.py --help

# 日常提交前门禁（P0）
python scripts/test_runner.py --mode dev-verify

# 合入门禁（P1）
python scripts/test_runner.py --mode verify

# 发布门禁（P2）
python scripts/test_runner.py --mode verify,regression

# 常用快捷模式
python scripts/test_runner.py --mode unit         # 全量单元测试
python scripts/test_runner.py --mode scenario     # 业务场景测试
python scripts/test_runner.py --mode edge         # 边缘/异常场景
python scripts/test_runner.py --mode smoke        # 冒烟测试（~2s）
python scripts/test_runner.py --mode data         # 数据正确性验证

# 多模式组合
python scripts/test_runner.py --mode scenario,edge

# 带行覆盖率
python scripts/test_runner.py --mode unit --coverage
```

> **`test_runner.py` 不支持 `--` 透传**（如 `-- --lf`）。如需 `--lf` 绕过它直接调 pytest，用 `-m` 复现目标模式的标记表达式。各 `--mode` 对应的 `-m` 表达式见下文"标记表达式对照"或直接查看 `MODES` 字典。

#### `--mode` 与 pytest `-m` 对照

| `--mode` | 等效 `-m` 表达式 | 典型耗时 |
|:---------|:-----------------|:--------:|
| `regression` | `scenario` | ~6min |
| `smoke` | `smoke` | ~2s |
| `unit` | `unit` | ~30s |
| `standard` | `unit -edge -data` | ~30s |
| `edge` | `edge` | ~15s |
| `data` | `data` | ~10s |
| `scenario` | `scenario` | ~6min |
| `integration` | `integration` | ~50s |
| `verify` | `unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis` | ~1min |
| `dev-verify` | `(unit_core or unit_providers or unit_fetcher or unit_analysis) and not (edge or data) or (scenario_basic)` | ~1min |
| `all` | （无过滤，全量） | ~10min |
| `all_no_unit` | `not unit` | ~7min |
| `report` | `unit_report` | ~15s |
| `scenario_extreme` | `scenario_extreme` | ~1min 45s |

---

### `extract-test-failures.py` — 失败用例提取

运行 `test_runner.py --mode verify,regression` 等全量测试后，直接从 HTML 报告中提取失败/错误用例信息。

```bash
# 自动查找 test-reports/latest/ 下最新报告
python scripts/extract-test-failures.py

# 指定报告路径
python scripts/extract-test-failures.py test-reports/latest/all/report.html

# 仅输出汇总统计（不打印日志）
python scripts/extract-test-failures.py --summary

# 输出 JSON 格式（便于管道处理）
python scripts/extract-test-failures.py --json
```

**典型工作流**：

```bash
python scripts/test_runner.py --mode verify,regression     # ① 跑全量验证
python scripts/extract-test-failures.py --summary           # ② 看哪些失败
python scripts/extract-test-failures.py                     # ③ 看详细错误
# 修复代码后只重跑失败用例：
python -m pytest <test_file>::<test_name> -v --tb=short     # ④ 单用例验证
python scripts/test_runner.py --mode verify,regression     # ⑤ 发布确认
```

---

### `check-test-markers.py` — 标记合规性检查

AST 静态扫描所有 `test_*.py` 文件，检查：
- 标记完整性（是否有 `unit_*` 子标记）
- 拼写错误（未注册的 marker 名）
- `_edge.py` 是否漏标 `edge`，或非 `_edge.py` 文件是否误标 `edge`

```bash
python scripts/check-test-markers.py
```

无报错输出即合规。新增/修改测试文件后必须运行此脚本。

---

### `llm_hallucination_sampler.py` — LLM 幻觉率采样

对 **10 组标准化持仓数据** 调用当前 prompt，经事实校验器验证后统计幻觉率（P4‑08 幻觉率采样测试）。

```bash
# 完整采样（调用 LLM API 对 10 组数据生成分析）
python scripts/llm_hallucination_sampler.py

# 仅测试特定模块（默认 expert_review）
python scripts/llm_hallucination_sampler.py --module health_check

# 仅测试特定数据集（1-indexed）
python scripts/llm_hallucination_sampler.py --dataset 1,3,5

# 跳过 API 调用，只构建 prompt 验证结构
python scripts/llm_hallucination_sampler.py --dry-run

# 跳过缓存强制重新生成
python scripts/llm_hallucination_sampler.py --force
```

**输出**：
- 报告文件：`docs-stm/tmp/hallucination-report.md`
- Dry-run prompt 转储：`docs-stm/tmp/hallucination-prompts-{module}.md`

---

### `calibrate-dedup-threshold.py` — 新闻去重阈值校准

新闻标题去重（同源/跨源两档阈值 + 中文 bigram）在每次报告运行时自动记录"边界案例"到 `data/cache/dedup_anchors.jsonl`。积累足够锚点后，用此脚本分析当前阈值是否合理。

```bash
# 分析全部锚点，输出建议
python scripts/calibrate-dedup-threshold.py

# 仅看汇总统计（不展开详细列表）
python scripts/calibrate-dedup-threshold.py --summary

# 指定锚点文件
python scripts/calibrate-dedup-threshold.py --file data/cache/dedup_anchors.jsonl
```

**校准时机**：建议锚点文件积累 **100 条以上**（约 5~10 次报告运行）后校准一次。脚本只分析不自动修改阈值，是否需要调整由开发者判断。

**输出示例**：

```
=== cross_skip（跨源 ≥0.30 但 bigram<3 被跳过 — 潜在漏判）===
  数量: 12
  ratio 范围: 0.300 ~ 0.450
  bigram 范围: 0 ~ 2

=== 校准建议 ===
[!] cross_threshold=0.30: 5 条 ratio≥0.35 被跳过
    建议审查这些案例是否应为重复
[OK] 跨源 bigram=3: 无边界样本
```

---

## 质量类

### `check-version-consistency.py` — 版本号一致性检查

发布版本前必须运行。检查 `APP_VERSION`（`src/python/constants.py`）与以下文件的版本号是否一致：

- `README.md`
- `pyproject.toml`
- `docs-stm/managements/plan.md`
- `docs-stm/managements/technical.md`
- `docs-stm/managements/requirements.md`
- `docs-stm/managements/testplan.md`
- `docs-stm/managements/changelog.md`
- `docs-stm/manuals/how-to-test-my-code.md`

```bash
# 无参数运行，逐项检查并报 [OK]/[ERR]
python scripts/check-version-consistency.py
```

全部 `[OK]` 方可提交。如有 `[ERR]`，按提示逐个同步，然后重跑直到全部通过。

**版本切换工作流**：

```bash
# ① 发布版本：修改 APP_VERSION → 运行检查 → 同步全部 → 提交 → git tag
# ② 开发版本：修改 APP_VERSION 为 next-version-dev → 运行检查 → 全部 [OK] → 提交
```

---

## 诊断类

### `perf_report.py` — 端到端性能基准

生成 20+ 品种 + 3 年模拟持仓，运行 basic/both 报告生成管线，测量各阶段耗时。

```bash
python scripts/perf_report.py
```

**输出**：`docs-stm/tmp/better-investment-performance-test-report.md`

**目标**：basic 模式总耗时 < 60s

---

### `perf_view.py` — 性能历史趋势查看

读取 `data/state/perf_history.jsonl`（由 `PerfCollector` 在每次报告生成时自动追加），按版本和报告类型分组统计，输出版本间性能趋势对比。

```bash
# 输出全部历史趋势到 stdout
python scripts/perf_view.py

# 仅看 full 类型报告的性能趋势
python scripts/perf_view.py --report-type full

# 仅看最近 30 条记录
python scripts/perf_view.py --last 30

# 同时写入 docs-stm/tmp/perf_trend.md
python scripts/perf_view.py --save
```

**输出列说明**：

| 列 | 含义 |
|:---|:------|
| 阶段 | 报告生成管线阶段名称（行情获取/快照对比/历史走势/HTML 生成/Excel 生成 等） |
| 平均耗时 | 该阶段历史平均耗时 |
| 最短/最长 | 该阶段历史最小/最大耗时 |
| 次数 | 该阶段出现次数（条件阶段如历史走势仅在启用时出现） |

**数据来源**：每次 `generate_report()` 调用时自动记录到 `data/state/perf_history.jsonl`，无需手动触发。

---

### `diagnose_gemini_proxy.py` — Gemini API 代理诊断

当 Gemini API 代理（如 `http://10.22.207.29:10037`）出现连通性问题时，逐项检测网络层、代理层和 API 层的健康状况。

```bash
python scripts/diagnose_gemini_proxy.py
```

**检测项目**：
1. 直接 Google 连通性（`google.com`）
2. 代理服务器连通性（`telnet` 式探测）
3. 代理 HTTP 请求（`curl -x` 等效）
4. Gemini API 真实调用（使用当前 `llm_key.json` 配置）
5. DNS 解析
6. 各环境变量（`HTTP_PROXY` / `HTTPS_PROXY` / `http_proxy` / `https_proxy`）

每项显示 ✅/❌ 状态和详细错误信息，定位哪一层出了问题。

---

## 启动脚本

### `launch.sh` — Linux/macOS 启动

```bash
./scripts/launch.sh
```

### `launch.ps1` — Windows PowerShell 启动

```powershell
.\scripts\launch.ps1
```

两者均负责：激活虚拟环境（如存在）、设置 `PYTHONPATH`、启动主程序 TUI。

---

## CLI 模式

### `--check-sources` — 数据源健康检查

跳过 TUI 交互界面，直接测试各数据源联通性并报告延迟。

```bash
# 运行数据源健康检查
python -m src.python.cli check-sources
```

**输出示例**：

```
数据源健康检查结果 (2026-07-26)
──────────────────────────────────────────────────────────
  ✅  腾讯财经      行情           45ms  正常
  ✅  新浪财经      行情           82ms  正常
  ⚠️  天天基金      持仓/排名     2.3s  响应慢
  ❌  akshare       资金           timeout  连接超时
```

**检查覆盖范围**：腾讯财经行情、新浪财经行情、东方财富净值、天天基金持仓/排名、东方财富行业分类、新浪财经新闻、东方财富新闻、华尔街见闻、财联社、腾讯 K 线——共 **10 个端点**。

**退出码**：0=全部正常，1=有告警（部分源慢），2=有失败。
