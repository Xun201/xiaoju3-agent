/* =========================================================
 * mobile.js — 小橘3号 移动端 MA2 网络接线层（IIFE）
 * 规格来源：_dev/docs/design_mobile_ui.md / design_mobile_architecture.md
 *          design_mobile_features.md（对照表：HITL 卡✅/协作面板❌）
 * MA2 范围：探活横幅 / 历史加载 / /api/chat/stream 流式（think+answer 双帧）
 *           / /api/events 总线（bus_reply+collab_msg HITL 卡）/ legacy 回退。
 * 拷贝复用策略（架构文档 §三）：网络与渲染函数定点拷贝自 console.js@ee66ef0，
 *   每函数带溯源注释；同步清单=_dev/mobile_sync_checklist.md；桌面 console.js 零改动。
 * 沿用 MA1：抽屉/stick-to-bottom/自增高/visualViewport 兜底/Enter=换行（无 keydown 发送）。
 * netfix（2026-10-31 P0-2 断连根治）：旧键迁移(xj3_api_base→xj3_mobile_base)/
 *   APK 空基址守卫(不发虚空探活)/配对门回迁(扫码+手输,22b0d12 形态)/
 *   三击标题诊断面板(#mCssDiag)/probeBase 换 XJ3Net 核心转发+诊断回调。
 * 全局污染：唯一例外 window.__xj3Mobile（验收/调试钩子）。
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
    var composer = $('#mComposer');
    var micBtn = $('#mMicBtn');
    var banner = $('#mConnBanner');
    var connDot = $('#mConnDot');
    var drawerConnDot = $('#mDrawerConnDot');
    var drawerConnText = $('#mDrawerConnText');

    /* ---------- API 基址（单点；MA3 接候选切换） ----------
     * 缺省 ''=同源相对路径（mobile.html 经 /console/mobile.html 同源托管，
     * 对齐 console.js 的相对路径策略——探活函数已按 base 参数化）。
     * netfix（2026-10-31 P0-2）旧键迁移：v2.2.x console.js 壳扫码配对写的
     * 是 xj3_api_base（fce91ee:console.js:124/180 考古实锤），换 mobile 壳
     * 后该值成孤儿数据（新壳零读取零迁移）→ 覆盖升级即 BASE='' 断连。
     * 迁移规则：新键为空而旧键有值 → 一次性迁入 xj3_mobile_base；幂等=
     * 新键已有值永不重迁（saved 先行早退），旧键保留不删（回滚旧 APK
     * 配对不丢）。 */
    var BASE_SRC = '默认空（同源相对）';
    var BASE = (function () {
        try {
            var saved = localStorage.getItem('xj3_mobile_base');
            if (saved) { BASE_SRC = '已保存地址（xj3_mobile_base）'; return saved; }
            var legacy = localStorage.getItem('xj3_api_base');
            if (legacy) {
                try { localStorage.setItem('xj3_mobile_base', legacy); } catch (e) { /* 忽略 */ }
                BASE_SRC = '旧配对键迁移（xj3_api_base→xj3_mobile_base）';
                return legacy;
            }
        } catch (e) { /* 隐私模式忽略 */ }
        var injected = (typeof window.__XJ3_MOBILE_BASE === 'string')
            ? window.__XJ3_MOBILE_BASE : '';
        if (injected) { BASE_SRC = '注入（window.__XJ3_MOBILE_BASE）'; }
        return injected;
    })();

    /* APK 环境判定（22b0d12 console.js 同款口径 window.Capacitor）：
     * 空基址守卫/配对门只在 Capacitor 壳内启用——浏览器同源托管
     * （/console/mobile.html）BASE='' 是合法形态，不许弹门。 */
    function inApk() {
        try {
            return !!(window.Capacitor && (
                typeof window.Capacitor.isNativePlatform !== 'function' ||
                window.Capacitor.isNativePlatform()));
        } catch (e) { return false; }
    }

    /* ---------- 网络诊断（netfix：诊断面板数据源） ----------
     * probeBase 只回 bool 的旧口径下，失败类别全被 catch 吞掉——断连排查
     * 只能瞎猜。此处集中记录，供三击顶栏标题呼出的诊断面板（#mCssDiag
     * 复用）与 window.__xj3Mobile.diag（验收/调试钩子）展示。 */
    var DIAG = {
        base: BASE, baseSrc: BASE_SRC,
        env: inApk() ? 'APK（Capacitor）' : '浏览器',
        last: null                       /* 最近一次探活 {url,ts,ok,err} */
    };
    function diagRecord(entry) {
        DIAG.last = entry;
        diagRender();
    }
    function diagRender() {
        var d = document.getElementById('mCssDiag');
        if (!d || d.style.display === 'none' || !DIAG.last) { return; }
        var t = DIAG.last.ts instanceof Date ? DIAG.last.ts : new Date();
        d.textContent = '[小橘3号 网络诊断]\n'
            + '环境: ' + DIAG.env + ' | 能力级: '
            + (document.body && document.body.getAttribute('data-caps')) + '\n'
            + '基址: ' + (DIAG.base || '（空=同源相对）') + '\n'
            + '来源: ' + DIAG.baseSrc + '\n'
            + '最近探活: GET ' + DIAG.last.url + ' @'
            + t.toLocaleTimeString('zh-CN', { hour12: false }) + '\n'
            + '结果: ' + (DIAG.last.ok ? '✅ ok' : '❌ ' + DIAG.last.err);
    }

    /* ==================== 1. 抽屉开合（MA1 原样） ==================== */
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
        scrim.addEventListener('click', closeDrawer);
        var items = drawer.querySelectorAll('.drawer-item');
        Array.prototype.forEach.call(items, function (item) {
            item.addEventListener('click', function () {
                Array.prototype.forEach.call(items, function (it) {
                    var active = it === item;
                    it.classList.toggle('is-active', active);
                    if (active) { it.setAttribute('aria-current', 'page'); }
                    else { it.removeAttribute('aria-current'); }
                });
                /* MA2.1（队长真机反馈"侧边栏按钮全死"）：每个条目必须有真实
                 * 去处——聊天=回消息流，其余=打开对应面板（待办/快捷指令/
                 * 连接设置/关于）。只关抽屉无下文=体感死按钮。 */
                handleNav(item.dataset.nav);
                closeDrawer();
            });
        });
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
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { closeDrawer(); }
        });
    }

    /* ==================== 2. 消息流 stick-to-bottom（MA1 原样） ==================== */
    var FOLLOW_THRESHOLD = 80;
    var following = true;

    function streamAppend(row) {
        var s = streamEl();
        if (!s) { return; }        /* 流缺失=静默跳过（极端时序防御） */
        s.appendChild(row);
    }

    function streamEl() {
        /* 惰性解析+自愈（排雷批）：内联后元素捕获时序曾致 null——
         * 调用时重查 DOM，仍无则如实返回 null 由调用方防御 */
        if (stream && stream.isConnected) { return stream; }
        stream = document.getElementById('mStream');
        return stream;
    }

    function nearBottom() {
        var s = streamEl();
        if (!s) { return true; }   /* 无流=默认跟随（不做强制滚动） */
        return s.scrollHeight - s.scrollTop - s.clientHeight <= FOLLOW_THRESHOLD;
    }

    function scrollToBottom(smooth) {
        var s = streamEl();
        if (!s) { return; }
        if (smooth && typeof s.scrollTo === 'function') {
            s.scrollTo({ top: s.scrollHeight, behavior: 'smooth' });
        } else {
            s.scrollTop = s.scrollHeight;
        }
    }

    function followIfPinned() {
        /* 渲染管线统一出口：仅跟随态吸底，流式绝不强制拉扯 */
        if (following) { scrollToBottom(false); }
    }

    function bindStream() {
        streamEl().addEventListener('scroll', function () {
            following = nearBottom();
            fab.classList.toggle('is-visible', !following);
        }, { passive: true });
        fab.addEventListener('click', function () {
            following = true;
            fab.classList.remove('is-visible');
            scrollToBottom(true);
        });
    }

    /* ==================== 3. textarea 自增高（MA1 原样） ==================== */
    var INPUT_MAX_HEIGHT = 108;

    function autoGrow() {
        input.style.height = 'auto';
        var h = Math.min(input.scrollHeight, INPUT_MAX_HEIGHT);
        input.style.height = h + 'px';
        input.style.overflowY = input.scrollHeight > INPUT_MAX_HEIGHT ? 'auto' : 'hidden';
    }

    function refreshSend() {
        sendBtn.disabled = generating || input.value.trim().length === 0;
    }

    function bindComposer() {
        input.addEventListener('input', function () {
            autoGrow();
            refreshSend();
        });
        /* Enter=换行不发送（UI 文档 §五）；发送只靠按钮 */
        sendBtn.addEventListener('click', function () {
            var text = input.value.trim();
            if (!text || generating) { return; }
            input.value = '';
            autoGrow();
            refreshSend();
            sendMessage(text);
        });
        autoGrow();
        refreshSend();
    }

    /* ==================== 4. visualViewport 键盘兜底（MA1 原样） ==================== */
    function bindViewportFallback() {
        var vv = window.visualViewport;
        if (!vv) { return; }
        var MIN_KEYBOARD = 120;
        function applyViewport() {
            if (!composer) { return; }   /* head 阶段元素未就绪防御（排雷批） */
            var scale = vv.scale || 1;
            if (Math.abs(scale - 1) > 0.01) {
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

    /* ==================== 5. 连接状态（MA1 setConnState + MA2 探活触发源） ==================== */
    function setConnState(ok) {
        banner.hidden = ok;
        /* 能力分级（2026-10-31 队长指令：移动端自适应降级）：探活状态唯一落点
         * 追加 body 能力属性切换——可达='l2' 全面板；不可达='l0' 重型模块
         * 由 CSS [data-needs-server] 统一门控隐藏。初值保守 'l0'（mobile.html
         * body 标签），探活成功才升 'l2'。探活/重载逻辑本体零改动。 */
        if (document.body) {
            document.body.setAttribute('data-caps', ok ? 'l2' : 'l0');
        }
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

    /* ==================== 6. 探活自愈（拷贝自 console.js@ee66ef0 probeBase L2687 /
     *                        xj3LinkCheck L2739，移动端 MA2 只探当前 base 不换址） ==================== */
    function probeBase(base) {
        /* netfix：探活唯一实现=XJ3Net.probeBase（防拷贝漂移红线，桌面
         * console.js:2689 同款转发形态）；本层只挂诊断记录（失败类别
         * 透出）。URL/5s 超时/j.status==='ok' 判据口径零改动。 */
        return XJ3Net.probeBase(base, 5000, diagRecord);
    }

    var linkTimer = null;
    var failStreak = 0;               /* 连续探活失败计数（无效基址兜底触发器） */
    function linkCheck() {
        /* 空基址守卫（netfix）：APK 内 BASE='' 时同源 /api/health 探活会
         * 被 Capacitor WebViewLocalServer '**' 通配+html5mode 劫持成
         * 200+index.html → r.json() 必炸 → 永假 → 15s 一轮的永久离线
         * 死循环（探活请求根本没出 WebView，手机网络再好也无济于事；
         * bf4b6a8 真机 ERR_CONNECTION_REFUSED@http://localhost/ 同根）。
         * 守卫=不发虚空请求，直接离线态+唤起配对门——绝不静默滑进永久
         * 离线。浏览器同源托管不触发（inApk() 门控）。 */
        if (!BASE && inApk()) {
            setConnState(false);
            updateBannerText();
            ensurePairGate();
            return;
        }
        probeBase(BASE).then(function (ok) {
            var was = !banner.hidden;
            failStreak = ok ? 0 : (failStreak + 1);
            setConnState(ok);
            updateBannerText();
            if (ok) { flushDrafts(); }   /* 恢复在线→补发草稿箱（含启动遗留） */
            /* 无效基址兜底（netfix）：APK 内地址连续 3 轮探活失败（约45s）
             * =基址失联——唤起配对门重连。===3 只在跨越阈值那一次触发
             * （用户取消门后不再骚扰，探活恢复即复位）；浏览器端不弹，
             * 横幅+草稿箱口径照旧。 */
            if (!ok && inApk() && failStreak === 3) { ensurePairGate(); }
        });
    }
    function startLinkCheck() {
        linkCheck();                                   /* 启动即探一次 */
        linkTimer = setInterval(linkCheck, 15000);     /* 15s 周期（同桌面） */
    }

    /* ==================== 6.8 配对门（netfix：22b0d12 console.js 形态回迁） ====================
     * v2.2.x 旧壳的 pairProbe『断连自动弹门扫码秒连』+扫码主路径在换 mobile
     * 壳时全灭（grep 零痕迹，考古实锤）——断连只剩菜单三层深的手输自救，
     * 体感即"永久离线"。本节按 22b0d12 既有形态回迁：扫码主路径
     * （getUserMedia 后摄+BarcodeDetector）+手输折叠兜底+xiaoju3://connect
     * 载荷解析+逐候选探活（XJ3Net.probeBase 唯一实现，首个 ok 落键重载）。
     * jsQR 逐帧兜底未回迁：mobile.html 全内联零外部脚本（打包纪律），
     * 安卓 System WebView 现代版本 BarcodeDetector 原生可用；缺席时
     * 明示走手动输入，不装死。 */
    function parsePairingPayload(text) {
        /* 解析二维码载荷：xiaoju3://connect?ips=a,b&port=5003（新）/
         * http://ip:port 直填（兼容手输）。返回候选 base 列表。 */
        var s = String(text || '').trim();
        if (!s) { return []; }
        var m = s.match(/^xiaoju3:\/\/connect\?([^#]+)/);
        if (m) {
            var q = new URLSearchParams(m[1]);
            var ips = (q.get('ips') || '').split(',')
                .map(function (x) { return x.trim(); }).filter(Boolean);
            var port = q.get('port') || '5003';
            return ips.map(function (ip) {
                return 'http://' + ip + ':' + port;
            });
        }
        if (/^https?:\/\//.test(s)) { return [s.replace(/\/+$/, '')]; }
        return [];
    }

    function pairConnect(candidates) {
        /* 逐候选探活，首个 /api/health ok 的写入 xj3_mobile_base 并重载
         * （键=新壳唯一键；与 BASE 迁移链同键，无双写）。 */
        var i = 0;
        var gate = document.getElementById('mPairGate');
        var statusEl = gate ? gate.querySelector('.pair-status') : null;
        function setStatus(t) { if (statusEl) { statusEl.textContent = t; } }
        function next() {
            if (i >= candidates.length) {
                setStatus('扫到的地址都连不上——请确认电脑端小橘在线，或改用手动输入');
                return;
            }
            var base = candidates[i++];
            setStatus('正在连接 ' + base + ' …');
            XJ3Net.probeBase(base).then(function (ok) {
                if (!ok) { next(); return; }
                try { localStorage.setItem('xj3_mobile_base', base); } catch (e) { /* 忽略 */ }
                window.location.reload();
            });
        }
        next();
    }

    function openPairScanner() {
        /* 扫码器（22b0d12 形态）：getUserMedia 后摄 + BarcodeDetector 原生
         * 解码，180ms 逐帧轮询；取消键收场。 */
        var overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;z-index:10000;background:rgba(15,23,42,0.6);'
            + 'display:flex;align-items:center;justify-content:center;padding:24px;';
        var card = document.createElement('div');
        card.style.cssText = 'background:#fff;border-radius:16px;padding:18px;'
            + 'width:min(86vw,340px);color:#1f2937;font-size:14px;';
        var titleEl = document.createElement('div');
        titleEl.style.cssText = 'font-size:16px;font-weight:700;margin-bottom:10px;';
        titleEl.textContent = '对准电脑上的二维码';
        var video = document.createElement('video');
        video.setAttribute('playsinline', '');
        video.muted = true;
        video.style.cssText = 'width:100%;border-radius:10px;background:#111827;';
        var hint = document.createElement('div');
        hint.style.cssText = 'font-size:12px;color:#6b7280;margin-top:8px;';
        hint.textContent = '打开后请稍候——首次会请求相机权限';
        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'panel-btn';
        cancelBtn.style.cssText = 'margin-top:12px;';
        cancelBtn.textContent = '取消';
        card.appendChild(titleEl);
        card.appendChild(video);
        card.appendChild(hint);
        card.appendChild(cancelBtn);
        overlay.appendChild(card);
        document.body.appendChild(overlay);
        var stopped = false;
        var streamRef = null;
        function stop() {
            stopped = true;
            if (streamRef) { streamRef.getTracks().forEach(function (t) { t.stop(); }); }
            if (overlay.parentNode) { overlay.remove(); }
        }
        cancelBtn.addEventListener('click', stop);
        function onDecode(text) {
            if (stopped) { return; }
            var candidates = parsePairingPayload(text);
            if (candidates.length) {
                stop();
                pairConnect(candidates);
            } else {
                hint.textContent = '二维码不是小橘的配对码，请重试';
            }
        }
        function run() {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                hint.textContent = '此设备不支持相机，请手动输入地址';
                return;
            }
            navigator.mediaDevices.getUserMedia(
                { video: { facingMode: 'environment' }, audio: false })
                .then(function (s) {
                    streamRef = s;
                    video.srcObject = s;
                    return video.play();
                })
                .then(function () {
                    var Detector = window.BarcodeDetector || null;
                    var detector = null;
                    if (Detector) {
                        try { detector = new Detector({ formats: ['qr_code'] }); }
                        catch (e) { detector = null; }
                    }
                    if (!detector) {
                        hint.textContent = '此 WebView 不支持扫码识别，请手动输入地址';
                        return;
                    }
                    (function loop() {
                        if (stopped) { return; }
                        if (video.readyState >= 2) {
                            detector.detect(video).then(function (bars) {
                                var text = bars && bars.length ? bars[0].rawValue : null;
                                if (text) { onDecode(text); return; }
                                setTimeout(loop, 180);
                            }).catch(function () { setTimeout(loop, 180); });
                            return;
                        }
                        setTimeout(loop, 180);
                    })();
                })
                .catch(function () {
                    hint.textContent = '相机打开失败（权限未授予）——请用手动输入';
                });
        }
        run();
    }

    function showPairGate() {
        /* 首启/断连配对门：扫码为主（像正经 App），手动输入折叠兜底；
         * 可"暂不连接"离线用（L0 底线：聊天+草稿箱永存，门绝不锁死）。 */
        var overlay = document.createElement('div');
        overlay.id = 'mPairGate';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', '连接小橘主机');
        overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(15,23,42,0.55);'
            + 'display:flex;align-items:center;justify-content:center;padding:24px;';
        var card = document.createElement('div');
        card.style.cssText = 'background:#fff;border-radius:16px;padding:22px 18px;'
            + 'width:min(86vw,340px);box-shadow:0 12px 40px rgba(15,23,42,0.25);'
            + 'color:#1f2937;font-size:14px;';
        var titleEl = document.createElement('div');
        titleEl.style.cssText = 'font-size:17px;font-weight:700;margin-bottom:6px;';
        titleEl.textContent = '连接小橘';
        var msgEl = document.createElement('p');
        msgEl.style.cssText = 'margin:0 0 6px;color:#6b7280;line-height:1.5;';
        msgEl.textContent = '扫电脑端「连接手机」二维码，或手动输入主机地址。'
            + '消息会先存草稿箱，连上后自动发送。';
        var statusEl = document.createElement('div');
        statusEl.className = 'pair-status';
        statusEl.style.cssText = 'min-height:18px;margin:0 0 10px;color:#b45309;'
            + 'font-size:12px;line-height:1.4;';
        var scanBtn = document.createElement('button');
        scanBtn.type = 'button';
        scanBtn.className = 'panel-btn';
        scanBtn.style.cssText = 'display:flex;align-items:center;justify-content:center;gap:8px;'
            + 'font-weight:600;background:#203170;border-color:#203170;color:#fff;';
        scanBtn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" '
            + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            + 'stroke-linejoin="round" aria-hidden="true"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>'
            + '<span>扫码连接</span>';
        scanBtn.addEventListener('click', function () {
            if (overlay.parentNode) { overlay.remove(); }
            openPairScanner();
        });
        var manual = document.createElement('details');
        manual.style.cssText = 'margin-top:12px;font-size:12px;color:#6b7280;';
        var summary = document.createElement('summary');
        summary.style.cssText = 'cursor:pointer;';
        summary.textContent = '手动输入地址（备用）';
        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'hitl-input';
        input.placeholder = 'http://192.168.31.50:5003';
        input.setAttribute('aria-label', '服务器地址');
        var saveBtn = document.createElement('button');
        saveBtn.type = 'button';
        saveBtn.className = 'panel-btn';
        saveBtn.textContent = '保存并连接';
        saveBtn.addEventListener('click', function () {
            var base = input.value.trim().replace(/\/+$/, '');
            if (!base) { return; }
            try { localStorage.setItem('xj3_mobile_base', base); } catch (e) { /* 忽略 */ }
            window.location.reload();
        });
        var laterBtn = document.createElement('button');
        laterBtn.type = 'button';
        laterBtn.className = 'panel-btn';
        laterBtn.style.cssText = 'border:none;background:none;color:#6b7280;min-height:36px;';
        laterBtn.textContent = '暂不连接（离线使用，消息存草稿箱）';
        laterBtn.addEventListener('click', function () {
            pairGateDismissed = true;   /* 记住选择：15s 周期探活不再自动弹门 */
            if (overlay.parentNode) { overlay.remove(); }
        });
        manual.appendChild(summary);
        manual.appendChild(input);
        manual.appendChild(saveBtn);
        card.appendChild(titleEl);
        card.appendChild(msgEl);
        card.appendChild(statusEl);
        card.appendChild(scanBtn);
        card.appendChild(manual);
        card.appendChild(laterBtn);
        overlay.appendChild(card);
        document.body.appendChild(overlay);
    }

    var pairGateDismissed = false;   /* 用户点过「暂不连接」→ 周期探活不再骚扰 */
    function ensurePairGate(force) {
        if (!force && pairGateDismissed) { return; }   /* 尊重离线使用的选择 */
        if (document.getElementById('mPairGate')) { return; }   /* 去重：同时至多一扇门 */
        showPairGate();
    }

    /* ==================== 7. 富文本渲染（拷贝自 console.js@ee66ef0：
     *                        escapeHtml / renderRich L3540 / renderRichTables L3579） ==================== */
    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function renderRichTables(text) {
        /* 表格块 → 圆角容器内横滑表格（表格只在气泡内滑动，页面级永不横滚） */
        var lines = String(text).split('\n');
        var out = [];
        var i = 0;
        function isRow(l) { return /^\s*\|.*\|\s*$/.test(l); }
        function isSep(l) { return /^\s*\|[\s:\-|]+\|\s*$/.test(l); }
        while (i < lines.length) {
            if (isRow(lines[i]) && i + 1 < lines.length && isSep(lines[i + 1])) {
                var head = lines[i].split('|').slice(1, -1);
                i += 2;
                var rows = [];
                while (i < lines.length && isRow(lines[i])) {
                    rows.push(lines[i].split('|').slice(1, -1));
                    i += 1;
                }
                var html = '<div class="md-table-wrap"><table><thead><tr>';
                head.forEach(function (c) { html += '<th>' + escapeHtml(c.trim()) + '</th>'; });
                html += '</tr></thead><tbody>';
                rows.forEach(function (r) {
                    html += '<tr>';
                    r.forEach(function (c) { html += '<td>' + escapeHtml(c.trim()) + '</td>'; });
                    html += '</tr>';
                });
                html += '</tbody></table></div>';
                out.push(html);
            } else {
                out.push(escapeHtml(lines[i]));
                i += 1;
            }
        }
        return out.join('\n');
    }

    function renderRich(text) {
        /* 转义 → 行内 code/粗体/标题/换行（console.js renderRich 精简镜像） */
        var s = escapeHtml(text);
        s = s.replace(/`([^`\n]+)`/g, '<code class="md-code">$1</code>');
        s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
        s = s.replace(/^### (.+)$/gm, '<div class="md-h">$1</div>');
        return s;
    }

    function renderFinal(text) {
        /* done 后正文富化：表格优先，其余走 renderRich（逐行保留换行结构） */
        if (/^\s*\|.*\|\s*$/m.test(text) && text.indexOf('|') !== -1) {
            return renderRichTables(text);
        }
        return renderRich(text);
    }

    /* ==================== 8. 消息构建器（镜像 console.js appendUserMessage L3838 /
     *                        appendBotMessage L4765 的移动端精简形态） ==================== */
    var ICON_BRAIN = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 18V5"/><path d="M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4"/><path d="M17.598 6.5A3 3 0 1 0 12 5a3 3 0 1 0-5.598 1.5"/><path d="M17.997 5.125a4 4 0 0 1 2.526 5.77"/><path d="M18 18a4 4 0 0 0 2-7.464"/><path d="M19.967 17.483A4 4 0 1 1 12 18a4 4 0 1 1-7.967-.517"/><path d="M6 18a4 4 0 0 1-2-7.464"/><path d="M6.003 5.125a4 4 0 0 0-2.526 5.77"/></svg>';
    var ICON_CHEV = '<svg class="think-chevron" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>';
    var ICON_CLIP = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg>';
    var ICON_CHECK = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';
    var ICON_X = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

    function appendUserMessage(text) {
        var row = document.createElement('div');
        row.className = 'msg-row msg-row--me';
        var b = document.createElement('div');
        b.className = 'bubble bubble--me';
        b.textContent = text;                     /* 用户消息 textContent=零 XSS（桌面同源纪律） */
        row.appendChild(b);
        streamAppend(row);
        followIfPinned();
        return b;
    }

    /* <think> 块剥离（拷贝自 console.js splitThinkBlock L3640 的行为契约：
     * 成对/游离标签容错剥离，正文空则给占位） */
    function splitThinkBlock(text) {
        var think = null;
        var body = String(text == null ? '' : text);
        var m = body.match(/<think>([\s\S]*?)<\/think>/);
        if (m) {
            think = m[1];
            body = body.replace(m[0], '');
        } else if (/<think>/.test(body)) {
            var idx = body.indexOf('<think>');
            think = body.slice(idx + 7);
            body = body.slice(0, idx);
        }
        body = body.replace(/^\s+|\s+$/g, '');
        return { think: think, body: body || (think !== null ? '（已思考完毕）' : text) };
    }

    function buildThinkStatic(thinkText, elapsedLabel) {
        /* 静态折叠卡（done 后形态）：默认收起、点击展开 */
        var row = document.createElement('div');
        row.className = 'msg-row msg-row--them';
        var card = document.createElement('div');
        card.className = 'think-card';
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'think-toggle';
        btn.setAttribute('aria-expanded', 'false');
        btn.innerHTML = ICON_BRAIN + '<span>' + escapeHtml(
            elapsedLabel || '已思考') + '</span>' + ICON_CHEV;
        var bodyEl = document.createElement('div');
        bodyEl.className = 'think-body';
        bodyEl.hidden = true;
        var ol = document.createElement('ol');
        ol.className = 'think-steps';
        String(thinkText || '').split('\n').forEach(function (line) {
            var t = line.replace(/^\s+/, '').replace(/^[-*\d.、\s]+/, '');
            if (!t) { return; }
            var li = document.createElement('li');
            li.textContent = t;
            ol.appendChild(li);
        });
        if (!ol.children.length) {
            var li = document.createElement('li');
            li.textContent = '（无分步内容）';
            ol.appendChild(li);
        }
        bodyEl.appendChild(ol);
        btn.addEventListener('click', function () {
            var open = bodyEl.hidden;
            bodyEl.hidden = !open;
            btn.classList.toggle('is-open', open);
            btn.setAttribute('aria-expanded', String(open));
            followIfPinned();
        });
        card.appendChild(btn);
        card.appendChild(bodyEl);
        row.appendChild(card);
        return row;
    }

    function appendBotMessage(text, source) {
        /* 静态 bot 气泡（历史/bus_reply 用）：think 剥离→折叠卡+富文本正文 */
        var parts = splitThinkBlock(text);
        var row = document.createElement('div');
        row.className = 'msg-row msg-row--them';
        if (parts.think !== null) {
            row.appendChild(buildThinkStatic(parts.think, '已思考'));
        }
        var b = document.createElement('div');
        b.className = 'bubble bubble--them';
        b.innerHTML = renderFinal(parts.body);
        if (source) {
            var tag = document.createElement('span');
            tag.className = 'msg-src';
            tag.textContent = source;
            b.appendChild(document.createElement('br'));
            b.appendChild(tag);
        }
        row.appendChild(b);
        streamAppend(row);
        followIfPinned();
        return b;
    }

    function appendErrorBubble(text) {
        var row = document.createElement('div');
        row.className = 'msg-row msg-row--them';
        var b = document.createElement('div');
        b.className = 'bubble bubble--them bubble--error';
        b.textContent = text;
        row.appendChild(b);
        streamAppend(row);
        followIfPinned();
        return b;
    }

    /* ==================== 9. 流式对话（拷贝自 console.js@ee66ef0：
     *   sendMessageStream L5042 / pump L5227 / handleEvent L5155 / ensureThinkCard L5080） ==================== */
    var generating = false;
    /* 看门狗/总闸已移交 XJ3Net.chatStream（双端唯一实现） */

    function el(tag, cls, textContent) {
        var e = document.createElement(tag);
        if (cls) { e.className = cls; }
        if (textContent !== undefined) { e.textContent = textContent; }
        return e;
    }

    /* 乐观挂载 think 卡：骨架→think delta 逐行→done 折叠（桌面 .think-live 移动形态） */
    function ensureLiveThink() {
        var row = el('div', 'msg-row msg-row--them');
        var card = el('div', 'think-card think-card--live');
        var btn = el('button', 'think-toggle is-open');
        btn.type = 'button';
        btn.setAttribute('aria-expanded', 'true');
        btn.innerHTML = ICON_BRAIN + '<span class="think-label">🧠 小橘正在思考…</span>' + ICON_CHEV;
        var bodyEl = el('div', 'think-body');
        var ol = el('ol', 'think-steps');
        var sk1 = el('li', 'think-skeleton');
        var sk2 = el('li', 'think-skeleton');
        ol.appendChild(sk1);
        ol.appendChild(sk2);
        bodyEl.appendChild(ol);
        btn.addEventListener('click', function () {
            var open = bodyEl.hidden;
            bodyEl.hidden = !open;
            btn.classList.toggle('is-open', open);
            btn.setAttribute('aria-expanded', String(open));
            followIfPinned();
        });
        card.appendChild(btn);
        card.appendChild(bodyEl);
        row.appendChild(card);
        streamAppend(row);
        followIfPinned();
        return {
            row: row, card: card, btn: btn, label: btn.querySelector('.think-label'),
            ol: ol, startedAt: Date.now(),
            addLine: function (text) {
                if (sk1.parentNode) { sk1.remove(); sk2.remove(); }
                var t = String(text || '').replace(/^\s+/, '').replace(/^[-*\d.、\s]+/, '');
                if (!t) { return; }
                ol.appendChild(el('li', 'think-line', t));
                while (ol.children.length > 40) { ol.removeChild(ol.firstChild); }
                followIfPinned();
            },
            finish: function () {
                var secs = Math.round((Date.now() - this.startedAt) / 100) / 10;
                this.label.textContent = '已思考（' + secs + ' 秒）';
                if (sk1.parentNode) { sk1.remove(); sk2.remove(); }
                var self = this;
                setTimeout(function () {
                    bodyEl.hidden = true;
                    self.btn.classList.remove('is-open');
                    self.btn.setAttribute('aria-expanded', 'false');
                    followIfPinned();
                }, 1500);
            }
        };
    }

    /* ==================== 8.5 离线草稿箱（红线加固：断网不发虚空） ====================
     * 断网时消息进 localStorage 队列（有序持久），探活恢复后按序自动补发；
     * 横幅文案带队列数=离线模式可视化（红线 A2，2026-10-31 队长最高指令）。 */
    var DRAFT_KEY = 'xj3_draft_queue';
    function draftAll() {
        try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || '[]'); }
        catch (e) { return []; }
    }
    function draftSave(q) {
        try { localStorage.setItem(DRAFT_KEY, JSON.stringify(q)); } catch (e) { /* 隐私模式忽略 */ }
    }
    function draftPush(text) {
        var q = draftAll();
        q.push({ text: text, ts: Date.now() });
        draftSave(q);
        updateBannerText();
    }
    function draftCount() { return draftAll().length; }
    function updateBannerText() {
        var span = banner ? banner.querySelector('span') : null;
        if (!span) { return; }
        if (!BASE && inApk()) {
            /* netfix：APK 空基址≠"重连中"（没有可重连的目标）——明示
             * 未连接主机+草稿箱兜底+配对门引导，不装死不瞎转。 */
            span.textContent = '未连接主机：消息自动存草稿箱——扫码或输入地址连接后发送';
            return;
        }
        var n = draftCount();
        span.textContent = n
            ? '离线模式：' + n + ' 条消息存于草稿箱，恢复后自动发送'
            : '连接断开，正在重连…';
    }

    function flushDrafts() {
        var q = draftAll();
        if (!q.length || generating) { return; }
        var item = q[0];
        toast('网络恢复，补发草稿箱消息（' + q.length + ' 条）…');
        sendRaw(item.text, true, function (ok) {
            if (ok) {
                q.shift();
                draftSave(q);
                if (q.length) { flushDrafts(); }
                else { updateBannerText(); toast('草稿箱已清空'); }
            } else {
                updateBannerText();      /* 补发失败→留队列等下一轮探活 */
            }
        });
    }

    function sendMessage(text) {
        if (generating) { return; }
        /* 红线 A2：断网不发虚空——探活失败即入草稿箱（恢复自动补发）；
         * netfix：APK 空基址=无目标可发，同走草稿箱+唤起配对门（横幅
         * 文案引导），绝不向本地资产服务器发虚空请求。 */
        if ((banner && !banner.hidden) || (!BASE && inApk())) {
            draftPush(text);
            appendUserMessage(text + '  [已存草稿箱]');
            if (!BASE && inApk()) {
                toast('未连接主机：消息已存草稿箱，连接后自动发送');
                ensurePairGate(true);   /* 发送动作=明确要连，无视 dismissal */
            } else {
                toast('当前离线：消息已存草稿箱，恢复后自动发送');
            }
            return;
        }
        sendRaw(text, false, null);
    }

    function sendRaw(text, skipUserBubble, doneCb) {
        var failed = false;          /* 单次上报口径：失败只在 finally 报一次 */
        if (generating) { return; }
        generating = true;
        refreshSend();
        if (!skipUserBubble) { appendUserMessage(text); }   /* 草稿补发不重复画用户气泡 */
        var think = ensureLiveThink();
        var answerEl = null;

        function ensureAnswer() {
            if (answerEl) { return answerEl; }
            var row = el('div', 'msg-row msg-row--them');
            var b = el('div', 'bubble bubble--them');
            var content = el('div', 'bubble-content');
            b.appendChild(content);
            row.appendChild(b);
            streamAppend(row);
            answerEl = content;
            followIfPinned();
            return content;
        }

        var accAnswer = '';
        var accThink = '';
        var finished = false;

        function handleEvent(etype, data) {
            if (etype === 'think' && data && data.delta) {
                accThink += data.delta;
                think.addLine(data.delta);
            } else if (etype === 'tool' && data && data.name) {
                think.addLine('调用工具：' + data.name);
            } else if (etype === 'answer' && data && data.delta) {
                accAnswer += data.delta;
                ensureAnswer().textContent = accAnswer;
                followIfPinned();
            } else if (etype === 'done') {
                finished = true;
                var parts = splitThinkBlock((data && data.reply) || accAnswer);
                var row = answerEl ? answerEl.parentNode.parentNode : null;
                /* 乐观卡退役：done 后由静态折叠卡接位（E2E 实锤：不移除
                 * 会留"正在思考…"僵尸卡） */
                if (think.row && think.row.parentNode) { think.row.remove(); }
                if (parts.think !== null && row) {
                    var stat = buildThinkStatic(parts.think, '已思考');
                    row.parentNode.insertBefore(stat, row);
                }
                if (answerEl) {
                    answerEl.innerHTML = renderFinal(parts.body);
                    if (data && data.source) {
                        answerEl.appendChild(document.createElement('br'));
                        var tag = el('span', 'msg-src', data.source);
                        answerEl.appendChild(tag);
                    }
                } else if (parts.body) {
                    appendBotMessage((data && data.reply) || parts.body, data && data.source);
                }
                followIfPinned();
            } else if (etype === 'error') {
                finished = true;
                if (think.row && think.row.parentNode) { think.row.remove(); }
                appendErrorBubble('❌ ' + ((data && data.error) || '请求失败，稍后再试'));
                followIfPinned();
                failed = true;                   /* 服务端错误帧=草稿补发失败，留队重试 */
            }
        }

        XJ3Net.chatStream({
            message: text,
            base: BASE,
            onFrame: function (etype, data) {
                try { handleEvent(etype, data); } catch (e) { /* 帧处置异常不上抛（移动口径） */ }
            },
        }).catch(function (e) {
            if (finished) { return; }
            if (e && e.xj3Watchdog) {
                /* 看门狗中断：报错不转 legacy（桌面同款口径） */
                if (think.row && think.row.parentNode) { think.row.remove(); }
                appendErrorBubble('❌ ⏱️ 长时间无响应已自动中断——请直接重试');
                followIfPinned();
                failed = true;
                return;
            }
            /* 流式失败 → legacy 单帧回退（拷贝自 console.js sendMessageLegacy L5281） */
            fetch(BASE + '/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            }).then(function (r) { return r.json(); }).then(function (j) {
                if (j && j.code === 200 && j.data && j.data.reply) {
                    var d = j.data;
                    handleEvent('done', { reply: d.reply, source: d.source });
                } else {
                    appendErrorBubble('❌ ' + ((j && j.error) || '请求失败，稍后再试'));
                }
            }).catch(function () {
                appendErrorBubble('❌ 网络异常——请检查与主机的连接');
                followIfPinned();
                failed = true;
            });
        }).finally(function () {
            /* 看门狗/总闸已移交 XJ3Net 核心（唯一实现）——此处只管生成态收尾 */
            generating = false;
            refreshSend();
            if (doneCb) { doneCb(!failed); }   /* 单次上报（成功=补发成功出队） */
        });
    }

    /* ==================== 10. 历史加载（拷贝自 console.js loadHistory L4852） ==================== */
    function loadHistory() {
        if (!BASE && inApk()) { return; }   /* 空基址守卫：不去撞资产服务器 */
        fetch(BASE + '/api/history').then(function (r) { return r.json(); })
            .then(function (res) {
                if (!res || res.code !== 200 || !res.data || !res.data.messages) { return; }
                var msgs = res.data.messages;
                msgs.forEach(function (m, idx) {
                    setTimeout(function () {
                        if (m.role === 'user') { appendUserMessage(m.content); }
                        else { appendBotMessage(m.content, m.source); }
                    }, Math.min(idx * 45, 400));
                });
            })
            .catch(function () { /* 历史失败不阻塞主流程（探活横幅已示警） */ });
    }

    /* ==================== 11. 事件总线（拷贝自 console.js initUiEvents L4457：
     *                        bus_reply L4497 + collab_msg L4526 的移动端形态） ==================== */
    function initUiEvents() {
        if (typeof EventSource !== 'function') { return; }
        /* 排雷批：指数退避重连（2s 起、30s 封顶+抖动）——多 tab/后台线程
         * 同时连 /api/events 时不再以固定 3s 硬重试打后端；恢复即清退避。 */
        var es = null;
        var esBackoff = 2000;
        var esTimer = null;
        function esConnect() {
            /* 空基址守卫（netfix）：APK 内 SSE 同样吃资产服务器劫持的亏
             * （200+HTML→es.onerror→被反复打回离线，探活偶然通过也会被
             * 打穿）——BASE 空时不建连；配对成功即 reload 重建。 */
            if (!BASE && inApk()) { return; }
            es = new EventSource(BASE + '/api/events');
            es.onopen = function () {
                esBackoff = 2000;         /* 恢复清退避 */
                linkCheck();
            };
            es.onerror = function () {
                setConnState(false);      /* SSE 断=连接异常，横幅示警 */
                try { es.close(); } catch (e) { /* 忽略 */ }
                es = null;
                if (esTimer) { clearTimeout(esTimer); }
                var delay = esBackoff + Math.floor(Math.random() * 800);
                esBackoff = Math.min(30000, esBackoff * 2);
                esTimer = setTimeout(esConnect, delay);
            };
            es.addEventListener('bus_reply', busReplyHandler);
            es.addEventListener('collab_msg', collabMsgHandler);
        }
        var busReplyHandler = function (ev) {
            try {
                var d = JSON.parse(ev.data);
                if (d && d.reply) { appendBotMessage(d.reply, d.source); }
            } catch (e) { /* 坏帧丢弃 */ }
        };
        var collabMsgHandler = function (ev) {
            try {
                var m = JSON.parse(ev.data);
                if (m && m.hitl) { renderHitlCard(m); }
            } catch (e) { /* 坏帧丢弃 */ }
        };
        esConnect();
    }

    /* ==================== 12. HITL 确认卡（镜像 console.js renderCollabMsg L4542 /
     *                        sendCollab L4663；移动端=老板手机审批面） ==================== */
    function renderHitlCard(m) {
        var options = (m.options && m.options.length) ? m.options
            : ['同意', '驳回', '暂缓', '修改方案'];
        var summary = String(m.summary || m.preview || '小橘请求确认').slice(0, 120);
        var row = el('div', 'msg-row msg-row--them');
        var card = el('div', 'hitl-card');
        card.setAttribute('role', 'group');
        card.setAttribute('aria-label', '操作确认卡');
        var head = el('div', 'hitl-head');
        head.innerHTML = ICON_CLIP;
        head.appendChild(el('span', 'hitl-title', '⏸ 需要老板确认'));
        card.appendChild(head);
        card.appendChild(el('p', 'hitl-summary', summary));
        var actions = el('div', 'hitl-actions');
        var done = false;

        function settle() {
            done = true;
            Array.prototype.forEach.call(actions.querySelectorAll('button'), function (b) {
                b.disabled = true;
            });
            customInput.disabled = true;
        }
        function sendCollab(text) {
            if (done) { return; }
            settle();
            fetch(BASE + '/api/collab/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })   /* 契约=body.text（桌面 sendCollab 同款） */
            }).then(function (r) { return r.json(); })
                .then(function (j) {
                    var ok = j && (j.code === 200 || j.code === 0);
                    card.appendChild(el('div', 'hitl-result',
                        ok ? '✅ 已写回总线，等待小橘执行' : '❌ 写回失败，请到桌面控制台处理'));
                })
                .catch(function () {
                    card.appendChild(el('div', 'hitl-result', '❌ 网络异常，请重试或到桌面处理'));
                });
            followIfPinned();
        }
        options.forEach(function (opt) {
            var b = el('button', 'hitl-btn');
            b.type = 'button';
            if (opt === '同意') { b.className += ' hitl-btn--approve'; }
            if (opt === '驳回') { b.className += ' hitl-btn--reject'; }
            b.innerHTML = (opt === '同意' ? ICON_CHECK : (opt === '驳回' ? ICON_X : ''))
                + '<span>' + escapeHtml(opt) + '</span>';
            b.addEventListener('click', function () {
                sendCollab('选择了：' + opt + ' — ' + summary.slice(0, 60));
            });
            actions.appendChild(b);
        });
        card.appendChild(actions);
        var customInput = el('input', 'hitl-input');
        customInput.type = 'text';
        customInput.placeholder = '自定义回复（可选）…';
        customInput.setAttribute('aria-label', '自定义回复');
        customInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                var v = customInput.value.trim();
                if (v) { sendCollab('自定义指令：' + v); }
            }
        });
        card.appendChild(customInput);
        row.appendChild(card);
        streamAppend(row);
        followIfPinned();
    }

    /* ==================== 6.5 面板系统（MA2.1：抽屉条目的真实去处） ====================
     * 待办=真实列表（/api/todos + done/reopen）；快捷指令=chip 直发；
     * 连接设置=连接信息+刷新+清缓存；关于=版本+免责。 */
    function handleNav(nav) {
        if (nav === 'chat') { closePanel(); return; }
        openPanel(nav);
    }

    var panel = $('#mPanel');
    var panelTitle = $('#mPanelTitle');
    var panelBody = $('#mPanelBody');
    var panelBack = $('#mPanelBack');
    if (panelBack) { panelBack.addEventListener('click', closePanel); }

    function openPanel(nav) {
        if (!panel) { return; }
        panel.hidden = false;
        var titles = { todo: '待办', quick: '快捷指令', settings: '连接设置', about: '关于' };
        panelTitle.textContent = titles[nav] || '';
        panelBody.textContent = '';
        if (nav === 'todo') { renderTodoPanel(panelBody); }
        else if (nav === 'quick') { renderQuickPanel(panelBody); }
        else if (nav === 'settings') { renderSettingsPanel(panelBody); }
        else if (nav === 'about') { renderAboutPanel(panelBody); }
    }

    function closePanel() {
        if (panel) { panel.hidden = true; panelBody.textContent = ''; }
    }

    function toast(text, isError) {
        var t = el('div', 'toast' + (isError ? ' toast--err' : ''), text);
        document.body.appendChild(t);
        setTimeout(function () { t.classList.add('is-shown'); }, 30);
        setTimeout(function () {
            t.classList.remove('is-shown');
            setTimeout(function () { t.remove(); }, 300);
        }, 2600);
    }

    /* ---- 待办面板：/api/todos + done/reopen ---- */
    function renderTodoPanel(body) {
        body.textContent = '加载中…';
        fetch(BASE + '/api/todos').then(function (r) { return r.json(); })
            .then(function (res) {
                body.textContent = '';
                if (!res || res.code !== 200 || !res.data || !res.data.todos) {
                    body.appendChild(el('div', 'panel-hint', '待办加载失败'));
                    return;
                }
                var todos = res.data.todos || [];
                var groups = [
                    { key: 'pending', label: '未完成', items: todos.filter(function (t) { return t.status === 'pending'; }) },
                    { key: 'done', label: '已完成', items: todos.filter(function (t) { return t.status !== 'pending'; }) },
                ];
                groups.forEach(function (g) {
                    if (!g.items.length) { return; }
                    body.appendChild(el('div', 'panel-group', g.label + '（' + g.items.length + '）'));
                    g.items.forEach(function (t) {
                        var row = el('button', 'todo-row' + (g.key === 'done' ? ' todo-row--done' : ''));
                        row.type = 'button';
                        var dot = el('span', 'todo-dot');
                        var txt = el('span', 'todo-text', String(t.content || t.text || t.title || ''));
                        row.appendChild(dot);
                        row.appendChild(txt);
                        if (t.priority) {
                            row.appendChild(el('span', 'todo-pri', String(t.priority)));
                        }
                        row.addEventListener('click', function () {
                            var isDone = g.key === 'done';
                            var action = isDone ? 'reopen' : 'done';
                            fetch(BASE + '/api/todos/' + t.id + '/' + action, { method: 'POST' })
                                .then(function (r) { return r.json(); })
                                .then(function (j) {
                                    if (j && j.code === 200) { renderTodoPanel(body); }
                                    else { toast((j && j.error) || '操作失败', true); }
                                })
                                .catch(function () { toast('网络异常', true); });
                        });
                        body.appendChild(row);
                    });
                });
                if (!todos.length) {
                    body.appendChild(el('div', 'panel-hint', '待办清单是空的——对我说"记个待办"就行。'));
                }
            })
            .catch(function () { body.textContent = '待办加载失败（网络异常）'; });
    }

    /* ---- 快捷指令面板：chip 直发（对齐桌面 PLUGIN_QUICK_ACTIONS 可用子集） ---- */
    function renderQuickPanel(body) {
        body.appendChild(el('div', 'panel-hint', '点一下=直接对小橘说这句话：'));
        var grid = el('div', 'quick-grid');
        [
            { label: '记个待办', text: '帮我记个待办：' },
            { label: '系统自检', text: '系统自检' },
            { label: '掷骰子', text: '掷骰子' },
            { label: '帮我选股', text: '帮我选股' },
        ].forEach(function (q) {
            var chip = el('button', 'quick-chip', q.label);
            chip.type = 'button';
            chip.addEventListener('click', function () {
                closePanel();
                if (q.text.endsWith('：')) {
                    input.value = q.text;      /* 需要补内容的指令：填入输入框 */
                    input.focus();
                    autoGrow();
                    refreshSend();
                } else {
                    sendMessage(q.text);       /* 完整指令：直接发 */
                }
            });
            grid.appendChild(chip);
        });
        body.appendChild(grid);
    }

    /* ---- 连接设置面板 ---- */
    function renderSettingsPanel(body) {
        body.textContent = '';
        var info = el('div', 'panel-card');
        info.appendChild(el('div', 'panel-line', '连接地址：' + (BASE || '同源（当前页面托管地址）')));
        var online = !banner.hidden ? '重连中' : '已连接';
        info.appendChild(el('div', 'panel-line', '连接状态：' + online));
        body.appendChild(info);
        var addrWrap = el('div', 'panel-card');
        addrWrap.appendChild(el('div', 'panel-line', '服务器地址（APK/跨机场景填写，如 http://192.168.31.x:5003）：'));
        var addrInput = el('input', 'hitl-input');
        addrInput.type = 'text';
        addrInput.value = BASE;
        addrInput.placeholder = '留空=同源';
        addrInput.setAttribute('aria-label', '服务器地址');
        addrWrap.appendChild(addrInput);
        var saveBtn = el('button', 'panel-btn', '保存地址并重连');
        saveBtn.type = 'button';
        saveBtn.addEventListener('click', function () {
            var v = addrInput.value.trim().replace(/\/+$/, '');
            try { localStorage.setItem('xj3_mobile_base', v); } catch (e) { /* 忽略 */ }
            location.reload();
        });
        addrWrap.appendChild(saveBtn);
        body.appendChild(addrWrap);
        var pair = el('button', 'panel-btn', '扫码配对 / 重连主机');
        pair.type = 'button';
        pair.addEventListener('click', function () { showPairGate(); });
        body.appendChild(pair);
        var act = el('button', 'panel-btn', '立即检测连接');
        act.type = 'button';
        act.addEventListener('click', function () {
            linkCheck();
            toast('已发起连接检测');
        });
        body.appendChild(act);
        var clear = el('button', 'panel-btn panel-btn--warn', '清除本页数据并刷新');
        clear.type = 'button';
        clear.addEventListener('click', function () {
            try { localStorage.clear(); sessionStorage.clear(); } catch (e) { /* 忽略 */ }
            location.reload();
        });
        body.appendChild(clear);
        body.appendChild(el('div', 'panel-hint',
            '说明：当前经同源/局域网直连主机。独立中继通道（账号绑定+多终端管控）已立项调研，见《独立中继服务器架构设计方案》。'));
    }

    /* ---- 关于面板 ---- */
    function renderAboutPanel(body) {
        body.textContent = '加载中…';
        fetch(BASE + '/api/status').then(function (r) { return r.json(); })
            .then(function (res) {
                body.textContent = '';
                var v = (res && res.data && res.data.version) || '未知';
                var card = el('div', 'panel-card');
                card.appendChild(el('div', 'panel-line', '小橘3号 移动端'));
                card.appendChild(el('div', 'panel-line', '服务版本：v' + v));
                card.appendChild(el('div', 'panel-line', '定位：本地个人辅助 AI 管家'));
                body.appendChild(card);
                body.appendChild(el('div', 'panel-hint',
                    '⚠️ 免责提示：自动化操作可能存在误差，重要文件请提前备份。'));
            })
            .catch(function () {
                body.textContent = '';
                body.appendChild(el('div', 'panel-hint', '版本信息获取失败（离线？）'));
            });
    }

    /* ==================== 6.6 语音输入（MA2.1：麦克风必须活） ====================
     * getUserMedia 权限申请 → MediaRecorder 录音 → POST /api/stt/transcribe
     * （PyAV 解码+Whisper，与桌面 STT 同门槛）→ 文字填入输入框（可改后发送）。 */
    var mediaStream = null;
    var mediaRecorder = null;
    var chunks = [];

    function setMicRecording(on) {
        micBtn.classList.toggle('mic-rec', on);
        micBtn.setAttribute('aria-label', on ? '停止录音' : '语音输入');
    }

    function bindMic() {
        micBtn.addEventListener('click', function () {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();          /* 停止→转写→填输入框 */
                return;
            }
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                toast('当前环境不支持麦克风（需 HTTPS/权限）', true);
                return;
            }
            navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
                mediaStream = stream;
                try {
                    mediaRecorder = new MediaRecorder(stream);
                } catch (e) {
                    toast('录音器初始化失败：' + e.message, true);
                    stream.getTracks().forEach(function (t) { t.stop(); });
                    return;
                }
                chunks = [];
                mediaRecorder.ondataavailable = function (e) {
                    if (e.data && e.data.size) { chunks.push(e.data); }
                };
                mediaRecorder.onstop = function () {
                    mediaStream.getTracks().forEach(function (t) { t.stop(); });
                    setMicRecording(false);
                    var blob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });
                    if (blob.size < 1000) { toast('录音太短', true); return; }
                    toast('转写中…');
                    var fd = new FormData();
                    fd.append('audio', blob, 'voice.webm');
                    fetch(BASE + '/api/stt/transcribe', { method: 'POST', body: fd })
                        .then(function (r) { return r.json(); })
                        .then(function (j) {
                            if (j && j.code === 200) {
                                var text = (j.data && j.data.text) || '';
                                if (text) {
                                    input.value = (input.value ? input.value + ' ' : '') + text;
                                    input.focus();
                                    autoGrow();
                                    refreshSend();
                                    toast('已转写');
                                } else {
                                    toast((j.data && j.data.note) || '没听清', true);
                                }
                            } else {
                                toast((j && j.error) || '转写失败', true);
                            }
                        })
                        .catch(function () { toast('转写请求失败', true); });
                };
                mediaRecorder.start();
                setMicRecording(true);
                toast('开始录音，再点一次结束');
            }).catch(function (e) {
                toast('麦克风权限被拒绝，请在系统设置中允许 APP 使用麦克风后重试', true);
            });
        });
    }

    /* ==================== 6.7 附件上传（MA3：复用 doc_ingest 解析链） ==================== */
    function bindAttach() {
        var attachBtn = $('#mAttachBtn');
        var fileInput = $('#mAttachFile');
        if (!attachBtn || !fileInput) { return; }
        attachBtn.addEventListener('click', function () { fileInput.click(); });
        fileInput.addEventListener('change', function () {
            var file = fileInput.files && fileInput.files[0];
            fileInput.value = '';                 /* 允许重复选同一文件 */
            if (!file) { return; }
            toast('附件上传中：' + file.name);
            var fd = new FormData();
            fd.append('file', file, file.name);
            fetch(BASE + '/api/attach_upload', { method: 'POST', body: fd })
                .then(function (r) { return r.json(); })
                .then(function (j) {
                    if (j && j.code === 200) {
                        toast('📎 附件已就绪：' + (j.data && j.data.name) + '（随下一条消息发送）');
                    } else {
                        toast('❌ ' + ((j && j.error) || '附件上传失败'), true);
                    }
                })
                .catch(function () { toast('附件上传失败（网络）', true); });
        });
    }

    /* ==================== 6.9 诊断面板呼出（netfix） ====================
     * 三击顶栏标题「小橘3号」切换 #mCssDiag（MA3 记录的三击呼出当时未
     * 落实，本批补齐）：显示当前基址+来源/最近探活 URL+结果+失败类别/
     * 能力级——断连排查从"瞎猜"变"看数"。600ms 内三连击生效。 */
    function bindDiagToggle() {
        var title = document.querySelector('.topbar-title');
        if (!title) { return; }
        var taps = 0, last = 0;
        title.addEventListener('click', function () {
            var now = Date.now();
            taps = (now - last < 600) ? (taps + 1) : 1;
            last = now;
            if (taps < 3) { return; }
            taps = 0;
            var d = document.getElementById('mCssDiag');
            if (!d) { return; }
            var show = d.style.display === 'none';
            d.style.display = show ? 'block' : 'none';
            if (show) { diagRender(); }
        });
    }

    /* ==================== 初始化 ==================== */
    function init() {
        bindDrawer();
        bindStream();
        bindComposer();
        bindMic();
        bindAttach();
        bindViewportFallback();
        bindDiagToggle();
        following = true;
        scrollToBottom(false);
        startLinkCheck();     /* 探活横幅触发源（MA2 接入） */
        loadHistory();        /* 刷新加载后端历史 */
        initUiEvents();       /* 总线：bus_reply+collab_msg HITL */
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    /* 验收/调试钩子（唯一全局出口；netfix 扩容：配对门+诊断） */
    window.__xj3Mobile = {
        setConnState: setConnState,
        sendMessage: sendMessage,
        linkCheck: linkCheck,
        showPairGate: showPairGate,
        pairConnect: pairConnect,
        parsePairingPayload: parsePairingPayload,
        diag: DIAG
    };
})();
