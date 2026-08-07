# README 嵌入 SVG 架构图 + 排版优化

## Context

README.md 当前是纯文本：长段落文字墙、无任何可视化。用户希望根据软件功能特性，寻找或制作 SVG 图嵌入 README，显得专业（1~3 个），同时优化排版与语句组织。

**已确认决策**（用户明确选择）：
- **3 张 SVG**
- **深色科技风**（深蓝渐变底 + 亮色节点卡片 + 圆角分层）
- **中等排版重构**：插入 SVG + 精炼副标题 + 功能特性分组统一 emoji + 语句润色，不动章节大框架

**方案**：纯手写 SVG（独立 `assets/` 文件，README 相对路径引用），不依赖外部图片工具/库。

## 新增资产

新建目录 `assets/`（仓库根，与 README 同层），含 3 个 SVG 文件（语义命名，禁任务代号）：

1. **`assets/architecture.svg`** — 首屏主图：三渠道 → 引擎 → 双报告
2. **`assets/llm-chain.svg`** — LLM 智囊团技术图（放 LLM 分析章节）
3. **`assets/capabilities.svg`** — 功能能力总览图（放功能特性章节首）

### SVG 通用规范（三张共用）

- 深色科技风：背景深蓝渐变（`#0f1b2d` → `#16283f`），卡片 `#1d3557`/`#223b5c` 系，圆角 10-16，柔和阴影
- 强调色：青 `#22d3ee`、蓝 `#60a5fa`、绿 `#34d399`、紫 `#a78bfa`、橙 `#fbbf24`、红 `#f87171`
- 文本：中文字体栈 `font-family="-apple-system,'PingFang SC','Microsoft YaHei','Noto Sans SC',sans-serif"`
- 宽度 ~1000px（GitHub 内容区 ~800px 自动缩放，字号 18-26 保证可读）
- 关键元素加 `role="img"` + `<title>` 无障碍标注

### 图 1 `architecture.svg` — 三渠道 → 引擎 → 双报告（首屏）

```
┌ TUI ────────┐   ┌─ 分析引擎（大卡）─────────────┐   ┌ Excel 报告 ┐
│ 全键盘菜单   │   │  实时行情 · 资产穿透 TOP10      │   │ 19 条件页签 │
├ CLI ────────┤──▶│  基金评级 · 新闻关联 · 风控      │──▶├────────────┤
│ 定时任务     │   │  LLM 智囊团（政经/复盘/体检）    │   │ HTML 报告   │
├ Web ────────┤   └──────────────────────────────┘   │ 9 交互图表   │
│ 浏览器即用   │                                      └────────────┘
└─────────────┘   底部横条：同一套分析引擎 · 三种渠道结果一致
```

- 左列 3 张入口卡片（TUI/CLI/Web），中间一个引擎大卡（内部 6 个能力标签），右侧 2 张输出卡（Excel/HTML）
- 底部横条：`同一套分析引擎 · 三种渠道 · 报告结果完全一致`

### 图 2 `llm-chain.svg` — LLM 智囊团技术图（LLM 分析章节）

```
持仓变更/报告触发 ──▶ 缓存指纹判定（变更自动失效）
                          │ 未命中
                          ▼
              Provider Chain 链式分发
        Claude · OpenAI · DeepSeek · Gemini（任一失败自动递补）
              priority / weighted / cost_first / fallback_only
                          ▼
        输出：全球政经 · 智囊团复盘 · 持仓体检 · 穿透分析
              （Extended Thinking 按模块独立开启）
```

- 顶部输入 → 缓存指纹判定 → 中部 Provider 链（4 个 provider 节点横排）→ 策略 4 标签 → 底部 4 个输出模块

### 图 3 `capabilities.svg` — 功能能力总览（功能特性章节首）

8 个能力卡片 2×4 网格（每卡：图标 + 标题 + 一句说明），底部双报告输出条：
- 🔍 基础报告与行情（多账户/实时行情/智能缓存/19 页签）
- 📰 新闻与数据增强（5 源并行/行业关键词/盈利预测/分红）
- 🤖 LLM 智囊团（多 Provider 链式分发/Extended Thinking）
- 📈 分析与风控（Beta CI/情景分析/再平衡/流动性）
- 🔄 调仓 What-if（双持仓 diff/时序回测）
- ⚙️ 运维追踪（阶段计时/数据源健康检查/趋势查看）
- 🏆 基金评价（5 级评级/经理变更/重合度/风格因子）
- 🔒 隐私安全（匿名化 4 模式/缓存审查/状态隔离）

## README.md 修改

1. **副标题精炼**：保留 `**把持仓 Excel 变成决策级投资洞察。**`，其后长句压缩为更精炼的价值主张（去重核心亮点表已覆盖的信息）
2. **插入图 1**：标题 + 副标题 + 版本行之后、`## ✨ 核心亮点` 之前
   `![](assets/architecture.svg)`
3. **插入图 3**：`## 功能特性` 标题下、`### 基础报告与行情` 之前
   `![](assets/capabilities.svg)`
4. **插入图 2**：`### LLM 分析` 标题下（`#### LLM 报告实际输出` 之前）
   `![](assets/llm-chain.svg)`
5. **功能特性 8 个分组标题统一 emoji**：
   - `### 基础报告与行情` → `### 🔍 基础报告与行情`
   - `### 新闻与数据增强` → `### 📰 新闻与数据增强`
   - `### LLM 分析` → `### 🤖 LLM 分析`
   - `### 投资分析与风控` → `### 📈 投资分析与风控`
   - `### 调仓 What-if 模拟（独立报告）` → `### 🔄 调仓 What-if 模拟（独立报告）`
   - `### 性能追踪与运维` → `### ⚙️ 性能追踪与运维`
   - `### 基金评价` → `### 🏆 基金评价`
   - `### 隐私与安全` → `### 🔒 隐私与安全`
6. **语句润色**：微调个别长句断行/措辞，保持信息不变，纯可读性优化

## folders.md 同步登记（CLAUDE.md 强制）

1. **项目统计表**新增一行：
   `| 架构图示 | SVG | 3 | ~1,500 | \`assets/\` README 架构图（architecture/llm-chain/capabilities） |`
2. **目录树顶部**新增 `assets/` 分支：
   ```
   ├── assets/                          # README 架构图（SVG）
   │   ├── architecture.svg             #   三渠道→引擎→双报告 首屏主图
   │   ├── llm-chain.svg                #   LLM 智囊团 Provider 链式分发图
   │   └── capabilities.svg             #   功能能力总览图
   ```

## 不改动

- 核心亮点表、用户指南表、开发者参考表、项目内部文档表（结构完整，不改）
- 章节大框架与顺序（保持现状）
- 版本号（README 改版不涉及版本切换，版本头仍 0.10.13-dev）

## 验证

1. **SVG 语法**：`.venv/bin/python -c` 用 xml.dom.minidom 解析 3 个 SVG 文件确认合法 XML
2. **README 渲染**：检查 3 个 `![](assets/xxx.svg)` 引用路径与实际文件名一致
3. **P0 门禁**：`.venv/bin/python scripts/test_runner.py --mode dev-verify` + 4 checks（check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci`）
4. **视觉核对**：在浏览器打开 README.md 预览（或截图 SVG 文件）确认布局无重叠、中文正常渲染
5. **changelog 登记**：`[0.10.13-dev]` 段登记 README 架构图 + 排版优化条目
6. 提交 dev 分支（folders.md 目录树同步在同一提交内）

## 计划文件迁移

执行完成后将本 plan 迁移到 `docs-stm/plan/`（CLAUDE.md 要求 .claude/plans/ 中间计划文件必须迁移）。
