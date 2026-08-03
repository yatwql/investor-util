"""fact_checker 子包 — 正则模式定义。

关键词词表见 _constants.py。
"""

from __future__ import annotations

import re

# 6 位数字代码（A 股/基金/指数）
# 使用 re.ASCII 确保 \b 在中文和非 ASCII 字符旁也正常匹配边界
_CODE_PATTERN = re.compile(r"\b[0-9]{6}\b", re.ASCII)

# 排名声称模式 — 按声称类型拆分，便于校验器按各自维度验证：
#   _RANK_MAX_PATTERN     — "最大持仓"/"最重持仓"/"首要持仓" 等"市值第一"声称。
#   _RANK_ORDINAL_PATTERN — "第N大持仓"/"第一重仓" 等精确名次声称（N 可省略"大"，如"第一重仓"）。
#   _RANK_TOP_PATTERN     — "前N大持仓"/"头N大持仓" 等前 N 名声称。
# 要求排名词与持仓名词紧邻（允许中间一个"的"），避免将
# "最大单项亏损品种"/"主要利润贡献"/"最大亏损来源"/"最大特点" 等
# 非持仓排名语境误判为排名声称。
# "主要持仓"等模糊声称不纳入排名校验：不断言精确名次，无法确定性验证
# （按"最大"处理会误报——如"X 为主要持仓"并不等同于 X 是最大持仓）。
_RANK_MAX_PATTERN = re.compile(r"(?:最大|最重|首要)(?:的)?(?:持仓|重仓|仓位|持股|权重)")
_RANK_ORDINAL_PATTERN = re.compile(r"第([一二三四五六七八九十两\d]+)(?:大)?(?:的)?(?:持仓|重仓|仓位|持股|权重)")
_RANK_TOP_PATTERN = re.compile(r"(?:前|头)([一二三四五六七八九十两\d]+)(?:大)?(?:的)?(?:持仓|重仓|仓位|持股|权重)")

# 百分比数值
_PERCENT_PATTERN = re.compile(r"(\d+\.?\d*)\s*%")
