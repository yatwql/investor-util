/* chart-print.js — Chart.js 打印降级（§4.5）。
 *
 * 职责：
 *   - 提供 window.ChartPrint.register(chart)：登记已创建的 Chart.js 实例
 *   - beforeprint → 每张图 toBase64Image 快照为 <img>（2x 分辨率），隐藏 canvas
 *   - afterprint → 移除 <img>，恢复 canvas 交互
 *   - 必须在 chart-init.js 之前加载（chart-init.js 初始化时立即 register）
 * - ES5 保守语法：var / function / 无箭头函数
 *
 * 独立成文件：保持 chart-init.js 纯净（≤300 行，§4.11 ），打印与初始化分离。
 */
(function () {
  'use strict';

  var charts = [];

  /* ── 登记图表实例（chart-init.js 在创建时调用）──────── */
  function register(chart) {
    if (chart && typeof chart.toBase64Image === 'function') {
      charts.push(chart);
    }
    return chart;
  }

  /* ── beforeprint：快照为静态 <img>，隐藏 canvas ────── */
  function snapshotForPrint() {
    charts.forEach(function (chart) {
      var canvas = chart.canvas;
      if (!canvas) return;
      var box = canvas.parentNode;
      if (!box) return;
      var img = document.createElement('img');
      img.src = chart.toBase64Image({ width: Math.round(canvas.width * 2) });
      img.style.maxWidth = '100%';
      img.style.display = 'block';
      img.alt = '图表打印快照';
      img.setAttribute('data-chart-print', '1');
      box.insertBefore(img, canvas.nextSibling);
      canvas.style.display = 'none';
    });
  }

  /* ── afterprint：移除 <img>，恢复 canvas 交互 ──────── */
  function restoreFromPrint() {
    charts.forEach(function (chart) {
      var canvas = chart.canvas;
      if (!canvas) return;
      if (canvas.style) canvas.style.display = '';
      var box = canvas.parentNode;
      if (!box) return;
      var img = box.querySelector('img[data-chart-print]');
      if (img && img.parentNode) {
        img.parentNode.removeChild(img);
      }
    });
  }

  if (window.addEventListener) {
    window.addEventListener('beforeprint', snapshotForPrint);
    window.addEventListener('afterprint', restoreFromPrint);
  }

  window.ChartPrint = { register: register };
})();
