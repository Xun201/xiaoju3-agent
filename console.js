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

    // 自动朗读开关（任务 5，前端体验三件套）：与音效开关（🔔/🔕 提示音）
    // 相互独立——音效是回复到达提示音，朗读是 AI 回复的语音播报，键名亦
    // 区分（音效 xiaoju3_sound 在 desktop-pet.js，朗读 xiaoju3_autotts）。
    // 开启后 AI 每次回复自动朗读（复用 playMsg 既有 Edge-TTS 链路：emoji
    // 剔除 → Edge 优先 → 浏览器降级链，见下方 speakMessageEl）；关闭时仅
    // 手动点播放朗读。状态 localStorage 记忆、刷新保持，默认关闭。
    const AUTO_TTS_KEY = 'xiaoju3_autotts';
    function autoTTSEnabled() {
        try { return localStorage.getItem(AUTO_TTS_KEY) === '1'; }
        catch (e) { return false; }
    }
    function setAutoTTS(on) {
        try {
            if (on) localStorage.setItem(AUTO_TTS_KEY, '1');
            else localStorage.removeItem(AUTO_TTS_KEY);   // 默认关闭：清键即关
        } catch (e) { /* localStorage 不可用时仅本次会话生效 */ }
    }
    const autoTTSBtn = document.getElementById('auto-tts-toggle');
    function refreshAutoTTSBtn() {
        if (autoTTSBtn) autoTTSBtn.textContent = autoTTSEnabled() ? '🔊' : '🔇';
    }
    if (autoTTSBtn) {
        autoTTSBtn.addEventListener('click', () => {
            const on = !autoTTSEnabled();
            setAutoTTS(on);
            refreshAutoTTSBtn();
            showToast(on ? '自动朗读已开启：AI 回复将自动播报' : '自动朗读已关闭');
        });
        refreshAutoTTSBtn();   // 载入即按 localStorage 回显（刷新保持）
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

    // ==================== 0.5 TTS 朗读 emoji 剔除（任务 7）+ 音色选择（任务 4） ====================
    // 语音引擎读不出 emoji（静音/跳读）：朗读前正则整体剔除——emoji 主体区
    //（\u{1F300}-\u{1FAFF}，肤色修饰符 1F3FB-1F3FF 亦在其中）、牌类/括号/
    // 旗帜扩展区（\u{1F000}-\u{1F2FF}）、杂项符号与装饰（\u2600-\u27BF）、
    // 箭头与技术符号（\u2B00-\u2BFF、\u2300-\u23FF）、变体选择符
    //（\uFE00-\uFE0F）、ZWJ 零宽连接符（\u200D，emoji 组合序列）、键帽
    // 组合符（\u20E3）与标签变体（\u{E0020}-\u{E007F}）。标点不在任何
    // 区间内，保留作自然停顿；剔除后连续空白折叠为一个空格。
    const TTS_EMOJI_RE = /[\u{1F300}-\u{1FAFF}\u{1F000}-\u{1F2FF}\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\uFE00-\uFE0F\u200D\u20E3\u{E0020}-\u{E007F}]/gu;
    function stripEmojiForTTS(text) {
        return String(text == null ? '' : text)
            .replace(TTS_EMOJI_RE, '')     // emoji/修饰符/ZWJ 序列整体剔除
            .replace(/\s+/g, ' ')          // 连续空白折叠为一个空格
            .trim();
    }

    // 朗读音色回退链：localStorage(xiaoju3_tts_voice) → /api/status 下发的
    // tts_voice（后端 .env TTS_VOICE，localStorage 为空时采用并写回）→
    // getVoices() 首个中文女声（name 含女性特征词）→ 首个 zh 音色 →
    // 引擎默认音色（不设 utter.voice）。
    const TTS_VOICE_KEY = 'xiaoju3_tts_voice';
    // 女性特征词（zh 音色 name 命中其一即视为女声，大小写不敏感）
    const TTS_FEMALE_HINTS = ['晓晓', '小艺', '悦', 'female', 'Xiaoxiao'];
    // /api/status 下发的 tts_voice（空串表示后端未配置）
    let backendTTSVoice = '';

    function getStoredTTSVoiceName() {
        try { return localStorage.getItem(TTS_VOICE_KEY); } catch (e) { return null; }
    }

    // zh 音色列表（lang 以 zh 开头，兼容 zh-CN / zh-Hans-CN 等写法）
    function listZhVoices() {
        const voices = (window.speechSynthesis && window.speechSynthesis.getVoices()) || [];
        return voices.filter(v => /^zh/i.test(String(v.lang || '')));
    }

    function isFemaleZhVoice(voice) {
        const name = String((voice && voice.name) || '').toLowerCase();
        return TTS_FEMALE_HINTS.some(hint => name.indexOf(hint.toLowerCase()) !== -1);
    }

    // 按回退链解析当前朗读音色；返回 null 表示交给引擎默认音色
    function pickTTSVoice() {
        const zhVoices = listZhVoices();
        const wanted = getStoredTTSVoiceName() || backendTTSVoice;
        if (wanted) {
            const all = (window.speechSynthesis && window.speechSynthesis.getVoices()) || [];
            const hit = zhVoices.find(v => v.name === wanted) ||
                all.find(v => v.name === wanted);
            if (hit) return hit;                    // 用户/后端指定且当前可用
        }
        if (!zhVoices.length) return null;          // 无 zh 音色：默认音色兜底
        return zhVoices.find(isFemaleZhVoice) || zhVoices[0];   // 首个中文女声 → 首个 zh
    }

    // /api/status 下发 tts_voice 的采用与写回（仅 localStorage 为空时接管；
    // 同值轮询直接跳过，避免每 2s 重复重建下拉）
    function adoptBackendTTSVoice(val) {
        if (typeof val !== 'string' || !val || backendTTSVoice === val) return;
        backendTTSVoice = val;
        if (!getStoredTTSVoiceName()) {
            try { localStorage.setItem(TTS_VOICE_KEY, val); } catch (e) { /* 忽略 */ }
        }
        refreshVoiceSelector();
    }

    // ==================== 0.55 Edge-TTS 播放链路（后端 /api/tts，组 M4 契约） ====================
    // 契约钉死：POST /api/tts body {text, voice} → 200 返回 audio/mpeg 音频流
    // （blob 直接播放）或 4xx/5xx JSON {error}。voice 缺省时后端走默认音色。
    // Edge 音色常量表：与后端 xiaoju3_dashboard.EDGE_VOICES 口径一致（voice id
    // 必须逐字相同，label 为中文说明）；首个为后端默认音色（晓晓）。
    const EDGE_TTS_VOICES = [
        { name: 'zh-CN-XiaoxiaoNeural', label: '晓晓-温柔女声' },
        { name: 'zh-CN-XiaoyiNeural',   label: '晓伊-活泼女声' },
        { name: 'zh-CN-XiaomoNeural',   label: '晓墨-阳光女声' },
        { name: 'zh-CN-XiaoqiuNeural',  label: '晓秋-知性女声' },
    ];

    // localStorage 键值协议（键沿用 xiaoju3_tts_voice，测试锁定）：
    // ① 值为 EDGE_TTS_VOICES 中的音色名（如 zh-CN-XiaoxiaoNeural）→ Edge 链：
    //    /api/tts 的 voice 参数即用该值；
    // ② 值含"浏览器"字样（浏览器项写入的哨兵值 '浏览器TTS（降级）'——真值
    //    可阻止 adoptBackendTTSVoice 在 2s 轮询中回填覆盖用户选择）、值含
    //    浏览器音色名（如"Google 普通话"）等非 Edge 音色名、或两者皆空
    //    → 浏览器 TTS 降级链（既有回退链语义零回退）。
    // /api/status 下发的 tts_voice（.env TTS_VOICE）仍经上方 adoptBackendTTSVoice
    // 在 localStorage 为空时写回——后端配置 Edge 音色名即成为 Edge 初始默认。
    function isEdgeTTSVoice(name) {
        return EDGE_TTS_VOICES.some(v => v.name === name);
    }

    // 朗读链路解析：Edge 优先（记忆值为 Edge 音色名），否则浏览器降级链
    function resolveTTSMode() {
        const stored = getStoredTTSVoiceName() || backendTTSVoice;
        if (stored && isEdgeTTSVoice(stored)) return { mode: 'edge', voice: stored };
        // 协议口径：browser 分支返回音色"名称字符串"（SpeechSynthesisVoice
        // 对象则解包 .name；playMsg 浏览器路径不经 plan.voice，自行重挑）
        var v = pickTTSVoice();
        return { mode: 'browser', voice: (v && v.name) ? v.name : v };
    }

    // 音色下拉菜单（纯 JS 动态构建，不改 index.html）：挂在聊天头部工具区。
    // 升级为 Edge 音色列表（/api/tts 云端合成，值 = Edge 音色名）+ "浏览器
    // TTS（降级）"项（值 = ''，走既有回退链）；切换即写 localStorage；
    // 选中项按上方键值协议回显。
    let ttsVoiceSelect = null;
    function refreshVoiceSelector() {
        const actions = document.querySelector('.chat-header .header-actions');
        if (!actions) return;
        if (!ttsVoiceSelect) {
            ttsVoiceSelect = document.createElement('select');
            ttsVoiceSelect.id = 'tts-voice-select';
            ttsVoiceSelect.title = '朗读音色（Edge 云端合成 / 浏览器降级）';
            ttsVoiceSelect.style.cssText =
                'max-width: 140px; font-size: 12px; padding: 3px 4px;' +
                'border: 1px solid var(--color-border); border-radius: var(--radius-tool);' +
                'background: var(--color-card); color: var(--color-text-secondary);' +
                'outline: none; cursor: pointer;';
            ttsVoiceSelect.addEventListener('change', function () {
                const name = ttsVoiceSelect.value;
                try {
                    if (name) {
                        localStorage.setItem(TTS_VOICE_KEY, name);   // Edge 音色名（协议①）
                    } else {
                        // 空值兜底分支（正常情况下浏览器项 value 直接含"浏览
                        // 器"字样，走不到这里）：清除记忆交回退链
                        localStorage.removeItem(TTS_VOICE_KEY);
                    }
                } catch (e) { /* localStorage 不可用时仅本次会话生效 */ }
                showToast(name && name.indexOf('浏览器') === -1
                                ? '朗读音色已切换：' + name
                                : '朗读音色：浏览器 TTS（降级）');
            });
            actions.prepend(ttsVoiceSelect);
        }
        const zhVoices = listZhVoices();
        const browserVoice = pickTTSVoice();   // 降级链解析照常（回退链语义零回退）
        ttsVoiceSelect.innerHTML = '';
        // Edge 音色组：值 = Edge 音色名（协议①，/api/tts 携带 voice 参数）
        EDGE_TTS_VOICES.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.name;
            opt.textContent = v.label + '（Edge）';
            ttsVoiceSelect.appendChild(opt);
        });
        // 浏览器降级项：值含"浏览器"字样（协议②哨兵值，真值可阻断
        // adoptBackendTTSVoice 回填；title 提示降级后实际使用的音色）
        const browserOpt = document.createElement('option');
        browserOpt.value = '浏览器TTS（降级）';
        browserOpt.textContent = '浏览器 TTS（降级）';
        browserOpt.title = browserVoice
            ? '降级音色：' + browserVoice.name
            : '浏览器引擎默认音色（当前 ' + zhVoices.length + ' 个中文音色可用）';
        ttsVoiceSelect.appendChild(browserOpt);
        // 选中项回显：Edge 音色按名回显；浏览器链路（哨兵值/浏览器音色名/空）
        // 回落"浏览器 TTS（降级）"项
        const storedVoice = getStoredTTSVoiceName() || backendTTSVoice;
        ttsVoiceSelect.value = isEdgeTTSVoice(storedVoice)
            ? storedVoice : '浏览器TTS（降级）';
    }

    if (window.speechSynthesis) {
        refreshVoiceSelector();   // 首次构建（部分引擎同步即可列出音色）
        // 音色列表常异步到达：voiceschanged 后重建下拉（addEventListener 与
        // onvoiceschanged 双保险，重建幂等）
        if (typeof window.speechSynthesis.addEventListener === 'function') {
            window.speechSynthesis.addEventListener('voiceschanged', refreshVoiceSelector);
        }
        window.speechSynthesis.onvoiceschanged = refreshVoiceSelector;
    }

    // ==================== 1. 定时请求后端系统状态（2 秒轮询） ====================
    function fetchStatus() {
        fetch('/api/status')
            .then(res => res.json())
            .then(res => {
                if (res.code === 200) {
                    const d = res.data;
                    // 版本徽标（步 A1）：/api/status 下发 version，有值才写
                    // （旧后端无此键时保持空，不显示 undefined）
                    const verEl = document.getElementById('header-version');
                    if (verEl && d.version) {
                        verEl.textContent = 'v' + d.version;
                    }
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
                        tempText.textContent = (typeof d.temperature === 'number'
                ? d.temperature + ' °C'
                : (d.temperature || 'N/A'));   // 字符串占位（如"暂无温度"）直接展示
                    }

                    // TTS 音色回退链第二级：后端 .env TTS_VOICE（payload 契约
                    // 字段 tts_voice；localStorage 为空时采用并写回）
                    adoptBackendTTSVoice(d.tts_voice);

                    // ✍️ 创作者署名（2026-10-02）：不再写入页面标题/顶栏
                    //（2026-10-02 用户口径：标题栏隐藏"为 XUN 而建"，保持
                    // "小橘3号 · 控制台" 原样）；/creator 命令与启动日志
                    // 署名不受影响。creator 字段仍随 /api/status 下发。
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

    // 思考正文展示主链路（2026-10-01 用户口径，DeepSeek 风格改版）：收到
    // 思考内容后【一次性把所有行渲染出来】——[思考]/[计划]/[行动] 各占一行、
    // 徽章分色 + 层级缩进成完整列表（既有逐行淡入 setTimeout 链已废止，
    // 无逐条闪动/逐字打字）；全部渲染完等待 1.5 秒后动画折叠
    //（max-height 收缩约 300ms），折叠完成才显示正文气泡；用户点击折叠
    // 卡片标题可再展开（.think-card-body 既有 max-height + overflow 滚动
    // 保留，展开时内容完整可见）。无阶段标记的思考文本降级沿用原逐字
    // 打字机（约 15ms/字，规格 12-20ms 区间，口径零回退），打完走同一套
    // "等待 → 动画折叠 → 放行正文"节奏。animate=false（历史回放共用入口）
    // 不打字不动画，直接完整填充并保持折叠态、正文气泡立即可见。
    // 注：全部 textContent 注入，无需 escapeHtml（转义反而会显示 HTML 实体），
    // CQ 码仍走 renderCQFace 与正文同口径净化。
    const THINK_TYPE_MS = 15;
    // 折叠节奏常量：全部行渲染完等待 1.5s → 动画折叠约 300ms（CSS 过渡
    // 见 index.html .think-card.think-anim .think-card-body，两处口径一致；
    // JS 常量供兜底收尾定时器取值）
    const THINK_COLLAPSE_DELAY_MS = 1500;
    const THINK_COLLAPSE_MS = 300;
    // 阶段标记行：[思考]/[计划]/[行动] 起始（半角方括号，与后端协议同口径）
    const THINK_STAGE_RE = /^\[(思考|计划|行动)\]/;

    // 把思考文本拆成逐行段：阶段标记行起新段（tag 取标记文字、text 去掉
    // 标记前缀），其余行并入当前段（保留换行，由 pre-wrap 渲染）
    function splitThinkStageLines(text) {
        const segs = [];
        let cur = null;
        String(text == null ? '' : text).split('\n').forEach(function (raw) {
            const line = String(raw).trim();
            if (!line) return;
            const m = line.match(THINK_STAGE_RE);
            if (m) {
                cur = { tag: m[1], text: line.slice(m[0].length).trim() };
                segs.push(cur);
            } else if (cur) {
                cur.text = cur.text ? cur.text + '\n' + line : line;
            } else {
                cur = { tag: '', text: line };
                segs.push(cur);
            }
        });
        return segs;
    }

    // 阶段 → 徽章配色 / 行缩进类映射（2026-10-01 用户口径：三阶段用不同
    // 颜色与缩进区分，形成完整列表视觉；样式见 index.html .think-tag-* /
    // .think-indent-*）
    const THINK_TAG_CLASS = {
        '思考': 'think-tag-think',
        '计划': 'think-tag-plan',
        '行动': 'think-tag-action',
    };
    const THINK_INDENT_CLASS = {
        '思考': 'think-indent-1',
        '计划': 'think-indent-2',
        '行动': 'think-indent-3',
    };

    // 构建单行段元素：阶段标签徽章（[思考]/[计划]/[行动]，分色）+ 灰色正文
    //（textContent 注入免 XSS；无标签段只有正文）
    function buildThinkLineEl(seg) {
        const line = document.createElement('div');
        line.className = 'think-line';
        if (seg.tag) {
            line.classList.add(THINK_INDENT_CLASS[seg.tag] || 'think-indent-1');
            const tag = document.createElement('span');
            tag.className = 'think-line-tag';
            tag.classList.add(THINK_TAG_CLASS[seg.tag] || 'think-tag-think');
            tag.textContent = seg.tag;
            line.appendChild(tag);
        }
        const text = document.createElement('span');
        text.className = 'think-line-text';
        text.textContent = seg.text;
        line.appendChild(text);
        return line;
    }

    // ==================== 思考动画期间正文气泡显隐（DeepSeek 节奏配套） ====================
    // 思考列表展示 → 等待 → 动画折叠完成后才显示正文气泡；.think-pending
    // 的隐藏样式在 index.html（display:none 作用于 .bubble-content /
    // .source-badge / .msg-tools）。历史回放（animate=false）不隐藏、正文
    // 立即可见；任何提前退出（卡片被移除/构建失败）都必须放行正文，绝不
    // 让气泡永久不可见。
    function hideBubbleUntilThinkDone(msgEl) {
        if (msgEl && msgEl.classList) msgEl.classList.add('think-pending');
    }
    function showBubbleNow(msgEl) {
        if (msgEl && msgEl.classList) msgEl.classList.remove('think-pending');
    }

    // 折叠动画（2026-10-01 用户口径）：max-height 技法——先把正文内联
    // max-height 设为当前可视高度（clientHeight，内容超限滚动态时即可视
    // 高度，避免先跳到完整内容高度再收起的视觉跳动），挂 .think-anim 启用
    // CSS transition、强制回流后归零触发收缩；完成后落回既有 .think-collapsed
    // 静态折叠口径（display:none）并清内联样式。选型说明：grid-rows 0fr/1fr
    // 需要额外单行子容器包裹且旧引擎兼容差；max-height 以实测可视高度过渡、
    // 无魔法数字上限，主流引擎表现一致。
    function animateThinkCollapse(card, msgEl) {
        const body = card.querySelector('.think-card-body');
        if (!body || card.classList.contains('think-collapsed')) {
            showBubbleNow(msgEl);   // 无正文容器/已折叠：直接放行正文
            return;
        }
        body.style.maxHeight = body.clientHeight + 'px';
        card.classList.add('think-anim');
        void body.offsetHeight;     // 强制回流：确保过渡从实测高度起算
        body.style.maxHeight = '0px';
        let finished = false;
        const finish = function () {
            if (finished) return;
            finished = true;
            card.classList.add('think-collapsed');   // 复用既有折叠类（点击标题可再展开）
            card.classList.remove('think-anim');
            body.style.maxHeight = '';               // 清内联样式，交回类控制
            showBubbleNow(msgEl);                    // 折叠完成 → 显示正文气泡
        };
        body.addEventListener('transitionend', finish);
        setTimeout(finish, THINK_COLLAPSE_MS + 150); // 兜底收尾（transitionend 丢失时）
    }

    // 渲染完成后的收起节奏（DeepSeek 口径）：全部内容上屏后等待
    // THINK_COLLAPSE_DELAY_MS（1.5s）再动画折叠；等待期间卡片被移除
    //（刷新重建/清空历史）则本链路静默终止——正文放行由接管方负责
    //（刷新路径 syncThinkCard 会启动新动画链重新接管气泡显隐）。
    function scheduleThinkCollapse(card, msgEl) {
        setTimeout(function () {
            if (!card.isConnected) return;
            animateThinkCollapse(card, msgEl);
        }, THINK_COLLAPSE_DELAY_MS);
    }

    function startThinkTypewriter(msgEl, thinkText, animate) {
        const card = msgEl.querySelector('.think-card');
        const body = card && card.querySelector('.think-card-body');
        if (!card || !body) return;
        const text = renderCQFace(thinkText);
        if (!animate || !text) {
            body.textContent = text;   // 历史回放：完整填充、保持折叠、不打字
            return;
        }
        card.classList.remove('think-collapsed');   // 展示期间展开
        hideBubbleUntilThinkDone(msgEl);            // 思考收起后才显示正文气泡
        const segs = splitThinkStageLines(text);
        if (!segs.length || (segs.length === 1 && !segs[0].tag)) {
            // 无阶段标记：降级沿用原逐字打字机（口径零回退），打完走同一套收起节奏
            let shown = 0;
            const timer = setInterval(() => {
                if (!card.isConnected) { clearInterval(timer); return; }   // 卡片被移除即停
                shown += 1;
                body.textContent = text.slice(0, shown);
                const history = document.getElementById('chat-history');
                if (history) history.scrollTop = history.scrollHeight;     // 跟随滚动
                if (shown >= text.length) {
                    clearInterval(timer);
                    scheduleThinkCollapse(card, msgEl);   // 打完 → 等 1.5s → 动画折叠
                }
            }, THINK_TYPE_MS);
            return;
        }
        // 一次性渲染（2026-10-01 用户口径，替代既有逐行淡入链）：全部行
        // 同帧插入、完整列表一次上屏，无逐条闪动/逐字打字；整体浮现动效由
        // .think-line 的 CSS 动画承担（所有行同时淡入，非逐行错峰）
        body.textContent = '';
        segs.forEach(function (seg) { body.appendChild(buildThinkLineEl(seg)); });
        const history = document.getElementById('chat-history');
        if (history) history.scrollTop = history.scrollHeight;     // 跟随滚动
        // 全部渲染完 → 等 1.5s → 动画折叠（约 300ms）→ 显示正文气泡
        scheduleThinkCollapse(card, msgEl);
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

    // ==================== 2.6 系统类消息统一工具栏（任务 5） ====================
    // 首条系统欢迎语与系统提示类消息（清空后的欢迎语、请求失败提示）与
    // AI 回复共用同一套工具栏行为：复制/朗读/点赞/点踩（重新生成依赖
    // dataset.prompt 原消息、转发面向会话回复，系统消息不提供这两项）。
    // 正文包进 .bubble-content，与 appendBotMessage 气泡结构同构——
    // copyText/playMsg/toggleLike/toggleDislike 全局函数零改动直接复用。
    function buildSystemMsgTools() {
        const tools = document.createElement('div');
        tools.className = 'msg-tools';
        tools.innerHTML =
            '<span class="tool-btn" onclick="copyText(this)" title="复制">' +
                '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>' +
            '</span>' +
            '<span class="tool-btn" onclick="playMsg(this)" title="播放">' +
                '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>' +
            '</span>' +
            '<span class="tool-btn like-btn" onclick="toggleLike(this)" title="点赞">' +
                '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path></svg>' +
            '</span>' +
            '<span class="tool-btn dislike-btn" onclick="toggleDislike(this)" title="踩">' +
                '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"></path></svg>' +
            '</span>';
        return tools;
    }

    // 给系统类消息挂统一工具栏：已有 .msg-tools（appendBotMessage 产物）
    // 直接跳过，不重复挂载；挂载后消息自带 .bubble-content，复制/朗读
    // 取到的就是纯文本正文
    function mountSystemToolbar(msgEl) {
        if (!msgEl || msgEl.querySelector('.msg-tools')) return;
        const inner = document.createElement('div');
        inner.style.cssText = 'display:flex; flex-direction:column; gap:5px;';
        const bubble = document.createElement('div');
        bubble.className = 'bubble-content';
        while (msgEl.firstChild) bubble.appendChild(msgEl.firstChild);   // 正文迁入气泡容器
        inner.appendChild(bubble);
        inner.appendChild(buildSystemMsgTools());
        msgEl.appendChild(inner);
    }

    // 首条系统欢迎语（index.html 静态节点）挂统一工具栏；appendBotMessage
    // 生成的消息自带 .msg-tools，经上方 guard 自动跳过
    document.querySelectorAll('#chat-history .message.bot-message')
        .forEach(mountSystemToolbar);

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
        // T4a 常驻诊断②（用户指定文案）：打印切分结果——只有 think 非 null
        // 才会进入下方卡片渲染分支；RAW_REPLY 含 <think> 而本行 PARSED_THINK
        // 为 null，即切分环节异常（此时正文会带出标签原文）
        console.log("PARSED_THINK:", thinkParts.think, "PARSED_BODY:", thinkParts.body);
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
            // T4a 常驻诊断③（用户指定文案）：卡片渲染分支入口——本行出现
            // 而 F12 Elements 里无 .think-card，即"执行了但插入/显示被静默
            // 吞掉"，配合下方实测校验定位
            console.log("RENDERING_THINK_CARD...");
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
            // T4a 强制渲染兜底：插入调用零异常 ≠ 卡片真的挂上了——实测
            // 校验 .think-card 是否真实存在（静默失败在此现形）；缺失且
            // 思考文本非空时，用最裸的 DOM 原语（createElement + classList
            // + prepend，不经任何可能被覆盖的快捷方法/构建函数）手工构建
            // 卡片（🧠 图标 + ▼ 折叠箭头 + 可展开思考文本）强制补插
            if (!botMsg.querySelector('.think-card') && thinkParts.think) {
                try {
                    const fbCard = document.createElement('div');
                    fbCard.classList.add('think-card');
                    fbCard.classList.add('think-collapsed');
                    const fbHeader = document.createElement('div');
                    fbHeader.classList.add('think-card-header');
                    fbHeader.setAttribute('onclick', 'toggleThinkCard(this)');
                    fbHeader.setAttribute('title', '展开/收起思考过程');
                    const fbIcon = document.createElement('span');
                    fbIcon.textContent = '🧠';
                    const fbTitle = document.createElement('span');
                    fbTitle.classList.add('think-card-title');
                    fbTitle.textContent = '思考过程';
                    const fbArrow = document.createElement('span');
                    fbArrow.classList.add('think-card-arrow');
                    fbArrow.textContent = '▼';
                    const fbBody = document.createElement('div');
                    fbBody.classList.add('think-card-body');
                    // 思考文本 textContent 注入（可展开、免 XSS），与打字机同口径净化
                    fbBody.textContent = renderCQFace(thinkParts.think);
                    fbHeader.appendChild(fbIcon);
                    fbHeader.appendChild(fbTitle);
                    fbHeader.appendChild(fbArrow);
                    fbCard.appendChild(fbHeader);
                    fbCard.appendChild(fbBody);
                    botMsg.prepend(fbCard);
                } catch (mErr) {
                    console.error("CoT Render Error: ", mErr);
                }
                // 兜底插入后再校验一次：卡片仍未挂上 → 最终降级为深色纯
                // 文本块（复用 F4 既有 buildThinkFallbackBlock 实现）
                if (!botMsg.querySelector('.think-card')) {
                    try {
                        botMsg.prepend(buildThinkFallbackBlock(thinkParts.think));
                    } catch (fbErr) {
                        console.error("CoT Render Error: ", fbErr);
                    }
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
                // T4a 常驻诊断①（用户指定文案）：打印后端原始回复全文——
                // <think> 包装块应在此可见；F12 若连本行都看不到，说明
                // 浏览器加载的是旧版 console.js（缓存或部署未更新）
                console.log("RAW_REPLY:", res.data.reply);
                const botMsg = appendBotMessage(res.data.reply, res.data.source, text);
                // 本地与远端同步：后端已将本轮问答落盘 /api/history
                // 回复到达提示音（界面文档 §6.2 / §9.1，AudioContext 缺席时静默降级）
                if (window.xiaoju3Sound) window.xiaoju3Sound.ding();
                // 任务 5：自动朗读开启时，AI 回复到达即自动播报（与手动播放同链路）
                if (autoTTSEnabled()) speakMessageEl(botMsg);
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
            mountSystemToolbar(errMsg);   // 系统提示类消息同样挂统一工具栏
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
            // 任务 5：重新生成的回复同样是 AI 回复，自动朗读开启时一并播报
            if (autoTTSEnabled()) speakMessageEl(msgEl);
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

    // 播放（朗读）——任务 5：手动点播放与自动朗读共用同一条链路入口
    // speakMessageEl（见下），本函数仅作转发。
    window.playMsg = function(el) {
        speakMessageEl(el);
    };

    // 朗读链路共用入口（手动播放 / 自动朗读同一份逻辑）——Edge-TTS 优先：
    // 解析链路（协议见 0.55）→ Edge 音色时 POST /api/tts（voice 参数带上）
    // → blob → Audio 播放；网络/4xx/5xx/超时/播放失败一律自动降级浏览器
    // speechSynthesis（清队列防连点、emoji 剔除与音色回退链零回退）。
    // emoji 剔除在入口统一做一次，两条链路共用同一份净化文本（任务 7：
    // 引擎读不出 emoji，标点保留作自然停顿）。
    function speakMessageEl(el) {
        const text = el.closest('.message').querySelector('.bubble-content').innerText;
        const speakText = stripEmojiForTTS(text);
        if (!speakText) return;
        const plan = resolveTTSMode();
        if (plan.mode !== 'edge') {
            speakWithBrowserTTS(speakText);   // 浏览器音色/未配置 Edge：原链直走
            return;
        }
        requestEdgeTTS(speakText, plan.voice)
            .then(playAudioBlob)
            .catch(() => speakWithBrowserTTS(speakText));   // 任何失败 → 自动降级
    }

    // Edge-TTS 请求：POST /api/tts {text, voice} → 200 audio/mpeg → blob。
    // AbortController 超时 8s（超时按失败降级）；非 2xx（后端 4xx/5xx JSON
    // {error}）或 200 但 Content-Type 非音频（异常网关）一律抛错走降级。
    const EDGE_TTS_TIMEOUT_MS = 8000;
    let edgeAudio = null;   // Audio 单例：连点时打断上一段，不叠音
    function requestEdgeTTS(text, voice) {
        let timer = null;
        const ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
        if (ctrl) timer = setTimeout(() => ctrl.abort(), EDGE_TTS_TIMEOUT_MS);
        return fetch('/api/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, voice: voice }),
            signal: ctrl ? ctrl.signal : undefined
        }).then(res => {
            if (!res.ok) throw new Error('TTS HTTP ' + res.status);
            return res.blob();
        }).then(blob => {
            if (blob && blob.type && blob.type.indexOf('audio') !== 0) {
                throw new Error('TTS 响应非音频：' + blob.type);
            }
            if (timer) clearTimeout(timer);
            return blob;
        }, err => {
            if (timer) clearTimeout(timer);
            throw err;
        });
    }

    // blob → Audio 播放（URL.createObjectURL；播完/出错释放，Audio 单例防叠音）
    function playAudioBlob(blob) {
        return new Promise((resolve, reject) => {
            try {
                const url = URL.createObjectURL(blob);
                if (edgeAudio) edgeAudio.pause();
                edgeAudio = new Audio();
                edgeAudio.onended = () => { URL.revokeObjectURL(url); resolve(); };
                edgeAudio.onerror = () => { URL.revokeObjectURL(url); reject(new Error('音频播放失败')); };
                edgeAudio.src = url;
                const p = edgeAudio.play();
                if (p && p.catch) {
                    p.catch(() => { URL.revokeObjectURL(url); reject(new Error('自动播放被拦截')); });
                }
            } catch (e) { reject(e); }
        });
    }

    // 浏览器 TTS 降级链（既有链路零回退）：每次播放前清空队列防连点；
    // 按回退链选择音色（localStorage → /api/status tts_voice → 中文女声 → zh
    // → 引擎默认），无可用音色时不设 utter.voice
    function speakWithBrowserTTS(text) {
        window.speechSynthesis.cancel(); // 清空之前的播放队列
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = 'zh-CN';
        const voice = pickTTSVoice();
        if (voice) utter.voice = voice;
        window.speechSynthesis.speak(utter);
    }

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
                    // 清空后重建欢迎语并挂统一工具栏（与首条系统欢迎语同口径）
                    history.innerHTML = '';
                    const welcome = document.createElement('div');
                    welcome.className = 'message bot-message';
                    welcome.textContent = '你好！我是小橘3号，很高兴为你服务喵~';
                    mountSystemToolbar(welcome);
                    history.appendChild(welcome);
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

    // ==================== 7.5 终端记录标签页（对话窗口 / 终端记录切换） ====================
    // 终端记录入口（R3 后端契约承接）：标签栏切换对话窗口与终端记录两个内
    // 容区。终端记录经 GET /api/history?source=terminal 读取（后端契约：文件
    // 缺失恒 200 空列表，消息为纯 [{role, content}]），只读展示——无输入框、
    // 清空按钮禁用、消息不带操作工具栏；思考块沿用 splitThinkBlock 收敛为
    // 折叠卡片（历史回放口径：不打字、直接折叠展示全文）。切入即拉最新，
    // 停留期间每 15 秒自动刷新（降频口径：终端 CLI 每轮落盘，页面跟随，
    // 5s 轮询曾致 /api/history 后端日志量偏高），⟳ 手动刷新随时可用；
    // 竞态守卫（请求序号）丢弃慢响应，慢网不回写旧数据。
    const TERMINAL_HISTORY_URL = '/api/history?source=terminal';
    const TERMINAL_REFRESH_MS = 15000;
    const tabConsoleBtn = document.getElementById('tab-console');
    const tabTerminalBtn = document.getElementById('tab-terminal');
    const terminalPaneEl = document.getElementById('terminal-pane');
    const terminalHistoryEl = document.getElementById('terminal-history');
    const chatHistoryPaneEl = document.getElementById('chat-history');
    const chatInputAreaEl = document.querySelector('.chat-input-area');
    let terminalRefreshTimer = null;
    let terminalFetchSeq = 0;

    // 单条终端记录渲染（只读：无工具栏、无来源徽标；用户消息 textContent
    // 注入，AI 正文走 renderRich 转义——与聊天视图同口径免 XSS）
    function appendTerminalEntry(msg) {
        if (!msg || typeof msg.content !== 'string') return;
        if (msg.role === 'user') {
            const userEl = document.createElement('div');
            userEl.className = 'message user-message';
            userEl.textContent = msg.content;
            terminalHistoryEl.appendChild(userEl);
            return;
        }
        if (msg.role !== 'assistant') return;
        const parts = splitThinkBlock(msg.content);
        const botEl = document.createElement('div');
        botEl.className = 'message bot-message';
        const inner = document.createElement('div');
        inner.style.cssText = 'display:flex; flex-direction:column; gap:5px;';
        const bubble = document.createElement('div');
        bubble.className = 'bubble-content';
        bubble.innerHTML = renderRich(parts.body);
        inner.appendChild(bubble);
        botEl.appendChild(inner);
        if (parts.think !== null) {
            // 思考折叠卡片（不打字不动画，直接折叠展示；文本 textContent 注入免 XSS）
            const card = buildThinkCardEl();
            const cardBody = card.querySelector('.think-card-body');
            if (cardBody) cardBody.textContent = renderCQFace(parts.think);
            botEl.insertBefore(card, inner);   // 卡片在气泡上方（与聊天视图同构）
        }
        terminalHistoryEl.appendChild(botEl);
    }

    function loadTerminalHistory() {
        if (!terminalHistoryEl) return;
        const seq = ++terminalFetchSeq;   // 只采纳最新一次请求的响应
        fetch(TERMINAL_HISTORY_URL)
            .then(res => res.json())
            .then(res => {
                if (seq !== terminalFetchSeq) return;
                terminalHistoryEl.innerHTML = '';
                const messages = (res && res.code === 200 && res.data &&
                                  Array.isArray(res.data.messages))
                    ? res.data.messages : [];
                if (!messages.length) {
                    const empty = document.createElement('div');
                    empty.className = 'terminal-empty';
                    empty.textContent = '暂无终端记录：在终端运行 python xiaoju3.py 对话后，这里会显示终端通道的聊天记录。';
                    terminalHistoryEl.appendChild(empty);
                    return;
                }
                messages.forEach(appendTerminalEntry);
                terminalHistoryEl.scrollTop = terminalHistoryEl.scrollHeight;
            })
            .catch(err => {
                if (seq !== terminalFetchSeq) return;
                terminalHistoryEl.innerHTML = '';
                const tip = document.createElement('div');
                tip.className = 'terminal-empty';
                tip.style.color = '#e0433f';
                tip.textContent = '（终端记录读取失败：' + err.message + '）';
                terminalHistoryEl.appendChild(tip);
            });
    }

    // 标签切换：内容区/输入框互斥显隐 + 清空按钮只对对话窗口生效（终端记录只读）
    function switchChatTab(tab) {
        const isTerminal = tab === 'terminal';
        if (tabConsoleBtn) tabConsoleBtn.classList.toggle('active', !isTerminal);
        if (tabTerminalBtn) tabTerminalBtn.classList.toggle('active', isTerminal);
        if (chatHistoryPaneEl) chatHistoryPaneEl.hidden = isTerminal;
        if (terminalPaneEl) terminalPaneEl.hidden = !isTerminal;
        if (chatInputAreaEl) chatInputAreaEl.hidden = isTerminal;   // 只读：终端页无输入框
        const clearBtnEl = document.getElementById('clear-history');
        if (clearBtnEl) {
            clearBtnEl.disabled = isTerminal;
            clearBtnEl.title = isTerminal
                ? '终端记录为只读；切回对话窗口可清空控制台聊天记录'
                : '清空聊天记录';
        }
        if (isTerminal) {
            loadTerminalHistory();   // 每次切入拉最新
            if (!terminalRefreshTimer) {
                terminalRefreshTimer = setInterval(loadTerminalHistory, TERMINAL_REFRESH_MS);
            }
        } else if (terminalRefreshTimer) {
            clearInterval(terminalRefreshTimer);   // 切走即停，不留后台轮询
            terminalRefreshTimer = null;
        }
    }

    if (tabTerminalBtn) {
        tabTerminalBtn.addEventListener('click', function () { switchChatTab('terminal'); });
    }
    if (tabConsoleBtn) {
        tabConsoleBtn.addEventListener('click', function () { switchChatTab('console'); });
    }
    const terminalRefreshBtn = document.getElementById('terminal-refresh');
    if (terminalRefreshBtn) {
        terminalRefreshBtn.addEventListener('click', loadTerminalHistory);
    }

    // ==================== 8. 缩成加速球（任务 7：网页内缩略模式） ====================
    // 与本地桌宠（desktop-pet.js）不同功能、两者共存：本节只切换 body 的
    // 最小化类与球体显隐，不注入/不修改桌宠任何节点（desktop-pet.js 零改动）。
    // 球体为 index.html 静态节点 #xiaoju3-ball（60px 圆形、橘色 Q 版边框、
    // 小橘头像）；最小化时控制台主体（.sidebar + .chat-area）display:none，
    // 球体 display:block（样式见 index.html）；位置存 localStorage
    // （xiaoju3_ball_pos）刷新保持；互切幂等（重复最小化/展开不报错、不抖动），
    // 球体挂载点缺失时全部静默跳过，无 JS 报错路径。
    const MINIMIZE_CLASS = 'xiaoju3-minimized';
    const BALL_POS_KEY = 'xiaoju3_ball_pos';
    const BALL_SIZE = 60;   // 球体直径（px，与 index.html #xiaoju3-ball 一致）

    function getBallEl() {
        return document.getElementById('xiaoju3-ball');
    }

    // 球体位置钳制在视口内（拖拽中与 resize 重钳制共用）
    function clampBallPos(x, y) {
        const maxW = Math.max(0, document.documentElement.clientWidth - BALL_SIZE);
        const maxH = Math.max(0, document.documentElement.clientHeight - BALL_SIZE);
        return {
            x: Math.min(Math.max(x, 0), maxW),
            y: Math.min(Math.max(y, 0), maxH),
        };
    }

    function applyBallPos(pos) {
        const ball = getBallEl();
        if (!ball) return;
        const c = clampBallPos(pos.x, pos.y);
        ball.style.left = c.x + 'px';
        ball.style.top = c.y + 'px';
        ball.style.right = 'auto';
        ball.style.bottom = 'auto';
    }

    function loadBallPos() {
        try {
            const pos = JSON.parse(localStorage.getItem(BALL_POS_KEY) || 'null');
            if (pos && typeof pos.x === 'number' && typeof pos.y === 'number') return pos;
        } catch (e) { /* 记忆损坏：回退 CSS 默认位（右下角） */ }
        return null;
    }

    function saveBallPos(pos) {
        try { localStorage.setItem(BALL_POS_KEY, JSON.stringify(pos)); }
        catch (e) { /* localStorage 不可用时仅本次会话生效 */ }
    }

    // 最小化/展开互切（幂等）：已是目标状态直接返回，不重复操作
    function setConsoleMinimized(minimized) {
        const ball = getBallEl();
        if (!ball) return;   // 球体挂载点缺失：静默跳过，无 JS 报错路径
        const isMin = document.body.classList.contains(MINIMIZE_CLASS);
        if (isMin === minimized) return;
        document.body.classList.toggle(MINIMIZE_CLASS, minimized);
        if (minimized) {
            const stored = loadBallPos();
            if (stored) applyBallPos(stored);   // 恢复记忆位置；无记忆走 CSS 右下角默认
        }
    }

    // 球体交互初始化：点击展开、指针拖拽移动（拖拽阈值口径与桌宠一致：
    // 位移平方>9），松手超阈值存位置、未拖动视为点击展开；防重复绑定（幂等）
    function initConsoleBall() {
        const ball = getBallEl();
        if (!ball || ball.dataset.ballBound === '1') return;
        ball.dataset.ballBound = '1';
        let dragging = false;
        let moved = false;
        let startX = 0, startY = 0, offX = 0, offY = 0;
        ball.addEventListener('pointerdown', function (e) {
            dragging = true;
            moved = false;
            startX = e.clientX;
            startY = e.clientY;
            const rect = ball.getBoundingClientRect();
            offX = e.clientX - rect.left;
            offY = e.clientY - rect.top;
            try { ball.setPointerCapture(e.pointerId); } catch (err) { /* 老引擎忽略 */ }
        });
        ball.addEventListener('pointermove', function (e) {
            if (!dragging) return;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            if (dx * dx + dy * dy > 9) moved = true;   // 拖拽阈值（位移平方>9）
            if (moved) applyBallPos({ x: e.clientX - offX, y: e.clientY - offY });
        });
        ball.addEventListener('pointerup', function () {
            if (!dragging) return;
            dragging = false;
            if (moved) {
                saveBallPos({
                    x: parseFloat(ball.style.left) || 0,
                    y: parseFloat(ball.style.top) || 0,
                });
            } else {
                setConsoleMinimized(false);   // 未拖动＝点击展开回完整控制台
            }
        });
        // 拖拽被系统打断（来电/手势竞争）：复位拖拽态，不误判为点击
        ball.addEventListener('pointercancel', function () { dragging = false; });
        // 窗口尺寸变化：最小化态下按记忆位置重钳制在视口内
        window.addEventListener('resize', function () {
            if (document.body.classList.contains(MINIMIZE_CLASS)) {
                const pos = loadBallPos();
                if (pos) applyBallPos(pos);
            }
        });
    }

    const minimizeBtn = document.getElementById('console-minimize');
    if (minimizeBtn) {
        minimizeBtn.addEventListener('click', function () {
            setConsoleMinimized(true);
            showToast('已缩成加速球，点击小球恢复');
        });
    }
    initConsoleBall();

    // 球体头像裂图兜底：素材缺失（404）时退化为 🦊 emoji 圆球——不改显隐
    // 类控制（display 仍由 CSS 类管），最小化态永不出现空球/裂图图标
    (function bindBallImgFallback() {
        const ball = getBallEl();
        const img = (ball && ball.querySelector) ? ball.querySelector('img') : null;
        if (!img) return;
        img.addEventListener('error', function () {
            img.remove();
            ball.textContent = '🦊';
            ball.style.textAlign = 'center';
            ball.style.lineHeight = '52px';   // 60px 球体减去上下 3px 橘色描边
            ball.style.fontSize = '30px';
        });
    })();

    // ==================== 首装引导覆盖层（安装器方案步 A4b） ====================
    // 三处零触碰：2s 轮询不暂停、showToast 原样调用、最小化只走 setConsoleMinimized。
    var FIRST_RUN_DONE_KEY = 'xiaoju3_first_run_done';

    function setFirstRunError(msg) {
        const el = document.getElementById('first-run-error');
        if (!el) return;
        if (msg) { el.textContent = msg; el.hidden = false; }
        else { el.textContent = ''; el.hidden = true; }
    }

    function markFirstRunDone() {
        // 跳过语义（前端标记）：localStorage 记 done，后端 .env 不写——
        // 下次启动后端 status 仍 true，但此处守卫命中即不再弹。
        try { localStorage.setItem(FIRST_RUN_DONE_KEY, '1'); } catch (err) { /* storage 不可用忽略 */ }
        const overlay = document.getElementById('first-run-overlay');
        if (overlay) overlay.hidden = true;
    }

    function initFirstRun() {
        // 跳过语义守卫：有 done 标记本轮不弹（必须先于 showFirstRun 判定）
        try {
            if (localStorage.getItem(FIRST_RUN_DONE_KEY) === '1') return;
        } catch (err) { /* storage 不可用：按未跳过处理 */ }
        fetch('/api/first_run/status')
            .then(res => res.json())
            .then(res => {
                if (!(res.code === 200 && res.data && res.data.first_run)) return;
                return fetch('/api/first_run/probes')
                    .then(r2 => r2.json())
                    .then(r2 => { showFirstRun(r2.data && r2.data.probes); });
            })
            .catch(() => { /* 引导层静默降级：控制台照常使用 */ });
    }

    function showFirstRun(probes) {
        // 防御：最小化态先展开（复用既有幂等函数，不直接操作 body 类）
        if (document.body.classList.contains('xiaoju3-minimized')) {
            setConsoleMinimized(false);
        }
        const list = document.getElementById('first-run-probes');
        if (list) {
            list.innerHTML = '';
            (probes || []).forEach(function (p) {
                const li = document.createElement('li');
                li.textContent = (p.ok ? '🟢' : '🟡') + ' ' + p.name + '：' + (p.detail || '');
                list.appendChild(li);
            });
        }
        const urlInput = document.getElementById('first-run-local-url');
        if (urlInput && !urlInput.value) {
            urlInput.value = 'http://127.0.0.1:11434/api/chat';
        }
        const overlay = document.getElementById('first-run-overlay');
        if (overlay) overlay.hidden = false;
    }

    function submitFirstRun(skip) {
        if (skip) {
            // 跳过：只记前端标记，.env 不写（不调 complete 端点）
            markFirstRunDone();
            if (typeof showToast === 'function') {
                showToast('已跳过首装引导，可稍后编辑 xiaoju3_data\\.env');
            }
            return;
        }
        const keyInput = document.getElementById('first-run-deepseek-key');
        const key = ((keyInput && keyInput.value) || '').trim();
        if (key && !(key.indexOf('sk-') === 0 && key.length >= 30)) {
            // 本地格式校验拦截：不发请求
            setFirstRunError('DeepSeek key 格式不对（应以 sk- 开头且足够长），未提交');
            return;
        }
        setFirstRunError('');
        const val = function (id) {
            const el = document.getElementById(id);
            return (el && el.value) ? el.value.trim() : '';
        };
        const payload = {
            env: {
                DEEPSEEK_API_KEY: key,
                HA_URL: val('first-run-ha-url'),
                HA_TOKEN: val('first-run-ha-token'),
                LOCAL_URL: val('first-run-local-url'),
                USER_CITY: val('first-run-user-city'),
            },
            autostart: !!(document.getElementById('first-run-autostart') &&
                          document.getElementById('first-run-autostart').checked),
        };
        fetch('/api/first_run/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(res => res.json())
        .then(res => {
            if (res.code === 200) {
                markFirstRunDone();
                if (typeof showToast === 'function') {
                    showToast('配置已保存，关闭窗口重新打开即生效');
                }
                setFirstRunError('');
                const hint = document.getElementById('first-run-restart-hint');
                if (hint) hint.hidden = false;
                const closeBtn = document.getElementById('first-run-restart-btn');
                if (closeBtn) closeBtn.hidden = false;   // 点击 → window.close() 触发整树终止，重开读新配置
            } else {
                setFirstRunError(res.error || '保存失败，请重试');
            }
        })
        .catch(function () {
            setFirstRunError('网络异常，配置未保存，请重试');
        });
    }

    const frSkipBtn = document.getElementById('first-run-skip');
    if (frSkipBtn) frSkipBtn.addEventListener('click', function () { submitFirstRun(true); });
    const frDoneBtn = document.getElementById('first-run-done');
    if (frDoneBtn) frDoneBtn.addEventListener('click', function () { submitFirstRun(false); });
    const frRestartBtn = document.getElementById('first-run-restart-btn');
    if (frRestartBtn) frRestartBtn.addEventListener('click', function () { window.close(); });
    const frDsLinkBtn = document.getElementById('first-run-ds-link');
    if (frDsLinkBtn) frDsLinkBtn.addEventListener('click', function () {
        // DeepSeek 开放平台（外链按 UI 哨兵口径不放 index.html 字面量，由 JS 打开新窗口）
        try { window.open('https://platform.deepseek.com', '_blank', 'noopener'); } catch (err) { /* 弹窗被拦时忽略 */ }
    });

    // 单点插入（IIFE 尾部）：所有既有绑定完成后再尝试弹引导
    initFirstRun();

})();
