/* chart-config.js — Chart.js 全局配置（颜色/字体/主题常量）。
 *
 * 职责：
 *   - 统一定义配色（CSS 变量驱动，与模板暗色模式兼容）
 * - 关闭入场动画（报告是静态分析工具，无需动画，hover tooltip 不受影响）
 * - 限制 devicePixelRatio（低配机 + 高分屏优化，防止 4K 屏 canvas 像素爆炸）
 * - ES5 保守语法（兼容微信 X5 / 老旧 Chromium，不使用 const/let/箭头函数）
 *
 * 行数预算：≤150 行（§4.11 ）。本文件应保持纯净：不初始化任何图表。
 */
(function () {
  if (typeof Chart === 'undefined') {
    // 引擎未加载（chart.min.js 缺失/损坏），配置无意义，静默返回
    return;
  }

 /* ── 动画关闭 ─────────────────────────────────────── */
  Chart.defaults.animation = false;
  Chart.defaults.transitions.active.animation.duration = 0;

 /* ── DPR 限制───────────────────────────────── */
  // Chart.js v4 默认 DPR 上限 1.0（不再自动放大），显式设 1.5 在高分屏
  // 清晰度与低配机性能之间取平衡：折线/柱状对这种分辨率差异视觉无感。
  Chart.defaults.devicePixelRatio = 1.5;

  /* ── 字体 ────────────────────────────────────────────── */
  Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif';
  Chart.defaults.font.size = 11;

  /* ── 主题色（CSS 变量驱动，暗色模式预留）────────────── */
  // 模板在 :root 定义 --chart-* 变量；此处读取，未定义时用默认值兜底。
  function cssVar(name, fallback) {
    var val = '';
    try {
      val = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    } catch (e) {
      val = '';
    }
    return val || fallback;
  }

  window.ChartTheme = {
    primary: cssVar('--chart-primary', '#2E75B6'),
    secondary: cssVar('--chart-secondary', '#CC0000'),
    danger: cssVar('--chart-danger', '#CC0000'),
    dangerTransparent: cssVar('--chart-danger-transparent', 'rgba(204,0,0,0.15)'),
    success: cssVar('--chart-success', '#2E7D32'),
    warning: cssVar('--chart-warning', '#E68A00'),
    grid: cssVar('--chart-grid', 'rgba(128,128,128,0.15)'),
    text: cssVar('--chart-text', '#333333'),
    benchmarkColors: ['#CC0000', '#E68A00', '#2E7D32'],
 // 色盲安全 palette（§4.8）：蓝/橙/绿/紫/灰，避开纯红绿对比。
    // 资产构成 Doughnut（股票/基金/债券/现金/其他）等分色图统一使用。
    doughnutColors: ['#2E75B6', '#E68A00', '#2E7D32', '#8E44AD', '#7B8A9E'],
    // 柱状图区分配色（蓝/橙）：资产穿透 TOP10 章节的行业分布柱状图用蓝、
    // 穿透 TOP10 柱状图用橙，两个垂直柱状图靠色相明显区分。
    barColors: ['#2E75B6', '#E68A00']
  };

  /* ── 通用交互选项（渐进增强，桌面端友好）────────────── */
  window.ChartTheme.commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: { color: window.ChartTheme.text, boxWidth: 12 }
      },
      tooltip: {
        enabled: true
      }
    },
    scales: {
      x: { ticks: { color: window.ChartTheme.text }, grid: { color: window.ChartTheme.grid } },
      y: { ticks: { color: window.ChartTheme.text }, grid: { color: window.ChartTheme.grid } }
    }
  };
})();
