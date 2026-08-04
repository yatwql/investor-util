/* chart-common.js — Chart.js 公共初始化 helper（chart-init.js 与调仓 What-if 页共用）。
 *
 * 提供 window.ChartCommon：
 *   trackChart(chart, key)   — 登记图表实例（打印快照 chart-print.js + 导出按钮 chart-export.js）
 *   lineOptions(yLabel)      — 折线图通用配置（净值/回撤/组合演进趋势共用）
 *   doughnutOptions(percent) — 环形图通用配置（图例右侧；percent=true 时 tooltip 显示百分比）
 *
 * 主题色统一取自 window.ChartTheme（chart-config.js，色盲安全 palette），
 * 避免 Python/JS 调色板漂移与各页复制配置。
 * 缺 ChartPrint/ChartExport 引擎时静默跳过登记（隔离，单页不加载也安全）。
 * ES5 保守语法。
 */
(function () {
  'use strict';

  var theme = window.ChartTheme || {};

  /* ── 登记图表实例（打印快照 + 导出按钮，见 chart-print.js / chart-export.js）── */
  function trackChart(chart, key) {
    if (window.ChartPrint && typeof window.ChartPrint.register === 'function') {
      window.ChartPrint.register(chart);
    }
    if (window.ChartExport && typeof window.ChartExport.register === 'function') {
      window.ChartExport.register(chart, key);
    }
    return chart;
  }

  /* ── 折线图通用配置（净值/回撤/演进趋势共用）────────────────── */
  function lineOptions(yLabel) {
    var opts = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: theme.text || '#333', boxWidth: 12 } },
        tooltip: { enabled: true }
      }
    };
    opts.scales = {
      x: { ticks: { color: theme.text }, grid: { color: theme.grid } },
      y: { ticks: { color: theme.text }, grid: { color: theme.grid } }
    };
    if (yLabel) {
      opts.scales.y.title = { display: true, text: yLabel, color: theme.text };
    }
    return opts;
  }

  /* ── 环形图通用配置（图例右侧；percent=true 时 tooltip 显示百分比）── */
  function doughnutOptions(percent) {
    var opts = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right', labels: { boxWidth: 12, color: theme.text || '#333' } },
        tooltip: { enabled: true }
      }
    };
    if (percent) {
      opts.plugins.tooltip.callbacks = {
        label: function (ctx) { return ' ' + ctx.label + ': ' + ctx.raw + '%'; }
      };
    }
    return opts;
  }

  window.ChartCommon = {
    trackChart: trackChart,
    lineOptions: lineOptions,
    doughnutOptions: doughnutOptions
  };
})();
