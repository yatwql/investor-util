"""pipeline_data 组装构建器已知键注册契约测试。

对应数据契约：所有 pipeline_data 顶层键必须先在已知键集合注册，
否则 build()/merge_pipeline_data() 会记录「未注册键」警告并自动补注册。

重点覆盖三契约键（危机标注/尾部风险/快照差异）：
  - crisis_annotation_data
  - tail_risk_data
  - snapshot_diff_data
"""

from __future__ import annotations

import unittest

import pytest

from src.python.report.pipeline_data_builder import (
    _PIPELINE_DATA_KNOWN_KEYS,
    build,
    merge_pipeline_data,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

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


if __name__ == "__main__":
    unittest.main()
