"""敏感路径隔离的实现体 — 由 ``src/test/conftest.py`` 的 autouse fixture 调用。

conftest 保留 fixture 本体（装饰器/名称/文档串），实现体集中在此模块：把真实
config.json / 缓存 / 快照等落点重定向到 ``tmp_path``，并在两个真实落盘入口对
指向项目 ``reports/`` 的输出做透明重定向。
"""

from __future__ import annotations

import os

# 项目真实 reports 目录（默认配置 output_dir 指向这里；测试防线的重定向基准）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REAL_REPORTS_DIR = os.path.abspath(os.path.join(_PROJECT_ROOT, "reports"))


def seed_sensitive_path_isolation(monkeypatch, tmp_path, _doctor_probe_targets) -> None:
    """把 config.json / 缓存 / 快照等真实落点重定向到 tmp_path（语义见同名 conftest fixture 文档）。"""
    monkeypatch.setattr(
        "src.python.config._config_defaults._CONFIG_FILE",
        str(tmp_path / "data/config/config.json"),
    )
    # 测试敏感路径隔离: _CACHE_DIR 存在于 cache/ 子包中
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
    # 极简再平衡信号模块（行动章）静默期文件隔离（与 rebalance.py 共用同文件）
    monkeypatch.setattr(
        "src.python.analysis.simple_rebalance._SILENCE_FILE",
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
    # 指标熔断器持久化文件隔离（data/state/ 运行时状态目录 + 旧 data/cache/ 路径）
    monkeypatch.setattr(
        "src.python.analysis.circuit_breaker_wrapper._METRICS_BREAKER_FILE",
        str(tmp_path / "data/state/metrics_breaker.json"),
    )
    monkeypatch.setattr(
        "src.python.analysis.circuit_breaker_wrapper._LEGACY_METRICS_BREAKER_FILE",
        str(tmp_path / "data/cache/metrics_breaker.json"),
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
    # DataSinking 日配额计数文件隔离（provider 请求前写盘）
    monkeypatch.setattr(
        "src.python.providers.datasink._QUOTA_FILE",
        str(tmp_path / "data/state/datasink_quota.json"),
    )
    # decision_ledger.jsonl 决策跨期反思账本文件隔离（无单例，
    # 路径隔离即状态隔离——lessons_block/lessons_cache_suffix 按需读档现算）
    monkeypatch.setattr(
        "src.python.core.decision_ledger._DECISION_LEDGER_FILE",
        str(tmp_path / "data/state/decision_ledger.jsonl"),
    )
    # signal_ledger.jsonl 确定性数值信号账本文件隔离（同为无单例纯函数集，
    # 路径隔离即状态隔离——fold_signals/summary_block 按需读档现算）
    monkeypatch.setattr(
        "src.python.core.signal_ledger._SIGNAL_LEDGER_FILE",
        str(tmp_path / "data/state/signal_ledger.jsonl"),
    )
    # doctor 自检目录探针隔离：_check_writable 会**真实写盘**（写哨兵文件后删除），
    # 三个目标不重定向则每次自检测试都瞬写用户真实的 reports/、data/cache/、logs/，
    # 用例中途失败还会留下探针残留。目标目录取 session 级独立临时目录 —— 不落在
    # 各用例的 tmp_path 下（有用例断言 tmp_path 内无哨兵残留，见 test_doctor）。
    monkeypatch.setattr(
        "src.python.core.doctor._probe_targets",
        lambda: list(_doctor_probe_targets),
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
    # Web 上传临时目录隔离（data/holdings/uploads/ —— 上传文件落盘/清理的靶目录）
    monkeypatch.setattr(
        "src.python.web.upload._UPLOAD_DIR",
        str(tmp_path / "data/holdings/uploads"),
    )
    # Web 上传 file_id 注册表隔离（防跨测试 TTL/残留串扰）
    monkeypatch.setattr(
        "src.python.web.upload._file_registry",
        {},
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
    # 新闻去重锚点文件隔离（data/calibration/dedup_anchors.jsonl —— _flush_anchors
    # 追写目标；防测试运行污染真实校准数据，与 _auto_reset_anchor_state 配套）
    monkeypatch.setattr(
        "src.python.providers.news_dedup._ANCHOR_PATH",
        str(tmp_path / "data/calibration/dedup_anchors.jsonl"),
    )
    # 清空配置缓存，使下次 get_config() 使用新路径
    import src.python.config._config_defaults as _cfg_defaults
    import src.python.config._core as _cfg_core

    monkeypatch.setitem(
        _cfg_defaults._DEFAULT_CONFIG,
        "llm_settings_file",
        str(tmp_path / "data/config/llm_settings.json"),
    )
    # 测试敏感路径隔离: llm_key.json / llm_providers.json 路径同样 seed 到默认配置。
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
    # DataSinking 密钥文件路径 seed 到临时目录（凭据就绪判定与 provider 取数均读该键）
    monkeypatch.setitem(
        _cfg_defaults._DEFAULT_CONFIG,
        "data_key_file",
        str(tmp_path / "data/config/data_key.json"),
    )
    _cfg_core._clear_config_cache()


def apply_report_output_isolation(monkeypatch, tmp_path) -> None:
    """把指向项目真实 reports/ 的输出重定向到 tmp_path/reports（语义见同名 conftest fixture 文档）。"""
    redirect_to = str(tmp_path / "reports")

    def _redirect(output_dir):
        if not output_dir:
            return redirect_to
        try:
            abspath = os.path.abspath(output_dir)
        except (TypeError, ValueError):
            return output_dir
        if abspath == _REAL_REPORTS_DIR:
            return redirect_to
        return output_dir

    # Excel 落盘入口
    import src.python.report.excel_writer as _ew

    _orig_save_workbook = _ew.save_workbook

    def _wrapped_save_workbook(wb, output_dir="reports", *args, **kwargs):
        return _orig_save_workbook(wb, output_dir=_redirect(output_dir), *args, **kwargs)

    monkeypatch.setattr(_ew, "save_workbook", _wrapped_save_workbook)

    # HTML 落盘入口（定义方 + html_writer 调用方拷贝名）
    import src.python.report.html_save as _hs
    import src.python.report.html_writer as _hw

    _orig_save_html = _hs._save_html_report

    def _wrapped_save_html(html, output_dir, *args, **kwargs):
        return _orig_save_html(html, _redirect(output_dir), *args, **kwargs)

    monkeypatch.setattr(_hs, "_save_html_report", _wrapped_save_html)
    monkeypatch.setattr(_hw, "_save_html_report", _wrapped_save_html)
