"""pipeline_data 组装构建器已知键注册契约测试。

对应数据契约：所有 pipeline_data 顶层键必须先在已知键集合注册，
否则 build()/merge_pipeline_data() 会记录「未注册键」警告并自动补注册。

重点覆盖三契约键（危机标注/尾部风险/快照差异）：
  - crisis_annotation_data
  - tail_risk_data
  - snapshot_diff_data
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import pytest

from src.python.report.pipeline_data_builder import (
    _PIPELINE_DATA_KNOWN_KEYS,
    _PIPELINE_DATA_TYPE_MAP,
    build,
    merge_pipeline_data,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

_REPO_ROOT = Path(__file__).resolve().parents[4]  # 仓库根目录（src/test/unit/report 向上 4 级）
_TECHNICAL_DOC = _REPO_ROOT / "docs-stm" / "managements" / "technical.md"


def _appendix_h_keys() -> set[str]:
    """解析 technical.md 附录 H 的键名列表（表格第一列）。

    附录 H 是 pipeline_data 的注册台账：键必须先在此登记类型与写入/消费模块，
    才能在代码中使用。此处解析出的集合即「已登记键」。
    """
    text = _TECHNICAL_DOC.read_text(encoding="utf-8")
    section = text.split("### 附录 H：pipeline_data Schema 定义", 1)[1]
    # 截到下一个同级/更高级标题（附录 I 或任一 ### 标题）
    section = re.split(r"\n#{2,3} ", section, maxsplit=1)[0]
    keys: set[str] = set()
    for line in section.splitlines():
        m = re.match(r"^\|\s*([A-Za-z_][A-Za-z0-9_]*)\s*\|", line)
        if m:
            keys.add(m.group(1))
    return keys


_EXTRA_KEYS = {"crisis_annotation_data", "tail_risk_data", "snapshot_diff_data"}


class TestPipelineDataKnownKeys(unittest.TestCase):
    """pipeline_data 顶层键注册契约测试。"""

    def test_three_contract_keys_registered(self):
        """危机标注/尾部风险/快照差异三契约键已在已知键集合注册。"""
        self.assertTrue(_EXTRA_KEYS.issubset(_PIPELINE_DATA_KNOWN_KEYS))


class TestPipelineDataBuildExtra(unittest.TestCase):
    """build() 注入新增契约键 → 正常合并且不产生未注册警告。"""

    def test_build_accepts_three_keys_without_warning(self):
        """通过 extra 注入三键（合法类型）→ 合并成功；已注册键不走未注册补注册路径。"""
        before = set(_PIPELINE_DATA_KNOWN_KEYS)
        result = build(
            crisis_annotation_data={"available": True, "intervals": []},
            tail_risk_data={"available": False},
            snapshot_diff_data=None,
        )
        self.assertIn("crisis_annotation_data", result)
        self.assertIn("tail_risk_data", result)
        self.assertIn("snapshot_diff_data", result)
        self.assertIsNone(result["snapshot_diff_data"])
        # 三键本就已注册：build() 不应触发未注册键的自动补注册（集合不增长）
        self.assertEqual(set(_PIPELINE_DATA_KNOWN_KEYS), before)

    def test_build_rejects_wrong_type_with_warning(self):
        """类型断言：crisis_annotation_data 传入非 dict → 记录类型警告但容错保留。"""
        with self.assertLogs("invest", level="WARNING") as cm:
            result = build(crisis_annotation_data="not-a-dict")
        self.assertEqual(result["crisis_annotation_data"], "not-a-dict")
        self.assertIn("类型异常", "\n".join(cm.output))


class TestPipelineDataMergeExtra(unittest.TestCase):
    """merge_pipeline_data() 合并新增契约键。"""

    def test_merge_appends_three_keys(self):
        """在基础 pipeline_data 上合并三键 → 键均保留。"""
        base = {"diff": None, "data_degradation": []}
        merged = merge_pipeline_data(
            base,
            crisis_annotation_data={"available": True},
            tail_risk_data=None,
            snapshot_diff_data=None,
        )
        self.assertIn("crisis_annotation_data", merged)
        self.assertIn("tail_risk_data", merged)
        self.assertIn("snapshot_diff_data", merged)

    def test_merge_from_none_builds_via_build(self):
        """base_pipeline_data=None 且含 extra → 走 build() 构建并保留扩展键。"""
        merged = merge_pipeline_data(
            None,
            crisis_annotation_data={"available": True},
            tail_risk_data={"available": False},
        )
        self.assertIsNotNone(merged)
        self.assertIn("crisis_annotation_data", merged)
        self.assertIn("tail_risk_data", merged)


class TestSchemaRegisteredInAppendixH(unittest.TestCase):
    """数据契约：代码中在用的 pipeline_data 键必须先在附录 H 登记。

    背景：`decision_review_data`（决策复盘区块）曾由挂载点写入并被执行章消费，
    却未登记进 `_PIPELINE_DATA_KNOWN_KEYS`/附录 H——两处清单各自漂移即失去
    「先定义类型再使用」的守门作用；`portfolio_daily_returns` 则是反向问题
    （登记了类型却在全仓库无任何消费者，属死键，已随本次整改移除）。
    本用例锁定「代码用键 ⊆ 附录 H 登记键」的单向不变式。
    """

    def test_known_keys_documented_in_appendix_h(self):
        """_PIPELINE_DATA_KNOWN_KEYS 全量键均在附录 H 表格中登记。"""
        documented = _appendix_h_keys()
        self.assertTrue(documented, "附录 H 解析为空——标题或表格格式可能已变更")
        undocumented = sorted(_PIPELINE_DATA_KNOWN_KEYS - documented)
        self.assertEqual(undocumented, [], f"以下键未在附录 H 登记（C19）：{undocumented}")

    def test_type_map_keys_documented_in_appendix_h(self):
        """类型断言表中的键均在附录 H 登记（类型断言不能脱离 schema 台账）。"""
        documented = _appendix_h_keys()
        undocumented = sorted(set(_PIPELINE_DATA_TYPE_MAP) - documented)
        self.assertEqual(undocumented, [], f"以下键未在附录 H 登记（C19）：{undocumented}")

    def test_decision_review_data_registered(self):
        """决策复盘区块键已登记类型（dict / None）并可经 build() 注入不告警。"""
        self.assertEqual(_PIPELINE_DATA_TYPE_MAP.get("decision_review_data"), (dict, type(None)))
        with self.assertNoLogs("invest", level="WARNING"):
            build(decision_review_data={"rows": []})

    def test_portfolio_daily_returns_is_not_a_pipeline_key(self):
        """死键回归：portfolio_daily_returns 无消费者，不得再登记为契约键。

        `history_data.daily_returns_portfolio` 由 `_full_risk_metrics` 直接读取，
        无需（也不应）额外投射为 pipeline_data 顶层键。
        """
        self.assertNotIn("portfolio_daily_returns", _PIPELINE_DATA_KNOWN_KEYS)
        self.assertNotIn("portfolio_daily_returns", _PIPELINE_DATA_TYPE_MAP)


if __name__ == "__main__":
    unittest.main()
