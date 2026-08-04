"""天天基金 API — 基金历史净值数据。

职责：
  - 从 pingzhongdata/{code}.js 提取 Data_netWorthTrend / Data_ACWorthTrend
  - 按日期合并单位净值和累计净值
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from src.python.providers.tiantian_base import _request_pingzhong_data, _safe_float

logger = logging.getLogger("invest")


def fetch_fund_nav_history(code: str) -> list[dict]:
    """获取 OTC 基金历史净值数据（纯获取，由 chain 层管理缓存）。

    从 pingzhongdata/{code}.js 中提取 Data_netWorthTrend（单位净值）
    和 Data_ACWorthTrend（累计净值）。

    ✅ 使用 make_http_client()（通过 tiantian_base 转发）。
    Provider 函数保持纯数据获取，不碰缓存层。

    Args:
        code: 6 位基金代码

    Returns:
        list[dict]: [{date, nav, acc_nav}, ...]
        按日期升序排列。API 失败返回空列表。
    """
    text = _request_pingzhong_data(code)
    if text is None:
        return []

    # 解析 Data_netWorthTrend — 每日单位净值
    # JS 格式: var Data_netWorthTrend = [{"x": 20260701, "y": 1.2345}, ...]
    net_worth = _parse_nav_trend(text, "Data_netWorthTrend")

    # 解析 Data_ACWorthTrend — 每日累计净值
    acc_worth = _parse_nav_trend(text, "Data_ACWorthTrend")

    # 合并为统一格式：优先使用累计净值（含分红再投资），回退到单位净值
    acc_map: dict[str, float] = {item["date"]: item["nav"] for item in acc_worth}
    net_map: dict[str, float] = {item["date"]: item["nav"] for item in net_worth}

    # 合并日期并排序
    all_dates = sorted(set(acc_map.keys()) | set(net_map.keys()))
    result: list[dict] = []
    for date in all_dates:
        nav = net_map.get(date, 0.0)
        acc_nav = acc_map.get(date, 0.0)
        if nav <= 0 and acc_nav <= 0:
            continue
        result.append(
            {
                "date": date,
                "nav": nav,
                "acc_nav": acc_nav,
            }
        )

    logger.info("基金 %s 历史净值: %d 条", code, len(result))
    return result


def _parse_nav_trend(text: str, var_name: str) -> list[dict]:
    """从 JS 文本中解析指定变量的净值趋势数组。

    支持两种格式：
      var Data_netWorthTrend = [{"x": 20260701, "y": 1.2345}, ...]
      var Data_netWorthTrend = {"data": [{"x": 20260701, "y": 1.2345}, ...]}

    Returns:
        [{date: "YYYY-MM-DD", nav: float}, ...] 按日期升序排列
    """
    # 匹配 var/let/const/window.xxx = [...] 或 {...data: [...]}
    pattern = re.compile(
        r"(?:var|let|const|window\.)\s*" + re.escape(var_name) + r"\s*=\s*(.*?);",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        logger.debug("未找到 JS 变量: %s", var_name)
        return []

    raw = match.group(1).strip()

    # 处理包装格式：{"data": [...]}
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            arr = parsed.get("data", [])
        except (json.JSONDecodeError, TypeError):
            arr = []
    else:
        try:
            arr = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            arr = []

    if not isinstance(arr, list):
        return []

    bars: list[dict] = []
    for entry in arr:
        if not isinstance(entry, dict):
            continue
        ts = entry.get("x", 0)
        val = _safe_float(entry.get("y"))
        if not ts or val <= 0:
            continue
        # x 可以是 int YYYYMMDD，也可以是毫秒时间戳（13 位）
        date_str = str(ts)
        if len(date_str) == 8:
            date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        elif len(date_str) == 10 and "-" in date_str:
            pass  # 已经是 YYYY-MM-DD 格式
        elif len(date_str) >= 13:
            # 毫秒时间戳 → YYYY-MM-DD
            try:
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                date_str = dt.strftime("%Y-%m-%d")
            except (OSError, ValueError):
                continue
        else:
            continue
        bars.append({"date": date_str, "nav": val})

    return sorted(bars, key=lambda x: x["date"])
