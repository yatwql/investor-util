/* chart-export.js — 单图导出 PNG 按钮。
 *
 * 职责：
 *   - 提供 window.ChartExport.register(chart, key)：为每个 Chart.js 图表
 *     注入"导出PNG"按钮
 *   - 点击按钮 → chart.toBase64Image()（2x 分辨率）→ <a download> 下载 PNG
 *   - 必须在 chart-init.js 之前加载（chart-init.js 创建图表后立即 register）
 *   - ES5 保守语法（R17/R22）：var / function / 无箭头函数
 *
 * 按钮位置：存在 .chart-title 时追加到标题栏右侧；否则以绝对定位浮于
 * .chart-box 右上角（图表区固定高度，普通流式追加会溢出）。
 */
(function () {
  'use strict';

  /* ── 注入导出按钮 ───────────────────────────────────── */
  function addExportButton(chart, key) {
    if (!chart || !chart.canvas) return;
    var box = chart.canvas.parentNode;
    while (box && (!box.className || String(box.className).indexOf('chart-box') === -1)) {
      box = box.parentNode;
    }
    if (!box || box.querySelector('.chart-export-btn')) return;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'chart-export-btn';
    btn.textContent = '导出PNG';
    btn.setAttribute('aria-label', '导出图表为 PNG 图片');
    btn.onclick = function () {
      try {
        var a = document.createElement('a');
        a.href = chart.toBase64Image({ width: Math.round(chart.canvas.width * 2) });
        a.download = (key || 'chart') + '.png';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch (e) {
        console.warn('[chart] 导出 PNG 失败（' + key + '）: ', e);
      }
    };

    var titleEl = box.querySelector('.chart-title');
    if (titleEl) {
      titleEl.appendChild(btn);
    } else {
      box.appendChild(btn);
    }
  }

  window.ChartExport = {
    register: function (chart, key) {
      addExportButton(chart, key);
      return chart;
    }
  };
})();
