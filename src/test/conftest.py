"""conftest.py — 全局 pytest 配置与标记注册 + edge 文件隔离校验 + 标记遗漏警告。

标记分组（支持 -m 选择运行）：
  - scenario: 全部业务场景（S0a-S0d + S1-S33 + T1-T21）
  - llm: LLM 相关测试（全部 mock，无需 API key）
  - edge: 边缘/异常场景测试 — 必须放在 *_edge.py 文件中
  - smoke / data / integration（详见各 marker 说明）

用法：
  cd D:/codebase/zoo/investor-util
  pytest src/test/ -m "smoke"                                    # 仅冒烟
  pytest src/test/ -m "not llm"                                  # 排除 LLM
  pytest src/test/ -m "scenario"                                 # 全部场景
  pytest src/test/                                             # 全量运行
"""

from __future__ import annotations

import os
import warnings

import pytest

# ── 项目自定义标记全集（与 pytest_configure 注册的标记保持一致）──

_KNOWN_MARKERS: set[str] = {
    # scenario 分支
    "scenario", "scenario_basic", "scenario_resilience", "scenario_llm", "scenario_datetime",
    "scenario_stock", "scenario_fund", "scenario_mixed_accounts", "scenario_new_holdings",
    "scenario_cache_hit", "scenario_bond", "scenario_network_down", "scenario_single_holding",
    "scenario_zero_cost", "scenario_extreme", "scenario_perf", "scenario_security",
    # unit 分支
    "unit", "unit_providers", "unit_fetcher", "unit_llm", "unit_news", "unit_report",
    "unit_config", "unit_config_edge", "unit_core", "unit_cli", "unit_ui", "unit_analysis",
    "unit_scripts",
    # 跨领域标记
    "llm", "edge", "smoke", "data", "integration",
    # integration 分支
    "integration_contract", "integration_isolation", "integration_news_pipeline",
    "integration_cache", "integration_tui",
}

# pytest 内置标记 — 这些不算"项目标记"
_BUILTIN_MARKERS: set[str] = {"skip", "skipif", "xfail", "usefixtures", "filterwarnings"}


def pytest_configure(config):
    """注册自定义标记，避免 pytest 警告。"""
    config.addinivalue_line("markers", "scenario: 业务场景集成测试（S0a-S0d + S1-S33 + T1-T21）")
    config.addinivalue_line("markers", "scenario_basic: 基础业务链路（S1-S5 + S0a-S0d + S21-S28 + S29-S33）")
    config.addinivalue_line("markers", "scenario_resilience: 异常容错场景（S6-S10）")
    config.addinivalue_line("markers", "scenario_llm: LLM 场景组合（S11-S20）")
    config.addinivalue_line("markers", "scenario_perf: 性能基准测试")
    config.addinivalue_line("markers", "scenario_security: 安全基线测试")
    config.addinivalue_line("markers", "scenario_datetime: 日期/时间场景（T1-T21）")
    config.addinivalue_line("markers", "scenario_stock: 场景 S1 — 纯股票组合")
    config.addinivalue_line("markers", "scenario_fund: 场景 S2 — 纯基金组合")
    config.addinivalue_line("markers", "scenario_mixed_accounts: 场景 S3 — 混合多账户")
    config.addinivalue_line("markers", "scenario_new_holdings: 场景 S4 — 新持仓无缓存")
    config.addinivalue_line("markers", "scenario_cache_hit: 场景 S5 — 缓存全命中")
    config.addinivalue_line("markers", "scenario_bond: 场景 S6 — 纯债券基金组合")
    config.addinivalue_line("markers", "scenario_network_down: 场景 S7 — 网络中断降级")
    config.addinivalue_line("markers", "scenario_single_holding: 场景 S8 — 单账户单持仓")
    config.addinivalue_line("markers", "scenario_zero_cost: 场景 S9 — 零成本持仓")
    config.addinivalue_line("markers", "scenario_extreme: 场景 S10 — 极端值")
    config.addinivalue_line("markers", "unit: 单元测试总标记")
    config.addinivalue_line("markers", "unit_providers: 数据源提供商单元测试")
    config.addinivalue_line("markers", "unit_fetcher: 数据获取调度单元测试")
    config.addinivalue_line("markers", "unit_llm: LLM 模块单元测试")
    config.addinivalue_line("markers", "unit_news: 新闻模块单元测试")
    config.addinivalue_line("markers", "unit_report: 报告生成单元测试")
    config.addinivalue_line("markers", "unit_config: 配置管理单元测试")
    config.addinivalue_line("markers", "unit_config_edge: 配置管理边缘场景单元测试（必须放在 *_edge.py）")
    config.addinivalue_line("markers", "unit_core: 核心基础设施单元测试")
    config.addinivalue_line("markers", "unit_cli: CLI 命令行模式单元测试")
    config.addinivalue_line("markers", "unit_ui: TUI/UI 交互单元测试")
    config.addinivalue_line("markers", "unit_analysis: 分析计算模块单元测试（流动性/再平衡/汇率/无风险利率）")
    config.addinivalue_line("markers", "unit_scripts: scripts/ 工程脚本单元测试（历史痕迹检查/版本一致性等）")
    config.addinivalue_line("markers", "llm: LLM 相关测试（全部 mock，无需 API key）")
    config.addinivalue_line("markers", "edge: 边缘/异常场景测试 — 必须放在 *_edge.py 文件中，不得与普通测试混搭")
    config.addinivalue_line("markers", "smoke: 冒烟测试（快速验证核心功能）")
    config.addinivalue_line("markers", "data: 数据正确性验证测试")
    config.addinivalue_line("markers", "integration: 集成测试—模块间契约/全链路/缓存一致性")
    config.addinivalue_line("markers", "integration_contract: 模块间接口契约验证")
    config.addinivalue_line("markers", "integration_isolation: 错误隔离业务语义验证")
    config.addinivalue_line("markers", "integration_news_pipeline: 新闻流水线全链路")
    config.addinivalue_line("markers", "integration_cache: 跨模块缓存一致性验证")
    config.addinivalue_line("markers", "integration_tui: TUI → Handler 路由集成测试")


# ═══════════════════════════════════════════════════════════════
# 敏感路径自动隔离（autouse）
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _isolate_sensitive_paths(tmp_path, monkeypatch):
    """自动将 config.json 和缓存目录重定向到临时目录。

    防止测试运行意外修改用户的真实配置文件（data/config/config.json）、
    LLM 密钥文件（data/config/llm_key.json）、缓存文件（data/cache/）、
    持仓快照（data/history/snapshots/）等。

    机制：
    - 替换 _config_defaults._CONFIG_FILE → tmp_path/data/config/config.json
    - 替换 cache._CACHE_DIR → tmp_path/data/cache
    - 替换 HISTORY_SNAPSHOT_DIR → tmp_path/data/history/snapshots
    - 清除 config 内存缓存，使 get_config() 从临时路径读取
    （无文件时自动回退到 _DEFAULT_CONFIG 默认值）

    注意：本 fixture 不影响 holdings_dir/output_dir 等配置值本身，
    测试如需使用真实文件读写，应在测试类中自行 setup 隔离。
    """
    monkeypatch.setattr(
        "src.python.config._config_defaults._CONFIG_FILE",
        str(tmp_path / "data/config/config.json"),
    )
    # C13: _CACHE_DIR 存在于 cache/ 子包中
    monkeypatch.setattr(
        "src.python.cache._paths._CACHE_DIR",
        str(tmp_path / "data/cache"),
    )
    monkeypatch.setattr(
        "src.python.cache._stats._CACHE_DIR",
        str(tmp_path / "data/cache"),
    )
    monkeypatch.setattr(
        "src.python.cache._cleanup._CACHE_DIR",
        str(tmp_path / "data/cache"),
    )
    monkeypatch.setattr(
        "src.python.cache._groups._CACHE_DIR",
        str(tmp_path / "data/cache"),
    )
    monkeypatch.setattr(
        "src.python.cache._CACHE_DIR",
        str(tmp_path / "data/cache"),
    )
    # data/state/ 运行时状态目录隔离（从 cache_dir 推导，显式 patch 确保清晰）
    monkeypatch.setattr(
        "src.python.report.data_status._default_persist_path",
        lambda: str(tmp_path / "data/state/.degradation_state.json"),
    )
    # rebalance 静默期文件隔离（_silence.py 是实际定义方，rebalance.py 仅 re-export）
    monkeypatch.setattr(
        "src.python.analysis._silence._SILENCE_FILE",
        str(tmp_path / "data/state/rebalance_silence.json"),
    )
    monkeypatch.setattr(
        "src.python.analysis.rebalance._SILENCE_FILE",
        str(tmp_path / "data/state/rebalance_silence.json"),
    )
    # 交易纪律静默期文件隔离（独立于再平衡静默文件，避免信号互相抑制）
    monkeypatch.setattr(
        "src.python.analysis.trade_discipline._SILENCE_FILE",
        str(tmp_path / "data/state/discipline_silence.json"),
    )
    # local_state.json 机器本地状态隔离（首次运行引导/隐私提示已读标志等）
    monkeypatch.setattr(
        "src.python.config._local_state._LOCAL_STATE_FILE",
        str(tmp_path / "data/state/local_state.json"),
    )
    # perf_history.jsonl 性能历史文件隔离
    monkeypatch.setattr(
        "src.python.core.perf._PERF_HISTORY_FILE",
        str(tmp_path / "data/state/perf_history.jsonl"),
    )
    # datasource_health.jsonl 数据源健康检查历史文件隔离
    monkeypatch.setattr(
        "src.python.core.perf._HEALTH_CHECK_FILE",
        str(tmp_path / "data/state/datasource_health.jsonl"),
    )
    # LLM 配置文件隔离
    monkeypatch.setattr(
        "src.python.config._llm_providers._LLM_KEY_FILE_DEFAULT",
        str(tmp_path / "data/config/llm_key.json"),
    )
    monkeypatch.setattr(
        "src.python.config._llm_providers._LLM_PROVIDERS_FILE_DEFAULT",
        str(tmp_path / "data/config/llm_providers.json"),
    )
    # features.json 功能开关覆写文件隔离（save_feature_overrides 写入）
    monkeypatch.setattr(
        "src.python.config.features._FEATURES_FILE",
        str(tmp_path / "data/config/features.json"),
    )
    # data/history/ 快照目录隔离
    monkeypatch.setattr(
        "src.python.core.constants.HISTORY_SNAPSHOT_DIR",
        str(tmp_path / "data/history/snapshots"),
    )
    monkeypatch.setattr(
        "src.python.report.history_snapshot.HISTORY_SNAPSHOT_DIR",
        str(tmp_path / "data/history/snapshots"),
    )
    # 清空配置缓存，使下次 get_config() 使用新路径
    import src.python.config._config_defaults as _cfg_defaults
    import src.python.config._core as _cfg_core

    monkeypatch.setitem(
        _cfg_defaults._DEFAULT_CONFIG,
        "llm_settings_file",
        str(tmp_path / "data/config/llm_settings.json"),
    )
    # C13: llm_key.json / llm_providers.json 路径同样 seed 到默认配置。
    # _get_llm_key_path()/_get_llm_providers_path() 优先读 config["llm_key_file"]
    # / config["llm_providers_file"]（来自 _DEFAULT_CONFIG），仅靠 patch
    # _LLM_KEY_FILE_DEFAULT 会被默认配置里的真实路径绕过 —— 必须同步 seed，
    # 否则测试会读写用户真实凭据文件（data/config/llm_key.json）。
    monkeypatch.setitem(
        _cfg_defaults._DEFAULT_CONFIG,
        "llm_key_file",
        str(tmp_path / "data/config/llm_key.json"),
    )
    monkeypatch.setitem(
        _cfg_defaults._DEFAULT_CONFIG,
        "llm_providers_file",
        str(tmp_path / "data/config/llm_providers.json"),
    )
    _cfg_core._clear_config_cache()
    # 注：llm_settings.json 不在此处 seed 隔离路径。需要读写真实配置的测试
    # （如 test_all_keys_tracked 检查代码 vs 配置文件的键名一致性），
    # 应直接从 PROJECT_ROOT 读取真实文件，而非依赖隔离路径的副本。


@pytest.fixture(autouse=True)
def _auto_reset_provider_registry():
    """自动重置 DataSourceRegistry 单例，防止测试间状态污染。

    每个测试执行前清空注册信息、熔断状态和会话缓存。
    依赖 provider_registry.get_registry().reset() 而非重新创建实例。
    """
    from src.python.core.provider_registry import get_registry
    get_registry().reset()


@pytest.fixture(autouse=True)
def _auto_reset_feature_flags():
    """自动重置 FEATURE_FLAGS 为默认值，防止测试间 feature 状态泄漏。

    每个测试执行前通过 reset_feature_flags() 恢复出厂默认值。
    需要特定 feature 状态的测试应自行 mock is_feature_enabled()
    或在测试体内调用 set_feature_enabled()，reset fixture 保证不污染下游。
    """
    from src.python.config.features import reset_feature_flags
    reset_feature_flags()


@pytest.fixture(autouse=True)
def _reset_degradation_tracker():
    """自动重置 DegradationTracker 单例，防止测试间状态污染。

    每次测试执行前清空计数器和事件日志。
    依赖 reset_tracker() 销毁当前实例，下次 get_tracker() 重新创建。
    """
    from src.python.report.data_status import reset_tracker
    reset_tracker()


@pytest.fixture(autouse=True)
def _auto_reset_cost_tracker():
    """自动重置 cost_tracker 全局状态 + session 用量，防止测试间状态污染。

    问题场景（xdist 并发）：
      测试 A 通过 patch('src.python.llm.session.get_session_usage') 使用 MagicMock，
      同一 worker 上后续的 BudgetManagement 测试调用 get_budget_status() 时，
      get_session_usage() 返回 MagicMock，导致 usage.get('input_tokens', 0) 返回
      MagicMock → max(0, _input_budget - MagicMock) 抛出 TypeError。

    修复策略：
      1. 重置 session 用量，确保 get_session_usage() 返回干净数据
      2. 重置 budget 为默认值，消除自定义预算残留
    """
    from src.python.llm.cost_tracker import DEFAULT_INPUT_BUDGET, reset_budget
    from src.python.llm.session import reset_session_usage

    reset_session_usage()
    reset_budget(DEFAULT_INPUT_BUDGET)


@pytest.fixture(autouse=True)
def _auto_reset_llm_module_failure():
    """自动重置 LLM_MODULE_FAILURE 全局字典，防止测试间状态污染。

    问题场景（xdist 并发）：
      write_llm_sheets() 读取 LLM_MODULE_FAILURE 判断模块是否被禁用（见
      llm_content.py write_llm_sheets），若某测试设置
      LLM_MODULE_FAILURE[key]=FAIL_REASON_DISABLED 后未清理，同一 worker
      上后续 test_content_none 等测试的页签被跳过不写入，A2 占位符断言失败。
    """
    from src.python.llm.prompts import LLM_MODULE_FAILURE

    LLM_MODULE_FAILURE.clear()


@pytest.fixture(autouse=True)
def _mock_market_hours_api(monkeypatch):
    """禁用实时东方财富 push2 API 调用，使用内置默认值判断市场时段。

    `is_market_open()` 有 3 层降级（config → push2 API → 内置默认值），
    本 fixture 跳过第 2 层（push2 HTTP 请求），直接走内置 fallback 判断，
    避免每测试类首次调用时触发 ~1-3s 的网络请求。

    `_is_market_open_fallback()` 基于北京时区工作日 09:30-11:30+13:00-15:00
    判断，在测试环境中稳定返回预期值。不影响任何测试断言——测试依赖的是
    mock 返回的行情数据，而非真实市场状态。
    """
    monkeypatch.setattr(
        "src.python.core.market_hours._is_market_open_official",
        lambda _: None,
    )


def pytest_collection_modifyitems(config, items):
    """收集期校验 edge 标记与文件名的匹配约束。

    规则（§1.9 边缘测试文件隔离规范）：
      1. 任何带 @pytest.mark.edge 的测试，其所属文件必须以 _edge.py 结尾
      2. 任何 *_edge.py 文件中的测试，必须带有 @pytest.mark.edge 标记
      3. 违规项报错停止，不允许静默跳过
    """
    for item in items:
        fspath = str(item.fspath)
        has_edge_marker = item.get_closest_marker("edge") is not None
        is_edge_file = fspath.endswith("_edge.py")

        if has_edge_marker and not is_edge_file:
            raise pytest.UsageError(
                f"[!] 边缘测试文件隔离违规：\n"
                f"    测试项 {item.name} 带有 @pytest.mark.edge 标记，\n"
                f"    但所在文件 {fspath} 不以 _edge.py 结尾。\n"
                f"    请将该测试移至对应的 *_edge.py 文件，或移除 edge 标记。"
            )
        if is_edge_file and not has_edge_marker:
            raise pytest.UsageError(
                f"[!] 边缘测试文件隔离违规：\n"
                f"    文件 {fspath} 以 _edge.py 结尾，\n"
                f"    但其测试项 {item.name} 缺少 @pytest.mark.edge 标记。\n"
                f"    请为该测试添加 @pytest.mark.edge，或移出 _edge.py 文件。"
            )

    # ═══════════════════════════════════════════════════════════════
    # 标记遗漏警告（预防性）
    # ═══════════════════════════════════════════════════════════════
    # 检查每个测试是否至少有一个项目自定义标记。
    # 若没有，发出 PytestWarning 提醒补充 pytestmark 模块级变量。
    # 当前全部已有测试均已覆盖（通过 pytestmark 模块级变量），
    # 本检查旨在防止新增测试文件时遗漏标记。
    _warned_files: set[str] = set()
    for item in items:
        item_markers = {m.name for m in item.iter_markers()}
        has_custom = not _KNOWN_MARKERS.isdisjoint(item_markers)
        if has_custom or item_markers.issubset(_BUILTIN_MARKERS):
            continue
        fspath = str(item.fspath)
        if fspath not in _warned_files:
            _warned_files.add(fspath)
            warnings.warn(
                pytest.PytestWarning(
                    f"[!] 测试文件缺少项目标记（pytestmark）：{fspath}\n"
                    f"    请在文件顶部添加 pytestmark 变量，例如：\n"
                    f"    pytestmark = [pytest.mark.unit, pytest.mark.unit_report]\n"
                    f"    已知标记：{', '.join(sorted(_KNOWN_MARKERS))}"
                )
            )
