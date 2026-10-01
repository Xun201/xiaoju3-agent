// 小橘3号 · 新版控制台前端逻辑（纯轮询，无 WebSocket）
(function() {
    console.log('小橘3号控制台逻辑已启动');

    // ==================== 0. 主题 / 音效开关（localStorage 记忆） ====================
    // 皮肤系统基础（界面文档 §10.1）：data-theme="orange" 橘色主题，默认深蓝不变。
    const THEME_KEY = 'xiaoju3_theme';

    function applyTheme(theme) {
        if (theme === 'orange') {
            document.documentElement.setAttribute('data-theme', 'orange');
        } else {
            document.documentElement.removeAttribute('data-theme');  // 默认深蓝主题
        }
    }
    applyTheme(getStoredTheme());

    function getStoredTheme() {
        try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; }
    }

    const themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const next = getStoredTheme() === 'orange' ? '' : 'orange';
            try {
                if (next) localStorage.setItem(THEME_KEY, next);
                else localStorage.removeItem(THEME_KEY);
            } catch (e) { /* localStorage 不可用时仅本次会话生效 */ }
            applyTheme(next);
            showToast(next === 'orange' ? '已切换到橘色主题 🦊' : '已切换到深蓝主题');
        });
    }

    // 音效总开关（WebAudio 引擎在 desktop-pet.js 中，localStorage 记忆）
    const soundBtn = document.getElementById('sound-toggle');
    function refreshSoundBtn() {
        if (soundBtn && window.xiaoju3Sound) {
            soundBtn.textContent = window.xiaoju3Sound.enabled() ? '🔔' : '🔕';
        }
    }
    if (soundBtn && window.xiaoju3Sound) {
        soundBtn.addEventListener('click', () => {
            window.xiaoju3Sound.toggle();
            refreshSoundBtn();
            showToast(window.xiaoju3Sound.enabled() ? '音效已开启' : '音效已关闭');
        });
        refreshSoundBtn();
    }

    // ==================== 轻提示 toast（替代 alert 占位） ====================
    let toastTimer = null;
    function showToast(text) {
        let el = document.getElementById('xiaoju3-toast');
        if (!el) {
            el = document.createElement('div');
            el.id = 'xiaoju3-toast';
            document.body.appendChild(el);
        }
        el.textContent = text;
        el.classList.add('show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => el.classList.remove('show'), 2000);
    }

    // ==================== 1. 定时请求后端系统状态（2 秒轮询） ====================
    function fetchStatus() {
        fetch('/api/status')
            .then(res => res.json())
            .then(res => {
                if (res.code === 200) {
                    const d = res.data;
                    const cpuText = document.getElementById('cpu-text');
                    const cpuBar = document.getElementById('cpu-bar');
                    if (cpuText && cpuBar) {
                        cpuText.textContent = d.cpu + '%';
                        cpuBar.style.width = d.cpu + '%';
                        // CPU 超过 80%：进度条由绿变红
                        cpuBar.style.backgroundColor = d.cpu > 80 ? '#e0433f' : '#2fa24c';
                    }

                    const memText = document.getElementById('mem-text');
                    const memBar = document.getElementById('mem-bar');
                    if (memText && memBar) {
                        memText.textContent = d.memory + '%';
                        memBar.style.width = d.memory + '%';
                        // 内存超过 80%：进度条由绿变红
                        memBar.style.backgroundColor = d.memory > 80 ? '#e0433f' : '#2fa24c';
                    }

                    const tempText = document.getElementById('temp-text');
                    if (tempText) {
                        tempText.textContent = (d.temperature === 'N/A' ? 'N/A' : d.temperature + ' °C');
                    }
                }
            })
            .catch(err => console.error('获取系统状态失败', err));
    }

    fetchStatus();
    setInterval(fetchStatus, 2000);

    // ==================== 2. 聊天渲染辅助（历史加载与实时发送共用） ====================
    // XSS 防护（界面文档 §4.4 / §10.4 近期项）：回复文本转义后渲染，换行转 <br>
    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    // QQ 表情渲染（网页永不显示方括号 CQ 原文，与后端 web_sanitize 同口径）：
    // ① [CQ:face,id=XX] → 对应 Emoji（经典 id 0-103 全量 + 常用扩展，与
    //    web_sanitize.CQ_FACE_EMOJI 同源同义；未收录 id 兜底通用表情，不再原样保留）
    // ② [CQ:image,...] → [表情] 占位（网页无法渲染表情包图片，且不泄露服务器本机路径）
    // ③ 其余 [CQ:...]（at/record 等 QQ 专用格式）一律剥除
    const CQ_FACE_EMOJI = {
        0: '😊', 1: '😒', 2: '😍', 3: '😔', 4: '😎', 5: '😢', 6: '😊', 7: '🤫',
        8: '😴', 9: '😭', 10: '😅', 11: '😠', 12: '😜', 13: '😁', 14: '😄', 15: '😰',
        16: '😝', 17: '🤔', 18: '😪', 19: '🤮', 20: '🤭', 21: '😘', 22: '😤', 23: '😖',
        24: '😨', 25: '🥱', 26: '😵', 27: '🤐', 28: '😆', 29: '🙃', 30: '💪', 31: '🤬',
        32: '🙈', 33: '🤫', 34: '💫', 35: '😫', 36: '😩', 37: '🤗', 38: '😱', 39: '🥺',
        40: '😤', 41: '👃', 42: '👏', 43: '😬', 44: '😏', 45: '😤', 46: '🐱', 47: '🥱',
        48: '🙄', 49: '🥺', 50: '😣', 51: '😈', 52: '😘', 53: '😨', 54: '🥺', 55: '🔪',
        56: '🍉', 57: '🍺', 58: '🏀', 59: '🏓', 60: '☕', 61: '🍚', 62: '🐷', 63: '👍',
        64: '👎', 65: '💋', 66: '❤️', 67: '💔', 68: '🎂', 69: '⚡', 70: '💣', 71: '🔪',
        72: '⚽', 73: '🐞', 74: '💩', 75: '🌙', 76: '🌹', 77: '🎁', 78: '🍀', 79: '👍',
        80: '👎', 81: '🤝', 82: '✌️', 83: '🙏', 84: '👉', 85: '⚡', 86: '👎', 87: '💖',
        88: '🙅', 89: '🍺', 90: '💕', 91: '😘', 92: '🕺', 93: '😰', 94: '🔄', 95: '🙇',
        96: '👀', 97: '🤝', 98: '👋', 99: '🤩', 100: '💃', 101: '🙏', 102: '☯️', 103: '☯️',
        109: '🐱', 124: '💀', 129: '🙏', 144: '🍺', 146: '🐱',
    };
    const CQ_FACE_FALLBACK = '😊';   // 未收录 face id 的兜底表情
    function renderCQFace(text) {
        return String(text)
            .replace(/\[CQ:face,id=(\d+)\]/g, function (m, id) {
                return Object.prototype.hasOwnProperty.call(CQ_FACE_EMOJI, Number(id))
                    ? CQ_FACE_EMOJI[Number(id)] : CQ_FACE_FALLBACK;
            })
            .replace(/\[CQ:image,[^\]]*\]/g, '[表情]')
            .replace(/\[CQ:[^\]]*\]/g, '');
    }
    function renderRich(text) {
        return renderCQFace(escapeHtml(text)).replace(/\n/g, '<br>');
    }

    // ==================== 2.5 思维链（<think> 块 / 裸 [思考]/[计划] 标记）解析与折叠卡片 ====================
    // 契约（2026-10-01 全对话强制包装口径）：brain.smart_ask 对所有自然语言
    // 回复一律包装 <think>...</think> 块——工具流程用原生 [思考]/[计划] 或
    // 按工具名生成的占位符，普通闲聊（无工具调用）注入"[思考] 正在理解你
    // 的意图..."默认占位符；渲染入口仅由 think !== null 守卫，正文为自然
    // 语言或占位符都出卡。裸标记扫描保留作纵深防御：万一仍有旁路/旧版
    // 后端漏出裸的 [思考]/[计划]/[行动] 文本，统一入口 splitThinkBlock 做
    // 两段解析，两种形态（<think> 包装 / 裸标记）收敛到同一张折叠卡片：
    // ① <think> 包装块提取（非锚定正则 + 循环剔块；正文只保留最后一个
    //    </think> 之后的部分，块前杂散字符丢弃——用户口径）；
    // ② 剩余正文裸标记扫描：[思考]/[计划] 段落并入思考卡内容并从正文剥离；
    //    [行动] 标记与其后的单行 JSON 工具载荷（模型过程输出）一并剥离，
    //    正文只留最终自然语言回复；剥离后正文为空时显示"（操作已执行）"占位。
    // 非锚定匹配（串内任意位置，非贪婪到第一个闭合标签）：即使净化/表情转换
    // 等环节日后在块前插入了任何字符，只要 reply 含 <think> 块就必定渲染卡片，
    // 不因锚定串首而静默漏卡。
    const THINK_BLOCK_RE = /<think>([\s\S]*?)<\/think>/;

    // 裸 [思考] 段（协议硬性要求半角方括号标记，全角变体仅后端兼容）：内容
    // 跨行（[\s\S] 非贪婪），止于下一个 [计划]/[行动] 标记或串尾——前瞻零
    // 消费，标记本身留给下一段扫描/[行动] 剥离；普通聊天提到"思考"二字
    // （无方括号标记）不命中，不误剥离。
    const BARE_THINK_RE = /(\[思考\][\s\S]*?)(?=\[行动\]|\[计划\]|$)/;
    // 裸 [计划] 段：止于 [行动] 标记或串尾（边界口径同上）。
    const BARE_PLAN_RE = /(\[计划\][\s\S]*?)(?=\[行动\]|$)/;
    // [行动] 剥离：标记本身一律剥离；其后若跟以 { 起头的行内 JSON 工具载荷
    // （prompts 协议硬性口径"[行动] 行必须且只能是一行合法 JSON"），载荷同样
    // 剥离（[^\n] 不跨行，载荷之后各行的最终自然语言回复保留）；载荷不是
    // JSON 形态时只剥标记、保留其后文本，防误伤普通聊天里合法出现的
    // "[行动]"字样。
    const BARE_ACTION_RE = /\s*\[行动\](?:[ \t]*\{[^\n]*)?/;

    // 渲染入口先判 thinkMatch：把原始 reply 切分为 { think, body }，
    // 调用方再各自走 textContent / renderRich（先切分后转义，顺序不可反）。
    // F4 加固：函数体整体包 try/catch——任何解析异常都不影响后续消息渲染，
    // catch 记录 "CoT Render Error" 并返回安全降级值（think=已剥离出的
    // 部分或 null、body=原文），绝不让单条消息解析崩溃吞掉整轮回复。
    function splitThinkBlock(rawReply) {
        const raw = String(rawReply == null ? '' : rawReply);
        let think = null;
        let body = raw;
        try {
            // ① <think> 包装块（用户口径）：非锚定 + 循环剔块——只要 reply 含
            //    <think> 就必定出卡片，多个块全部并入同一张卡；正文只保留最后
            //    一个 </think> 之后的部分，块前杂散字符一律丢弃，思考文本绝不
            //    混进聊天正文。空 <think></think> 块同样算"有思考块"（think 为
            //    空串而非 null，与既有 think !== null 卡片判定口径一致）。
            let thinkMatch;
            while ((thinkMatch = body.match(THINK_BLOCK_RE)) !== null) {
                think = (think ? think + '\n' : '') + thinkMatch[1].trim();
                body = body.slice(thinkMatch.index + thinkMatch[0].length);
            }
            // ①-b 游离闭合标签容错（后端拼装异常可能残留不成对标签，2026-10-01
            //     用户口径）：只有闭合 </think> 时——闭合标签（含）之前的全部
            //     内容按思考处理，正文只保留最后一个 </think> 之后的部分。
            const closeIdx = body.lastIndexOf('</think>');
            if (closeIdx !== -1) {
                const before = body.slice(0, closeIdx).replace(/<\/?think>/g, '').trim();
                if (before) think = (think ? think + '\n' : '') + before;
                body = body.slice(closeIdx + '</think>'.length);
            }
            // ①-c 未配对 <think> 容错（任何位置，2026-10-01 用户口径）：成对
            //     块已在 ① 剔尽，此处残留的开头标签必无闭合（串尾截断的畸形
            //     残块）——标签及其后的截断思考内容整段并入思考卡（同孤儿
            //     口径，绝不作为正文上屏），标签前的正文保留；剥离后正文
            //     剥空由既有占位口径兜底。残留的游离 <think>/</think> 一律
            //     剥除，绝不上屏。
            const openIdx = body.indexOf('<think>');
            if (openIdx !== -1) {
                const head = body.slice(0, openIdx).trim();
                const orphan = body.slice(openIdx).replace(/<\/?think>/g, '').trim();
                if (orphan) think = (think ? think + '\n' : '') + orphan;
                body = head;
            }
            body = body.trim();

            // ② 裸 [思考]/[计划] 段落扫描：并入思考卡内容并从正文剥离
            //    （<think> 包装缺失时，裸 CoT 不再漏进聊天正文）
            const bareParts = [];
            body = body.replace(BARE_THINK_RE, function (m, seg) {
                if (seg.trim()) bareParts.push(seg.trim());
                return '';
            });
            body = body.replace(BARE_PLAN_RE, function (m, seg) {
                if (seg.trim()) bareParts.push(seg.trim());
                return '';
            });
            if (bareParts.length) {
                // 两种形态收敛到同一张卡片：<think> 内容在前，裸段按出现顺序追加
                think = (think ? think + '\n' : '') + bareParts.join('\n');
            }

            // ③ [行动] 标记与其后的行内 JSON 工具载荷剥离（模型过程输出不上屏）；
            //    正文被剥空且确有过程输出被剥离（有思考卡或剥过 [行动]）时，
            //    正文显示占位——说明本轮是纯工具动作、无自然语言收尾
            const hadAction = BARE_ACTION_RE.test(body);
            body = body.replace(BARE_ACTION_RE, '').trim();
            // 安全网：剥离一切残留游离标签（成对块已在 ① 提取，此处只兜底）
            body = body.replace(/<\/?think>/g, '').trim();
            if (think !== null) think = think.replace(/<\/?think>/g, '').trim();
            if (!body && (think !== null || hadAction)) body = '（操作已执行）';

            return { think: think, body: body };
        } catch (e) {
            // 安全降级：解析出错时 think 返回已剥离出的部分（尚无则 null、
            // 不出卡），body 回退原文，正文照常渲染
            console.error("CoT Render Error: ", e);
            return { think: think, body: raw };
        }
    }

    // 构建折叠卡片骨架（纯静态结构，不拼任何用户数据；
    // 思考正文一律 textContent 注入，天然免 XSS）。初始为折叠态。
    function buildThinkCardEl() {
        const card = document.createElement('div');
        card.className = 'think-card think-collapsed';
        card.innerHTML =
            '<div class="think-card-header" onclick="toggleThinkCard(this)" title="展开/收起思考过程">' +
                '<span>🧠</span>' +
                '<span class="think-card-title">思考过程</span>' +
                '<span class="think-card-arrow">▼</span>' +
            '</div>' +
            '<div class="think-card-body"></div>';
        return card;
    }

    // 深色降级兜底块（F4 加固）：思考卡片构建/插入任何环节失败时，改用
    // 纯 createElement + 内联样式的深色文本块展示思考过程（无类名依赖、
    // 不经 innerHTML），内容取思考文本前 200 字、textContent 注入免 XSS
    // ——保证思考过程任何情况下可见。
    function buildThinkFallbackBlock(thinkText) {
        const block = document.createElement('div');
        block.style.background = '#1f2937';     // 深色背景（任务规格色）
        block.style.color = '#ffffff';          // 白字
        block.style.fontSize = '13px';
        block.style.padding = '6px 10px';
        block.style.borderRadius = '10px';
        block.style.marginBottom = '5px';
        block.style.whiteSpace = 'pre-wrap';
        block.style.wordBreak = 'break-word';
        block.textContent = '🧠 思考过程：' + String(thinkText == null ? '' : thinkText).slice(0, 200);
        return block;
    }

    // 思考正文打字机：约 15ms/字（规格 12-20ms 区间），逐字 textContent 注入。
    // animate=false（历史回放共用入口）不打字，直接完整填充并保持折叠。
    // 注：textContent 注入无需 escapeHtml（转义反而会显示 HTML 实体），
    // CQ 码仍走 renderCQFace 与正文同口径净化。
    const THINK_TYPE_MS = 15;
    function startThinkTypewriter(msgEl, thinkText, animate) {
        const card = msgEl.querySelector('.think-card');
        const body = card && card.querySelector('.think-card-body');
        if (!card || !body) return;
        const text = renderCQFace(thinkText);
        if (!animate || !text) {
            body.textContent = text;
            return;
        }
        card.classList.remove('think-collapsed');   // 打字期间展开
        let shown = 0;
        const timer = setInterval(() => {
            if (!card.isConnected) { clearInterval(timer); return; }   // 卡片被移除即停
            shown += 1;
            body.textContent = text.slice(0, shown);
            const history = document.getElementById('chat-history');
            if (history) history.scrollTop = history.scrollHeight;     // 跟随滚动
            if (shown >= text.length) {
                clearInterval(timer);
                card.classList.add('think-collapsed');   // 打完自动折叠（点击标题可再展开）
            }
        }, THINK_TYPE_MS);
    }

    // 点击标题展开/收起（折叠用 display 切换，样式见 index.html .think-collapsed）
    window.toggleThinkCard = function(headerEl) {
        const card = headerEl.closest('.think-card');
        if (card) card.classList.toggle('think-collapsed');
    };

    // 刷新重生成后同步思考卡片：有 <think> 则重建并打字，无则移除旧卡片。
    // F4 加固：插入手工 DOM 化（不依赖 before 系快捷方法）——显式父引用 +
    // insertBefore，卡片同样位于气泡正文上方；插入失败降级为深色纯文本块。
    function syncThinkCard(msgEl, thinkText) {
        const bubble = msgEl.querySelector('.bubble-content');
        if (!bubble) return;
        const old = msgEl.querySelector('.think-card');
        if (old) old.remove();
        if (thinkText === null) return;   // 新回复没有 think 块：不插卡片
        try {
            const card = buildThinkCardEl();  // 先构建完整元素、再插入 DOM（顺序同上）
            bubble.parentNode.insertBefore(card, bubble);
        } catch (e) {
            console.error("CoT Render Error: ", e);
            // 降级兜底：深色纯文本块仍插在气泡上方，思考过程必可见
            try {
                bubble.parentNode.insertBefore(
                    buildThinkFallbackBlock(thinkText), bubble);
            } catch (fbErr) {
                console.error("CoT Render Error: ", fbErr);
            }
        }
        startThinkTypewriter(msgEl, thinkText, true);
    }

    function appendUserMessage(text) {
        const history = document.getElementById('chat-history');
        const userMsg = document.createElement('div');
        userMsg.className = 'message user-message';
        userMsg.textContent = text;   // textContent 注入，无 XSS 风险
        history.appendChild(userMsg);
        history.scrollTop = history.scrollHeight;
        return userMsg;
    }

    // 大脑来源徽标（§4.3：消费 /api/chat 返回的 source 字段）
    // dataset.prompt 记录触发本回复的原消息，供"刷新"按钮重新生成
    // opts.animateThink=false（历史回放）时思考卡片不打字、直接折叠展示全文
    function appendBotMessage(rawReply, source, prompt, opts) {
        const options = opts || {};
        const history = document.getElementById('chat-history');
        const botMsg = document.createElement('div');
        botMsg.className = 'message bot-message';
        botMsg.dataset.prompt = prompt || '';
        // XSS 顺序：先在原始 reply 上切分出 <think> 块，think 与正文再各自
        // 走 textContent / renderRich 转义（不可先转义后切分）
        const thinkParts = splitThinkBlock(rawReply);
        const reply = thinkParts.body;   // 剥离 think 后的正文
        const sourceBadge = source
            ? `<div class="source-badge">大脑来源：${escapeHtml(source)}</div>`
            : '';
        botMsg.innerHTML = `
            <div style="display:flex; flex-direction:column; gap:5px;">
                <div class="bubble-content">${renderRich(reply)}</div>
                ${sourceBadge}
                <div class="msg-tools">
                    <span class="tool-btn" onclick="copyText(this)" title="复制">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                    </span>
                    <span class="tool-btn" onclick="refreshMsg(this)" title="重新生成">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"></path><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path></svg>
                    </span>
                    <span class="tool-btn like-btn" onclick="toggleLike(this)" title="点赞">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path></svg>
                    </span>
                    <span class="tool-btn dislike-btn" onclick="toggleDislike(this)" title="踩">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"></path></svg>
                    </span>
                    <span class="tool-btn" onclick="playMsg(this)" title="播放">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>
                    </span>
                    <span class="tool-btn" onclick="forwardMsg(this)" title="转发">
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path><polyline points="16 6 12 2 8 6"></polyline><line x1="12" y1="2" x2="12" y2="15"></line></svg>
                    </span>
                </div>
            </div>
        `;
        // 渲染入口先判 thinkMatch：仅当切分出思考内容（<think> 块或裸
        // [思考]/[计划] 段）才插思考卡片——后端全对话强制包装后，普通闲聊
        // 同样带默认占位符块，正文为自然语言或占位符都出卡；无块仍不插卡
        //（前端行为零改动），卡片位于消息气泡正文上方
        if (thinkParts.think !== null) {
            // F4 加固：手工插入（不依赖 before()/prepend() 系快捷方法）——
            // 显式父引用 + insertBefore，卡片位于消息气泡正文上方；先构建
            // 完整卡片元素、再插入 DOM（顺序不可反）；.bubble-content 意外
            // 缺失时降级为消息容器直插，插入环节任何异常都不吞掉整条回复
            // ——卡片插不上时再降级为深色纯文本块，思考过程必可见
            try {
                const thinkCard = buildThinkCardEl();
                const bubbleEl = botMsg.querySelector('.bubble-content');
                const parentEl = bubbleEl ? bubbleEl.parentNode : botMsg;
                parentEl.insertBefore(thinkCard, bubbleEl);
            } catch (e) {
                console.error("CoT Render Error: ", e);
                // 降级兜底：深色纯文本块仍插在气泡上方（消息首子节点之前）
                try {
                    botMsg.insertBefore(buildThinkFallbackBlock(thinkParts.think),
                                        botMsg.firstChild);
                } catch (fbErr) {
                    console.error("CoT Render Error: ", fbErr);
                }
            }
            startThinkTypewriter(botMsg, thinkParts.think, options.animateThink !== false);
        }
        history.appendChild(botMsg);
        history.scrollTop = history.scrollHeight;
        return botMsg;
    }

    // ==================== 3. 聊天历史持久化（功能文档 §12 / 界面 §10.4 近期项） ====================
    // 页面加载时拉取 /api/history 渲染历史（此前仅存页面内存、刷新即清空）
    function loadHistory() {
        fetch('/api/history')
            .then(res => res.json())
            .then(res => {
                if (res.code !== 200 || !res.data || !Array.isArray(res.data.messages)) return;
                let lastUser = '';
                res.data.messages.forEach(m => {
                    if (!m || typeof m.content !== 'string') return;
                    if (m.role === 'user') {
                        lastUser = m.content;
                        appendUserMessage(m.content);
                    } else if (m.role === 'assistant') {
                        // 历史回放共用入口：思考卡片不打字，直接折叠展示
                        appendBotMessage(m.content, m.source || '', lastUser, { animateThink: false });
                    }
                });
            })
            .catch(err => console.error('加载聊天历史失败', err));
    }
    loadHistory();

    // ==================== 4. 聊天发送逻辑 ====================
    // 等待期轮换状态：占位气泡初始"小橘3号正在思考... 🧠"，此后每 900ms
    // 依次轮换下列状态文案（数组循环），收到回复/出错即停止轮换
    const THINKING_STATUS = [
        '🧠 正在思考执行方案…',
        '👁️ 正在分析屏幕…',
        '📁 正在读取文件…',
        '⚙️ 正在执行操作…',
    ];
    const THINKING_ROTATE_MS = 900;

    window.sendMessage = function() {
        const input = document.getElementById('chat-input');
        if (!input) return;

        const text = input.value.trim();
        if (!text) return;

        appendUserMessage(text);
        input.value = '';

        const loadingMsg = document.createElement('div');
        loadingMsg.className = 'message bot-message';
        loadingMsg.style.color = '#9fb0d9';
        loadingMsg.textContent = '小橘3号正在思考... 🧠';
        const history = document.getElementById('chat-history');
        history.appendChild(loadingMsg);
        history.scrollTop = history.scrollHeight;

        // 动态轮换：每 900ms 换一条状态文案（初始文案先展示一个周期再轮换）
        let statusIdx = 0;
        const rotateTimer = setInterval(() => {
            loadingMsg.textContent = THINKING_STATUS[statusIdx % THINKING_STATUS.length];
            statusIdx += 1;
        }, THINKING_ROTATE_MS);

        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        })
        .then(res => res.json())
        .then(res => {
            clearInterval(rotateTimer);   // 收到回复：停止轮换并替换为正常气泡
            history.removeChild(loadingMsg);
            if (res.code === 200) {
                appendBotMessage(res.data.reply, res.data.source, text);
                // 本地与远端同步：后端已将本轮问答落盘 /api/history
                // 回复到达提示音（界面文档 §6.2 / §9.1，AudioContext 缺席时静默降级）
                if (window.xiaoju3Sound) window.xiaoju3Sound.ding();
            } else {
                throw new Error(res.error || '未知错误');
            }
        })
        .catch(err => {
            clearInterval(rotateTimer);   // 出错同样停止轮换
            if (history.contains(loadingMsg)) history.removeChild(loadingMsg);
            const errMsg = document.createElement('div');
            errMsg.className = 'message bot-message';
            errMsg.style.color = '#e0433f';
            errMsg.textContent = '（请求失败：' + err.message + '）';
            history.appendChild(errMsg);
            history.scrollTop = history.scrollHeight;
        });
    };

    // ==================== 5. 工具按钮的对应全局函数 ====================

    // 复制
    window.copyText = function(el) {
        const text = el.closest('.message').querySelector('.bubble-content').innerText;
        navigator.clipboard.writeText(text).then(() => showToast('✅ 已复制'))
            .catch(() => showToast('复制失败，请手动选择文本'));
    };

    // 刷新（§4.2 实装）：对触发该回复的原消息重新 POST /api/chat，
    // 替换当前回复气泡；后端成功后自动把重新生成的问答追加落盘（历史同步更新）
    window.refreshMsg = function(el) {
        const msgEl = el.closest('.message');
        const bubble = msgEl.querySelector('.bubble-content');
        const prompt = (msgEl && msgEl.dataset.prompt) || '';
        if (!prompt || !bubble) {
            showToast('未找到原消息，无法刷新');
            return;
        }
        const original = bubble.innerHTML;
        bubble.textContent = '正在重新生成... 🧠';
        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: prompt })
        })
        .then(res => res.json())
        .then(res => {
            if (res.code !== 200) throw new Error(res.error || '未知错误');
            // 重新生成结果同样可能带 <think> 块或裸 [思考]/[计划] 标记：
            // 先切分（与 appendBotMessage 同口径），思考卡片同步更新，
            // 正文剥离后再渲染
            const thinkParts = splitThinkBlock(res.data.reply);
            const reply = thinkParts.body;
            syncThinkCard(msgEl, thinkParts.think);
            bubble.innerHTML = renderRich(reply);
            // 来源徽标同步更新
            let badge = msgEl.querySelector('.source-badge');
            if (res.data.source) {
                if (!badge) {
                    badge = document.createElement('div');
                    badge.className = 'source-badge';
                    bubble.after(badge);
                }
                badge.textContent = '大脑来源：' + res.data.source;
            } else if (badge) {
                badge.remove();
            }
            if (window.xiaoju3Sound) window.xiaoju3Sound.ding();
        })
        .catch(err => {
            bubble.innerHTML = original;   // 失败还原原回复
            showToast('刷新失败：' + err.message);
        });
    };

    // 转发（§4.2 实装）：全文复制到剪贴板，提示可粘贴转发
    window.forwardMsg = function(el) {
        const text = el.closest('.message').querySelector('.bubble-content').innerText;
        navigator.clipboard.writeText(text)
            .then(() => showToast('已复制，可粘贴转发'))
            .catch(() => showToast('复制失败，请手动选择文本'));
    };

    // 播放：每次播放前清空队列，防止连点无限循环
    window.playMsg = function(el) {
        window.speechSynthesis.cancel(); // 清空之前的播放队列
        const text = el.closest('.message').querySelector('.bubble-content').innerText;
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    };

    // 点赞/踩：互斥逻辑（点一个自动取消另一个），再次点击可取消
    window.toggleLike = function(el) {
        const msgEl = el.closest('.message');
        const dislikeBtn = msgEl.querySelector('.dislike-btn');
        const isActive = el.classList.contains('active-like');

        el.classList.remove('active-like');
        if (dislikeBtn) dislikeBtn.classList.remove('active-dislike');

        if (!isActive) {
            el.classList.add('active-like');
            console.log('👍 已点赞');
        } else {
            console.log('已取消点赞');
        }
    };

    window.toggleDislike = function(el) {
        const msgEl = el.closest('.message');
        const likeBtn = msgEl.querySelector('.like-btn');
        const isActive = el.classList.contains('active-dislike');

        el.classList.remove('active-dislike');
        if (likeBtn) likeBtn.classList.remove('active-like');

        if (!isActive) {
            el.classList.add('active-dislike');
            console.log('👎 已踩');
        } else {
            console.log('已取消踩');
        }
    };

    // ==================== 6. 清空聊天记录（带确认语义） ====================
    const clearBtn = document.getElementById('clear-history');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            if (!confirm('确定清空聊天记录吗？此操作不可恢复。')) return;
            fetch('/api/history', { method: 'DELETE' })
                .then(res => res.json())
                .then(res => {
                    if (res.code !== 200) throw new Error(res.error || '清空失败');
                    const history = document.getElementById('chat-history');
                    history.innerHTML = '<div class="message bot-message">你好！我是小橘3号，很高兴为你服务喵~</div>';
                    showToast('聊天记录已清空');
                })
                .catch(err => showToast('清空失败：' + err.message));
        });
    }

    // ==================== 7. 移动端监控抽屉开关（界面文档 §7） ====================
    const sidebar = document.querySelector('.sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    if (sidebar && sidebarToggle) {
        sidebarToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
    }

})();
