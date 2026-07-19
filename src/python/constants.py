"""项目共享常量模块。

此模块不含对本项目其他任何模块的 import，保持零依赖。
供 cache.py、registry.py、main.py 等模块引用。
"""

import os


def _find_project_root() -> str:
    """从当前文件向上查找标记文件，确定项目根目录。

    查找顺序：pyproject.toml → .git（目录）。两种标记均可，找到即停。
    不依赖目录树深度，重构移动文件不会导致路径偏移。
    """
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(20):  # 安全上限，防止意外死循环
        if os.path.isfile(os.path.join(current, "pyproject.toml")):
            return current
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    # 回退：按当前 src/python/ 深度计算
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 项目根路径（单一来源，所有模块从此导入） ─────────────
# 使用标记文件查找法，不依赖目录树深度。
# cache.py 曾因重构移动文件后忘记更新 dirname 次数导致路径偏移，
# 集中定义后彻底避免此类问题。
PROJECT_ROOT = _find_project_root()

# ── 项目版本 ──────────────────────────────────────────────

APP_VERSION = "0.7.3"

# ── 缓存频率常量（秒，用作代码内默认值） ──────────────────

CACHE_DAILY = 86400  # 每日（24h）
CACHE_WEEKLY = 604800  # 每周（7d）
CACHE_TWO_WEEKS = 1209600  # 两周（14d）
CACHE_MONTHLY = 2592000  # 每月（30d）

# ── 组合历史走势 ─────────────────────────────────

# 快照目录（相对于 PROJECT_ROOT）
HISTORY_SNAPSHOT_DIR = os.path.join(PROJECT_ROOT, "data", "history", "snapshots")
# 快照保留天数（超过此天数的旧快照自动清理）
HISTORY_SNAPSHOT_RETENTION_DAYS = 60
# 快照最大保留数量（安全上限，远超 retention 正常生成量，仅在异常堆积时触发）
# 60天×每日数份 ≈ 200 以内，设为 365 防止误伤正常快照
HISTORY_SNAPSHOT_MAX_COUNT = 365

# 历史 K 线缓存 TTL（每周刷新）
HISTORY_CHAIN_STOCK_TTL = CACHE_WEEKLY
# 历史净值缓存 TTL（每月刷新）
HISTORY_CHAIN_FUND_TTL = CACHE_MONTHLY

# ── LLM 模型定价表（每百万 token，CNY）══ 唯一默认源 ══

MODEL_PRICING: dict[str, dict[str, float]] = {
    # 单一来源：此表为唯一默认定价。pricing.py 以此为基，从 llm_settings.json
    # 的 "pricing" 段加载覆盖（若存在），运行时合并到 _PRICING_MERGED。
    # 新增模型请在此处添加，不要仅修改 llm_settings.json。
    # Per 1M token:
    #   input: 标准输入（缓存未命中）
    #   output: 输出
    #   input_cache_hit: 缓存命中输入（可选，默认等于 input 即无折扣）
    # 通用前缀（如 "claude-sonnet-4-"）用作 startswith() 回退匹配，
    # 覆盖所有日期戳变体（如 claude-sonnet-4-20250514），避免费用显示 "-"。
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "input_cache_hit": 0.30},
    "claude-sonnet-4-8": {"input": 3.0, "output": 15.0, "input_cache_hit": 0.30},
    "claude-sonnet-4-": {"input": 3.0, "output": 15.0, "input_cache_hit": 0.30},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "input_cache_hit": 1.50},
    "claude-opus-4-8": {"input": 15.0, "output": 75.0, "input_cache_hit": 1.50},
    "claude-opus-4-": {"input": 15.0, "output": 75.0, "input_cache_hit": 1.50},
    "claude-haiku-4-5": {"input": 0.25, "output": 1.25, "input_cache_hit": 0.025},
    "claude-haiku-4-": {"input": 0.25, "output": 1.25, "input_cache_hit": 0.025},
    "claude-fable-5": {"input": 3.0, "output": 15.0, "input_cache_hit": 0.30},
    "gpt-4o": {"input": 2.5, "output": 10.0, "input_cache_hit": 2.5},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6, "input_cache_hit": 0.15},
    "deepseek-v4-flash": {"input": 1, "output": 2, "input_cache_hit": 0.02},
    "deepseek-v4-pro": {"input": 3, "output": 6, "input_cache_hit": 0.025},
    "deepseek-chat": {"input": 1, "output": 2, "input_cache_hit": 0.02},
    # Gemini
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60, "input_cache_hit": 0.015},
    "gemini-2.5-pro": {"input": 1.25, "output": 5.0, "input_cache_hit": 0.125},
    "gemini-2.5-": {"input": 1.25, "output": 5.0, "input_cache_hit": 0.125},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "input_cache_hit": 0.01},
    "gemini-2.0-": {"input": 0.10, "output": 0.40, "input_cache_hit": 0.01},
}
