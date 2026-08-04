/* 左侧目录 TOC：展开/收起 + 滚动高亮当前章节。
 *
 * 纯原生 JS，离线自包含，无外部依赖。
 * 功能：
 *   1. 折叠/展开左侧目录栏（body.toc-collapsed），偏好持久化到 localStorage
 *   2. 点击目录项平滑滚动到对应章节（CSS scroll-behavior: smooth）
 *   3. 滚动时高亮当前所在章节（IntersectionObserver 滚动侦测）
 *
 * 降级：模板未渲染 #toc-sidebar 时静默跳过；无 IntersectionObserver 时仅保留
 * 折叠/展开功能，不报错。
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'investor-toc-collapsed';

    function init() {
        var sidebar = document.getElementById('toc-sidebar');
        if (!sidebar) return;

        var body = document.body;
        var collapseBtn = sidebar.querySelector('.toc-collapse-btn');
        var toggleBtn = document.getElementById('toc-toggle-btn');

        function setCollapsed(collapsed) {
            body.classList.toggle('toc-collapsed', collapsed);
            try {
                localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
            } catch (e) { /* file:// 或隐私模式下 localStorage 可能不可用，忽略 */ }
            var expanded = collapsed ? 'false' : 'true';
            if (collapseBtn) collapseBtn.setAttribute('aria-expanded', expanded);
            if (toggleBtn) toggleBtn.setAttribute('aria-expanded', expanded);
        }

        // 恢复上次折叠偏好
        var restored = false;
        try { restored = localStorage.getItem(STORAGE_KEY) === '1'; } catch (e) { /* ignore */ }
        if (restored) setCollapsed(true);

        if (collapseBtn) {
            collapseBtn.addEventListener('click', function () {
                setCollapsed(!body.classList.contains('toc-collapsed'));
            });
        }
        if (toggleBtn) {
            toggleBtn.addEventListener('click', function () {
                setCollapsed(false);
            });
        }

        // 滚动高亮当前章节
        var links = Array.prototype.slice.call(sidebar.querySelectorAll('a[href^="#sec-"]'));
        if (!links.length) return;
        var sections = links.map(function (a) {
            return document.getElementById(a.getAttribute('href').slice(1));
        }).filter(Boolean);

        function setActive(id) {
            links.forEach(function (a) {
                a.classList.toggle('active', a.getAttribute('href') === '#' + id);
            });
        }

        if ('IntersectionObserver' in window) {
            var io = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) setActive(entry.target.id);
                });
            }, { rootMargin: '-25% 0px -65% 0px' });
            sections.forEach(function (s) { io.observe(s); });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
