# 语言移植分析：Python → Rust / Java

> **状态**：需求探讨，非立项计划  
> **日期**：2026-07-19  
> **基线版本**：v0.7.2（约 79,000 行 Python）

---

## 1. 项目规模概览

| 维度 | 数值 |
|------|------|
| 生产代码文件数 | 74 个 `.py` |
| 生产代码行数 | ~48,900 行 |
| 测试文件数 | 74 个 `test_*.py` |
| 测试代码行数 | ~30,400 行 |
| 脚本 | 6 个 (5 py + 1 sh) |
| 外部 Python 依赖 | 6 个生产依赖 + 4 个测试依赖 |
| 外部 API/数据源 | 3 个 LLM 提供商 + 8+ 个金融数据源 |
| 生成报告格式 | Excel (.xlsx) + HTML |
| 缓存层 | 文件 JSON 缓存，按前缀 TTL |
| 目标平台 | Windows + Linux |

---

## 2. 核心风险——通用

以下风险不因语言选择而消失，两个方案均需面对：

### 2.1 akshare 替代 —— ⚠️ 最大单项风险

`akshare` 是当前项目最重的依赖，提供了：
- 行业分类数据
- 资金流向（sector fund flow）
- 分红历史
- 盈利预测（分析师评级、EPS 预测）
- 财新网 / CCTV 新闻

**现状**：akshare 是纯 Python 库，无 Rust/Java 官方替代。包装了大量中国金融数据网站的 HTTP 爬取 + HTML 解析。

**应对选项**：
| 方案 | 工作量 |
|------|--------|
| 子进程调用原 Python akshare | 低，但引入混合运行时依赖 |
| 逐接口用 HTTP 客户端重写 | 高（需逆向每个接口） |
| 寻找 Java/Rust 生态替代库 | 中—高（生态不成熟） |

**结论**：无论 Rust 还是 Java，akshare 都是最棘手的移植障碍。如果需要保留全功能，**混合运行时方案**（主程序 Rust/Java + 子进程调用 Python akshare）是最现实的选择——但代价是失去"单二进制"的优势。

### 2.2 测试体系 —— 全部重写

当前 74 个测试文件 / ~30,400 行 pytest 代码——完全无法复用。
- Rust：`cargo test` + rstest 生态
- Java：JUnit 5 + Mockito + Testcontainers

测试覆盖了复杂的领域逻辑（穿透计算、风格分析、持仓模拟、新闻去重），重写的工作量不可忽视。

### 2.3 CI/CD 流水线

当前 GitHub Actions 流水线（3 种模式门禁）需完全重建。
- Rust：`cargo build/test/clippy/fmt` 流水线，跨平台 target 矩阵
- Java：Maven/Gradle + JUnit 流水线，JDK 矩阵

### 2.4 文档体系

30+ 文档文件（中文 Markdown）——无需移植，可保留。

---

## 3. Rust 方案分析

### 3.1 依赖映射

| Python 依赖 | Rust 替代 | 成熟度 | 风险 |
|-------------|----------|--------|------|
| openpyxl (读写 Excel) | `calamine` (读) + `rust_xlsxwriter` (写) | ⭐⭐⭐⭐ | 写到功能接近；读侧重性能，对复杂样式支持弱于 openpyxl |
| httpx (HTTP) | `reqwest` | ⭐⭐⭐⭐⭐ | 功能更强（原生异步，HTTP/2，TLS），rustls 可静态链接 |
| jinja2 (HTML 模板) | `minijinja` 或 `tera` | ⭐⭐⭐⭐ | minijinja 语法与 Jinja2 几乎一致，迁移成本低 |
| akshare | 子进程 / 逐接口重写 | ⭐⭐ | 见 2.1 |
| lxml (HTML 解析) | `scraper` + `select.rs` | ⭐⭐⭐⭐ | 功能足够，API 风格不同 |
| colorama | `colored` 或 `termion` / `ratatui` | ⭐⭐⭐⭐⭐ | 简单包装，无风险 |
| 标准库 (json, os, re 等) | `serde_json` + 标准库 | ⭐⭐⭐⭐⭐ | serde 是 Rust 生态标杆 |

### 3.2 关键模块移植评估

| 模块 | 行数 | 移植难度 | 说明 |
|------|------|----------|------|
| **cache/** | ~852 | 🟢 低 | JSON 文件缓存 → `serde_json` + 文件锁，逻辑简单直接 |
| **code_utils.py** | 520 | 🟢 低 | 正则 + 枚举匹配，Rust `regex` 性能更好 |
| **reader.py** | 191 | 🟢 低 | calamine 读取 xlsx，col_idx 映射 |
| **registry.py** | 476 | 🟢 低 | 静态数据定义 → Rust `const` / `lazy_static` / `enum` |
| **provider_registry.py** | 602 | 🟡 中 | 单例 + 熔断 + 会话缓存 → `Arc<RwLock<HashMap>>`，需注意生命周期 |
| **fetcher/chain.py** | 470 | 🟡 中 | Provider Chain 模式 → trait + `Vec<Box<dyn Provider>>`，fallback 逻辑 |
| **providers/ (10 个)** | ~3,449 | 🟡 中 | 每个 API 接口需重写 HTTP 请求 + 响应解析，serde 反序列化 |
| **llm/ (15 个文件)** | ~2,903 | 🟡🔴 中—高 | 多 provider 路由、重试退避、token 计价、流式思考——逻辑复杂但无依赖障碍 |
| **report/excel_generator/** | ~2,400 | 🟡🔴 中—高 | `rust_xlsxwriter` API 与 openpyxl 差异明显，需要设计适配层 |
| **report/penetration.py** | 809 | 🟡 中 | 纯算法（递归穿透），无依赖，直接移植 |
| **report/portfolio_history.py** | 490 | 🟡 中 | 模拟回算算法，无依赖 |
| **report/fund_style_analysis.py** | 652 | 🟡 中 | 风格分析算法，无依赖 |
| **report/html_writer.py** + **html_renderers.py** | ~1,130 | 🟡 中 | 渲染逻辑 + minijinja 模板，renderer 函数需逐移植 |
| **report/orchestrator.py** | 778 | 🟡🔴 中—高 | 编排逻辑复杂，含多线程并发控制 |
| **tui/** | ~629 | 🟡 中 | ratatui 框架成熟，需要重新设计 UI 组件 |

### 3.3 Rust 方案优势

1. **单二进制分发** —— 编译为静态链接的可执行文件，用户无需安装运行时
   - Windows: `.exe` 约 5–15 MB
   - Linux: ELF 约 5–10 MB
   - macOS: 同理
2. **零成本抽象** —— 运行时性能接近 C，但对本应用 CLI 场景提升有限
3. **内存安全** —— 编译期消除内存泄露、数据竞争等整类 bug
4. **跨平台条件编译** —— `#[cfg(target_os = "...")]` 精确控制平台差异代码
5. **异步一等公民** —— `tokio` / `async-std` 生态成熟，适合多 API 并发请求
6. **错误处理纪律** —— `Result<T, E>` 强制处理错误路径，可从根本上降低"配置缺失/网络超时 → 无声崩溃"的风险
7. **测试生态** —— `cargo test` + rstest 属性宏，测试体验接近 pytest

### 3.4 Rust 方案劣势

1. **学习曲线陡峭** —— 所有权/借用/生命周期需要大量心智投入，团队若没有 Rust 经验，初期效率低 3–5×
2. **编译速度慢** —— 全量编译 5–15 分钟，增量 30s–3min，影响开发迭代
3. **TUI 框架差异大** —— 当前 Python 实现用简单的 getch + print，Rust 的 ratatui 是完全不同的即时模式渲染（immediate mode），UI 代码需全部重写
4. **动态能力缺失** —— Python 的运行时自省（如 `registry.py` 中动态加载模块列表）在 Rust 中需要静态注册
5. **库生态较小** —— 中国金融数据、Excel 高级样式等领域的 Rust 库远少于 Python/Java
6. **反射缺失** —— 无法像 Python 那样动态 `import_module()`，需要改为显式注册模式

### 3.5 Rust 工作量估算

| 阶段 | 预估工时 | 说明 |
|------|---------|------|
| 基础设施（cache, registry, models, http） | 2–3 周 | 相对直接，serde 模板代码多但逻辑简单 |
| 数据源层（providers + fetcher/chain） | 4–6 周 | 每个 API 接口需手动实现，含 akshare 替代 |
| 报告引擎（Excel + HTML + 分析模块） | 6–10 周 | 最大模块，Excel 样式/sheet 构建量大 |
| LLM 模块 | 3–4 周 | 逻辑复杂但无生态障碍 |
| TUI + CLI 入口 | 2–3 周 | ratatui 学习曲线，比原 getch 实现更复杂 |
| 测试重写 | 4–6 周 | 并行，可与其他阶段同步 |
| CI/CD + 文档 | 1 周 | |
| **总计（单人，有 Rust 经验）** | **22–35 周（≈6–9 个月）** | |
| **总计（单人，零 Rust 经验）** | **35–50 周（≈9–12 个月）** | |

---

## 4. Java 方案分析

### 4.1 依赖映射

| Python 依赖 | Java 替代 | 成熟度 | 风险 |
|-------------|----------|--------|------|
| openpyxl | Apache POI | ⭐⭐⭐⭐⭐ | 行业标准，功能比 openpyxl 更丰富，但 API 极其啰嗦 |
| httpx | OkHttp / java.net.http | ⭐⭐⭐⭐⭐ | Java 11+ 内置 HttpClient，OkHttp 补充功能 |
| jinja2 | 无直接等价 | ⭐⭐ | Thymeleaf（过重）、Pebble（接近，但已停维）、JMustache（语法不同） |
| akshare | 子进程 / 逐接口重写 | ⭐⭐ | 同 Rust |
| lxml | Jsoup | ⭐⭐⭐⭐⭐ | Jsoup 是 java 生态 HTML 解析标杆，API 比 lxml 更友好 |
| colorama | JANSI / System.out | ⭐⭐⭐⭐ | 简单包装 |
| 标准库 | java.{io,net,util,regex} | ⭐⭐⭐⭐⭐ | 标准库完善 |

### 4.2 关键模块移植评估

| 模块 | 行数 | 移植难度 | 说明 |
|------|------|----------|------|
| **cache/** | ~852 | 🟢 低 | JSON 文件缓存 → Jackson + 文件锁 |
| **code_utils.py** | 520 | 🟢 低 | `java.util.regex` + `enum` |
| **reader.py** | 191 | 🟢 低 | POI XSSFWorkbook 读取，标准流程 |
| **registry.py** | 476 | 🟢 低 | `enum` + 静态 `Map` 注册 |
| **provider_registry.py** | 602 | 🟡 中 | 单例 + 熔断器 → Guava/RateLimiter + ConcurrentHashMap |
| **fetcher/chain.py** | 470 | 🟡 中 | 接口 + 策略模式，fallback 链 |
| **providers/ (10 个)** | ~3,449 | 🟡 中 | 每个 API 接口需重写，OkHttp + Jackson |
| **llm/ (15 个文件)** | ~2,903 | 🟡 中 | 多 provider 路由、重试退避、token 计价 |
| **report/excel_generator/** | ~2,400 | 🟡🔴 中—高 | POI 代码量巨大，cell 样式需逐一定义 |
| **report/penetration.py** | 809 | 🟢 低 | 纯算法，直接移植 |
| **report/portfolio_history.py** | 490 | 🟢 低 | 纯算法，直接移植 |
| **report/fund_style_analysis.py** | 652 | 🟡 中 | 算法可移植，可能需要 BigDecimal 处理精度 |
| **report/html_writer.py** + renderers | ~1,130 | 🟡🔴 中—高 | 需选择模板引擎并逐函数移植渲染逻辑 |
| **report/orchestrator.py** | 778 | 🟡 中 | CompletableFuture / Virtual Threads 替代 ThreadPoolExecutor |
| **tui/** | ~629 | 🔴 **高** | **Java 无成熟的跨平台 TUI 框架** |

### 4.3 Java 方案优势

1. **生态成熟完善** —— 几乎所有领域都有久经考验的库
   - POI 比 openpyxl 功能更全（图表、数据透视表、条件格式）
   - Jackson/Gson、OkHttp、Jsoup 都是各自领域的标杆
2. **人才池大** —— Java 开发者远多于 Rust，招聘/协作成本低
3. **静态类型 + 优秀 IDE 支持** —— IntelliJ 的重构/代码分析能力显著降低移植 bug
4. **Virtual Threads (Java 21+)** —— 轻量级并发，适合多 API 并行请求的编排场景
5. **Java 21 LTS** —— 长期支持版本，语言特性已现代化（Records, Pattern Matching, Sealed Classes）
6. **跨平台成熟** —— JVM 本身就是"一次编译到处运行"
7. **Gradle/Maven** —— 构建系统丰富，依赖管理成熟

### 4.4 Java 方案劣势

1. **TUI 是致命短板** —— ⚠️ 无成熟的跨平台终端 UI 框架
   - `lanterna`：功能有限，ActiveMQ 项目已弃用
   - `charva`：10 年未更新
   - `jline` / `org.jline`：仅处理输入，不提供布局
   
   **应对选项**：
   | 方案 | 代价 |
   |------|------|
   | **剥离 TUI，仅保留 CLI** | 失去交互式菜单体验 |
   | **改用 Web UI**（Spring Boot + 浏览器）| 从 CLI 工具变成 Web 应用，架构差异巨大，发行复杂 |
   | **TUI 转用 Kotlin + Compose Multiplatform Desktop** | 实际是 Compose Desktop 不是 TUI，~50MB 打包 |
   | **保留 Python TUI 前端 + Java 后端子进程** | 混合运行时，部署复杂 |
   | **Java 直接调用系统 `termios` 做 TUI** | 需 JNI，跨平台兼容性差 |
   
   这是 Java 方案**最大**的技术阻碍。

2. **运行时依赖** —— 用户需安装 JRE (≥21)，或捆绑 jlink 最小镜像
   - 捆绑 jlink：~40–80 MB（含 java.base + java.net.http）
   - 用户安装 JDK：增加使用门槛
3. **POI API 啰嗦** —— 写 Excel 的代码量约为 Python openpyxl 的 3–5×
   ```java
   // openpyxl: ws.cell(row=1, column=1, value="Hello")
   // POI:
   Row row = sheet.createRow(0);
   Cell cell = row.createCell(0);
   cell.setCellValue("Hello");
   ```
4. **启动延迟** —— JVM 启动 0.5–2s，对 CLI 工具来说虽可接受但不如 Rust 的瞬时启动
5. **HTML 模板** —— 缺少 jinja2 的直接等价品，Thymeleaf 太重，Pebble 维护状态不明
6. **文件打包** —— 发行需处理 JAR + 依赖，不如 Rust 单二进制简洁

### 4.5 Java 工作量估算

| 阶段 | 预估工时 | 说明 |
|------|---------|------|
| 基础设施（cache, registry, models, http） | 2–3 周 | Jackson + OkHttp，模板代码量大但简单 |
| 数据源层（providers + fetcher/chain） | 4–6 周 | 同 Rust，每个接口需手动实现 |
| 报告引擎（Excel + HTML + 分析模块） | 8–14 周 | POI 代码量大，是移植中工作量最大的部分 |
| LLM 模块 | 3–5 周 | 逻辑复杂，但 Java 生态工具完备 |
| TUI 替代方案 | 2–6 周 | 取决于方案选择（纯 CLI / Web 前端 / 保留 Python TUI） |
| 测试重写 | 4–6 周 | JUnit 5 + Mockito |
| CI/CD + 文档 + 打包 | 1–2 周 | Maven/Gradle + jlink |
| **总计（单人）** | **24–42 周（≈6–10 个月）** | |

> **注**：如果选择"保留 Python TUI + Java 后端子进程"的混合方案，TUI 部分工作量大幅降低，但部署复杂度增加。如果选择"转 Web UI"，
> 则还需额外的 Web 前端开发时间（另加 4–8 周）。

---

## 5. 对比总览

| 维度 | Rust | Java |
|------|------|------|
| **总工作量** | 6–9 个月（有经验） / 9–12 个月（零经验） | 6–10 个月 |
| **二进制分发** | 🟢 单文件 5–15MB | 🔴 需 JRE (≥40MB jlink 或要求用户安装) |
| **TUI 可行性** | 🟡 可行（ratatui），需重写 | 🔴 无合适方案，需架构调整 |
| **Excel 功能** | 🟡 读写分离，复杂样式受限 | 🟢 POI 功能最全 |
| **HTML 模板** | 🟢 minijinja ≈ jinja2 | 🟡 无直接等价，需适配 |
| **开发周期迭代** | 🔴 编译慢 (30s–15min) | 🟢 增量编译快 (2–10s) |
| **学习成本** | 🔴 极高 | 🟡 中等（若团队有 Java 经验） |
| **人才可获性** | 🔴 稀缺 | 🟢 普遍 |
| **内存安全** | 🟢 编译期保证 | 🟡 GC + null 安全（Kotlin 更优） |
| **并发模型** | 🟢 async/await + Send/Sync trait | 🟢 Virtual Threads |
| **跨平台条件编译** | 🟢 `#[cfg]` 精确控制 | 🟡 运行时检测 |
| **生态——中国金融数据** | 🔴 几乎无 | 🔴 几乎无 |
| **akshare 替代成本** | 🔴 高 | 🔴 高 |
| **启动速度** | 🟢 瞬时 | 🟡 0.5–2s |
| **文件格式解析** | 🟡 需第三方 crate | 🟢 标准库 + 成熟生态 |

---

## 6. 推荐排序

### 第一选择：Rust（条件：团队有 Rust 意愿/学习能力）

**核心理由**：
1. 单二进制分发最符合当前"轻量级个人工具"的定位
2. ratatui TUI 生态已足够成熟，可完整保留终端交互体验
3. 所有外部 API 调用都是 HTTP 请求 + JSON/HTML 解析，Rust 生态（reqwest + serde + scraper）覆盖充分
4. 编译期错误处理可根治当前 Python 版本中常见的"某数据源超时 → 无声降级"的模糊状态
5. minijinja ≈ Jinja2 语法，模板迁移成本最低

**最大阻碍**（需先解决）：
- akshare 替代方案需要明确（子进程 vs 重写）
- Excel 高级样式的 `rust_xlsxwriter` 能力边界确认

### 第二选择：保持 Python + 局部优化

**核心理由**：
- 当前 Python 实现已稳定运行，门禁体系完备
- 移植 6–12 个月的人力成本能否带来对等的价值提升，值得审慎评估
- 如果核心痛点只是"分发需 Python 环境"，可通过 PyInstaller / Nuitka 打包为单文件
- 如果核心痛点是"性能"，实际瓶颈在 IO（网络请求+Excel 写入）而非 CPU

### 第三选择：Java（不推荐，除非有特殊约束）

**不推荐理由**：
- TUI 问题无优雅解决方案——要么丢失交互体验，要么改为 Web 应用导致架构巨变
- 与 Rust 相比，Java 方案的唯一优势（人才池/POI 全功能）不足以抵消 TUI 根本缺陷
- 如果团队已有 Java 码农且愿意牺牲 TUI 改为纯 CLI+参数模式，可考虑

---

## 7. 如果决定移植——建议路径

### 前提：确定 akshare 替代方案

```
┌─ 选项 A：子进程调用 Python aksshare
│   ├ 优点：零重写成本，保持功能100%覆盖
│   └ 缺点：失去单二进制，部署需捆绑 Python + akshare
│
├─ 选项 B：HTTP 重写关键接口
│   ├ 优点：完全独立，无运行时依赖
│   ├ 范围：行业分类 + 资金流向 + 分红 + 盈利预测（约 8–10 个 API）
│   └ 缺点：2–4 周额外开发 + 维护逆向工程
│
└─ 选项 C：两者兼有（逐步迁移）
    ├ 阶段1：子进程调用 Python akshare（快速实现）
    └ 阶段2：逐一重写为原生 HTTP 调用（逐步消除依赖）
```

### 建议实施顺序（以 Rust 为例）

```
Phase 0 ─ 搭建工程骨架（cargo init, CI, crate 选型）          → 1 周
Phase 1 ─ 基础层：cache, models, code_utils, registry          → 2 周
Phase 2 ─ 数据层：providers + fetcher/chain                    → 4–5 周
Phase 3 ─ 报告核心：penetration, fund_performance, history    → 3–4 周
Phase 4 ─ Excel 输出：rust_xlsxwriter 适配                     → 3–4 周
Phase 5 ─ HTML 输出：minijinja + renderers                     → 2 周
Phase 6 ─ LLM 模块：多 provider 路由 + 重试 + pricing          → 3 周
Phase 7 ─ TUI + CLI 入口                                       → 2 周
Phase 8 ─ 测试 + 门禁 + 文档                                   → 并行 4–6 周
```

---

## 8. 附录：模块复杂度热力图

```
低复杂度（纯算法，无外部依赖，直接移植）
  ├ penetration.py                🟢 递归算法
  ├ portfolio_history.py           🟢 数组计算
  ├ fund_concentration.py          🟢 公式计算
  ├ code_utils.py                  🟢 正则 + 枚举
  ├ cache/                         🟢 文件读写 + TTL 判断
  ├ models.py                      🟢 数据结构
  └ benchmark.py                   🟢 静态配置

中复杂度（有依赖，需适配层）
  ├ providers/*.py                 🟡 每个 API 一次 HTTP 解析
  ├ fetcher/chain.py               🟡 策略 + fallback 链
  ├ fund_performance.py            🟡 排序 + 百分位 + 评级
  ├ fund_style_analysis.py         🟡 风格归因计算
  ├ news_*.py                      🟡 多源聚合 + 去重算法
  └ llm/*.py                       🟡 多 provider 路由 + 重试

高复杂度（大量依赖交互，UI 密集）
  ├ report/orchestrator.py         🔴 多模块编排 + 并发控制
  ├ report/excel_generator/        🔴 17 个 sheet 逐构建
  ├ report/html_renderers.py       🔴 14 个渲染函数
  ├ report/penetration_sheet.py    🔴 复杂的 Excel 格式输出
  └ tui_menu.py + tui_handlers.py  🔴 TUI 交互逻辑（Java 不可行）

极高复杂度（生态依赖，无直接替代）
  ├ providers/akshare_extras.py    🔴🔥 akshare 替代
  └ providers/eastmoney_industry.py 🔴🔥 页面结构逆向
```
