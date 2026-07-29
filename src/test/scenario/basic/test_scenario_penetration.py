"""穿透 TOP10 业务场景验证（S-P1 ~ S-P10）。

此文件已被拆分为 4 个子文件，请使用具体子文件运行测试：

  基础场景：test_scenario_penetration_basic.py   （S-P1 ~ S-P4）
  高级场景：test_scenario_penetration_advanced.py（S-P5, S-P7, S-P8）
  混合场景：test_scenario_penetration_mixed.py   （S-P9, S-P10）
  边缘场景：test_scenario_penetration_edge.py     （S-P6）

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/basic/test_scenario_penetration_basic.py -v
  pytest src/test/ -m "scenario_basic" -v    # 全部基础场景
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from src.python.models import Holding
from src.python.report.market_value import DetailRow
from src.python.report import penetration as pene

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic]

if __name__ == "__main__":
    unittest.main()
