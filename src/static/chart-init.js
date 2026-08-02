/* chart-init.js — 6 张 Chart.js 图表初始化。
 *
 * 读取模板内联 chart-data（chart_datasets），为每个 <canvas id="chart_<key>">
 * 初始化对应图表。O1 隔离：每图独立 try/catch，单图失败仅 console.warn。
 * 守卫：Chart 引擎缺失（R21）或 canvas 不存在（模块隐藏）→ 跳过该图。
 * ES5 保守语法（R17/R22）。打印快照降级见 chart-print.js。
 * 键名契约（§4.11 O2）：portfolio_line / drawdown / category_doughnut /
 * industry_bar / penetration_bar / radar。行数预算 ≤300（§4.11 O4）。
 */

(function () {
  'use strict';

  /* ── 引擎守卫：chart.min.js 未加载 → 全部跳过 ───────── */
  if (typeof Chart === 'undefined') {
    return;
  }

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

  /* ── 登记图表实例（打印快照遍历，见 chart-print.js）── */
  function trackChart(chart) {
    if (window.ChartPrint && typeof window.ChartPrint.register === 'function') {
      window.ChartPrint.register(chart);
    }
    return chart;
  }

  /* ── 折线图通用配置（净值/回撤共用）────────────────── */
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
      options: lineOptions('净值')
    }));
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
    }));
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
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right', labels: { color: theme.text || '#333', boxWidth: 12 } },
          tooltip: { enabled: true }
        }
      }
    }));
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
          backgroundColor: d.backgroundColor || (theme.primary || '#2E75B6'),
          borderColor: d.borderColor || 'rgba(46,117,182,0.2)',
          borderWidth: 1
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { enabled: true }
        },
        scales: {
          x: { ticks: { color: theme.text }, grid: { color: theme.grid } },
          y: { ticks: { color: theme.text }, grid: { display: false } }
        }
      }
    }));
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
          backgroundColor: d.backgroundColor || 'rgba(46,117,182,0.75)',
          borderColor: d.borderColor || 'rgba(46,117,182,0.2)',
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
    }));
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
    }));
  }

  /* ── 注册初始化函数（O1：每个独立 try/catch）────────── */
  var inits = {
    portfolio_line: initPortfolioChart,
    drawdown: initDrawdownChart,
    category_doughnut: initCategoryDoughnut,
    industry_bar: initIndustryBar,
    penetration_bar: initPenetrationBar,
    radar: initRadarChart
  };

  Object.keys(inits).forEach(function (key) {
    var fn = inits[key];
    if (typeof fn !== 'function') return;
    try { fn(); } catch (e) {
      console.warn('[chart] 初始化失败（' + key + '）: ', e);
    }
  });
})();
