/* chart-init.js — 6 张核心 Chart.js 图表 + 3 张组合演进图表初始化。
 *
 * 核心 6 图读取模板内联 chart-data（chart_datasets）；组合演进 3 图
 * 读取独立内联数据段 #evolution-chart-data（evolution_data 契约 dict）。
 * O1 隔离：每图独立 try/catch，单图失败仅 console.warn。
 * 守卫：Chart 引擎（chart.min.js）或 ChartCommon（chart-common.js）缺失
 * （R21）→ 全部跳过；canvas 不存在（模块隐藏）→ 跳过该图。
 * ES5 保守语法（R17/R22）。打印快照降级见 chart-print.js。
 * 键名契约（§4.11 O2）：portfolio_line / drawdown / category_doughnut /
 * industry_bar / penetration_bar / radar；evolution_total / evolution_hhi /
 * evolution_top（组合演进扩展）。
 */

(function () {
  'use strict';

  /* ── 引擎守卫：chart.min.js / chart-common.js 未加载 → 全部跳过 ───────── */
  if (typeof Chart === 'undefined' || !window.ChartCommon) {
    return;
  }
  var common = window.ChartCommon;

  /* ── 读取模板内联数据 ───────────────────────────────── */
  var dataEl = document.getElementById('chart-data');
  var chartData = null;
  if (dataEl) {
    try { chartData = JSON.parse(dataEl.textContent || '{}'); } catch (e) {
      console.warn('[chart] chart-data 解析失败，图表全部跳过');
      return;
    }
  }
  if (!chartData || typeof chartData !== 'object') { chartData = {}; }

  var theme = window.ChartTheme || {};

  /* ── 登记图表实例 + 折线图配置：统一委托 chart-common.js ──
   * 薄封装保持调用点可读；实现与 What-if 页共用，消除配置复制。 */
  function trackChart(chart, key) {
    return common.trackChart(chart, key);
  }

  function lineOptions(yLabel) {
    return common.lineOptions(yLabel);
  }

  function doughnutOptions(percent) {
    return common.doughnutOptions(percent);
  }

  /* ── 危机区间着色插件（净值图 C20：2015/2018/2020/2022 阴影带）──
   * 数据来自 portfolio_line 数据集的可选 crisis 字段（chart_data_builder
   * Python 侧计算起止索引）。beforeDatasetsDraw 在数据集之下绘制半透明带。 */
  function buildCrisisBandPlugin(crisis) {
    return {
      id: 'crisisBands',
      beforeDatasetsDraw: function (chart, args, opts) {
        if (!crisis || !crisis.length) return;
        var area = chart.chartArea;
        if (!area) return;
        var xScale = chart.scales && chart.scales.x;
        if (!xScale) return;
        var ctx = chart.ctx;
        ctx.save();
        for (var bi = 0; bi < crisis.length; bi++) {
          var band = crisis[bi];
          var x0 = xScale.getPixelForValue(band.startIndex);
          var x1 = xScale.getPixelForValue(band.endIndex);
          if (x0 === undefined || x1 === undefined || x1 <= x0) continue;
          ctx.fillStyle = 'rgba(231,76,60,0.07)';
          ctx.fillRect(x0, area.top, x1 - x0, area.bottom - area.top);
        }
        ctx.restore();
      }
    };
  }

  /* ── 单图初始化函数（O1：每个独立 try/catch）────────── */

  function initPortfolioChart() {
    var ds = chartData['portfolio_line'];
    var el = document.getElementById('chart_portfolio_line');
    if (!ds || !ds.labels || !ds.datasets || !el) {
      return;
    }
    var datasets = ds.datasets.map(function (d) {
      return {
        label: d.label,
        data: d.data,
        borderColor: d.borderColor || (theme.primary || '#2E75B6'),
        backgroundColor: d.backgroundColor || 'rgba(46,117,182,0.1)',
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0.1,
        borderDash: d.degraded ? [5, 5] : undefined
      };
    });
    // 叠加基准指数（如有）
    if (ds.benchmarks && ds.benchmarks.length) {
      ds.benchmarks.forEach(function (bm, i) {
        datasets.push({
          label: bm.label || ('基准 ' + (i + 1)),
          data: bm.data,
          borderColor: bm.borderColor || ((theme.benchmarkColors || [])[i % 3] || '#CC0000'),
          borderWidth: 1.5,
          borderDash: [5, 3],
          pointRadius: 0,
          fill: false,
          tension: 0.1
        });
      });
    }
    trackChart(new Chart(el, {
      type: 'line',
      data: { labels: ds.labels, datasets: datasets },
      options: lineOptions('净值'),
      plugins: [buildCrisisBandPlugin(ds.crisis)]
    }), 'portfolio_line');
  }

  function initDrawdownChart() {
    var ds = chartData['drawdown'];
    var el = document.getElementById('chart_drawdown');
    if (!ds || !ds.labels || !ds.datasets || !el) {
      return;
    }
    var datasets = ds.datasets.map(function (d) {
      return {
        label: d.label,
        data: d.data,
        borderColor: d.borderColor || (theme.danger || '#CC0000'),
        backgroundColor: d.backgroundColor || (theme.dangerTransparent || 'rgba(204,0,0,0.15)'),
        borderWidth: 1.5,
        pointRadius: 0,
        fill: true,
        tension: 0.1,
        borderDash: d.degraded ? [5, 5] : undefined
      };
    });
    // 叠加基准回撤
    if (ds.benchmarks && ds.benchmarks.length) {
      ds.benchmarks.forEach(function (bm, i) {
        datasets.push({
          label: bm.label || ('基准 ' + (i + 1)),
          data: bm.data,
          borderColor: bm.borderColor || ['#9CA3AF', '#B0BEC5', '#90A4AE'][i % 3],
          borderWidth: 1,
          borderDash: [4, 3],
          pointRadius: 0,
          fill: false
        });
      });
    }
    trackChart(new Chart(el, {
      type: 'line',
      data: { labels: ds.labels, datasets: datasets },
      options: lineOptions('回撤 (%)')
    }), 'drawdown');
  }

  function initCategoryDoughnut() {
    var ds = chartData['category_doughnut'];
    var el = document.getElementById('chart_category_doughnut');
    if (!ds || !ds.labels || !ds.datasets || !el) {
      return;
    }
    var d = ds.datasets[0];
    trackChart(new Chart(el, {
      type: 'doughnut',
      data: {
        labels: ds.labels,
        datasets: [{
          data: d.data,
          backgroundColor: d.backgroundColor || (theme.doughnutColors || ['#2E75B6', '#E68A00', '#2E7D32', '#8E44AD', '#7B8A9E'])
        }]
      },
      options: doughnutOptions(false)
    }), 'category_doughnut');
  }

  function initIndustryBar() {
    var ds = chartData['industry_bar'];
    var el = document.getElementById('chart_industry_bar');
    if (!ds || !ds.labels || !ds.datasets || !el) {
      return;
    }
    var d = ds.datasets[0];
    trackChart(new Chart(el, {
      type: 'bar',
      data: {
        labels: ds.labels,
        datasets: [{
          label: d.label || '行业市值',
          data: d.data,
          backgroundColor: d.backgroundColor || theme.barColors[0] || theme.primary || '#2E75B6',
          borderColor: d.borderColor || theme.barColors[0] || 'rgba(46,117,182,0.2)',
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { enabled: true }
        },
        scales: {
          x: { ticks: { color: theme.text, maxRotation: 45 }, grid: { color: theme.grid } },
          y: { ticks: { color: theme.text }, grid: { color: theme.grid } }
        }
      }
    }), 'industry_bar');
  }

  function initPenetrationBar() {
    var ds = chartData['penetration_bar'];
    var el = document.getElementById('chart_penetration_bar');
    if (!ds || !ds.labels || !ds.datasets || !el) {
      return;
    }
    var d = ds.datasets[0];
    trackChart(new Chart(el, {
      type: 'bar',
      data: {
        labels: ds.labels,
        datasets: [{
          label: d.label || '穿透市值',
          data: d.data,
          backgroundColor: d.backgroundColor || theme.barColors[1] || 'rgba(230,138,0,0.75)',
          borderColor: d.borderColor || theme.barColors[1] || 'rgba(230,138,0,0.35)',
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { enabled: true }
        },
        scales: {
          x: { ticks: { color: theme.text, maxRotation: 45 }, grid: { color: theme.grid } },
          y: { ticks: { color: theme.text }, grid: { color: theme.grid } }
        }
      }
    }), 'penetration_bar');
  }

  function initRadarChart() {
    var ds = chartData['radar'];
    var el = document.getElementById('chart_radar');
    if (!ds || !ds.labels || !ds.datasets || !el) {
      return;
    }
    var d = ds.datasets[0];
    // 降级标注：risk_metrics/history_data 兜底时模板已渲染 note 文本 + 虚线描边（与 line 图契约一致）
    trackChart(new Chart(el, {
      type: 'radar',
      data: {
        labels: ds.labels,
        datasets: [{
          label: d.label || '量化指标',
          data: d.data,
          borderColor: d.borderColor || (theme.primary || '#2E75B6'),
          backgroundColor: d.backgroundColor || 'rgba(46,117,182,0.2)',
          borderWidth: 2,
          pointRadius: 3,
          borderDash: d.degraded ? [5, 5] : undefined
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { enabled: true }
        },
        scales: {
          r: {
            ticks: { display: false },
            grid: { color: theme.grid },
            angleLines: { color: theme.grid },
            pointLabels: { color: theme.text || '#333' }
          }
        }
      }
    }), 'radar');
  }

  /* ── 组合演进图表（读取独立内联数据段）────────── */

  function readEvolutionChartData() {
    var dataEl = document.getElementById('evolution-chart-data');
    if (!dataEl) return null;
    try {
      var d = JSON.parse(dataEl.textContent || '{}');
      if (!d || !d.periods || !d.periods.length) return null;
      return d;
    } catch (e) {
      console.warn('[chart] evolution-chart-data 解析失败，组合演进图表跳过');
      return null;
    }
  }

  function initEvolutionTotalChart() {
    var d = readEvolutionChartData();
    var el = document.getElementById('chart_evolution_total');
    if (!d || !el) return;
    var datasets = [
      { label: '总市值', data: d.total_value || [], borderColor: theme.primary || '#2E75B6', borderWidth: 2, pointRadius: 2, fill: false, tension: 0.1 },
      { label: '总盈亏', data: d.total_pnl || [], borderColor: '#E68A00', borderWidth: 2, pointRadius: 2, fill: false, tension: 0.1 }
    ];
    trackChart(new Chart(el, {
      type: 'line',
      data: { labels: d.periods, datasets: datasets },
      options: lineOptions('金额 (元)')
    }), 'evolution_total');
  }

  function initEvolutionHhiChart() {
    var d = readEvolutionChartData();
    var el = document.getElementById('chart_evolution_hhi');
    if (!d || !el) return;
    var hhi = (d.hhi || []).map(function (v) {
      return (v === null || v === undefined) ? null : v;
    });
    trackChart(new Chart(el, {
      type: 'line',
      data: {
        labels: d.periods,
        datasets: [{
          label: 'HHI 集中度',
          data: hhi,
          borderColor: theme.danger || '#CC0000',
          backgroundColor: 'rgba(204,0,0,0.1)',
          borderWidth: 2,
          pointRadius: 3,
          fill: true,
          tension: 0.1
        }]
      },
      options: lineOptions('HHI (0~1)')
    }), 'evolution_hhi');
  }

  function initEvolutionTopChart() {
    var d = readEvolutionChartData();
    var el = document.getElementById('chart_evolution_top');
    if (!d || !el) return;
    var top = (d.top_holdings || []).slice(0, 6);
    if (!top.length) return;
    var palette = ['#2E75B6', '#E68A00', '#2E7D32', '#8E44AD', '#CC0000', '#7B8A9E'];
    var datasets = top.map(function (h, i) {
      return {
        label: h.name || h.code,
        data: h.weights || [],
        borderColor: palette[i % palette.length],
        borderWidth: 2,
        pointRadius: 2,
        fill: false,
        tension: 0.1
      };
    });
    trackChart(new Chart(el, {
      type: 'line',
      data: { labels: d.periods, datasets: datasets },
      options: lineOptions('占比 (%)')
    }), 'evolution_top');
  }

  /* ── 注册初始化函数（O1：每个独立 try/catch）────────── */
  var inits = {
    portfolio_line: initPortfolioChart,
    drawdown: initDrawdownChart,
    category_doughnut: initCategoryDoughnut,
    industry_bar: initIndustryBar,
    penetration_bar: initPenetrationBar,
    radar: initRadarChart,
    evolution_total: initEvolutionTotalChart,
    evolution_hhi: initEvolutionHhiChart,
    evolution_top: initEvolutionTopChart
  };

  Object.keys(inits).forEach(function (key) {
    var fn = inits[key];
    if (typeof fn !== 'function') return;
    try { fn(); } catch (e) {
      console.warn('[chart] 初始化失败（' + key + '）: ', e);
    }
  });
})();
