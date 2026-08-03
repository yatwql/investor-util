/* 主题切换：HTML 报告深/浅色模式（主题切换）。
 *
 * 纯原生 JS，离线自包含（R21），无外部依赖。与主报告、What-if 独立页共用。
 * 功能：
 *   1. 右上角浮动按钮切换深/浅色（根元素 data-theme="dark"），偏好持久化到 localStorage
 *   2. 切换后重读 CSS 变量更新 window.ChartTheme，遍历已创建图表刷新
 *      scales（ticks/grid/angleLines/pointLabels）与 legend 颜色并 update()
 *      —— ChartTheme 在 chart-config.js 加载时一次性烘焙进图表配置，需显式重绘
 *   3. 打印协调：beforeprint 捕获阶段（先于 chart-print.js 冒泡快照）若为深色，
 *      临时切浅色并同步重绘，使 toBase64Image 快照抓到浅色像素；afterprint 恢复
 *
 * 降级：localStorage 不可用（file:// 隐私模式）仅本次会话生效；window.Chart 缺失
 * 时跳过图表重绘，页面配色仍由 CSS 变量正常切换。
 *
 * ES5 保守语法（R17/R22）：var / function，无箭头函数。
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'investor-theme-dark';
    var isDark = false;
    var restoreAfterPrint = false;

    /* ── CSS 变量读取（与 chart-config.js 同款）────────── */
    function cssVar(name, fallback) {
        var val = '';
        try {
            val = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        } catch (e) {
            val = '';
        }
        return val || fallback;
    }

    /* ── 重读 CSS 变量更新 ChartTheme（in-place，保留数组色与 commonOptions）── */
    function refreshChartTheme() {
        var theme = window.ChartTheme;
        if (!theme) return;
        theme.primary = cssVar('--chart-primary', '#2E75B6');
        theme.secondary = cssVar('--chart-secondary', '#CC0000');
        theme.danger = cssVar('--chart-danger', '#CC0000');
        theme.dangerTransparent = cssVar('--chart-danger-transparent', 'rgba(204, 0, 0, 0.15)');
        theme.success = cssVar('--chart-success', '#2E7D32');
        theme.warning = cssVar('--chart-warning', '#E68A00');
        theme.grid = cssVar('--chart-grid', 'rgba(128, 128, 128, 0.15)');
        theme.text = cssVar('--chart-text', '#333333');
        var common = theme.commonOptions;
        if (common && common.plugins && common.plugins.legend) {
            common.plugins.legend.labels.color = theme.text;
        }
        if (common && common.scales) {
            common.scales.x.ticks.color = theme.text;
            common.scales.x.grid.color = theme.grid;
            common.scales.y.ticks.color = theme.text;
            common.scales.y.grid.color = theme.grid;
        }
    }

    /* ── 遍历已创建图表刷新配色并重绘 ─────────────────── */
    function applyThemeToCharts() {
        var theme = window.ChartTheme;
        if (!theme || typeof window.Chart === 'undefined' || typeof window.Chart.getChart !== 'function') {
            return;
        }
        var canvases = document.querySelectorAll('canvas');
        for (var i = 0; i < canvases.length; i++) {
            var chart = window.Chart.getChart(canvases[i]);
            if (!chart || !chart.options) continue;
            if (chart.options.plugins && chart.options.plugins.legend && chart.options.plugins.legend.labels) {
                chart.options.plugins.legend.labels.color = theme.text;
            }
            var scales = chart.options.scales;
            if (scales) {
                Object.keys(scales).forEach(function (name) {
                    var scale = scales[name];
                    if (!scale) return;
                    if (scale.ticks) scale.ticks.color = theme.text;
                    if (scale.grid) scale.grid.color = theme.grid;
                    if (scale.angleLines) scale.angleLines.color = theme.grid;
                    if (scale.pointLabels) scale.pointLabels.color = theme.text;
                });
            }
            if (typeof chart.update === 'function') {
                chart.update();  // animation=false（chart-config.js）下同步渲染
            }
        }
    }

    /* ── 应用主题（不写 localStorage，供打印临时切换复用）── */
    function applyTheme(dark) {
        isDark = dark;
        if (dark) {
            document.documentElement.setAttribute('data-theme', 'dark');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
        refreshChartTheme();
        applyThemeToCharts();
        updateButton();
    }

    /* ── 切换主题 + 持久化 ─────────────────────────────── */
    function setTheme(dark) {
        applyTheme(dark);
        try {
            localStorage.setItem(STORAGE_KEY, dark ? '1' : '0');
        } catch (e) { /* file:// 或隐私模式下 localStorage 可能不可用，忽略 */ }
    }

    /* ── 按钮图标/文案同步 ─────────────────────────────── */
    function updateButton() {
        var btn = document.getElementById('theme-toggle-btn');
        if (!btn) return;
        if (isDark) {
            btn.textContent = '☀️';
            btn.setAttribute('aria-label', '切换浅色模式');
            btn.setAttribute('title', '切换浅色模式');
        } else {
            btn.textContent = '🌙';
            btn.setAttribute('aria-label', '切换深色模式');
            btn.setAttribute('title', '切换深色模式');
        }
    }

    function init() {
        var btn = document.getElementById('theme-toggle-btn');
        if (!btn) return;

        // 恢复上次主题偏好（无记录默认浅色）
        var restored = false;
        try { restored = localStorage.getItem(STORAGE_KEY) === '1'; } catch (e) { /* ignore */ }
        applyTheme(restored);

        btn.addEventListener('click', function () {
            setTheme(!isDark);
        });

        // 打印协调：捕获阶段先于 chart-print.js 冒泡快照执行
        if (window.addEventListener) {
            window.addEventListener('beforeprint', function () {
                if (isDark) {
                    applyTheme(false);  // 临时切浅色 + 同步重绘，不写 localStorage
                    restoreAfterPrint = true;
                }
            }, true);
            window.addEventListener('afterprint', function () {
                if (restoreAfterPrint) {
                    applyTheme(true);
                    restoreAfterPrint = false;
                }
            }, true);
        }
    }

    window.ThemeSwitcher = {
        setTheme: setTheme,
        isDark: function () { return isDark; }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
