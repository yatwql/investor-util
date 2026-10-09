"""因子动物园目录评测工具（非生产代码，只住 scripts/；评测产物落 docs/tmp/factor-zoo/）。

先评测后立项：五个来源族各抽 5 个代表因子（共 25），三项指标——
A 字段可得率 ≥80%（≥20/25 因子可完整计算）、B 与既有信号族增量
（|ρ|<0.5 的因子占比 ≥30%、分母 ≥10）、C 全量计算耗时 ÷ 基线报告耗时 ≤20%。
A/B/C 全过 → 转正立项（另起实现计划）；任一不过 → 归档「已评估未采纳」。

纪律（设计文档约定）：
  - 取数只经既有 Provider Chain / 网关（fetch_with_incremental_fallback、
    fetch_index_history、fetch_valuation_fields、fetch_latest_indicator），禁裸调 provider；
  - 不 import report/llm，不向生产模块注入任何代码，生产侧零改动；
  - 穿透持仓股票池只读复用（不重算穿透逻辑），评测报告只落 docs/tmp/（git 忽略）；
  - 相关性复用 analysis.correlation 的共享 Pearson 原语（防评测口径与生产口径漂移）。

阶段（子命令，可单独重跑）：
  catalog  25 因子清单冻结（五族×5，字段需求与口径入 JSON）
  fields   穿透股票池冻结 + 逐因子字段可得性探测 → 指标 A
  signals  可计算因子近 1 年横截面信号 vs 既有信号族日频序列 → 指标 B
  timing   取数/计算耗时与缓存命中统计 + 真实报告耗时基线 → 指标 C
  verdict  三项指标汇总判定（阈值与口径预注册于判定书）
  all      依序执行全部阶段
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── 项目路径（脚本独立运行 / 动态加载时先把仓库根与 scripts/ 加入 sys.path） ──
_SCRIPTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPTS_DIR.parent
for _p in (str(_PROJECT_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _factor_zoo.catalog import (  # noqa: F401  原面 re-export（既有测试与调用方无需改动）
    BENCHMARK_INDEX,
    BETA_WINDOW,
    B_MIN_DENOM,
    CATALOG,
    COLD_SAMPLE_CODES,
    CORR_LOW,
    DAYS_PER_YEAR_TD,
    FAMILIES,
    FAMILY_DEGRADED,
    FAMILY_LABELS,
    FAMILY_MARKET_TEMPERATURE,
    FAMILY_NAMES,
    FAMILY_REBALANCE,
    FAMILY_STYLE_BETA,
    FAMILY_TAIL_VAR,
    FAMILY_VALUATION_PERCENTILE,
    FIELD_BARS,
    FIELD_FIN,
    FIELD_INDEX,
    FIELD_TYPES,
    FIELD_VAL,
    LOOKBACK_DAYS,
    MIN_CODES_PER_DAY,
    MIN_PAIRS,
    OUT_DIR_DEFAULT,
    STEP_NONZERO_FRACTION,
    TEMPERATURE_SLICE,
    THRESH_A,
    THRESH_B,
    THRESH_C,
    TYPE_COVERAGE,
    build_catalog,
    validate_catalog,
)
from _factor_zoo.probe import (  # noqa: F401  原面 re-export（既有测试与调用方无需改动）
    build_stock_pool,
    probe_bars,
    probe_fields,
    probe_fin_indicator,
    probe_index,
    probe_valuation,
    _extract_share_codes,
    _field_coverage,
    _required_value_key,
    _value_present,
)
from _factor_zoo.metrics import (  # noqa: F401  原面 re-export（既有测试与调用方无需改动）
    build_family_series,
    compute_factor_values,
    cross_sectional_series,
    evaluate_factor_correlation,
    judge,
    metric_a,
    metric_b,
    metric_c,
    read_report_baseline,
    _aligned_index_returns,
    _closes,
    _daily_returns,
    _delta,
    _ema,
    _is_step_signal,
    _mean,
    _pearson,
    _pearson_pvalue,
    _rolling_beta,
    _std,
)
from _factor_zoo.stages import (  # noqa: F401  原面 re-export（既有测试与调用方无需改动）
    json_cap_log,
    measure_cold_sample,
    stage_catalog,
    stage_fields,
    stage_signals,
    stage_timing,
    _pool_mean_returns,
    _read_json,
    _write_json,
)
from _factor_zoo.report import (  # noqa: F401  原面 re-export（既有测试与调用方无需改动）
    stage_verdict,
    _write_verdict_md,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="因子动物园目录评测（先评测后立项）")
    parser.add_argument("stage", choices=["catalog", "fields", "signals", "timing", "verdict", "all"])
    parser.add_argument(
        "--out-dir", default=str(OUT_DIR_DEFAULT), help="评测产物目录（默认 docs/tmp/factor-zoo，git 忽略）"
    )
    parser.add_argument("--refresh-pool", action="store_true", help="忽略冻结股票池重新构建（持仓变动后重评）")
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stages = ["catalog", "fields", "signals", "timing", "verdict"] if args.stage == "all" else [args.stage]
    for stage in stages:
        if stage == "catalog":
            stage_catalog(out_dir)
        elif stage == "fields":
            stage_fields(out_dir, refresh_pool=args.refresh_pool)
        elif stage == "signals":
            stage_signals(out_dir)
        elif stage == "timing":
            stage_timing(out_dir)
        elif stage == "verdict":
            stage_verdict(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
