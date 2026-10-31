/* =========================================================
 * mobile.js — 小橘3号 移动端 MA2 网络接线层（IIFE）
 * 规格来源：_dev/docs/design_mobile_ui.md / design_mobile_architecture.md
 *          design_mobile_features.md（对照表：HITL 卡✅/协作面板❌）
 * MA2 范围：探活横幅 / 历史加载 / /api/chat/stream 流式（think+answer 双帧）
 *           / /api/events 总线（bus_reply+collab_msg HITL 卡）/ legacy 回退。
 * 拷贝复用策略（架构文档 §三）：网络与渲染函数定点拷贝自 console.js@ee66ef0，
 *   每函数带溯源注释；同步清单=_dev/mobile_sync_checklist.md；桌面 console.js 零改动。
 * 沿用 MA1：抽屉/stick-to-bottom/自增高/visualViewport 兜底/Enter=换行（无 keydown 发送）。
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
    var banner = $('#mConnBanner');
    var connDot = $('#mConnDot');
    var drawerConnDot = $('#mDrawerConnDot');
    var drawerConnText = $('#mDrawerConnText');

    /* ---------- API 基址（单点；MA3 接候选切换） ----------
     * 缺省 ''=同源相对路径（mobile.html 经 /console/mobile.html 同源托管，
     * 对齐 console.js 的相对路径策略——探活函数已按 base 参数化）。 */
    var BASE = (typeof window.__XJ3_MOBILE_BASE === 'string')
        ? window.__XJ3_MOBILE_BASE : '';

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

    function followIfPinned() {
        /* 渲染管线统一出口：仅跟随态吸底，流式绝不强制拉扯 */
        if (following) { scrollToBottom(false); }
    }

    function bindStream() {
        stream.addEventListener('scroll', function () {
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
        var ctl = new AbortController();
        var timer = setTimeout(function () { ctl.abort(); }, 5000);
        return fetch((base || '') + '/api/health', { signal: ctl.signal })
            .then(function (r) { return r.json(); })
            .then(function (j) { return !!(j && j.status === 'ok'); })
            .catch(function () { return false; })
            .finally(function () { clearTimeout(timer); });
    }

    var linkTimer = null;
    function linkCheck() {
        probeBase(BASE).then(function (ok) {
            setConnState(ok);
        });
    }
    function startLinkCheck() {
        linkCheck();                                   /* 启动即探一次 */
        linkTimer = setInterval(linkCheck, 15000);     /* 15s 周期（同桌面） */
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
        stream.appendChild(row);
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
        stream.appendChild(row);
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
        stream.appendChild(row);
        followIfPinned();
        return b;
    }

    /* ==================== 9. 流式对话（拷贝自 console.js@ee66ef0：
     *   sendMessageStream L5042 / pump L5227 / handleEvent L5155 / ensureThinkCard L5080） ==================== */
    var generating = false;
    var WD_FIRST_MS = 30000;     /* 首帧看门狗（桌面同款） */
    var WD_FRAME_MS = 90000;     /* 帧间看门狗 */
    var WD_TOTAL_MS = 190000;    /* 总闸 AbortController */

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
        stream.appendChild(row);
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

    function sendMessage(text) {
        if (generating) { return; }
        generating = true;
        refreshSend();
        appendUserMessage(text);
        var think = ensureLiveThink();
        var answerEl = null;

        function ensureAnswer() {
            if (answerEl) { return answerEl; }
            var row = el('div', 'msg-row msg-row--them');
            var b = el('div', 'bubble bubble--them');
            var content = el('div', 'bubble-content');
            b.appendChild(content);
            row.appendChild(b);
            stream.appendChild(row);
            answerEl = content;
            followIfPinned();
            return content;
        }

        var accAnswer = '';
        var accThink = '';
        var controller = new AbortController();
        var firstFrame = setTimeout(function () { controller.abort(); }, WD_FIRST_MS);
        var frameTimer = firstFrame;
        var totalTimer = setTimeout(function () { controller.abort(); }, WD_TOTAL_MS);
        var finished = false;

        function handleEvent(etype, data) {
            clearTimeout(frameTimer);
            frameTimer = setTimeout(function () { controller.abort(); }, WD_FRAME_MS);
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
                clearTimeout(firstFrame);
                clearTimeout(frameTimer);
                clearTimeout(totalTimer);
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
                clearTimeout(firstFrame);
                clearTimeout(frameTimer);
                clearTimeout(totalTimer);
                if (think.row && think.row.parentNode) { think.row.remove(); }
                appendErrorBubble('❌ ' + ((data && data.error) || '请求失败，稍后再试'));
                followIfPinned();
            }
        }

        fetch(BASE + '/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text }),
            signal: controller.signal
        }).then(function (res) {
            if (!res.ok || !res.body) { throw new Error('HTTP ' + res.status); }
            var reader = res.body.getReader();
            var decoder = new TextDecoder();
            var buffer = '';
            function pump() {
                return reader.read().then(function (chunk) {
                    if (chunk.done) { return; }
                    buffer += decoder.decode(chunk.value, { stream: true });
                    var frames = buffer.split('\n\n');
                    buffer = frames.pop();
                    frames.forEach(function (frame) {
                        var etype = null;
                        var payload = '';
                        frame.split('\n').forEach(function (line) {
                            if (line.indexOf('event:') === 0) {
                                etype = line.slice(6).trim();
                            } else if (line.indexOf('data:') === 0) {
                                payload += line.slice(5).trim();
                            }
                        });
                        if (!etype || !payload) { return; }
                        try {
                            handleEvent(etype, JSON.parse(payload));
                        } catch (e) { /* 坏帧丢弃（桌面同款容错） */ }
                    });
                    return pump();
                });
            }
            return pump();
        }).catch(function (e) {
            if (finished) { return; }
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
            });
        }).finally(function () {
            clearTimeout(firstFrame);
            clearTimeout(frameTimer);
            clearTimeout(totalTimer);
            generating = false;
            refreshSend();
        });
    }

    /* ==================== 10. 历史加载（拷贝自 console.js loadHistory L4852） ==================== */
    function loadHistory() {
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
        var es = new EventSource(BASE + '/api/events');
        es.onerror = function () {
            setConnState(false);          /* SSE 断=连接异常，横幅示警；EventSource 自动重连 */
        };
        es.onopen = function () { linkCheck(); };
        es.addEventListener('bus_reply', function (ev) {
            try {
                var d = JSON.parse(ev.data);
                if (d && d.reply) { appendBotMessage(d.reply, d.source); }
            } catch (e) { /* 坏帧丢弃 */ }
        });
        es.addEventListener('collab_msg', function (ev) {
            try {
                var m = JSON.parse(ev.data);
                if (m && m.hitl) { renderHitlCard(m); }
            } catch (e) { /* 坏帧丢弃 */ }
        });
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
        stream.appendChild(row);
        followIfPinned();
    }

    /* ==================== 初始化 ==================== */
    function init() {
        bindDrawer();
        bindStream();
        bindComposer();
        bindViewportFallback();
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

    /* 验收/调试钩子（唯一全局出口） */
    window.__xj3Mobile = {
        setConnState: setConnState,
        sendMessage: sendMessage,
        linkCheck: linkCheck
    };
})();
