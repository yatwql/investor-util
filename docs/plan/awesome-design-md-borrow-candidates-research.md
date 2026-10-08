# awesome-design-md Web 展示借鉴候选研究

> 2026-10-07 · 借鉴批研究（plan-103 ~ plan-108 立项依据）· 材料：`docs/tmp/awesome-design-md`（临时研究材料，上游 `https://github.com/VoltAgent/awesome-design-md`，浅克隆 73 份 DESIGN.md，tmp 清理后以上游 URL 为准）

## 1. DESIGN.md 是什么

Google Stitch 提出的「设计系统纯文本契约」：与 `AGENTS.md`（怎么建）并列的 `DESIGN.md`（长什么样），AI 编码代理读它即可生成观感一致的 UI——无 Figma 导出、无 JSON schema，Markdown 即 LLM 读得最好的格式。上游每站一份，按 Stitch 规范 + 扩展节抽取（约 400~850 行/份）：

| 节 | 内容 | 对我方的价值 |
|---|---|---|
| Overview | 氛围、密度、设计哲学 | 定调一句话，防「每处各表一种气质」 |
| Colors | 语义角色 + hex + 功能角色（brand/accent/surface ladder/ink 层级/semantic status） | 我方两套 CSS 变量无角色表 → 直接对照 |
| Typography | 字体族 + 完整字阶表 | 报告字阶散落模板内联，未表化 |
| Components | 按钮/卡片/输入/导航 + 全状态 | 工作台组件状态未成矩阵 |
| Layout | 间距阶、网格、留白哲学 | 卡片/章节节奏无阶 |
| Elevation & Depth | 阴影阶与表面层级 | 两面阴影各自硬编码 |
| Do's and Don'ts | 可执行护栏（禁色越权/禁第二强调色/禁跳级…） | 可转机检/评审清单 |
| Responsive | 断点表 + 触控目标 ≥44px + 塌缩策略 | 两面零散 @media，无契约 |
| Iteration Guide | 新组件如何延展 | 30+ 章节 partial 增补时的一致性指引 |
| Known Gaps | 诚实声明未覆盖面 | 文档纪律，随档保留 |

## 2. 样板深读要点（可迁移原则）

- **sentry**（暗色数据密度）：窄色域——单主强调 + 单次要点色，禁第三色；功能性界面行高 1.5、营销面 2.0 刻意区分；明暗是「两个完整世界」，不做半吊子混搭。
- **linear.app**：四级 surface 阶梯（层级不跳级）+ 三级 hairline 边框 + **单一彩色强调**（lavender 只用于品牌/主 CTA/focus/链接强调，禁作卡片填充与区块底）；display 负字距、600/400 配对（拒 700+）。
- **notion**：矩形-克制几何（按钮 8px/卡片 12px 全局一致，拒 pill）；链接蓝与主紫角色分离不混用；阅读型字阶表 + 每断点英雄字号明确回落。
- **kraken / binance（金融向抽样）**：数据密集表格、状态色语义化——与报告数字表场景同构。
- 共性（四家皆有）：断点表 / 触控 ≥44px / 塌缩策略 / Do-Don't / Known Gaps——**契约完整性本身就是方法**。

## 3. 我方面貌（2026-10-07 实测）

| 面 | 现状 | 差距 |
|---|---|---|
| 报告 HTML | `report_template.html` 内联 **179 个 CSS 变量**（--bg/--surface/--text/--chart-*）+ `theme.js` 明暗双主题 + `toc.js` 目录 | 变量有注释无角色表；字阶/间距未成表；数值列无统一 tabular-nums |
| Web 工作台 | `src/static/web/style.css` **1,070 行 / 19 个变量**（--color-bg/--color-primary…），文件头自注「阶段 3 打磨视觉（design-quality 完整落地）」为规划态；仅浅色 | 与报告侧命名两套（--bg vs --color-bg）；组件状态未成矩阵；无暗色 |
| 设计契约 | **全仓无 DESIGN.md / 设计语言文档** | 新增 partial/面板无观感真值，AI 辅助改动易漂移 |
| 响应式 | 两面各有零散 @media | 无断点表/触控/塌缩契约 |

## 4. 立项映射（6 项）

| 借鉴点 | 我方差距 | 立项 |
|---|---|---|
| Stitch 9 节文档骨架 + 契约即真值 | 无设计语言文档 | **plan-103** Web/报告设计语言契约立档（DESIGN.md） |
| Colors 语义角色表方法 | 两套变量名、同义异名、职责边界靠注释 | **plan-104** 双面设计 token 统一（语义角色单源） |
| 「两个完整世界」+ 组件全状态矩阵 | 工作台浅色单世界、状态未成矩阵（阶段 3 未落） | **plan-105** 工作台组件状态矩阵与暗色主题补齐 |
| 阅读型字阶表 + 数据密集表格规范 | 字阶散落、数值列扫读费力 | **plan-106** 报告 HTML 阅读版式与数字排版升级 |
| 断点表 / 触控 ≥44px / 塌缩策略 | 零散 @media，手机浏览宽表溢出 | **plan-107** 响应式断点与触控契约 |
| Do/Don't 护栏可机检 | 样式面无护栏（check-svg/模板结构已有先例） | **plan-108** 设计护栏机检（Do/Don't → 样式检查） |

## 5. 不采纳清单

1. **营销型 hero/大图/插画/吉祥物**——报告与工具工作台是功能面非营销站，引入即噪音。
2. **整站搬用某一家品牌视觉**——上游各份均为「inspired / 公开可见值抽取」，直接复制品牌观感无必要且有辨识度风险；只借**结构方法**（节骨架/角色表/护栏），数值取我方既有 token。
3. **品牌定制字体与多色强调体系**——中文字体栈（PingFang/雅黑/Noto Sans SC）已定，强调色单一现状合理；多色 CTA 与我们的单主色语义冲突。
4. **复古系列（dell-1996 / nintendo-2001）**——娱乐向，与工具气质无关。
5. **独立 preview.html 视觉样张页**——成本/收益暂不成立；DESIGN.md 落地后若组件状态验收需要，再于 plan-105/106 内评估附带产出。

## 6. 引用与留存

- 上游规范：Stitch DESIGN.md specification（`https://stitch.withgoogle.com/docs/design-md/specification/`）；上游仓库见文首。
- 本笔记为中间计划文件（`docs/plan/`），对应任务完成收口时随完成态移入版本归档（沿用借鉴批研究文档惯例）。
