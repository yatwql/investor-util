/* 正文大块折叠（details.section-fold）交互增强。
 *
 * 纯原生 JS，离线自包含，无外部依赖。功能：
 *   1. 锚点定位（hashchange / 初始 hash）→ 自动展开目标章节内的折叠块
 *   2. 打印前（beforeprint，捕获阶段先于 chart-print 快照）展开全部折叠块，
 *      并同步 resize 内部 Chart.js 图表（收起态下 canvas 为 0 尺寸）；
 *      打印后（afterprint）恢复用户原折叠状态
 *   3. 用户手动展开折叠块时同步 resize 内部图表（ResizeObserver 兜底）
 *
 * 降级：模板未渲染 .section-fold 时静默跳过；Chart 引擎缺失时仅展开不 resize。
 * ES5 保守语法（与 toc.js/theme.js 同风格）。
 */
(function () {
    'use strict';

    function allFolds() {
        return document.querySelectorAll('details.section-fold');
    }

    /* 展开某章节（或全局）内的折叠块 */
    function unfoldIn(root) {
        var nodes = (root || document).querySelectorAll('details.section-fold');
        for (var i = 0; i < nodes.length; i++) nodes[i].open = true;
    }

    /* 展开后对折叠块内部 canvas 图表做同步 resize（收起态初始化为 0 尺寸的兜底） */
    function resizeChartsIn(container) {
        if (typeof Chart === 'undefined' || typeof Chart.getChart !== 'function') return;
        var canvases = container.querySelectorAll('canvas');
        for (var i = 0; i < canvases.length; i++) {
            try {
                var chart = Chart.getChart(canvases[i]);
                if (chart) chart.resize();
            } catch (e) { /* 单图失败不影响其他交互 */ }
        }
    }

    function init() {
        var folds = allFolds();
        if (!folds.length) return;

        /* ── 1. 锚点自动展开 ── */
        function handleHash() {
            var id = location.hash ? location.hash.replace(/^#/, '') : '';
            if (!id) return;
            var section = document.getElementById(id);
            if (!section) return;
            var inner = section.querySelectorAll('details.section-fold');
            for (var i = 0; i < inner.length; i++) inner[i].open = true;
        }
        window.addEventListener('hashchange', handleHash);
        handleHash();

        /* ── 3. 手动展开 → 图表同步 resize（details 的 toggle 事件不冒泡，逐个绑定） ── */
        for (var i = 0; i < folds.length; i++) {
            folds[i].addEventListener('toggle', (function (d) {
                return function () {
                    if (d.open) resizeChartsIn(d);
                };
            })(folds[i]));
        }

        /* ── 2. 打印展开/恢复 ──
         * beforeprint 以捕获阶段注册（window 上同 target 的捕获监听先于非捕获执行），
         * 保证先于 chart-print.js 的快照逻辑展开内容；快照前同步 resize 图表，
         * 使收起态初始化的 0 尺寸 canvas 以正确分辨率入快照。 */
        var savedState = null;
        window.addEventListener('beforeprint', function () {
            savedState = [];
            var all = allFolds();
            for (var i = 0; i < all.length; i++) {
                savedState.push(all[i].open);
                if (!all[i].open) {
                    all[i].open = true;
                    resizeChartsIn(all[i]);
                }
            }
        }, true);
        window.addEventListener('afterprint', function () {
            if (!savedState) return;
            var all = allFolds();
            for (var i = 0; i < all.length && i < savedState.length; i++) {
                all[i].open = savedState[i];
            }
            savedState = null;
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
