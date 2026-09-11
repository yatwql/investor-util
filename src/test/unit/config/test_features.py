"""实验功能注册表与名称解析单元测试。

覆盖 ``features.EXPERIMENTAL_FEATURES`` 注册表驱动的名称解析
（``resolve_experiment_flags`` / ``describe_experiment_flags``），
该解析是 CLI ``--experiment`` 参数与 TUI 菜单 S / Web 配置面板同源的保证。

另覆盖开关注册表自身的两条不变式：默认值表中每个开关都必须有消费者（声明即死
的开关会让用户照文档配置后毫无效果），以及 ``features.json`` 里出现无消费者开关
时必须告警而非静默忽略。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from src.python.config.features import (
    EXPERIMENT_ALL,
    EXPERIMENTAL_FEATURES,
    FEATURE_FLAGS,
    _FEATURE_FLAGS_DEFAULT,
    describe_experiment_flags,
    enabled_experimental_features,
    load_feature_overrides,
    resolve_experiment_flags,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_config]

# 仓库根：src/test/unit/config/<本文件> → parents[4]
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_REGISTRY_FILE = _PROJECT_ROOT / "src" / "python" / "config" / "features.py"


@pytest.mark.unit
class TestResolveExperimentFlags:
    """实验功能名解析测试。"""

    def test_resolve_by_flag_name(self):
        """按开关名解析。"""
        flags, unknown = resolve_experiment_flags(["signal_pre_digest"])
        assert flags == {"signal_pre_digest"}
        assert unknown == []

    def test_resolve_by_display_name(self):
        """按中文显示名解析（注册表驱动，无需维护第二份清单）。"""
        display_name = EXPERIMENTAL_FEATURES["signal_pre_digest"][0]
        flags, unknown = resolve_experiment_flags([display_name])
        assert flags == {"signal_pre_digest"}
        assert unknown == []

    def test_resolve_every_registry_entry(self):
        """注册表中每个实验功能的开关名与显示名均可解析。"""
        for flag, (display_name, _desc, _a) in EXPERIMENTAL_FEATURES.items():
            by_flag, unknown_flag = resolve_experiment_flags([flag])
            by_name, unknown_name = resolve_experiment_flags([display_name])
            assert by_flag == {flag}, f"开关名解析失败: {flag}"
            assert by_name == {flag}, f"显示名解析失败: {display_name}"
            assert unknown_flag == [] and unknown_name == []

    def test_resolve_flag_name_case_insensitive(self):
        """开关名大小写不敏感。"""
        flags, unknown = resolve_experiment_flags(["SIGNAL_PRE_DIGEST"])
        assert flags == {"signal_pre_digest"}
        assert unknown == []

    def test_resolve_all(self):
        """all 解析为全部实验功能。"""
        flags, unknown = resolve_experiment_flags([EXPERIMENT_ALL])
        assert flags == set(EXPERIMENTAL_FEATURES)
        assert unknown == []

    def test_resolve_mixed_and_dedup(self):
        """多种写法混用并去重。"""
        display_name = EXPERIMENTAL_FEATURES["decision_reflection"][0]
        flags, unknown = resolve_experiment_flags(["signal_pre_digest", "SIGNAL_PRE_DIGEST", display_name, "all"])
        assert flags == set(EXPERIMENTAL_FEATURES)
        assert unknown == []

    def test_unknown_reported_but_hits_kept(self):
        """未识别项进入 unknown，已识别项仍正常解析。"""
        flags, unknown = resolve_experiment_flags(["signal_pre_digest", "no_such_feature"])
        assert flags == {"signal_pre_digest"}
        assert unknown == ["no_such_feature"]

    def test_describe_lists_all_entries(self):
        """清单描述串覆盖全部开关名与显示名。"""
        text = describe_experiment_flags()
        for flag, (display_name, _desc, _a) in EXPERIMENTAL_FEATURES.items():
            assert flag in text
            assert display_name in text


@pytest.mark.unit
class TestEnabledExperimentalFeatures:
    """已启用清单（报告产物标注生成条件的唯一取数口）。"""

    def test_none_enabled_by_default(self):
        """实验开关默认全关 → 清单为空（报告不出现该行）。"""
        assert enabled_experimental_features() == []

    def test_returns_display_name_of_enabled_flag(self):
        """启用项返回 (开关名, 显示名)，显示名取自注册表而非另写一份。"""
        from src.python.config.features import set_feature_enabled

        set_feature_enabled("signal_ledger", True)

        assert enabled_experimental_features() == [("signal_ledger", EXPERIMENTAL_FEATURES["signal_ledger"][0])]

    def test_follows_registry_order(self):
        """多项启用时按注册表顺序返回，不随启用先后变化。"""
        from src.python.config.features import set_feature_enabled

        # 故意逆注册表顺序启用：signal_ledger 在注册表第 8，llm_debate_procon 第 1
        set_feature_enabled("signal_ledger", True)
        set_feature_enabled("llm_debate_procon", True)

        assert [flag for flag, _name in enabled_experimental_features()] == [
            "llm_debate_procon",
            "signal_ledger",
        ]

    def test_only_experimental_flags_listed(self):
        """默认开启的非实验开关（如 metrics_*）不进清单——清单只答「非默认产物」与否。"""
        from src.python.config.features import set_feature_enabled

        set_feature_enabled("metrics_hhi", True)

        assert enabled_experimental_features() == []


@pytest.mark.unit
class TestReportAffectingClassification:
    """产物自述的准入口径：能否改变报告产物。

    实验注册表第三字段是该问题的书面答案。报告是脱离本机流转的文件，其自述
    只应列出可能改变内容的开关；列进一个不改报告任何字节的开关，读者会推断
    内容受其影响（系统自检曾如此，转正前它门控 TUI 菜单与 Web 卡片，产物零影响）。
    """

    def test_every_entry_declares_affects_report(self):
        """每项都必须显式回答——缺字段即注册表结构漂移，宣告声明不再被强制。"""
        for flag, entry in EXPERIMENTAL_FEATURES.items():
            assert len(entry) == 3, f"{flag} 未声明是否影响报告产物"
            assert isinstance(entry[2], bool), f"{flag} 的 affects_report 须为布尔"

    def test_entry_only_feature_excluded_from_notice(self, monkeypatch):
        """只影响入口可见性的项不进清单（合成项验证，当前注册表恰无此类成员）。"""
        from src.python.config import features

        monkeypatch.setitem(features.EXPERIMENTAL_FEATURES, "ui_only_probe", ("仅入口探针", "只改面板显隐", False))
        monkeypatch.setitem(features.FEATURE_FLAGS, "ui_only_probe", True)
        monkeypatch.setitem(features.FEATURE_FLAGS, "signal_ledger", True)

        flags = [flag for flag, _name in features.enabled_experimental_features()]

        assert flags == ["signal_ledger"]

    def test_doctor_check_never_in_report_notice(self):
        """系统自检开启时产物自述仍为空——它不改报告任何字节。"""
        from src.python.config.features import get_feature_defaults, set_feature_enabled
        from src.python.report.experimental_notice import enabled_notice_line

        set_feature_enabled("doctor_check", True)

        assert get_feature_defaults()["doctor_check"] is True
        assert enabled_notice_line() is None


@pytest.mark.unit
class TestDoctorCheckPromotion:
    """系统自检的开关归类与默认值。

    它曾是实验项（沿用「新增能力默认关」的发布惯例），但它是只读诊断——不改
    产物、不写文件、联网检查每次显式确认。默认关的实际代价是：最需要它的人
    （环境坏掉的那批）恰好看不到它。故转正为普通开关、默认开启；开关本身保留，
    ``features.json`` 置 false 仍隐藏 TUI ``[D]`` 与 Web 卡片。
    """

    def test_default_enabled(self):
        from src.python.config.features import get_feature_defaults

        assert get_feature_defaults()["doctor_check"] is True

    def test_not_in_experimental_registry(self):
        """不在实验注册表里：不再上实验面板，也不再进产物自述。"""
        assert "doctor_check" not in EXPERIMENTAL_FEATURES

    def test_switch_still_honored(self):
        """转正不等于不可关。"""
        from src.python.config.features import is_feature_enabled, set_feature_enabled

        set_feature_enabled("doctor_check", False)

        assert is_feature_enabled("doctor_check") is False


@pytest.mark.unit
class TestRegistryLiveness:
    """开关注册表每一项都必须有消费者。

    缺陷场景：``_FEATURE_FLAGS_DEFAULT`` 曾声明 16 项全仓无任何代码读取的开关
    （LLM 模块启停、基金深度分析、新闻源、历史走势、匿名化总开关、缓存日清理）
    ——这些能力实际由 ``config.json`` / ``llm_settings.json`` 各自的键控制，开关
    声明了却从未接线（``git log -S`` 证实从未被任何提交消费过）。用户在
    ``features.json`` 里照文档配置后不产生任何效果，而文档仍按生效开关介绍。
    本类是该场景的回归防线。
    """

    # 已移出注册表的陈旧开关：能力各归其主，不得再回来（回来即意味着两处清单
    # 重新漂移，且多半又是声明即死）
    REMOVED_STALE_FLAGS = (
        # LLM 模块启停 → llm_settings.json 的 enabled_llm
        "llm_global_macro",
        "llm_expert_review",
        "llm_health_check",
        "llm_penetration_deep",
        "llm_news_correlation",
        # 基金深度分析模块 → config.json 的 enable_fund_deep_analysis
        "fund_deep_analysis_fund_manager",
        "fund_deep_analysis_fund_concentration",
        # 新闻源启停 → config.json 的 news_sources
        "news_sina",
        "news_eastmoney",
        "news_cls",
        "news_wallstreetcn",
        "news_akshare",
        # 历史走势与回撤 → config.json 的 enable_history
        "history_portfolio",
        "history_benchmark",
        # 匿名化 → config.json 的 anonymization.mode
        "anonymizer",
        # 启动缓存清理 → 无条件执行，无开关（见 cache/__init__.py）
        "cache_daily_cleanup",
    )

    @staticmethod
    def _source_text_outside_registry() -> str:
        """拼接 ``src/python`` 下除注册表自身外的全部源码文本。

        不限于 ``is_feature_enabled`` 的直接实参：开关名也可能经模块常量、元组
        或映射表间接传入（如指标开关的元组、熔断特性开关的映射），因此按「开关名
        是否作为字符串字面量出现在消费方的源码里」判定。
        """
        chunks: list[str] = []
        for path in sorted((_PROJECT_ROOT / "src" / "python").rglob("*.py")):
            if path == _REGISTRY_FILE:
                continue
            chunks.append(path.read_text(encoding="utf-8"))
        return "\n".join(chunks)

    @pytest.mark.unit
    def test_every_flag_has_a_consumer(self):
        """默认值表中每个开关名都必须在注册表之外的源码里被引用。

        新增开关若只在 ``_FEATURE_FLAGS_DEFAULT`` 里加一行、却没接线到任何消费点，
        本用例即失败——那正是「用户照文档配置后毫无效果」的缺陷形态。
        """
        source = self._source_text_outside_registry()
        dead = [flag for flag in _FEATURE_FLAGS_DEFAULT if not re.search(rf"""["']{re.escape(flag)}["']""", source)]
        assert not dead, (
            f"以下开关在 src/python 内无任何消费者，声明即死（用户配置后不产生效果）：{dead}；"
            "请接线到消费点，或按其能力归属移到 config.json / llm_settings.json 并从注册表移除"
        )

    @pytest.mark.unit
    def test_removed_stale_flags_stay_out(self):
        """陈旧开关不得再回到默认值表（否则与各自的真实归属键重复且多半又无人读）。"""
        resurrected = [flag for flag in self.REMOVED_STALE_FLAGS if flag in _FEATURE_FLAGS_DEFAULT]
        assert not resurrected, (
            f"以下开关已被移除，不得回到 _FEATURE_FLAGS_DEFAULT：{resurrected}；"
            "对应能力分别归属 llm_settings.json 的 enabled_llm / config.json 的 "
            "enable_fund_deep_analysis、news_sources、enable_history、anonymization.mode"
        )

    @pytest.mark.unit
    def test_every_experimental_flag_is_registered(self):
        """实验注册表中的开关都必须在默认值表登记，否则用户开了也无效。"""
        unregistered = sorted(set(EXPERIMENTAL_FEATURES) - set(_FEATURE_FLAGS_DEFAULT))
        assert not unregistered, f"实验开关未登记到 _FEATURE_FLAGS_DEFAULT（永远开不起来）：{unregistered}"


@pytest.mark.unit
class TestUnknownOverrideWarning:
    """``features.json`` 中的无消费者开关必须告警，不静默忽略。"""

    @staticmethod
    def _rendered_warnings(mock_logger) -> list[str]:
        """返回该 mock logger 上全部 warning 渲染后的文本。"""
        rendered = []
        for call in mock_logger.warning.call_args_list:
            template = str(call.args[0]) if call.args else ""
            try:
                rendered.append(template % call.args[1:])
            except (TypeError, ValueError):
                rendered.append(template)
        return rendered

    @pytest.mark.unit
    def test_unknown_flags_warn_in_one_message(self, tmp_path):
        """无消费者开关 → 合并为一条 WARNING，且逐键列名（不刷屏、不静默）。"""
        fpath = tmp_path / "features.json"
        fpath.write_text(json.dumps({"no_such_switch": True, "another_ghost": False}), encoding="utf-8")

        # patch.dict 传空值：进入时不预置任何键（预置会让「未知开关」在加载时变成
        # 已知而绕过告警），退出时按快照还原，顺带清掉本次加载新增的键。
        with (
            patch("src.python.config.features._FEATURES_FILE", str(fpath)),
            patch("src.python.config.features.logger") as mock_logger,
            patch.dict(FEATURE_FLAGS, {}),
        ):
            load_feature_overrides()
            warnings = [text for text in self._rendered_warnings(mock_logger) if "无消费者" in text]

            assert len(warnings) == 1, "多个无消费者开关应合并为一条告警，而非逐键刷屏"
            assert "no_such_switch" in warnings[0]
            assert "another_ghost" in warnings[0]

    @pytest.mark.unit
    def test_known_flag_does_not_warn(self, tmp_path):
        """已登记开关不触发无消费者告警，且覆写照常生效（正常配置不被误报）。"""
        fpath = tmp_path / "features.json"
        fpath.write_text(json.dumps({"metrics_hhi": False}), encoding="utf-8")

        with (
            patch("src.python.config.features._FEATURES_FILE", str(fpath)),
            patch("src.python.config.features.logger") as mock_logger,
            patch.dict(FEATURE_FLAGS, {}),
        ):
            load_feature_overrides()
            warnings = [text for text in self._rendered_warnings(mock_logger) if "无消费者" in text]

            assert warnings == []
            assert FEATURE_FLAGS["metrics_hhi"] is False, "已登记开关的覆写仍须正常生效"
