/* =========================================================
 * mobile.js — 小橘3号 移动端 MA1 骨架交互层（IIFE）
 * 规格来源：_dev/docs/design_mobile_ui.md（§四抽屉/§五输入条/§六滚动）
 *          design_mobile_architecture.md（§四键盘与视口硬规）
 * 范围：MA1 纯骨架交互。网络层（探活/SSE/sendMessage）属 MA2/MA3，
 *       此处不接任何 API；无 keydown 发送逻辑——移动端 Enter=换行（UI 文档 §五）。
 * 全局污染：唯一例外 window.__xj3Mobile（验收/MA3 调试钩子）。
 * ========================================================= */
(function () {
    'use strict';

    function $(sel) { return document.querySelector(sel); }

    /* ---------- 元素引用 ---------- */
    var drawer = $('#mDrawer');
    var scrim = $('#mScrim');
    var menuBtn = $('#mMenuBtn');
    var stream = $('#mStream');
    var fab = $('#mScrollBottomBtn');
    var input = $('#mInput');
    var sendBtn = $('#mSendBtn');
    var thinkToggle = $('#mThinkToggle');
    var thinkBody = $('#mThinkBody');
    var composer = $('#mComposer');
    var banner = $('#mConnBanner');
    var connDot = $('#mConnDot');
    var drawerConnDot = $('#mDrawerConnDot');
    var drawerConnText = $('#mDrawerConnText');

    /* ==================== 1. 抽屉开合（UI 文档 §四） ==================== */
    function openDrawer() {
        drawer.classList.add('is-open');
        scrim.classList.add('is-shown');
        drawer.setAttribute('aria-hidden', 'false');
        menuBtn.setAttribute('aria-expanded', 'true');
    }

    function closeDrawer() {
        drawer.classList.remove('is-open');
        scrim.classList.remove('is-shown');
        drawer.setAttribute('aria-hidden', 'true');
        menuBtn.setAttribute('aria-expanded', 'false');
    }

    function bindDrawer() {
        menuBtn.addEventListener('click', openDrawer);

        /* 关闭路①：点遮罩（scrim） */
        scrim.addEventListener('click', closeDrawer);

        /* 关闭路②：选中任意条目即关（M3 modal drawer 规范）。
         * 选中态即时反馈；待办/快捷指令等真实视图切换 MA4 接入（功能文档对照表）。 */
        var items = drawer.querySelectorAll('.drawer-item');
        Array.prototype.forEach.call(items, function (item) {
            item.addEventListener('click', function () {
                Array.prototype.forEach.call(items, function (it) {
                    var active = it === item;
                    it.classList.toggle('is-active', active);
                    if (active) { it.setAttribute('aria-current', 'page'); }
                    else { it.removeAttribute('aria-current'); }
                });
                closeDrawer();
            });
        });

        /* 关闭路③：横滑关闭。规格原文为"右滑回推"（UI 文档 §四），而 M3 官方
         * 手势定义是"滑向锚边"——左锚定抽屉即左滑。两向均收：按规格右滑可过
         * 验收，惯用左滑肌肉记忆也不落空。阈值 60px 且横向位移 > 纵向 1.2 倍，
         * 防抽屉内竖向滚动误触关闭。 */
        var tsX = null, tsY = null;
        drawer.addEventListener('touchstart', function (e) {
            if (e.touches.length !== 1) { tsX = null; return; }
            tsX = e.touches[0].clientX;
            tsY = e.touches[0].clientY;
        }, { passive: true });
        drawer.addEventListener('touchend', function (e) {
            if (tsX === null) { return; }
            var t = e.changedTouches[0];
            var dx = t.clientX - tsX;
            var dy = t.clientY - tsY;
            tsX = null;
            if (Math.abs(dx) >= 60 && Math.abs(dx) > Math.abs(dy) * 1.2) {
                closeDrawer();
            }
        }, { passive: true });

        /* Esc 关闭：桌面浏览器开发调试友好；移动端软键盘无 Esc，零副作用 */
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { closeDrawer(); }
        });
    }

    /* ==================== 2. 消息流 stick-to-bottom（UI 文档 §六） ==================== */
    var FOLLOW_THRESHOLD = 80;     /* 用户在底部 80px 阈值内视为跟随 */
    var following = true;

    function nearBottom() {
        return stream.scrollHeight - stream.scrollTop - stream.clientHeight <= FOLLOW_THRESHOLD;
    }

    function scrollToBottom(smooth) {
        if (smooth && typeof stream.scrollTo === 'function') {
            stream.scrollTo({ top: stream.scrollHeight, behavior: 'smooth' });
        } else {
            stream.scrollTop = stream.scrollHeight;
        }
    }

    function bindStream() {
        /* 上滑脱离底部 → 立即停止跟随 + 右下浮现"回到底部"；
         * 流式期间绝不强制拉回（强制滚动反模式，UI 文档 §六） */
        stream.addEventListener('scroll', function () {
            following = nearBottom();
            fab.classList.toggle('is-visible', !following);
        }, { passive: true });

        /* 点击回底：恢复跟随、悬浮钮消失 */
        fab.addEventListener('click', function () {
            following = true;
            fab.classList.remove('is-visible');
            scrollToBottom(true);
        });
    }

    /* ==================== 3. textarea 自增高（1→4 行封顶，超出内部滚动） ==================== */
    var INPUT_MAX_HEIGHT = 108;    /* 22px 行高 × 4 行 + 上下 padding 20px */

    function autoGrow() {
        input.style.height = 'auto';
        var h = Math.min(input.scrollHeight, INPUT_MAX_HEIGHT);
        input.style.height = h + 'px';
        input.style.overflowY = input.scrollHeight > INPUT_MAX_HEIGHT ? 'auto' : 'hidden';
    }

    function refreshSend() {
        /* 空内容禁用（灰态，CSS .round-btn--primary:disabled） */
        sendBtn.disabled = input.value.trim().length === 0;
    }

    function bindComposer() {
        input.addEventListener('input', function () {
            autoGrow();
            refreshSend();
        });
        /* Enter=换行不发送：不注册任何 keydown 发送逻辑（UI 文档 §五，
         * 手机软键盘 Enter 语义因输入法而异，发送只靠圆形发送按钮=移动共识）。
         * 发送动作本体属 MA2（sendMessage/SSE）。 */
        autoGrow();
        refreshSend();
    }

    /* ==================== 4. 思维链折叠条（默认收起，点击展开/收起） ==================== */
    function bindThink() {
        thinkToggle.addEventListener('click', function () {
            var open = thinkBody.hidden;       /* 即将切换到的状态 */
            thinkBody.hidden = !open;
            thinkToggle.classList.toggle('is-open', open);
            thinkToggle.setAttribute('aria-expanded', String(open));
            if (following) { scrollToBottom(false); }   /* 跟随态下展开保持吸底 */
        });
    }

    /* ==================== 5. visualViewport 键盘兜底（架构文档 §四.2） ====================
     * interactive-widget=resizes-content 未生效的环境（iOS Safari 等）下，键盘
     * 弹出不收缩布局视口 → 手动把输入条偏移到可视视口底沿。仅偏移输入条
     * （transform translateY），不缩放消息流。
     * 缩放/键盘区分：scale 偏离 1 = 捏合缩放不干预；遮挡量用 offsetTop 参与计算。 */
    function bindViewportFallback() {
        var vv = window.visualViewport;
        if (!vv) { return; }                   /* 存在才挂（架构文档硬规） */
        var MIN_KEYBOARD = 120;                /* 低于此值视为浏览器工具栏抖动而非键盘 */

        function applyViewport() {
            var scale = vv.scale || 1;
            if (Math.abs(scale - 1) > 0.01) {  /* 捏合缩放：不干预布局 */
                composer.style.transform = '';
                return;
            }
            var overlap = Math.round(window.innerHeight - (vv.offsetTop + vv.height));
            if (overlap > MIN_KEYBOARD) {
                composer.style.transform = 'translateY(-' + overlap + 'px)';
            } else {
                composer.style.transform = '';
            }
        }

        vv.addEventListener('resize', applyViewport);
        vv.addEventListener('scroll', applyViewport);
    }

    /* ==================== 6. 连接状态（MA3 探活接入；MA1 静态已连接） ====================
     * setConnState(false) → 顶部橙横幅出现 + 状态点转橙；
     * setConnState(true)  → 横幅消失（恢复自动消失）+ 状态点回绿。
     * MA1 无探活触发源（网络层 MA2），经 window.__xj3Mobile 人工触发验收。 */
    function setConnState(ok) {
        banner.hidden = ok;
        if (connDot) {
            connDot.classList.toggle('conn-dot--ok', ok);
            connDot.classList.toggle('conn-dot--warn', !ok);
            connDot.setAttribute('aria-label', ok ? '连接状态：已连接' : '连接状态：重连中');
            connDot.setAttribute('title', ok ? '已连接' : '重连中…');
        }
        if (drawerConnDot) {
            drawerConnDot.classList.toggle('conn-dot--ok', ok);
            drawerConnDot.classList.toggle('conn-dot--warn', !ok);
        }
        if (drawerConnText) { drawerConnText.textContent = ok ? '已连接' : '重连中…'; }
    }

    /* ==================== 初始化 ==================== */
    function init() {
        bindDrawer();
        bindStream();
        bindComposer();
        bindThink();
        bindViewportFallback();
        following = true;
        scrollToBottom(false);     /* 初始吸底 */
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    /* 验收/MA3 调试钩子（唯一全局出口） */
    window.__xj3Mobile = { setConnState: setConnState };
})();
