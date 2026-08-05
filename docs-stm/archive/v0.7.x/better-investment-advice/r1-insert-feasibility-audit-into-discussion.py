# -*- coding: utf-8 -*-
"""Round 1: Insert feasibility findings after section 2."""
with open(
    "D:/path/to/investor-util/docs-stm/plan/discussion-better-investment-advice.md",
    "r", encoding="utf-8"
) as f:
    content = f.read()

old = "---\n\n\n\n---\n\n\n## 3. 最终版综合建议"

new_block = """---\n
## 3. 数据源与代码可行性实测验证（立项前调研核心）

> **贯穿原则**：所有结论必须有代码行号和数据结构支撑。每一层的可行性取决于数据源的稳定性和可用性。

### Round 1 — 数据源可行性根基审查：文档假设与代码现实的 7 处断裂

**审查方法**：逐项追踪文档假设 → grep 代码验证 → 标注行号和数据格式。

#### 断裂 1: 组合日收益率序列不存在 (Critical)
- **文档假设**：Beta = Cov(Rp,Rm)/Var(Rm)，组合日收益率 Rp 可直接获得
- **代码现实**：`portfolio_history.py` 第 307-312 行计算 daily_returns 局部变量，但仅用于年化波动率后丢弃。返回字典(第 350-366 行)无 daily_returns 键。bars 每个 bar 只有 {date, total_value, drawdown, drawdown_pct}（第 297-304 行）
- **影响**：Beta 计算链在起点断裂。需修改返回结构增加 daily_returns 字段 (+1 天)
- **数据源稳定性**：**A 级**（从已有 bars 可推算，不需新数据源）

#### 断裂 2: 基准指数返回归一化序列而非日收益率 (Critical)
- **文档假设**：基准指数日收益率 Rm 可直接获得
- **代码现实**：`benchmark.py` 第 132 行 value = round(last_close/close_at_start*100,2) 归一化到起始值=100。fetch_index_history(index.py 第 204-248 行)返回原始 OHLC [{date,close,...}] 但从未暴露给 Beta 计算
- **影响**：需从 fetch_index_history 获取原始收盘价、计算基准日收益率、日期对齐 (+2 天)
- **数据源稳定性**：**A 级**（history_index 使用 Tencent->Sina 双链, chain.py 第 35 行）

#### 断裂 3: 行业分类仅覆盖 A 股 (Critical, 不可突破)
- **文档假设**：行业归因 = 穿透后各行业市值占比 x 行业指数收益
- **代码现实**：`industry.py` 第 96-103 行 a_codes=[c for c in valid_codes if _is_a_share_code(c)]，明确过滤非 A 股。code_utils.py 第 63-77 行 A 股判定前缀 (60,68,00,30,8)，港股00700/美股全排除。cache 中 55 个 industry_*.json 全为 A 股
- **数据源稳定性**：**不可突破**——东方财富不提供非 A 股行业数据。港股需恒生 HSICS (+3d), 美股需 GICS (+3d)
- **结论**：行业归因对含港股/美股组合天然不可用

#### 断裂 4: 行业指数 K 线完全不存在 (Critical)
- **文档假设**：行业归因需行业指数收益
- **代码现实**：`index.py` 仅获取 5+3 个宽基指数。全代码库搜索 BK(东方财富行业指数前缀): 零代码使用 BK 代码查 K 线
- **影响**：行业归因核心公式不可实现。需新增 5-10 个主力行业指数 K 线 fetcher (+14 天)
- **数据源稳定性**：**B 级**（BK 指数可通过东方财富获取，取决于 API 兼容性）

#### 断裂 5: 12 个关键词分类 vs 行业粒度不匹配 (High)
- **代码现实**：`penetration.py` 第 147-476 行 _SECTOR_KEYWORDS 仅 12 个分类(消费/医药/科技/金融/新能源/制造/农业/地产基建/军工/能源资源/交通物流/公用事业)。classify_sector(第 479-495 行)纯关键词子串匹配，首次命中返回
- **影响**：需行业名称规范化表映射东方财富三级行业到用户可读一级 (+1 天)

#### 断裂 6: 偏股基金指数不存在 (High)
- **代码现实**：全代码库搜索"偏股基金指数"、"基金指数"、"FOF" 零结果
- **影响**：需识别公开代码 930950.CSI 并新增 fetcher (+3 天)
- **数据源稳定性**：**A 级**（中证指数官网或新浪可获取）

#### 断裂 7: 换手率近似法精度 (Medium)
- **代码现实**：无交易流水数据，市值变化绝对值在净申购/赎回场景下扭曲
- **影响**：只能方向性参考高/中/低，加置信度标注 (+0.5 天)

#### Round 1 修正结论

| 断裂 | 严重度 | 修复代价 | 数据源稳定性 |
|------|--------|---------|------------|
| 1 日收益率未暴露 | Critical | +1 天 | A 级 |
| 2 基准非日收益率 | Critical | +2 天 | A 级 |
| 3 行业仅 A 股 | Critical | 港股+3d, 美股+3d | **不可突破** |
| 4 行业 K 线不存在 | Critical | +14 天 | B 级 |
| 5 分类不匹配 | High | +1 天 | A 级 |
| 6 偏股基金指数 | High | +3 天 | A 级 |
| 7 换手率精度 | Medium | +0.5 天 | N/A |

**修正前 Phase A**: 35 天 -> **修正后**: 38 天（断裂 1+2）
**修正前 Phase B**: 36 天 -> **修正后**: 53 天（断裂 3+4+5+6）

**核心风险提示**：断裂 3 不可突破，行业归因对混合市场组合天然不可用。所有假设必须有代码行号支撑。

---

## 4. 最终版综合建议（经数据源可行性验证修正）"""

if old in content:
    content = content.replace(old, new_block, 1)
    with open(
        "D:/path/to/investor-util/docs-stm/plan/discussion-better-investment-advice.md",
        "w", encoding="utf-8"
    ) as f:
        f.write(content)
    print("OK: Round 1 inserted successfully")
else:
    print("ERR: old string not found")
    # search with repr
    for i in range(4100, 4200):
        if content[i:i+10] == "---\n\n\n\n---":
            print(f"Found pattern at {i}: {repr(content[i:i+50])}")
            break
