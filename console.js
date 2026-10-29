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

    // 主题切换函数（头部 🦊 按钮已删——#264 B2b 微调拍板：与桌宠菜单
    // 「切换主题」+设置页「界面偏好」双入口冗余）；toggleTheme 保留供
    // 桌宠菜单桥与设置页主题选择器共用
    function toggleTheme() {
        const next = getStoredTheme() === 'orange' ? '' : 'orange';
        try {
            if (next) localStorage.setItem(THEME_KEY, next);
            else localStorage.removeItem(THEME_KEY);
        } catch (e) { /* localStorage 不可用时仅本次会话生效 */ }
        applyTheme(next);
        showToast(next === 'orange' ? '已切换到橘色主题 🦊' : '已切换到深蓝主题');
    }

    // 矢量图标表（2026-10-29 队长要求去 Emoji 凑数）：状态按钮经 innerHTML
    // 换图标（textContent 会抹掉 SVG 露白）；路径=Lucide/Feather 线性风，
    // 与 index.html 顶栏静态图标同源同款，stroke=currentColor 随色态联动。
    const ICON_SVGS = (function (a) {
        return {
            bell: a + '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
            bellOff: a + '<path d="M13.73 21a2 2 0 0 1-3.46 0"/><path d="M18.63 13A17.89 17.89 0 0 1 18 8"/><path d="M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14"/><path d="M18 8a6 6 0 0 0-9.33-5"/><line x1="1" y1="1" x2="23" y2="23"/></svg>',
            volume2: a + '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>',
            volumeX: a + '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>',
            settings: a + '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
            library: a + '<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/></svg>'
        };
    })('<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">');

    // ==================== 现代确认弹窗（2026-10-29 队长指令：原生 confirm 全量退役） ====================
    // 对齐 DeepSeek 规范：深色半透明遮罩+居中白圆角卡+加粗标题+灰描述+核心
    // 点缀蓝胶囊主钮+右上 ×。z-index 50000，遮罩全屏覆盖=弹出期背景不可点。
    // Esc/遮罩空白点击/× 均为取消；Enter=确认。textContent 注入零 XSS 面。
    // showConfirm(title, message, onConfirm, opts)：
    //   opts.confirmText（默认'确定'）/ opts.cancelText（默认'取消'）/
    //   opts.showCancel（默认 true；false=单钮提示态）
    function showConfirm(title, message, onConfirm, opts) {
        opts = opts || {};
        const overlay = document.createElement('div');
        overlay.className = 'xj3-modal-overlay';
        const card = document.createElement('div');
        card.className = 'xj3-modal-card';
        card.setAttribute('role', 'dialog');
        card.setAttribute('aria-modal', 'true');
        const closeBtn = document.createElement('button');
        closeBtn.className = 'xj3-modal-close';
        closeBtn.setAttribute('aria-label', '关闭');
        closeBtn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
        const titleEl = document.createElement('div');
        titleEl.className = 'xj3-modal-title';
        titleEl.textContent = title;
        const msgEl = document.createElement('p');
        msgEl.className = 'xj3-modal-msg';
        msgEl.textContent = message;
        const btns = document.createElement('div');
        btns.className = 'xj3-modal-btns';
        let settled = false;
        function close(result) {
            if (settled) return;
            settled = true;
            document.removeEventListener('keydown', onKey, true);
            overlay.remove();
            if (result === 'confirm' && typeof onConfirm === 'function') onConfirm();
        }
        function onKey(e) {
            if (e.key === 'Escape') close('cancel');
            else if (e.key === 'Enter') { e.preventDefault(); close('confirm'); }
        }
        if (opts.showCancel !== false) {
            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'xj3-modal-btn xj3-modal-btn-secondary';
            cancelBtn.textContent = opts.cancelText || '取消';
            cancelBtn.addEventListener('click', function () { close('cancel'); });
            btns.appendChild(cancelBtn);
        }
        const okBtn = document.createElement('button');
        okBtn.className = 'xj3-modal-btn xj3-modal-btn-primary';
        okBtn.textContent = opts.confirmText || '确定';
        okBtn.addEventListener('click', function () { close('confirm'); });
        btns.appendChild(okBtn);
        closeBtn.addEventListener('click', function () { close('cancel'); });
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) close('cancel');
        });
        document.addEventListener('keydown', onKey, true);
        card.appendChild(closeBtn);
        card.appendChild(titleEl);
        card.appendChild(msgEl);
        card.appendChild(btns);
        overlay.appendChild(card);
        document.body.appendChild(overlay);
        okBtn.focus();
    }
    window.showConfirm = showConfirm;   // 全局可达（控制台调试/外部脚本）

    // ==================== 手机端 API_BASE（APK 遥控壳，2026-10-29） ====================
    // 桌面端零变化：__XJ3_API_BASE=''=同源相对路径。APK 内经 localStorage
    // 'xj3_api_base' 配置（如 http://192.168.x.x:5003），fetch/EventSource
    // 统一前缀；Capacitor 环境探活失败/未配置 → 弹后端地址配置卡。
    window.__XJ3_API_BASE = '';
    (function () {
        try {
            if (window.Capacitor) {
                window.__XJ3_API_BASE =
                    localStorage.getItem('xj3_api_base') || '';
            }
        } catch (e) { /* localStorage 不可用：按同源处理 */ }
        const origFetch = window.fetch ? window.fetch.bind(window) : null;
        if (origFetch) {
            window.fetch = function (input, init) {
                try {
                    if (typeof input === 'string' && input.charAt(0) === '/'
                            && window.__XJ3_API_BASE) {
                        input = window.__XJ3_API_BASE + input;
                    }
                } catch (e) { /* 前缀失败按原请求发出 */ }
                return origFetch(input, init);
            };
        }
        const OrigES = window.EventSource;
        if (OrigES) {
            window.EventSource = function (url, cfg) {
                if (typeof url === 'string' && url.charAt(0) === '/'
                        && window.__XJ3_API_BASE) {
                    url = window.__XJ3_API_BASE + url;
                }
                return new OrigES(url, cfg);
            };
            window.EventSource.prototype = OrigES.prototype;
        }
    })();
    function showApiBaseConfig() {
        // 后端地址配置卡（仅 APK 弹）：复用 .xj3-modal-* 样式体系
        const overlay = document.createElement('div');
        overlay.className = 'xj3-modal-overlay';
        const card = document.createElement('div');
        card.className = 'xj3-modal-card';
        card.setAttribute('role', 'dialog');
        card.setAttribute('aria-modal', 'true');
        const titleEl = document.createElement('div');
        titleEl.className = 'xj3-modal-title';
        titleEl.textContent = '连接小橘主机';
        const msgEl = document.createElement('p');
        msgEl.className = 'xj3-modal-msg';
        msgEl.textContent = '填电脑上小橘后端的地址（同一 WiFi 下形如 '
            + 'http://192.168.31.50:5003；Tailscale 则填 100.x.x.x:5003）。'
            + '保存后自动重连。';
        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'http://192.168.31.50:5003';
        input.style.cssText = 'width:100%;box-sizing:border-box;margin-top:14px;'
            + 'padding:10px 14px;border:1px solid #d1d5db;border-radius:10px;'
            + 'font-size:14px;color:#1f2937;';
        const btns = document.createElement('div');
        btns.className = 'xj3-modal-btns';
        const saveBtn = document.createElement('button');
        saveBtn.className = 'xj3-modal-btn xj3-modal-btn-primary';
        saveBtn.textContent = '保存并连接';
        saveBtn.addEventListener('click', function () {
            const base = input.value.trim().replace(/\/+$/, '');
            try { localStorage.setItem('xj3_api_base', base); } catch (e) {}
            window.__XJ3_API_BASE = base;
            overlay.remove();
            window.location.reload();
        });
        btns.appendChild(saveBtn);
        card.appendChild(titleEl);
        card.appendChild(msgEl);
        card.appendChild(input);
        card.appendChild(btns);
        overlay.appendChild(card);
        document.body.appendChild(overlay);
        input.focus();
    }
    if (window.Capacitor) {
        // APK 内：首启/后端失联 → 弹配置卡；已配置且探活成功 → 静默
        setTimeout(function () {
            fetch('/api/health').then(function (r) { return r.json(); })
                .then(function (j) {
                    if (!j || j.status !== 'ok') throw new Error('not ok');
                })
                .catch(function () { showApiBaseConfig(); });
        }, 1500);
        // 桌面专属入口隐藏：截图提问（依赖桌面屏幕捕获链）
        const shotItem = document.querySelector(
            '.dock-menu-item[data-action="screenshot"]');
        if (shotItem) shotItem.hidden = true;
    }

    // 音效引擎自持兜底（2026-10-29 穿透修复）：桌宠 DOM 物理移除时
    // desktop-pet.js 的 WebAudio 引擎随之消失——window.xiaoju3Sound 缺席
    // → 铃铛绑定代码 if (soundBtn && window.xiaoju3Sound) 永假=监听器从未
    // 挂上（真机 CDP 实锤），回复到达 ding 同亡。此处自持同款最小引擎
    //（键 xiaoju3_sound/缺省 on/ding=880+1318.5Hz 双音，与旧引擎状态兼
    // 容）；pet 引擎若回归，此兜底自动让位（window 已存在则不覆盖）。
    if (!window.xiaoju3Sound) {
        const SOUND_KEY = 'xiaoju3_sound';
        let soundCtx = null;
        function soundEnsureCtx() {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;        // 无 AudioContext：静默降级
            try {
                if (!soundCtx) soundCtx = new AC();
                if (soundCtx.state === 'suspended') soundCtx.resume().catch(function () {});
                return soundCtx.state === 'running' ? soundCtx : null;
            } catch (e) { return null; }
        }
        function soundTone(freq, dur, delay, type, vol) {
            const c = soundEnsureCtx();
            if (!c) return;
            try {
                const osc = c.createOscillator();
                const gain = c.createGain();
                const t0 = c.currentTime + (delay || 0);
                osc.type = type || 'sine';
                osc.frequency.value = freq;
                gain.gain.setValueAtTime(0.0001, t0);
                gain.gain.exponentialRampToValueAtTime(vol || 0.08, t0 + 0.012);
                gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
                osc.connect(gain);
                gain.connect(c.destination);
                osc.start(t0);
                osc.stop(t0 + dur + 0.03);
            } catch (e) { /* 合成失败静默：提示音绝不打断主流程 */ }
        }
        window.xiaoju3Sound = {
            enabled: function () {
                try { return (localStorage.getItem(SOUND_KEY) || 'on') !== 'off'; }
                catch (e) { return true; }
            },
            ding: function () {
                if (!this.enabled()) return;
                soundTone(880, 0.10, 0, 'sine', 0.07);
                soundTone(1318.5, 0.16, 0.09, 'sine', 0.06);
            },
            toggle: function () {
                const next = this.enabled() ? 'off' : 'on';
                try { localStorage.setItem(SOUND_KEY, next); } catch (e) {}
                return this.enabled();
            },
        };
    }

    // 音效总开关（WebAudio 引擎：桌面窗侧 desktop-pet.js 或上方自持兜底）
    const soundBtn = document.getElementById('sound-toggle');
    function refreshSoundBtn() {
        if (soundBtn && window.xiaoju3Sound) {
            soundBtn.innerHTML = window.xiaoju3Sound.enabled() ? ICON_SVGS.bell : ICON_SVGS.bellOff;
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
        if (autoTTSBtn) autoTTSBtn.innerHTML = autoTTSEnabled() ? ICON_SVGS.volume2 : ICON_SVGS.volumeX;
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

    // ==================== 1a. 进度条三档变色（尾巴 H） ====================
    // CPU 与内存各自独立判定同一套阈值：<60 绿 / 60–85 黄 / >85 红。
    // 阈值集中常量，后续调整只改这里；颜色同步落在 .bar-* 类与内联样式。
    const BAR_THRESHOLDS = { mid: 60, high: 85 };
    const BAR_COLORS = { low: '#2fa24c', mid: '#eab308', high: '#e0433f' };

    function barLevel(percent) {
        if (percent > BAR_THRESHOLDS.high) return 'high';
        if (percent >= BAR_THRESHOLDS.mid) return 'mid';
        return 'low';
    }

    function applyBar(barEl, percent) {
        if (!barEl) return;
        const level = barLevel(Math.max(0, Math.min(100, Number(percent) || 0)));
        barEl.style.width = percent + '%';
        barEl.style.backgroundColor = BAR_COLORS[level];
        barEl.classList.remove('bar-low', 'bar-mid', 'bar-high');
        barEl.classList.add('bar-' + level);
    }

    function markConnecting() {
        // 失败加载态（2026-10-04 启动优化拍板② B/C 小补）：状态/待办拉取
        // 失败（多为轮询竞态或服务冷启动瞬间）→ UI 显"连接中…"而非静止
        // 旧值像"没数据"；下一轮轮询自动恢复（fetchStatus 2s / loadTodos
        // 30s），不加重试逻辑
        const cpuText = document.getElementById('cpu-text');
        const memText = document.getElementById('mem-text');
        if (cpuText) cpuText.textContent = '连接中…';
        if (memText) memText.textContent = '连接中…';
        const listEl = document.getElementById('todos-list');
        if (listEl) listEl.innerHTML = '<li class="todos-empty">连接中…</li>';
    }

    function fetchStatus() {
        fetch('/api/status')
            .then(res => res.json())
            .then(res => {
                if (res.code === 200) {
                    const d = res.data;
                    // 版本源（#264 B2c 收尾：header 版本号已删，版本只进
                    // VERSION_STATE 供关于卡使用；/api/status 能力保留）
                    if (d.version) {
                        window.__xiaoju3Version = String(d.version);
                        // #UI修复 2026-10-13：页脚版本号（连点 7 次=开发者
                        // 暗入口第二触发点）
                        const fv = document.getElementById('footer-version');
                        if (fv) fv.textContent =
                            'V' + String(d.version);
                    }
                    const cpuText = document.getElementById('cpu-text');
                    const cpuBar = document.getElementById('cpu-bar');
                    if (cpuText && cpuBar) {
                        cpuText.textContent = d.cpu + '%';
                        applyBar(cpuBar, d.cpu);   // 尾巴 H：三档变色
                    }

                    const memText = document.getElementById('mem-text');
                    const memBar = document.getElementById('mem-bar');
                    if (memText && memBar) {
                        memText.textContent = (d.mem_used != null
                            ? d.mem_used + 'GB / ' + d.mem_total + 'GB ('
                              + d.memory + '%)'
                            : d.memory + '%');
                        applyBar(memBar, d.memory);   // 尾巴 H：内存独立三档变色
                    }

                    // 多磁盘（UI 三期队长方案）：disks[] 驱动单行+▼切换
                    window.__disks = Array.isArray(d.disks) ? d.disks : [];
                    if (window.__diskSel == null
                        || window.__diskSel >= window.__disks.length) {
                        window.__diskSel = 0;   // 默认首盘（C:）
                    }
                    window.__updateDiskRow();
                    // 菜单仅在「用户开着」时刷新内容——每 2s 无条件重渲染
                    // 会把用户刚关掉的菜单又顶开（2026-10-26 真浏览器实测抓到）
                    var __dm = document.getElementById('disk-menu');
                    if (__dm && !__dm.hidden) window.__renderDiskMenu();
                    const batRow = document.getElementById('battery-row');
                    if (batRow) {
                        if (d.battery) {
                            batRow.hidden = false;
                            const bt = document.getElementById('battery-text');
                            const bb = document.getElementById('battery-bar');
                            if (bt) bt.textContent = d.battery.percent + '%'
                                + (d.battery.plugged ? ' ⚡' : '');
                            if (bb) bb.style.width = d.battery.percent + '%';
                        } else {
                            batRow.hidden = true;   // 台式机/无电池：整行隐藏
                        }
                    }

                    const tempText = document.getElementById('temp-text');
                    if (tempText) {
                        tempText.textContent = 'GPU '
                            + (typeof d.temperature === 'number'
                               ? d.temperature + '°C'
                               : (d.temperature || 'N/A'));
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
            .catch(err => {
                console.error('获取系统状态失败', err);
                markConnecting();
            });
    }

    fetchStatus();
    setInterval(fetchStatus, 2000);



    // ==================== 1b. 待办卡片（2026-10-04 待办提取，设计稿 §6） ====================
    // 数据=GET /api/todos；30 秒低频轮询（待办非实时数据）+ 标完成后即时刷新；
    // last_job.running 时卡片顶显示"⏳ 正在阅读链接…"（提取在后台线程进行）。
    const TODOS_REFRESH_MS = 30000;

    let todoEditing = false;   // 尾巴 F：优先级编辑模式（默认锁定 pill）
    let gearEl = null;
    // #239 待办说明折叠：展开态本会话 JS 记忆（不持久化，默认每次收起）
    let expandedNotes = [];

    // 尾巴 I（改服务端承载，2026-10-04）：WebView2 InPrivate 下 localStorage
    // 跨启动即焚（同 first_run 方案 C 前科）→ 折叠状态由 GET /api/todos 下发
    // （服务端 todo_ui_state.json），切换经 POST /api/todos/collapsed_groups
    let collapsedGroups = [];   // 最近一次服务端下发（toggle 时基于它切换）

    function toggleGroup(pr) {
        const i = collapsedGroups.indexOf(pr);
        if (i >= 0) collapsedGroups.splice(i, 1);
        else collapsedGroups.push(pr);
        fetch('/api/todos/collapsed_groups', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collapsed_groups: collapsedGroups })
        }).then(() => loadTodos())
          .catch(err => console.error('保存折叠状态失败', err));
    }

    function loadTodos() {
        fetch('/api/todos')
            .then(res => res.json())
            .then(res => {
                if (res.code === 200) renderTodos(res.data);
            })
            .catch(err => {
                console.error('获取待办失败', err);
                markConnecting();
            });
    }

    function renderTodos(data) {
        const listEl = document.getElementById('todos-list');
        const countEl = document.getElementById('todos-count-text');
        const jobEl = document.getElementById('todos-job-line');
        if (!listEl) return;
        if (countEl) countEl.textContent = data.pending_count ? `(${data.pending_count})` : '';
        if (gearEl) {
            gearEl.innerHTML = ICON_SVGS.settings;           // 尾巴 F2：单一图标（矢量齿轮，2026-10-29 去 Emoji）
            gearEl.classList.toggle('editing', todoEditing);  // 编辑态橙色高亮
        }
        if (jobEl) {
            const job = data.last_job;
            if (job && job.state === 'running') {
                jobEl.textContent = '⏳ 正在阅读链接…';
                jobEl.hidden = false;
            } else if (job && job.state === 'failed') {
                jobEl.textContent = '❌ 上次提取失败，可重新发送链接重试';
                jobEl.hidden = false;
            } else {
                jobEl.hidden = true;
            }
        }
        // 尾巴 1+C 精确版（2026-10-04）：P0/P1/P2 分区视图——各区带标题行
        // （── Px ──），空分区不显示；pill 点即改后 loadTodos 全量刷新 =
        // 条目实时移动到对应分区；分区内沿用 items 既有顺序（id 倒序）
        if (Array.isArray(data.collapsed_groups)) {
            collapsedGroups = data.collapsed_groups;   // 尾巴 I：服务端下发折叠状态
        }
        const items = data.todos;
        if (!items.length) {
            listEl.innerHTML = '<li class="todos-empty">暂无待办</li>';
            return;
        }
        // 尾巴 C 扩展修复（2026-10-04）：六档字典——旧三档初始化遇 P3+ 条目
        // 时 byPriority[pr] 为 undefined，分组循环读 .length 即 TypeError，
        // renderTodos 整体中断（卡片"暂无待办"+ 齿轮点击视觉失效的根因）
        const byPriority = { P0: [], P1: [], P2: [], P3: [], P4: [], P5: [] };
        items.forEach(t => {
            // 防再犯（2026-10-05）：priority 不在六档白名单时原逻辑静默回退
            // P1 组，脏数据伪装成正常条目（#242/#243 content↔priority 颠倒
            // 即此相——文字 P3/标签 P1）。缺省空值走 || 'P1' 不算非法，不警告
            // 时间老化（2026-10-07）：分组键用生效档 effective_priority
            // （服务端 COALESCE，未老化=原档）；"↑已升"标记在条目行渲染
            const eff = t.effective_priority || t.priority || 'P1';
            if (t.priority && !byPriority[eff]) {
                console.warn(`[todos] 非法 priority: "${eff}"（id=${t.id}），已回退至 P1 组`);
            }
            (byPriority[eff] || byPriority.P1).push(t);
        });
        let html = '';
        // #351 一期（2026-10-25）：侧栏紧凑视图——非编辑模式跨组只显示
        // 未完成前 5 条（P0 置顶天然成立：组序即优先级序），超出收进
        // "还有 X 项"尾行，防把左栏撑爆；编辑模式全量（改档需看全）。
        const pendingTotal = items.filter(t => t.status !== 'done').length;
        const compact = !todoEditing && pendingTotal > 5;
        let compactQuota = 5;
        let compactHidden = 0;
        for (const pr of ['P0', 'P1', 'P2', 'P3', 'P4', 'P5']) {
            const group = byPriority[pr] || [];   // 防御兜底：未知档位不崩
            if (!group.length) continue;   // 空分区不显示
            // 尾巴 I：分区可折叠——标题显示条数与箭头，折叠分区不输出条目
            const collapsed = collapsedGroups.includes(pr);
            const arrow = collapsed ? '▸' : '▾';
            html += `<li class="todo-group-title" data-pr="${pr}" title="点击折叠/展开">` +
                `${arrow} ── ${pr} ── (${group.length})</li>`;
            if (collapsed) continue;
            // 紧凑视图：本组只取未完成条目按剩余配额截取
            let groupRows = group;
            if (compact) {
                const pendingRows = group.filter(t => t.status !== 'done');
                const take = pendingRows.slice(0, Math.max(0, compactQuota));
                compactHidden += pendingRows.length - take.length;
                compactQuota -= take.length;
                groupRows = take;
            }
            html += groupRows.map(t => {
                const doneCls = t.status === 'done' ? ' done' : '';
                const checked = t.status === 'done' ? ' checked' : '';
                // 尾巴 F 改（用户精确要求）：锁定时 pills 完全不渲染（隐藏而非灰显）
            // 尾巴 C 扩展（用户拍板）：优先级下拉选择器——编辑态原生 select
            // 六项（P0-P5，可上下滚动），选择即 POST priority；锁定态只读
            // 徽标显示当前值（不可改）
            const prOptions = ['P0', 'P1', 'P2', 'P3', 'P4', 'P5'].map(p =>
                `<option value="${p}"${p === pr ? ' selected' : ''}>${p}</option>`).join('');
            const prControl = todoEditing
                ? `<select class="todo-pr-select" title="优先级">${prOptions}</select>`
                : `<span class="todo-pr-badge${pr === 'P0' ? ' todo-pr-p0' : ''}" title="点 ⚙️ 进入编辑模式后可改">${pr}</span>`;
            // #238：垃圾桶仅对已完成项渲染（pending 无删除入口）
            const delBtn = t.status === 'done'
                ? `<button class="todo-del" data-id="${t.id}" title="删除这条已完成待办">🗑️</button>`
                : '';
            // #239 待办说明折叠（2026-10-05）：note 非空 → 主任务下渲染
            // "淡淡说明"行（默认收起，▸/▾ 切换，本会话 JS 记忆展开态）；
            // 编辑模式下说明行变 textarea + 保存（POST /api/todos/<id>/note）
            const note = (t.note || '').trim();
            const expanded = expandedNotes.includes(t.id);
            let noteHtml = '';
            if (note || todoEditing) {
                if (todoEditing) {
                    noteHtml = `<div class="todo-item" style="padding:0 4px 4px 20px;">` +
                        `<textarea class="todo-note-edit" data-id="${t.id}">${escapeHtml(note)}</textarea>` +
                        `<button class="todo-note-save" data-id="${t.id}" title="保存说明">保存</button></div>`;
                } else if (note) {
                    const arrowN = expanded ? '▾' : '▸';
                    noteHtml = `<div class="todo-item" style="padding:0 4px 4px 20px;">` +
                        `<span class="todo-note-toggle" data-id="${t.id}" title="展开/收起说明">${arrowN}</span>` +
                        (expanded ? `<div class="todo-note">${escapeHtml(note)}</div>` : '') +
                        `</div>`;
                }
            }
            // 时间老化（2026-10-07 拍板②）："↑已升"轻量标记——生效档≠原档
            // 时渲染，悬浮 title 显示 原档 → 现档
            const agedBadge = (t.effective_priority && t.effective_priority !== t.priority)
                ? `<span class="todo-aged" title="时间老化：${t.priority} → ${t.effective_priority}">↑已升</span> `
                : '';
            const todoTime = (t.created_at || '').slice(11, 16);   // HH:MM
            return `<li class="todo-item${doneCls}" data-id="${t.id}">` +
                    `<input type="checkbox" class="todo-check"${checked} title="勾选=完成，取消=恢复">` +
                    `${agedBadge}<span class="todo-text">${escapeHtml(t.content)}</span>` +
                    (todoTime ? `<span class="todo-time">${todoTime}</span>` : '') +
                    `${prControl}${delBtn}</li>` + noteHtml;
            }).join('');
        }
        // 紧凑视图尾行：被收起的未完成条目计数（点击 ⚙️ 进编辑模式查看全部）
        if (compact && compactHidden > 0) {
            html += `<li class="todo-more" title="点 ⚙️ 进入编辑模式查看全部">还有 ${compactHidden} 项待办…</li>`;
        }
        listEl.innerHTML = html;
    }

    gearEl = document.getElementById('todos-edit-gear');
    if (gearEl) {
        gearEl.addEventListener('click', function () {
            todoEditing = !todoEditing;
            loadTodos();   // 重渲染使 pill 锁定/解锁立即生效
        });
    }

    const todosListEl = document.getElementById('todos-list');
    if (todosListEl) {
        // 尾巴 I：分区标题点击 → 折叠/展开（click 事件——标题无值变化，
        // change 永不触发；v12 曾误放 change 监听器内成死代码，已纠）
        todosListEl.addEventListener('click', function (ev) {
            const title = ev.target.closest('li.todo-group-title');
            if (title) {
                toggleGroup(title.dataset.pr);
                loadTodos();
                return;
            }
            // #239：说明折叠切换（▸/▾）
            const toggle = ev.target.closest('span.todo-note-toggle');
            if (toggle) {
                const tid = parseInt(toggle.dataset.id, 10);
                const i = expandedNotes.indexOf(tid);
                if (i >= 0) expandedNotes.splice(i, 1);
                else expandedNotes.push(tid);
                loadTodos();
                return;
            }
            // #239：编辑模式说明保存
            const saveBtn = ev.target.closest('button.todo-note-save');
            if (saveBtn) {
                const tid = parseInt(saveBtn.dataset.id, 10);
                const box = todosListEl.querySelector(
                    `textarea.todo-note-edit[data-id="${tid}"]`);
                if (!box) return;
                fetch(`/api/todos/${tid}/note`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ note: box.value })
                }).then(() => loadTodos())
                  .catch(err => console.error('保存待办说明失败', err));
            }
            // #238：删除单条待办（仅已完成项有入口；确认弹窗二次确认 → DELETE 硬删）
            const delBtn = ev.target.closest('button.todo-del');
            if (delBtn) {
                const tid = parseInt(delBtn.dataset.id, 10);
                showConfirm('删除已完成待办',
                    '确定删除这条已完成的待办？删除后不可恢复。',
                    function () {
                        fetch(`/api/todos/${tid}`, { method: 'DELETE' })
                            .then(() => loadTodos())
                            .catch(err => console.error('删除待办失败', err));
                    }, { confirmText: '删除' });
            }
        });
        // 复选框 + 优先级下拉：值变化类交互走 change（勾=完成/取消=恢复、
        // 下拉选优先级即改）
        todosListEl.addEventListener('change', function (ev) {
            const box = ev.target.closest('input.todo-check');
            if (box) {
                const li = box.closest('li.todo-item');
                if (!li) return;
                const action = box.checked ? 'done' : 'reopen';
                fetch(`/api/todos/${li.dataset.id}/${action}`, { method: 'POST' })
                    .then(() => loadTodos())
                    .catch(err => console.error('切换待办状态失败', err));
                return;
            }
            const sel = ev.target.closest('select.todo-pr-select');
            if (sel) {
                const li = sel.closest('li.todo-item');
                if (!li) return;
                fetch(`/api/todos/${li.dataset.id}/priority`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ priority: sel.value })
                }).then(() => loadTodos())
                  .catch(err => console.error('设置待办优先级失败', err));
            }
        });
    }

    loadTodos();
    setInterval(loadTodos, TODOS_REFRESH_MS);

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
        // 行内代码+粗体+标题（2026-10-28 三轮实锤：`xxx`/**bold**/### heading
        // 裸奔出戏）：转义后按序解析，零注入面
        return renderCQFace(escapeHtml(text))
            .replace(/`([^`\n]+)`/g, '<code class="md-code">$1</code>')
            .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
            .replace(/^#{1,4}\s+(.+)$/gm, '<b class="md-heading">$1</b>')
            .replace(/\n/g, '<br>');
    }

    // ==================== Markdown 表格渲染（2026-10-28，总线选股清单实锤） ====================
    // 总线选股结果/未来插件产出含 markdown 表格（|---| 特征），原 renderRich
    // 只做转义+换行 → 竖线乱码。这里把连续表格行解析成 HTML <table>，其余
    // 文本块原样 renderRich。纯转义渲染，无注入面（单元格走 escapeHtml）。
    function isTableSeparatorLine(line) {
        const t = line.trim();
        return /^\|[\s:|-]+\|$/.test(t) && t.indexOf('-') !== -1;
    }

    function isTableRowLine(line) {
        const t = line.trim();
        return t.startsWith('|') && t.endsWith('|') && t.length >= 2;
    }

    function buildTableHtml(headerCells, bodyRows) {
        const th = headerCells.map(function (c) {
            return '<th>' + escapeHtml(c.trim()) + '</th>';
        }).join('');
        const trs = bodyRows.map(function (row) {
            const tds = row.map(function (c) {
                return '<td>' + escapeHtml(c.trim()) + '</td>';
            }).join('');
            return '<tr>' + tds + '</tr>';
        }).join('');
        return '<div class="md-table-wrap"><table class="md-table">'
            + '<thead><tr>' + th + '</tr></thead>'
            + '<tbody>' + trs + '</tbody></table></div>';
    }

    function renderRichTables(text) {
        const lines = String(text || '').split('\n');
        const out = [];
        let i = 0;
        while (i < lines.length) {
            // 表块识别：当前行是表行，且下一行是 |---| 分隔行
            if (i + 1 < lines.length && isTableRowLine(lines[i])
                    && isTableSeparatorLine(lines[i + 1])) {
                const header = lines[i].trim().replace(/^\||\|$/g, '').split('|');
                i += 2;
                const bodyRows = [];
                while (i < lines.length && isTableRowLine(lines[i])) {
                    bodyRows.push(lines[i].trim().replace(/^\||\|$/g, '').split('|'));
                    i += 1;
                }
                out.push(buildTableHtml(header, bodyRows));
            } else {
                out.push(renderRich(lines[i]));
                i += 1;
            }
        }
        return out.join('\n');
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

    // 直出思维流块（2026-10-22 二轮拍板：废弃折叠卡，对标 DeepSeek）：
    // 🧠 标签行 + 灰色小号思考行直接外冒，纯静态无折叠无动画；流式态复用
    // 同一 DOM 形态（ensureThinkCard），最终/历史回放/刷新共用本构建器。
    // 全部 textContent 注入免 XSS；[思考]/[计划]/[行动] 前缀剥除不显示
    function buildThinkLiveBlock(thinkText) {
        const wrap = document.createElement('div');
        wrap.className = 'think-live';
        const label = document.createElement('div');
        label.className = 'think-live-label';
        label.textContent = '🧠 思考过程';
        wrap.appendChild(label);
        splitThinkStageLines(thinkText).forEach(function (seg) {
            const row = document.createElement('div');
            row.className = 'think-live-line';
            row.textContent = seg.text;
            wrap.appendChild(row);
        });
        return wrap;
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

    // 阶段标记行：[思考]/[计划]/[行动] 起始（半角方括号，与后端协议同口径）
    // 直出模式仅用于剥除前缀（行内容不再渲染徽章/缩进，二轮拍板）
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

    // 刷新重生成后同步思维流块：有 <think> 则重建直出块（无动画），无则移除
    // 旧块。F4 加固：插入手工 DOM 化（不依赖 before 系快捷方法）——显式父
    // 引用 + insertBefore，块位于气泡正文上方；插入失败降级为深色纯文本块。
    function syncThinkCard(msgEl, thinkText) {
        const bubble = msgEl.querySelector('.bubble-content');
        if (!bubble) return;
        const old = msgEl.querySelector('.think-live');
        if (old) old.remove();
        if (thinkText === null) return;   // 新回复没有 think 块：不插
        try {
            bubble.parentNode.insertBefore(buildThinkLiveBlock(thinkText), bubble);
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
    }

    // ==================== IM 式时间分隔（2026-10-10，问题 3） ====================
    // 连续消息只在第一条前显示时间；间隔 >5 分钟插新分隔条；格式分级
    // 今天 HH:MM / 昨天 HH:MM / MM-DD HH:MM / 跨年 YYYY-MM-DD HH:MM。
    let _lastMsgTs = null;   // 上一条消息时间（ISO 字符串或 null）

    function fmtTimeSep(ts) {
        const d = new Date(ts);
        if (isNaN(d)) return '';
        const p2 = n => String(n).padStart(2, '0');
        const hm = `${p2(d.getHours())}:${p2(d.getMinutes())}`;
        const now = new Date();
        if (d.toDateString() === now.toDateString()) return hm;
        const yest = new Date(now); yest.setDate(now.getDate() - 1);
        if (d.toDateString() === yest.toDateString()) return '昨天 ' + hm;
        const md = `${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
        if (d.getFullYear() === now.getFullYear()) return md + ' ' + hm;
        return `${d.getFullYear()}-${md} ` + hm;
    }

    function maybeTimeSeparator(ts) {
        if (!ts) { _lastMsgTs = new Date().toISOString(); return; }
        const t = new Date(ts);
        if (isNaN(t)) return;
        if (_lastMsgTs !== null) {
            const prev = new Date(_lastMsgTs);
            if (!isNaN(prev) && (t - prev) < 5 * 60 * 1000) {
                _lastMsgTs = ts; return;   // 连续消息：不插
            }
        }
        const history = document.getElementById('chat-history');
        const sep = document.createElement('div');
        sep.className = 'time-separator';
        sep.textContent = fmtTimeSep(ts);
        history.appendChild(sep);
        _lastMsgTs = ts;
    }

    function appendUserMessage(text, ts) {
        const history = document.getElementById('chat-history');
        maybeTimeSeparator(ts || new Date().toISOString());
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
        .forEach(function (m) { mountSystemToolbar(m); m.classList.add('msg-enter'); });

    // ==================== 快捷指令卡（2026-10-22 答辩微调） ====================
    // [记待办] 预填输入框并聚焦（话术已过触发词扩展全链验证，用户补内容即发）；
    // [系统自检] 消费既有 /api/health 端点 + toast 播报——零新增后端、
    // 零流式通信逻辑改动（纯前端既有接口消费）
    (function initQuickActions() {
        const quickTodo = document.getElementById('quick-todo');
        if (quickTodo) {
            quickTodo.addEventListener('click', function () {
                const input = document.getElementById('chat-input');
                if (!input) return;
                input.value = '帮我记待办：';
                input.focus();
            });
        }
        const quickCheck = document.getElementById('quick-check');
        if (quickCheck) {
            quickCheck.addEventListener('click', function () {
                fetch('/api/health')
                    .then(res => res.json())
                    .then(d => {
                        showToast(d && d.status === 'ok'
                            ? '🩺 系统自检通过：服务健康'
                            : '⚠️ 自检异常：服务状态 ' + (d && d.status || '未知'));
                    })
                    .catch(() => showToast('❌ 自检失败：服务不可达'));
            });
        }
    })();

    // ==================== 输入扩展栏（UI 一期 2026-10-25，豆包式） ====================
    // ＋ 轻量菜单（上传/截图/链接——二三期能力入口，一期占位 toast）+
    // ⚡技能/🧩插件双入口（浮层清单）+ 上下文标签条（动态渲染当前任务）。
    // 消费 GET /api/plugins（dashboard 新端点）与插件 _JOB 状态。
    (function initInputDock() {
        const menu = document.getElementById('input-dock-menu');
        const popover = document.getElementById('dock-popover');
        const plus = document.getElementById('dock-plus');
        if (!menu || !popover || !plus) return;

        function closeAll() {
            menu.hidden = true;
            popover.hidden = true;
        }
        function toggleMenu() {
            const was = menu.hidden;
            closeAll();
            menu.hidden = !was;
        }
        plus.addEventListener('click', toggleMenu);
        // 外点关闭豁免清单（2026-10-26 修复＋号/技能/插件"点击无响应"：旧版
        // 只认 .input-dock 类而 HTML 里无人带该类→按钮自己的点击也冒泡进
        // closeAll，同一次 click 内开了又关=肉眼无响应。改为显式豁免三个
        // 触发按钮+标签条+两浮层）
        document.addEventListener('click', function (ev) {
            if (!ev.target.closest('#dock-plus, #dock-skills, #dock-plugins, .context-tags-bar')
                && !ev.target.closest('.input-dock-menu')
                && !ev.target.closest('.dock-popover')) closeAll();
        });
        menu.addEventListener('click', function (ev) {
            // 技能/插件按钮自带 fetch+弹层逻辑（绑在按钮本体）——菜单关闭器
            // 跳过，防 closeAll 把异步弹出的清单又关掉
            if (ev.target.closest('#dock-skills, #dock-plugins')) return;
            const item = ev.target.closest('.dock-menu-item');
            if (!item) return;
            closeAll();
            const act = item.dataset.action;
            if (act === 'upload') {
                // UI 三期（队长纠偏 2026-10-26）：上传=附件直读上下文（非建
                // 知识库）——选择器拿绝对路径→后端解析全文挂「下一次对话」→
                // 📎 附件就绪标签，AI 直接看全文回答
                if (!window.pywebview || !window.pywebview.api) {
                    showToast('📎 上传请在桌面窗口中使用（浏览器预览不支持）');
                    return;
                }
                showToast('📎 支持 TXT/PDF/Word/Excel/代码等格式，'
                    + '请选择具体文件，不支持直接选文件夹');
                window.pywebview.api.pick_docs().then(function (r) {
                    if (!r || !r.ok) {
                        showToast('❌ ' + ((r && r.error) || '选择器打开失败'));
                        return;
                    }
                    if (!(r.paths || []).length) return;   // 用户取消：静默
                    showToast('⏳ 正在读取 ' + r.paths.length + ' 个文件…');
                    fetch('/api/doc_upload', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ paths: r.paths })
                    })
                        .then(res => res.json())
                        .then(d => {
                            if (d.code === 200 && (d.data || {}).ok_count > 0) {
                                showAttachBar((d.data.results || [])
                                    .filter(function (x) { return x.ok; })
                                    .map(function (x) {
                                        return {
                                            name: (x.path || '').split(/[\/]/).pop(),
                                            size: x.size || ''
                                        };
                                    }));
                                showToast('📎 文件已就绪，直接提问即可');
                            } else if (d.code === 200) {
                                showToast('❌ 读取失败：'
                                    + (((d.data || {}).results || [])[0] || {}).message);
                            } else {
                                showToast('❌ ' + (d.error || '上传失败'));
                            }
                        })
                        .catch(() => showToast('❌ 上传服务不可达'));
                }).catch(function (e) { showToast('❌ ' + e); });
            } else if (act === 'screenshot') {
                // UI 三期切片 b（2026-10-26）：js_api 隐藏主窗→冻结帧划选→
                // PNG 暂存→📷 条就绪→发送时 GLM-4V-Flash 看图回答
                if (!window.pywebview || !window.pywebview.api) {
                    showToast('📷 截图请在桌面窗口中使用（浏览器预览不支持）');
                    return;
                }
                showToast('📷 划选截图：主窗暂隐，拖红框，Esc 取消');
                window.pywebview.api.snip_now().then(function (r) {
                    if (!r || !r.ok) {
                        var msg = (r && r.error) || '截图失败';
                        showToast(msg.indexOf('❌') === 0 ? msg : '❌ ' + msg);
                        return;
                    }
                    if (!r.path) return;   // 用户取消：静默
                    fetch('/api/screenshot/stage', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ path: r.path })
                    })
                        .then(res => res.json())
                        .then(d => {
                            if (d.code === 200) {
                                showShotBar(d.data.size || '');
                                showToast('📷 截图已就绪，输入问题后发送');
                            } else {
                                showToast('❌ ' + (d.error || '截图暂存失败'));
                            }
                        })
                        .catch(() => showToast('❌ 截图服务不可达'));
                }).catch(function (e) { showToast('❌ ' + e); });
            } else if (act === 'link') {
                const input = document.getElementById('chat-input');
                if (input) { input.value = '总结这个视频 '; input.focus(); }
            }
        });

        // ⚡技能 / 🧩插件 浮层（消费 /api/plugins）
        function showPopover(title, rowsHtml) {
            popover.innerHTML = '<h4>' + title + '</h4>' + rowsHtml;
            closeAll();
            popover.hidden = false;
        }
        // 📎 附件就绪标签（上传→附件直读上下文；随下一次发送消费，发即隐）。
        // v0 芯片形态（2026-10-26 像素级对齐）：白底细边框微阴影圆角小方块，
        // 文件名+大小+右上角 ✕；显隐用 hidden 属性+CSS [hidden] 补丁
        const attachBar = document.getElementById('attach-bar');
        var DOC_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none"'
            + ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
            + ' stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0'
            + ' 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v4a2 2 0 0 0 2 2h6"/></svg>';
        var CAM_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none"'
            + ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
            + ' stroke-linejoin="round"><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2'
            + ' 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-1.5-3Z"/>'
            + '<circle cx="12" cy="13" r="3"/></svg>';
        function showAttachBar(items) {
            if (!attachBar || !(items || []).length) return;
            var chips = items.map(function (f) {
                return '<span class="attach-chip">'
                    + '<span class="attach-chip-ico">' + DOC_SVG + '</span>'
                    + '<span class="attach-chip-body">'
                    + '<span class="attach-chip-name">' + escapeHtml(f.name) + '</span>'
                    + '<span class="attach-chip-size">' + escapeHtml(f.size || '') + '</span>'
                    + '</span>'
                    + '<button class="attach-clear" title="移除附件">✕</button>'
                    + '</span>';
            }).join('');
            attachBar.innerHTML = '<div class="attach-chip-row">' + chips + '</div>'
                + '<div class="attach-ready">📎 文件已就绪（可以直接提问）</div>';
            attachBar.removeAttribute('hidden');
            attachBar.querySelector('.attach-clear').addEventListener(
                'click', function () {
                    fetch('/api/doc_attach/clear', { method: 'POST' })
                        .catch(() => {});
                    attachBar.setAttribute('hidden', '');
                });
        }
        function hideAttachBar() {
            if (attachBar) attachBar.setAttribute('hidden', '');
        }
        window.__xj3HideAttach = function () {
            hideAttachBar();
            if (window.__xj3HideShot) window.__xj3HideShot();
        };   // 发送流钩子（Stream/Legacy 首行调用）：文本附件+截图都随发送消费
        // 幽灵附件态封死（2026-10-26 阻断 Bug②，真机实锤：22:16 传书未发消息
        // →22:21 刷新页面芯片即焚→22:21:51 纯链路测试被注入 5 分钟前的 2500 字
        // 小说全文）。芯片是附件就绪的唯一信标：刷新/重开窗口后芯片必空，
        // 后端滞留的 _DOC_ATTACH/_SHOT_ATTACH 必须同步清空——页面加载即对表。
        fetch('/api/doc_attach/clear', { method: 'POST' }).catch(function () {});
        fetch('/api/screenshot/clear', { method: 'POST' }).catch(function () {});
        // 发送按钮置灰联动（2026-10-26 阻断 Bug①）：输入框空→disabled 置灰
        // 不可点，有字→蓝色可点；发送清空后经 __xj3SyncSendBtn 同步回灰。
        // Enter 键入口走 sendMessage 内空文本守卫，与按钮态同一判定源（trim）。
        var sendBtn = document.getElementById('send-btn');
        var chatInput = document.getElementById('chat-input');
        function syncSendBtn() {
            if (!sendBtn || !chatInput) return;
            sendBtn.disabled = !((chatInput.value || '').trim());
        }
        if (sendBtn && chatInput) {
            chatInput.addEventListener('input', syncSendBtn);
            syncSendBtn();
        }
        window.__xj3SyncSendBtn = syncSendBtn;
        // 📷 截图就绪标签（复用附件条位芯片形态；发送时 GLM-4V 看图回答）
        function showShotBar(size) {
            if (!attachBar) return;
            attachBar.innerHTML = '<div class="attach-chip-row">'
                + '<span class="attach-chip">'
                + '<span class="attach-chip-ico">' + CAM_SVG + '</span>'
                + '<span class="attach-chip-body">'
                + '<span class="attach-chip-name">屏幕截图</span>'
                + '<span class="attach-chip-size">' + escapeHtml(size || '') + '</span>'
                + '</span>'
                + '<button class="attach-clear" title="移除截图">✕</button>'
                + '</span></div>'
                + '<div class="attach-ready">📷 截图已就绪（发送时 AI 直接看图回答）</div>';
            attachBar.removeAttribute('hidden');
            attachBar.querySelector('.attach-clear').addEventListener(
                'click', function () {
                    fetch('/api/screenshot/clear', { method: 'POST' })
                        .catch(() => {});
                    attachBar.setAttribute('hidden', '');
                });
        }
        window.__xj3HideShot = function () {
            if (attachBar) attachBar.setAttribute('hidden', '');
        };
        // 插件快捷指令映射（2026-10-29 队长指令：插件面板从只读列表升级
        // 为可点击入口——点一下等价于输入触发指令并自动发送，走既有总线/
        // intent_router 链；打字触发保持原样不受影响）。不在表内的插件
        // 仍为纯展示。upload 动作=复用 ＋ 菜单的文件选择流（桌面窗口）。
        const PLUGIN_QUICK_ACTIONS = {
            stock_assistant: { label: '帮我选股', send: '帮我选股' },
            dice:            { label: '掷骰子', send: '掷骰子' },
            video_ingest:    { label: '提取视频内容', send: '提取视频内容' },
            doc_ingest:      { label: '上传文档', upload: true },
        };
        function fetchPlugins(kind) {
            fetch('/api/plugins')
                .then(res => res.json())
                .then(res => {
                    const d = (res.data || {});
                    const rows = [];
                    if (kind === 'plugins') {
                        (d.plugins || []).forEach(function (p) {
                            const qa = PLUGIN_QUICK_ACTIONS[p.name];
                            rows.push('<div class="dp-row">🧩 ' + escapeHtml(p.name)
                                + ' <span class="dp-sub">v' + escapeHtml(p.version)
                                + ' · ' + escapeHtml(p.desc || '') + '</span>'
                                + (qa ? '<button class="dp-quick" data-plugin="'
                                    + escapeHtml(p.name) + '" title="点击执行：'
                                    + escapeHtml(qa.label) + '">▶ ' + escapeHtml(qa.label)
                                    + '</button>' : '')
                                + '</div>');
                        });
                        showPopover('外部插件（' + (d.plugins || []).length + '）',
                                    rows.join('') || '<div class="dp-sub">暂无外部插件</div>');
                    } else {
                        (d.skills || []).forEach(function (s) {
                            rows.push('<div class="dp-row">⚡ ' + escapeHtml(s)
                                + '</div>');
                        });
                        showPopover('内置技能（' + (d.skills || []).length + '）',
                                    rows.join(''));
                    }
                })
                .catch(() => showToast('清单获取失败'));
        }
        document.getElementById('dock-skills').addEventListener('click', function () { fetchPlugins('skills'); });
        document.getElementById('dock-plugins').addEventListener('click', function () { fetchPlugins('plugins'); });
        // 插件快捷指令点击（事件委托绑 popover，重渲染不丢监听）：
        // send 型=填输入框即发（window.sendMessage 读输入框，走既有流式链）；
        // upload 型=转发 ＋ 菜单 upload 项（桌面文件选择器）。
        popover.addEventListener('click', function (ev) {
            const chip = ev.target.closest('.dp-quick');
            if (!chip) return;
            const qa = PLUGIN_QUICK_ACTIONS[chip.dataset.plugin];
            if (!qa) return;
            closeAll();
            if (qa.upload) {
                const upItem = document.querySelector(
                    '.dock-menu-item[data-action="upload"]');
                if (upItem) upItem.click();
                return;
            }
            if (qa.send) {
                const inputEl = document.getElementById('chat-input');
                if (!inputEl) return;
                inputEl.value = qa.send;
                window.sendMessage();
            }
        });

        // 上下文标签条：动态渲染（摄取文档计数+转写/扫描任务态）
        function refreshContextTags() {
            const bar = document.getElementById('context-tags-bar');
            if (!bar) return;
            fetch('/api/plugins')
                .then(res => res.json())
                .then(res => {
                    const ctx = (res.data || {}).context || {};
                    const parts = [];
                    if (ctx.doc_count) {
                        // 文档标签可点开清单（2026-10-26：旧版纯 span 零绑定=
                        // 设计缺口；context-tag--link 带指针态）
                        parts.push('<span class="context-tag context-tag--link"'
                            + ' data-action="docs" title="点击查看文档清单">' + ICON_SVGS.library
                            + '已摄取文档 '
                            + ctx.doc_count + '</span>');
                    }
                    if (ctx.video_job === 'running') parts.push('<span class="context-tag">⏳ 转写中</span>');
                    if (ctx.video_last) parts.push('<span class="context-tag">📺 '
                        + escapeHtml(ctx.video_last) + '</span>');
                    if (parts.length) {
                        bar.innerHTML = parts.join('');
                        bar.hidden = false;
                    } else {
                        bar.hidden = true;
                    }
                })
                .catch(() => {});
        }
        // 文档标签点击→文档清单浮层。标签条子元素每 30s 重渲染，事件委托
        // 绑静态父级（bar 本体），重渲染不丢监听。
        // 知识库文档管理器（2026-10-26 队长拍板）：清单每行=📄名（点击即
        // 重挂为附件）+大小/段数/入库时间+↻挂载+🗑删除。path 走 docsCache
        // 索引传递（路径塞 data 属性会被引号反斜杠搞坏）；行内按钮委托绑
        // popover 容器（showPopover 每次 innerHTML 重写不丢监听）。
        var docsCache = [];
        function fmtDocRow(d, i) {
            var sub = [];
            if (d.size) sub.push(escapeHtml(d.size));
            sub.push((d.chunks || 0) + ' 段');
            if (d.ingested_at) sub.push(escapeHtml(d.ingested_at));
            return '<div class="dp-row dp-doc-row">'
                + '<span class="dp-doc-main" data-act="remount" data-idx="' + i
                + '" title="点击挂载为附件，下一条消息 AI 直接读它回答">📄 '
                + escapeHtml(d.title || d.path) + '</span>'
                + '<span class="dp-sub">' + sub.join(' · ') + '</span>'
                + '<span class="dp-doc-acts">'
                + '<button class="dp-doc-btn" data-act="remount" data-idx="' + i
                + '" title="挂载为附件">↻</button>'
                + '<button class="dp-doc-btn dp-doc-del" data-act="del-doc" data-idx="' + i
                + '" title="从知识库彻底删除（切片+向量一并清除）">🗑</button>'
                + '</span></div>';
        }
        const tagsBar = document.getElementById('context-tags-bar');
        if (tagsBar) {
            tagsBar.addEventListener('click', function (ev) {
                const tag = ev.target.closest('[data-action="docs"]');
                if (!tag) return;
                fetch('/api/plugins')
                    .then(res => res.json())
                    .then(res => {
                        const ctx = (res.data || {}).context || {};
                        const docs = ctx.docs || [];
                        docsCache = docs;
                        showPopover('已摄取文档（' + (ctx.doc_count || docs.length) + '）',
                                    docs.map(fmtDocRow).join('')
                                    || '<div class="dp-sub">暂无已摄取文档</div>');
                    })
                    .catch(() => showToast('清单获取失败'));
            });
        }
        popover.addEventListener('click', function (ev) {
            const btn = ev.target.closest('[data-act]');
            if (!btn) return;
            const d = docsCache[parseInt(btn.dataset.idx, 10)];
            if (!d) return;
            if (btn.dataset.act === 'remount') {
                showToast('⏳ 正在挂载「' + (d.title || '文档') + '」…');
                fetch('/api/knowledge/doc/remount', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: d.path })
                }).then(res => res.json()).then(function (r) {
                    if (r.code === 200 && (r.data || {}).ok) {
                        showAttachBar([{ name: r.data.name,
                                         size: r.data.size || (r.data.chars + ' 字符') }]);
                        closeAll();
                        showToast('📎 已挂载「' + r.data.name + '」，直接提问即可'
                            + (r.data.source === 'chunks'
                               ? '（原文已不在，由知识切片拼回）' : ''));
                    } else {
                        showToast('❌ ' + ((r || {}).error || '挂载失败'));
                    }
                }).catch(function () { showToast('❌ 挂载失败'); });
            } else if (btn.dataset.act === 'del-doc') {
                showConfirm('删除知识库文档',
                    '确定从知识库彻底删除《' + (d.title || d.path)
                    + '》？其全部切片与向量将一并删除，不可恢复。',
                    function () {
                        fetch('/api/knowledge/doc/delete', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ path: d.path })
                        }).then(res => res.json()).then(function (r) {
                            if (r.code === 200 && (r.data || {}).ok) {
                                showToast('🗑 已删除《' + (d.title || '') + '》'
                                    + '（' + r.data.chunks + ' 块）');
                        refreshContextTags();   // 计数标签与清单即时同步
                        closeAll();
                    } else {
                        showToast('❌ ' + ((r || {}).error || '删除失败'));
                    }
                }).catch(function () { showToast('❌ 删除失败'); });
                }, { confirmText: '删除' });
            }
        });
        refreshContextTags();
        setInterval(refreshContextTags, 30000);   // 30s 低频（任务态非实时）
    })();


    // ==================== 多磁盘 ▼ 切换（UI 三期 2026-10-26） ====================
    window.__updateDiskRow = function () {
        var dsk = (window.__disks || [])[window.__diskSel || 0];
        var letter = document.getElementById('disk-letter');
        var text = document.getElementById('disk-text');
        var bar = document.getElementById('disk-bar');
        if (!dsk || !text) return;
        if (letter) letter.textContent = '(' + dsk.name + ')';
        if (text) text.textContent = dsk.used + 'GB / ' + dsk.total
            + 'GB (' + dsk.percent + '%)';
        if (bar) bar.style.width = dsk.percent + '%';
    };
    window.__renderDiskMenu = function () {
        var menu = document.getElementById('disk-menu');
        if (!menu) return;
        menu.innerHTML = (window.__disks || []).map(function (d, i) {
            return '<div class="v0-disk-item' + (i === window.__diskSel
                ? ' on' : '') + '" data-i="' + i + '">'
                + '<span>' + d.name + '</span>'
                + '<span>' + d.percent + '%</span></div>';
        }).join('');
        menu.hidden = false;
    };
    var diskTrigger = document.getElementById('disk-trigger');
    var diskMenu = document.getElementById('disk-menu');
    if (diskTrigger && diskMenu) {
        diskTrigger.addEventListener('click', function (ev) {
            ev.stopPropagation();
            if (!window.__disks || !window.__disks.length) return;
            if (diskMenu.hidden) window.__renderDiskMenu();
            else diskMenu.hidden = true;
        });
        diskMenu.addEventListener('click', function (ev) {
            var item = ev.target.closest('.v0-disk-item');
            if (!item) return;
            window.__diskSel = parseInt(item.dataset.i, 10) || 0;
            diskMenu.hidden = true;
            window.__updateDiskRow();
            ev.stopPropagation();
        });
        document.addEventListener('click', function () {
            if (diskMenu && !diskMenu.hidden) diskMenu.hidden = true;
        });   // 外点关闭（触发器/菜单项已 stopPropagation 不受影响）
    }

    // ==================== 语音输入（2026-10-25 UI 二期：🎤 两段式录音+本地转写） ====================
    // 方案：Python sounddevice 后端录音（/api/stt/start|stop 两段式）+
    // faster-whisper 本地转写（复用 video_ingest 的 _deps 底座）——比
    // MediaRecorder 稳（WebView2 getUserMedia 权限事件 pywebview 不代理）。
    // 交互：点击开始（红色波纹呼吸态）→ 再点停止 → 文字自动填入输入框
    //（不自动发送——用户可改后再发，队长口径）。
    (function initVoiceInput() {
        const mic = document.getElementById('mic-btn');
        const input = document.getElementById('chat-input');
        if (!mic || !input) return;
        let recording = false;
        // 请求在飞标志（2026-10-26 生产实锤：webview 对 start 响应处理迟滞
        // 时连点会让 recording 与后端脱同步——在飞期忽略连点+按后端应答
        // 采纳状态，双保险自愈）
        let busy = false;
        mic.addEventListener('click', function () {
            if (busy) return;
            if (!recording) {
                busy = true;
                fetch('/api/stt/start', { method: 'POST' })
                    .then(res => res.json())
                    .then(d => {
                        // 幂等语义：200 一律进录音态（含后端"已在录音中"
                        // note——前端脱同步时自此对齐后端真相）
                        if (d.code === 200) {
                            recording = true;
                            mic.classList.add('recording');
                            mic.title = '录音中…点击停止';
                            showToast((d.data && d.data.note)
                                ? '🎤 继续录音中，说完再点一次结束'
                                : '🎤 录音中，再点一次结束');
                        } else {
                            showToast('❌ ' + (d.error || '录音启动失败'));
                        }
                    })
                    .catch(() => showToast('❌ 录音服务不可达'))
                    .finally(function () { busy = false; });
            } else {
                busy = true;
                mic.classList.remove('recording');
                mic.title = '语音输入（点击开始/停止）';
                recording = false;
                showToast('⏳ 正在识别语音…');
                fetch('/api/stt/stop', { method: 'POST' })
                    .then(res => res.json())
                    .then(d => {
                        if (d.code === 200 && (d.data || {}).text) {
                            input.value = (input.value ? input.value + ' ' : '')
                                          + d.data.text;
                            input.focus();
                            showToast('✅ 已识别填入，可修改后发送');
                        } else if (d.code === 200) {
                            showToast('（没听清内容——' + ((d.data || {}).note || '空结果') + '）');
                        } else if ((d.error || '').indexOf('没有进行中的录音') >= 0) {
                            // 后端无录音（如识别完成后又点了一次）——状态已
                            // 对齐，轻提示不吓人
                            showToast('（当前没有录音了，再点麦克风开始）');
                        } else {
                            showToast('❌ ' + (d.error || '识别失败'));
                        }
                    })
                    .catch(() => showToast('❌ 识别请求失败'))
                    .finally(function () { busy = false; });
            }
        });
    })();

    // ==================== resize 视觉遮罩（白屏终极方案 B，2026-10-25） ====================
    // 窗口尺寸突变（拖拽放大/最大化）时 WebView2 GPU 重排的百毫秒级白屏/
    // 撕裂，用"视觉欺骗"遮住：resize 瞬间给 body 挂 .resizing（全屏主题灰
    // 遮罩+transition none 立即生效），150ms 防抖后移除——肉眼看到的是
    // 平滑的灰-内容过渡而非闪白。与方案 A（WS_EX_COMPOSITED 原生双缓冲）
    // 正交叠加双保险。
    (function initResizeMask() {
        let timer = null;
        window.addEventListener('resize', function () {
            document.body.classList.add('resizing');
            if (timer) clearTimeout(timer);
            timer = setTimeout(function () {
                document.body.classList.remove('resizing');
            }, 150);
        }, { passive: true });
    })();

    // ==================== UI 事件总线（#348 三期推模式） ====================
    // 页面级 EventSource 长连接（/api/events）——后台任务（插件转写等）
    // 完成时收到 video_note_done 事件，渲染为新 AI 气泡（带思考折叠+正常
    // 渲染管线）。与请求级 SSE 正交；断线自动重连（EventSource 原生）；
    // 事件丢失兜底=「查转写状态」（既有，保留）。
    (function initUiEvents() {
        if (typeof EventSource === "undefined") return;   // 老引擎降级（status 兜底）
        const es = new EventSource('/api/events');
        es.addEventListener('video_note_done', function (ev) {
            try {
                const d = JSON.parse(ev.data);
                if (d.reply) {
                    const history = document.getElementById('chat-history');
                    if (!history) return;
                    appendBotMessage(d.reply, '📺 视频转写', d.title || '');
                    history.scrollTop = history.scrollHeight;
                }
            } catch (e) {
                console.error('UI 事件渲染失败', e);   // 单事件失败不拆连接
            }
        });
        // 📊 总线进度推送：更新当前 ack 气泡内部的进度小字（不飘不插独立 div）
        es.addEventListener('bus_progress', function (ev) {
            try {
                const d = JSON.parse(ev.data);
                if (!d.text) return;
                const history = document.getElementById('chat-history');
                if (!history) return;
                // 找最后一个 bot 气泡内的进度行（有则更新/无则追加在 badge 下方）
                const bubbles = history.querySelectorAll('.message.bot-message');
                const last = bubbles[bubbles.length - 1];
                if (!last) return;
                let pl = last.querySelector('.bus-progress-line');
                if (!pl) {
                    pl = document.createElement('div');
                    pl.className = 'bus-progress-line';
                    pl.style.cssText = 'font-size:11px;color:#9ca3af;margin-top:2px;';
                    const inner = last.querySelector('.bubble-content');
                    if (inner) inner.appendChild(pl);
                }
                pl.textContent = '⏳ ' + d.text;
                history.scrollTop = history.scrollHeight;
            } catch (e) { /* 进度渲染失败不致命 */ }
        });
        // 🚌 总线异步推送（切片 a：选股等强拦截任务的结果气泡，控制台侧）
        es.addEventListener('bus_reply', function (ev) {
            try {
                const d = JSON.parse(ev.data);
                if (d.reply) {
                    const history = document.getElementById('chat-history');
                    if (!history) return;
                    // 清掉之前可能残留的进度行
                    history.querySelectorAll('.bus-progress-line').forEach(
                        function (el) { el.remove(); });
                    appendBotMessage(d.reply, d.source || '📣 总线', '');
                    history.scrollTop = history.scrollHeight;
                }
            } catch (e) {
                console.error('总线事件渲染失败', e);   // 单事件失败不拆连接
            }
        });
        es.onerror = function () { /* EventSource 原生自动重连，无需处理 */ };
        // 思考一行折叠（2026-10-28）：点击消息内思考行展开/收起全文
        document.addEventListener('click', function (ev) {
            const tl = ev.target.closest('.message.bot-message .think-live');
            if (tl) tl.classList.toggle('open');
        });
    })();

    // ==================== 天气卡真实化（#351 聚合面板一期） ====================
    // GET /api/weather（后端 15 分钟缓存）+ 前端 20 分钟轮询+载入即拉；
    // 异常/超时一律降级为"暂无数据"——绝不因网络卡顿崩面板（纪律红线）。
    // 图标后端已映射（weather_icon），前端只渲染。
    (function initWeatherCard() {
        const elTemp = document.getElementById('weather-temp');
        if (!elTemp) return;   // 节点缺失静默退出（面板降级不报错）
        const elCity = document.getElementById('weather-city');
        const elDesc = document.getElementById('weather-desc');
        const WEATHER_POLL_MS = 20 * 60 * 1000;   // 20 分钟（后端缓存 15 分钟，前端略长）
        const elMeta = document.getElementById('weather-meta');
        const elFc = document.getElementById('weather-forecast');
        function renderWeather(d) {
            if (elCity) elCity.textContent = (d.city || '天气') + ' · 今日';
            // emoji 退役（UI 三期 v0 单色 SVG 图标位）：温度只出纯数字
            if (elTemp) elTemp.textContent = Math.round(d.temp) + '°C';
            if (elDesc) elDesc.textContent = (d.desc || '') +
                (d.stale ? '（缓存·稍后自动刷新）' : '');
            // 湿度/风力胶囊（open-meteo current 真数据；缺字段整行隐藏）
            if (elMeta) {
                if (d.humidity != null || d.wind != null) {
                    elMeta.hidden = false;
                    elMeta.innerHTML =
                        '<span>💧 ' + (d.humidity != null
                            ? Math.round(d.humidity) + '%' : '--') + '</span>'
                        + '<span>🌬 ' + (d.wind != null
                            ? Math.round(d.wind) + ' km/h' : '--') + '</span>';
                } else {
                    elMeta.hidden = true;
                }
            }
            // 四天预报（今天+未来四天，open-meteo daily 真数据）
            if (elFc) {
                var fc = d.forecast || [];
                if (fc.length) {
                    elFc.hidden = false;
                    elFc.innerHTML = fc.map(function (x) {
                        return '<li><span class="v0-fc-day">' + x.day + '</span>'
                            + '<span class="v0-fc-icon">' + (x.icon || '') + '</span>'
                            + '<span class="v0-fc-temp">' + x.high + '°'
                            + '<i>/' + x.low + '°</i></span></li>';
                    }).join('');
                } else {
                    elFc.hidden = true;
                }
            }
        }
        function showUnavailable() {
            if (elTemp) elTemp.textContent = '--';
            if (elDesc) elDesc.textContent = '暂无数据（服务暂不可用）';
            if (elMeta) elMeta.hidden = true;
            if (elFc) elFc.hidden = true;
        }
        function loadWeather() {
            fetch('/api/weather')
                .then(res => res.json().then(body => ({ ok: res.ok, body: body })))
                .then(({ ok, body }) => {
                    if (ok && body.code === 200 && body.data) renderWeather(body.data);
                    else showUnavailable();
                })
                .catch(() => showUnavailable());   // 网络卡顿/断连：降级不崩
        }
        loadWeather();
        setInterval(loadWeather, WEATHER_POLL_MS);
    })();

    // 大脑来源徽标（§4.3：消费 /api/chat 返回的 source 字段）
    // dataset.prompt 记录触发本回复的原消息，供"刷新"按钮重新生成
    // 历史回放经同一入口：直出思维流块静态展示（无动画无折叠）
    function appendBotMessage(rawReply, source, prompt, opts) {
        const options = opts || {};
        const history = document.getElementById('chat-history');
        maybeTimeSeparator(options.ts || new Date().toISOString());
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
            <div style="display:flex; flex-direction:column; gap:3px;">
                <div class="bubble-content">${renderRichTables(reply)}</div>
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
            // 而 F12 Elements 里无 .think-live，即"执行了但插入/显示被静默
            // 吞掉"，配合下方实测校验定位
            console.log("RENDERING_THINK_LIVE...");
            // F4 加固：手工插入（不依赖 before()/prepend() 系快捷方法）——
            // 显式父引用 + insertBefore，思维流块位于气泡正文上方；插入环节
            // 任何异常都不吞掉整条回复——块插不上时再降级为深色纯文本块，
            // 思考过程必可见
            try {
                // 直出思维流收养（2026-10-22 二轮拍板）：thinkLiveEl 在位=流
                // 式块原地移动进本消息（done 已按净化全文定稿，不重建）；
                // 否则按最终口径构建静态思维流块
                const thinkLive = (options.thinkLiveEl && options.thinkLiveEl.classList &&
                                   options.thinkLiveEl.classList.contains('think-live'))
                    ? options.thinkLiveEl : buildThinkLiveBlock(thinkParts.think);
                const bubbleEl = botMsg.querySelector('.bubble-content');
                const parentEl = bubbleEl ? bubbleEl.parentNode : botMsg;
                parentEl.insertBefore(thinkLive, bubbleEl);
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
            // T4a 强制渲染兜底随折叠卡退役（直出块构建极简、无骨架依赖）：
            // 块插不上时上方 catch 已落深色纯文本块，思考过程必可见
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
                let idx = 0;
                res.data.messages.forEach(m => {
                    if (!m || typeof m.content !== 'string') return;
                    // 内容错开淡入（UI 微操 2026-10-22）：仅历史回放批渲染，
                    // 流式输出的思维链/正文绝不错开（流式路径零此类）
                    let el = null;
                    if (m.role === 'user') {
                        lastUser = m.content;
                        el = appendUserMessage(m.content, m.ts);
                    } else if (m.role === 'assistant') {
                        // 历史回放共用入口：直出思维流块静态展示（无动画）
                        el = appendBotMessage(m.content, m.source || '', lastUser,
                                              { ts: m.ts });
                    }
                    if (el) {
                        el.classList.add('msg-enter');
                        el.style.animationDelay = Math.min(idx * 45, 400) + 'ms';
                    }
                    idx += 1;
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

    // 💬 排队条（2026-10-28 对齐 ZCode）：生成中再发消息 → 缩成输入框上方
    // 一行排队条（💬 排队中：… + [立即执行][删除]）；立即执行=中断当前流式
    // （AbortController）转发排队消息；任务自然结束=自动补发排队消息。
    let __xj3Generating = false;
    let __xj3BusAbort = null;     // 总线任务无法 abort（后端线程）——立即执行
    let __xj3Queued = null;       // =并发二次请求（后端自排队，前端只补气泡）
    let __xj3AbortSkip = false;   // 主动中断时禁走 legacy 回退

    function ensureQueueBar() {
        let bar = document.getElementById('queue-bar');
        if (bar) return bar;
        bar = document.createElement('div');
        bar.id = 'queue-bar';
        bar.style.cssText = 'display:none;align-items:center;gap:8px;'
            + 'margin:0 12px 6px;padding:6px 12px;font-size:12px;'
            + 'background:rgba(240,243,249,0.92);border:1px solid '
            + 'var(--color-border,#e0e4ec);border-radius:8px;'
            + 'backdrop-filter:blur(4px);';
        const chatHistory = document.getElementById('chat-history');
        const inputArea = document.querySelector('.chat-input-area');
        (inputArea || chatHistory || document.body).parentNode.insertBefore(
            bar, inputArea || chatHistory);
        return bar;
    }

    function showQueueBar(text) {
        const bar = ensureQueueBar();
        bar.innerHTML = '';
        const label = document.createElement('span');
        label.textContent = '💬 排队中：' + text;
        label.style.cssText = 'flex:1;min-width:0;overflow:hidden;'
            + 'text-overflow:ellipsis;white-space:nowrap;color:#536ba9;';
        const runBtn = document.createElement('button');
        runBtn.textContent = '立即执行';
        runBtn.style.cssText = 'font-size:11px;padding:2px 10px;border-radius:6px;'
            + 'border:1px solid var(--color-border,#e0e4ec);background:#fff;'
            + 'cursor:pointer;';
        runBtn.addEventListener('click', function () {
            const q = __xj3Queued;
            __xj3Queued = null;
            hideQueueBar();
            if (__xj3BusAbort) {   // 总线任务不可中断：并发二次请求（后端自排队）
                __xj3Generating = false;
                window.sendMessage.__force = true;
            }
            if (__xj3Abort) {      // 流式任务：中断当前再发
                __xj3AbortSkip = true;
                try { __xj3Abort.abort(); } catch (e) {}
            }
            __xj3Generating = false;
            window.sendMessage.__force = true;
            window.sendMessage();
        });
        const delBtn = document.createElement('button');
        delBtn.textContent = '删除';
        delBtn.style.cssText = 'font-size:11px;padding:2px 10px;border-radius:6px;'
            + 'border:1px solid var(--color-border,#e0e4ec);background:#fff;'
            + 'cursor:pointer;';
        delBtn.addEventListener('click', function () {
            __xj3Queued = null;
            hideQueueBar();
        });
        bar.appendChild(label);
        bar.appendChild(runBtn);
        bar.appendChild(delBtn);
        bar.style.display = 'flex';
    }

    function hideQueueBar() {
        const bar = document.getElementById('queue-bar');
        if (bar) bar.style.display = 'none';
    }

    window.__xj3GenFinish = function () {
        __xj3Generating = false;
        if (__xj3Queued) {
            const q = __xj3Queued;
            __xj3Queued = null;
            hideQueueBar();
            window.sendMessage.__force = true;
            window.sendMessage();
            void q;
        }
    };

    window.sendMessage = function() {
        const input = document.getElementById('chat-input');
        if (!input) return;

        const text = input.value.trim();
        if (!text) return;

        // 💬 排队条：生成中再发 → 缩一行排队（不直发后端）
        if (__xj3Generating && !window.sendMessage.__force) {
            __xj3Queued = text;
            showQueueBar(text);
            input.value = '';
            window.__xj3SyncSendBtn && window.__xj3SyncSendBtn();
            return;
        }
        window.sendMessage.__force = false;

        appendUserMessage(text);
        input.value = '';
        if (window.__xj3SyncSendBtn) window.__xj3SyncSendBtn();   // 清空后同步回灰（Bug①）

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
        __xj3Generating = true;
        __xj3AbortSkip = false;
        window.sendMessage.__force = false;

        // 🌊 思维链真流式（2026-10-05 C2，#244）：优先走 SSE 流式端点，
        // 失败/异常回退旧 /api/chat（口径零回退）。历史回放/刷新重试仍走
        // appendBotMessage 旧管线（本次只改发送链）。主动中断（排队条
        // "立即执行"）不走 legacy 回退——用户要的是插队不是重发。
        sendMessageStream(text, loadingMsg, rotateTimer)
            .catch(() => {
                if (__xj3AbortSkip) {
                    try { loadingMsg.remove(); } catch (e) {}
                    window.__xj3GenFinish && window.__xj3GenFinish();
                    return;
                }
                sendMessageLegacy(text, loadingMsg, rotateTimer);
                window.__xj3GenFinish && window.__xj3GenFinish();
            })
            .finally(() => window.__xj3GenFinish && window.__xj3GenFinish());
    };

    // 流式分支：fetch POST + getReader 手解 SSE（EventSource 不支持 POST）。
    // 2026-10-22 二轮重构：全部辅助函数提升到本函数顶层作用域——757f321 曾
    // 把 ensureThinkCard() 调用提到 fetch 前而函数本体仍声明在 .then 回调内
    // 层作用域 → 运行时 ReferenceError 同步炸掉发送链（loadingMsg 轮换孤儿
    // =界面假死；node --check 与静态锚均查不出作用域错）。本轮结构根修：
    // 调用点与声明点同层，此类雷从结构上不可能再犯。
    function sendMessageStream(text, loadingMsg, rotateTimer) {
        if (window.__xj3HideAttach) window.__xj3HideAttach();   // 附件随本次消息消费（2026-10-26）
        // C3b 修复：自取元素与作用域解耦（裸 history 解析到 window.history）
        const history = document.getElementById('chat-history');
        // ⏱️ 总闸 190s AbortController（比后端 180s 硬超时略长的最终防线）
        const ac = new AbortController();
        __xj3Abort = ac;
        const streamGuard = setTimeout(() => ac.abort(), 190000);
        // ⏱️ 看门狗（2026-10-22 救火拍板）：首帧前 30s / 帧间 90s 无任何帧
        // → 中断并就地报错（不转 legacy——同源后端会同样卡死）。任何底层
        // 卡死（工具挂死/模型无响应/流中断）UI 都不死锁，可继续发下一条。
        let watchdogFired = false;
        let watchdog = setTimeout(fireWatchdog, 30000);
        function fireWatchdog() {
            watchdogFired = true;
            try { ac.abort(); } catch (e) { /* 已中断 */ }
        }
        function patWatchdog() {   // 每帧喂狗（首帧后转为 90s 帧间口径）
            clearTimeout(watchdog);
            watchdog = setTimeout(fireWatchdog, 90000);
        }
        // ⚡ 首字零等待（2026-10-22 队长拍板）：流式状态变量提升到 fetch 之前
        // ——直出思维流骨架在点击发送的同一 tick 同步挂载，把后端 TTFT
        //（实测闲聊首帧 1.37s≈全部为模型首字延迟；指令链无模型仅 21ms）
        // 整个遮进呼吸态
        let thinkCard = null;     // 直出思维流块（发送瞬间骨架挂载，首 think 增量接管）
        let thinkBodyEl = null;   // 思考行容器
        let thinkAcc = '';        // 累计思考原文（分段剥前缀用）
        let thinkStartTs = null;  // A1（#326 前置侦察）：首个 think 增量到达时刻→耗时显示
        let answerEl = null;      // 正文气泡（首个 answer 块建）
        let answerAcc = '';
        let toolEl = null;
        let segRows = [];         // 思考行元素（按序号复用，文本变化才重写）
        let reader = null;        // SSE reader/decoder/缓冲（pump 用，then 内赋值）
        let decoder = null;
        let buf = '';
        ensureThinkCard();   // ⚡ 乐观挂载骨架（点击发送同一 tick，零等待）

        function ensureThinkCard() {
            if (thinkCard) return;
            clearInterval(rotateTimer);
            if (loadingMsg.parentNode) loadingMsg.parentNode.removeChild(loadingMsg);
            // 直出思维流（2026-10-22 二轮拍板：废弃折叠卡，对标 DeepSeek）：
            // 🧠 标签行 + 灰色小号思考行直接外冒，无箭头无折叠无二次点击
            thinkCard = document.createElement('div');
            thinkCard.className = 'think-live';
            const labelEl = document.createElement('div');
            labelEl.className = 'think-live-label';
            labelEl.textContent = '🧠 小橘正在思考…';
            thinkBodyEl = document.createElement('div');
            labelEl.addEventListener('click', function () {
                // DOM 自锚定（closest）——闭包 thinkCard 在 done 收尾被置 null，
                // 收起 1.5s 后点击读到 null 曾致 toggle 静默炸（真机无响应实锤）
                const card = labelEl.closest('.think-live');
                if (card) card.classList.toggle('think-live-collapsed');
            });
            thinkCard.appendChild(labelEl);
            thinkCard.appendChild(thinkBodyEl);
            // 骨架屏：标签呼吸 + 两根占位线，首段真文本接管时摘除
            thinkCard.classList.add('think-live-waiting');
            for (let sk = 0; sk < 2; sk++) {
                const line = document.createElement('div');
                line.className = 'think-skeleton-line' + (sk ? ' think-skeleton-short' : '');
                thinkBodyEl.appendChild(line);
            }
            history.appendChild(thinkCard);
        }

        function renderThinkProgressive() {
            ensureThinkCard();
            // 无缝接管（首字零等待配套）：首段真文本到达——摘呼吸态+清骨架线
            if (thinkCard.classList.contains('think-live-waiting')) {
                thinkCard.classList.remove('think-live-waiting');
                thinkBodyEl.querySelectorAll('.think-skeleton-line').forEach(function (el) {
                    el.remove();
                });
            }
            // 严格区分：本函数只吃 event: think（answer 走 ensureAnswerEl 通
            // 道，二者 DOM 互不沾——绝不把正文当思考，也绝不把思考当正文）
            const segs = splitThinkStageLines(thinkAcc);
            while (segRows.length < segs.length) {
                const row = document.createElement('div');
                row.className = 'think-live-line';
                thinkBodyEl.appendChild(row);
                segRows.push(row);
            }
            segs.forEach(function (seg, i) {
                if (segRows[i].textContent !== seg.text) segRows[i].textContent = seg.text;
            });
            history.scrollTop = history.scrollHeight;
        }

        // done 收口：标签换耗时（A1 口径），内容已直出、无任何折叠动画
        function finalizeThinkCard(finalThink, label) {
            thinkAcc = finalThink;
            renderThinkProgressive();
            const st = thinkCard && thinkCard.querySelector('.think-live-label');
            if (st && label) st.textContent = label;
        }

        function ensureAnswerEl() {
            if (answerEl) return;
            clearInterval(rotateTimer);
            if (loadingMsg.parentNode) loadingMsg.parentNode.removeChild(loadingMsg);
            answerEl = document.createElement('div');
            answerEl.className = 'message bot-message';
            const bubble = document.createElement('div');
            bubble.className = 'bubble-content';
            answerEl.appendChild(bubble);
            history.appendChild(answerEl);
            history.scrollTop = history.scrollHeight;
        }

        function handleEvent(etype, data) {
            patWatchdog();   // 每帧喂狗（首帧后转为 90s 帧间口径）
            if (etype === 'think') {
                if (thinkStartTs === null) {
                    thinkStartTs = Date.now();   // A1：耗时计时起点
                    const st = thinkCard && thinkCard.querySelector('.think-live-label');
                    if (st) st.textContent = '🧠 思考中…';
                }
                thinkAcc += (data.delta || '');
                renderThinkProgressive();
            } else if (etype === 'tool') {
                ensureThinkCard();   // C3b：无卡也建（工具事件不再静默丢）
                if (!toolEl) {
                    toolEl = document.createElement('div');
                    toolEl.className = 'think-live-line';
                    thinkBodyEl.appendChild(toolEl);
                }
                toolEl.textContent = '🔧 正在执行工具：' + (data.name || '');
            } else if (etype === 'answer') {
                ensureAnswerEl();
                answerAcc += (data.delta || '');
                answerEl.querySelector('.bubble-content').textContent = answerAcc;
                history.scrollTop = history.scrollHeight;
            } else if (etype === 'done') {
                // 收尾（二轮拍板直出版）：思维流块不再移除——按 done 净化全文
                // 定稿后原地移动进最终消息（正文/工具栏/落盘口径零分叉）；
                // 无流式块（指令单帧 done）走原重建路径零变化。
                // 顺序：先挂最终气泡再撤 answerEl（换屏零空白）。
                clearTimeout(streamGuard);
                clearTimeout(watchdog);
                maybeTimeSeparator(new Date().toISOString());
                let adopted = null;
                if (thinkCard) {
                    const parts = splitThinkBlock(String(data.reply == null ? '' : data.reply));
                    if (parts.think !== null && parts.think !== '') {
                        if (toolEl && toolEl.parentNode) toolEl.parentNode.removeChild(toolEl);
                        let secs = null;
                        if (thinkStartTs !== null) {
                            secs = ((Date.now() - thinkStartTs) / 1000).toFixed(1);
                        }
                        finalizeThinkCard(parts.think,
                            secs === null ? '🧠 思考过程' : '🧠 已思考（用时 ' + secs + ' 秒）');
                        adopted = thinkCard;
                        // 完成后自动收起（2026-10-25 队长验收拍板）：直出流式全程
                        // 可见，done 定稿后 1.5s 收起为折叠行（标签保留+点击可展开），
                        // 长思考不再霸屏
                        setTimeout(function () {
                            if (adopted && adopted.isConnected) {
                                adopted.classList.add('think-live-collapsed');
                            }
                        }, 1500);
                    } else {
                        // 旧口径：最终回复无 <think>（理论边角）不保留过程块
                        if (thinkCard && thinkCard.parentNode) thinkCard.parentNode.removeChild(thinkCard);
                    }
                }
                if (!adopted && toolEl && toolEl.parentNode) toolEl.parentNode.removeChild(toolEl);
                const botMsg = appendBotMessage(data.reply, data.source, text,
                    adopted ? { thinkLiveEl: adopted } : null);
                if (answerEl && answerEl.parentNode) answerEl.parentNode.removeChild(answerEl);
                thinkCard = null;
                thinkBodyEl = null;
                toolEl = null;
                answerEl = null;
                segRows = [];
                if (window.xiaoju3Sound) window.xiaoju3Sound.ding();
                if (autoTTSEnabled()) speakMessageEl(botMsg);
            } else if (etype === 'error') {
                throw new Error(data.error || 'stream error');
            }
        }

        function pump() {
            return reader.read().then(({ done, value }) => {
                if (done) return;
                buf += decoder.decode(value, { stream: true });
                let idx;
                while ((idx = buf.indexOf('\n\n')) !== -1) {
                    const frame = buf.slice(0, idx);
                    buf = buf.slice(idx + 2);
                    let etype = 'message';
                    let payload = '';
                    frame.split('\n').forEach(l => {
                        if (l.startsWith('event:')) etype = l.slice(6).trim();
                        else if (l.startsWith('data:')) payload += l.slice(5).trim();
                    });
                    if (!payload) continue;
                    handleEvent(etype, JSON.parse(payload));
                }
                return pump();
            });
        }

        return fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text }),
            signal: ac.signal
        }).then(res => {
            if (!res.ok || !res.body) throw new Error('stream unavailable');
            reader = res.body.getReader();
            decoder = new TextDecoder();
            return pump();
        }).catch(function (err) {
            clearTimeout(streamGuard);
            clearTimeout(watchdog);
            // C3b：半途断流——闭包内清理过程件再处置（外层 catch 才转 legacy
            // 重答；宽 DOM 查询会误删历史消息，必须用闭包引用）
            if (thinkCard && thinkCard.parentNode) thinkCard.parentNode.removeChild(thinkCard);
            if (toolEl && toolEl.parentNode) toolEl.parentNode.removeChild(toolEl);
            if (answerEl && answerEl.parentNode) answerEl.parentNode.removeChild(answerEl);
            if (watchdogFired) {
                // 看门狗中断：就地报错收尾，不转 legacy（同源后端会同样卡死）
                const errMsg = document.createElement('div');
                errMsg.className = 'message bot-message';
                errMsg.style.color = '#e0433f';
                errMsg.textContent = '（⏱️ 长时间无响应已自动中断——模型可能卡住，请直接重试）';
                mountSystemToolbar(errMsg);
                history.appendChild(errMsg);
                history.scrollTop = history.scrollHeight;
                return;
            }
            throw err;
        });
    }
    // 旧路分支（回退用；原实现原样保留）
    function sendMessageLegacy(text, loadingMsg, rotateTimer) {
        if (window.__xj3HideAttach) window.__xj3HideAttach();   // 附件随本次消息消费（2026-10-26）
        // C3b 修复：同 sendMessageStream——自取 history，裸名解析到
        // window.history 使 .then/.catch 全链 DOM 操作炸、回复不渲染
        const history = document.getElementById('chat-history');
        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        })
        .then(res => res.json())
        .then(res => {
            clearInterval(rotateTimer);   // 收到回复：停止轮换并替换为正常气泡
            if (history.contains(loadingMsg)) history.removeChild(loadingMsg);   // C3b：流式回退时 loadingMsg 可能已被过程卡消费
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
            showConfirm('清空聊天记录', '确定清空聊天记录吗？此操作不可恢复。', function () {
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
            }, { confirmText: '清空' });
        });
    }

    // ==================== 7. 移动端监控抽屉开关（界面文档 §7） ====================
    const sidebar = document.querySelector('.sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    if (sidebar && sidebarToggle) {
        sidebarToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
    }

    // ==================== 7.2 侧栏拖拽调宽（2026-10-27） ====================
    // 把手 #sidebar-resizer（index.html flex 兄弟节点，负外边距净零位移）：
    // 指针捕获拖拽实时改 .sidebar 宽（rAF 节流不掉帧），松手持久化——桌面
    // 形态 js_api set_layout_pref 存 ui_pref.json（跨启动唯一真源，
    // localStorage 关窗即焚铁律），浏览器形态降级 localStorage。恢复以
    // ui_pref.json 为真源（api 异步就绪轮询 3s 上限，未就绪=浏览器形态
    // 静默走 localStorage）。双击复位；≤768px 抽屉态清内联宽（宽度交还
    // CSS min(80vw,300px)）；窗口缩放时已拖宽度夹紧进当前窗口。
    (function initSidebarResize() {
        const sb = document.querySelector('.sidebar');
        const handle = document.getElementById('sidebar-resizer');
        // matchMedia 缺席=非浏览器 JS 环境（node 运行时烟雾桩等），静默不启用
        if (!sb || !handle || typeof window.matchMedia !== 'function') return;
        const LS_KEY = 'xiaoju3_sidebar_width';
        const MIN_W = 300;                       // 下限同 .sidebar min-width:300px
        const mqMobile = window.matchMedia('(max-width: 768px)');
        let dragging = false, startX = 0, startW = 0, rafId = 0, pendingW = 0;

        function maxW() { return Math.max(MIN_W + 60, Math.round(window.innerWidth * 0.55)); }
        function clamp(w) { return Math.max(MIN_W, Math.min(maxW(), Math.round(w))); }
        function applyWidth(w) {
            sb.style.width = w + 'px';
            sb.style.minWidth = w + 'px';        // 压过 CSS min-width，下限由 clamp 保证
        }
        function clearWidth() {
            sb.style.removeProperty('width');
            sb.style.removeProperty('min-width');
        }
        function savedWidth() {
            let n = NaN;
            try { n = parseInt(localStorage.getItem(LS_KEY), 10); } catch (e) { /* 隐私模式 */ }
            return (n >= MIN_W && n <= 2000) ? n : 0;
        }
        function persist(w) {
            try { localStorage.setItem(LS_KEY, String(w)); } catch (e) { /* 同上 */ }
            const api = window.pywebview && window.pywebview.api;
            if (api && typeof api.set_layout_pref === 'function') {
                api.set_layout_pref(w).catch(function () {});
            }
        }
        function syncViewport() {
            if (mqMobile.matches) { clearWidth(); return; }
            const m = /^(\d+)px$/.exec(sb.style.width || '');
            if (m) applyWidth(clamp(parseInt(m[1], 10)));
        }

        handle.addEventListener('pointerdown', function (e) {
            if (mqMobile.matches || e.button !== 0) return;
            dragging = true;
            startX = e.clientX;
            startW = sb.getBoundingClientRect().width;
            handle.classList.add('dragging');
            document.body.style.cursor = 'col-resize';       // 拖出把手光标不闪断
            document.body.style.userSelect = 'none';         // 防拖拽选中文本
            try { handle.setPointerCapture(e.pointerId); } catch (err) { /* 旧内核无捕获 */ }
            e.preventDefault();
        });
        handle.addEventListener('pointermove', function (e) {
            if (!dragging) return;
            pendingW = clamp(startW + (e.clientX - startX));
            if (!rafId) {
                rafId = requestAnimationFrame(function () {
                    rafId = 0;
                    if (dragging) applyWidth(pendingW);
                });
            }
        });
        function endDrag() {
            if (!dragging) return;
            dragging = false;
            handle.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            const w = clamp(sb.getBoundingClientRect().width);
            applyWidth(w);
            persist(w);
        }
        handle.addEventListener('pointerup', endDrag);
        handle.addEventListener('pointercancel', endDrag);
        handle.addEventListener('dblclick', function () {
            clearWidth();
            try { localStorage.removeItem(LS_KEY); } catch (e) { /* 同上 */ }
            const api = window.pywebview && window.pywebview.api;
            if (api && typeof api.set_layout_pref === 'function') {
                api.set_layout_pref(0).catch(function () {});   // 0=后端解释为删键复位
            }
        });
        if (mqMobile.addEventListener) mqMobile.addEventListener('change', syncViewport);
        else mqMobile.addListener(syncViewport);
        window.addEventListener('resize', function () { if (!dragging) syncViewport(); });

        restoreAndWatch();
        function restoreAndWatch() {
            const w = savedWidth();
            if (w && !mqMobile.matches) applyWidth(clamp(w));
            let tries = 0;
            const t = setInterval(function () {
                const api = window.pywebview && window.pywebview.api;
                if (api && typeof api.get_layout_pref === 'function') {
                    clearInterval(t);
                    api.get_layout_pref().then(function (r) {
                        const v = r && parseInt(r.sidebar_width, 10);
                        if (v >= MIN_W && !mqMobile.matches) applyWidth(clamp(v));
                    }).catch(function () {});
                } else if (++tries > 20) {
                    clearInterval(t);                // 浏览器形态：api 永不来，静默
                }
            }, 150);
        }
    })();

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
    // #264 B2d③ B 方案：tab 栏不再有「设置」按钮——入口=右上角⚙️齿轮/
    // 桌宠菜单「设置」，返回=设置页顶部「← 返回」（注册表 settings 条目
    // btn 恒 null，空值安全）
    const terminalPaneEl = document.getElementById('terminal-pane');
    const settingsPaneEl = document.getElementById('settings-pane');   // #264 B2a 设置页
    const settingsListEl = document.getElementById('settings-list');   // #264 B2a
    const keysEntryBtn = document.getElementById('keys-entry');        // #264 B2b 密钥管理（LV3+，探针定显隐）
    const keysPaneEl = document.getElementById('keys-pane');           // #264 B2b
    const keysListEl = document.getElementById('keys-list');           // #264 B2b
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
        bubble.innerHTML = renderRichTables(parts.body);
        inner.appendChild(bubble);
        botEl.appendChild(inner);
        if (parts.think !== null) {
            // 直出思维流块（静态不打字不动画；文本 textContent 注入免 XSS）
            botEl.insertBefore(buildThinkLiveBlock(parts.think), inner);   // 块在气泡上方（与聊天视图同构）
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

    // 标签切换（#264 B2a 重构为注册表）：新增 tab 只加 CHAT_TABS 条目，
    // 不再膨胀 if/else——pane 显隐/输入框/清空按钮/进入退出副作用全部由
    // 条目声明（B2b 密钥页、B2c 开发者暗开关直接续条目）。既有行为逐条
    // 保留：终端切入拉最新+15s 轮询、切走即停；输入框与清空按钮仅对话窗口。
    const CHAT_TABS = {
        console: {
            btn: function () { return null; },   // #UI修复：tab 栏退役，按钮已删（空值安全同 settings 条目）
            show: function () { return [chatHistoryPaneEl]; },
            // 2026-10-29 穿透修复：hide 必须收全四个视图——旧清单漏
            // keysPaneEl，密钥页点「← 返回」后 keys 面板留在聊天下方穿模
            //（队长截图实锤；terminal.hide 同漏同修）
            hide: function () { return [terminalPaneEl, settingsPaneEl, keysPaneEl]; },
            input: true,
            clearTitle: '清空聊天记录',
            enter: null,
            leave: null,
        },
        terminal: {
            btn: function () { return null; },   // #UI修复：tab 栏退役，按钮已删
            show: function () { return [terminalPaneEl]; },
            hide: function () { return [chatHistoryPaneEl, settingsPaneEl, keysPaneEl]; },   // 2026-10-29 穿透修复：补 keysPaneEl（同 console 条目）
            input: false,
            clearTitle: '',
            enter: function () {
                loadTerminalHistory();   // 每次切入拉最新
                if (!terminalRefreshTimer) {
                    terminalRefreshTimer = setInterval(loadTerminalHistory, TERMINAL_REFRESH_MS);
                }
            },
            leave: function () {
                if (terminalRefreshTimer) {
                    clearInterval(terminalRefreshTimer);   // 切走即停，不留后台轮询
                    terminalRefreshTimer = null;
                }
            },
        },
        settings: {
            btn: function () { return null; },   // #264 B2d③：tab 栏无设置按钮（B 方案），空值安全
            show: function () { return [settingsPaneEl]; },
            hide: function () { return [chatHistoryPaneEl, terminalPaneEl, keysPaneEl]; },
            input: false,
            clearTitle: '',
            enter: function () {
                document.body.classList.add('xiaoju3-settings-open');   // 桌宠随设置族隐藏（批 4 收尾补丁）
                loadSettings();   // 链式调 loadPersonaCard（人格卡随设置拉取）
            },
            leave: function () {
                document.body.classList.remove('xiaoju3-settings-open');
            },
        },
        keys: {
            btn: function () { return keysEntryBtn; },   // #264 B2b：LV3+ 才显示（探针定显隐）
            show: function () { return [keysPaneEl]; },
            hide: function () { return [chatHistoryPaneEl, terminalPaneEl, settingsPaneEl]; },
            input: false,
            clearTitle: '',
            enter: function () {
                document.body.classList.add('xiaoju3-settings-open');   // 密钥页同族同藏
                loadKeys();   // 切入即拉掩码
            },
            leave: function () {
                document.body.classList.remove('xiaoju3-settings-open');
            },
        },
    };
    let activeChatTab = 'console';

    function switchChatTab(tab) {
        const def = CHAT_TABS[tab];
        if (!def) return;
        Object.keys(CHAT_TABS).forEach(function (name) {
            const d = CHAT_TABS[name];
            if (d.btn()) d.btn().classList.toggle('active', name === tab);
        });
        def.show().forEach(function (el) { if (el) el.hidden = false; });
        def.hide().forEach(function (el) { if (el) el.hidden = true; });
        if (chatInputAreaEl) chatInputAreaEl.hidden = !def.input;
        // #264 B2d③ 回归修复：输入框显隐改变桌宠下界基准（隐藏=窗口底/
        // 可见=输入框上沿），pane 切完立即按新基准重钳——设置/终端落过底
        // 的桌宠切回对话窗不再卡进输入框/发送按钮区
        if (window.__xiaoju3Pet && typeof window.__xiaoju3Pet.reclamp === 'function') {
            window.__xiaoju3Pet.reclamp();
        }
        const clearBtnEl = document.getElementById('clear-history');
        if (clearBtnEl) {
            clearBtnEl.disabled = !def.clearTitle;
            clearBtnEl.title = def.clearTitle || '该页无此操作';
        }
        if (activeChatTab !== tab) {
            const prev = CHAT_TABS[activeChatTab];
            if (prev && prev.leave) prev.leave();
            activeChatTab = tab;
        }
        if (def.enter) def.enter();
    }

    // #UI修复（2026-10-13）：顶部 tab 栏取消——终端/设置经 🧰 面板进入；
    // tabConsoleBtn/tabTerminalBtn 常量与绑定随之退役（settings 先例：
    // btn 恒 null 空值安全，此处直接删——不留引用已删 DOM 的死代码）
    // #264 B2d③ 回归修复：旧 tab-settings 按钮绑定块随 B 方案删除——
    // const 已移除但此块曾残留，对已删变量的事实引用在运行时抛
    // ReferenceError 打断 IIFE 求值，其后所有绑定（⚙️齿轮/桥/关于/返回）
    // 全部失效（node --check 抓不到：语法合法、运行时才炸）。设置入口现只
    // 经齿轮/桌宠菜单。
    const terminalRefreshBtn = document.getElementById('terminal-refresh');
    const terminalBackBtn = document.getElementById('terminal-back');
    if (terminalBackBtn) {
        terminalBackBtn.addEventListener('click', function () {
            switchChatTab('console');   // #UI修复：tab 取消后的终端页返回回路
        });
    }
    if (terminalRefreshBtn) {
        terminalRefreshBtn.addEventListener('click', loadTerminalHistory);
    }
    const settingsSaveBtn = document.getElementById('settings-save');
    if (settingsSaveBtn) settingsSaveBtn.addEventListener('click', saveSettings);
    const settingsRefreshBtn = document.getElementById('settings-refresh');
    if (settingsRefreshBtn) settingsRefreshBtn.addEventListener('click', loadSettings);
    // #264 B2d③ B 方案：设置页「← 返回」= 回对话窗口（tab 栏无设置按钮后的退出路径）
    const settingsBackBtn = document.getElementById('settings-back');
    if (settingsBackBtn) settingsBackBtn.addEventListener('click', function () { switchChatTab('console'); });
    // #264 B2b 密钥管理绑定：入口按钮（探针放行后才可见）+返回+刷新
    if (keysEntryBtn) {
        keysEntryBtn.addEventListener('click', function () { switchChatTab('keys'); });
    }
    const keysBackBtn = document.getElementById('keys-back');
    if (keysBackBtn) keysBackBtn.addEventListener('click', function () { switchChatTab('console'); });
    const keysRefreshBtn = document.getElementById('keys-refresh');
    if (keysRefreshBtn) keysRefreshBtn.addEventListener('click', loadKeys);
    probeKeysAccess();   // 页面加载即定 🔑 显隐（LV3+ 门）

    // ==================== 7.6 设置页（#264 B2a，B1 API 契约） ====================
    // 数据=GET /api/settings → {code,level,items:[{key,label,tier,type,value}]}：
    // 低档项后端已按 level 隐藏——前端只渲染返回 items，零键名硬编码；
    // 保存=POST {updates}（只提交改动项）；403 → toast 权限不足（含所需
    // 等级/TOTP 原因）；响应 applied=已写 .env 并补 os.environ（🟢 即改
    // 即生效），其余 written=需重启。类型渲染：str/int/bool/enum(:a,b,c)。
    let settingsFetchSeq = 0;
    let personaFetchSeq = 0;   // 人格卡独立竞态守卫（与 settings 互不挤兑）
    const SETTINGS_STATE = { level: null, original: {}, tiers: {} };
    const SETTINGS_TIER_LABELS = {
        daily: '常规设置',
        admin: '管理员开关',
        danger: '高危险（保存需 Lv.4+TOTP）',
    };

    function settingsChecked(value) {
        return String(value) === '1' || String(value) === 'true';
    }

    function appendSettingsTip(text) {
        const tip = document.createElement('div');
        tip.className = 'settings-empty';
        tip.textContent = text;
        settingsListEl.appendChild(tip);
    }

    function buildSettingsField(it) {
        SETTINGS_STATE.original[it.key] = it.value;
        SETTINGS_STATE.tiers[it.key] = it.tier || 'other';   // #264 B2c b：TOTP 分流需要
        const row = document.createElement('label');
        row.className = 'first-run-field settings-field';
        const cap = document.createElement('span');
        cap.textContent = (it.label || it.key) + '（' + it.key + '）';
        row.appendChild(cap);
        const type = String(it.type || '');
        let input;
        if (type === 'bool') {
            input = document.createElement('input');
            input.type = 'checkbox';
            input.checked = settingsChecked(it.value);
        } else if (type.indexOf('enum:') === 0) {
            input = document.createElement('select');
            const cur = String(it.value === null || it.value === undefined ? '' : it.value);
            const options = String(type.slice(5)).split(',').filter(function (o) { return o; });
            if (cur && options.indexOf(cur) === -1) options.push(cur);   // 表外现值原样保留，防保存误改
            options.forEach(function (opt) {
                const o = document.createElement('option');
                o.value = opt;
                o.textContent = opt;
                input.appendChild(o);
            });
            input.value = cur || (options[0] || '');
            if (!cur) SETTINGS_STATE.original[it.key] = input.value;   // 空现值记默认选中，防幻影 diff
        } else {
            input = document.createElement('input');
            input.type = (type === 'int') ? 'number' : 'text';
            input.value = it.value === null || it.value === undefined ? '' : String(it.value);
        }
        input.className = 'settings-input';
        input.id = 'settings-field-' + it.key;
        input.dataset.key = it.key;
        input.dataset.type = type || 'str';
        input.autocomplete = 'off';
        row.appendChild(input);
        return row;
    }

    // 界面偏好（#264 B2d④ 静态本地组）：与 API items 并列渲染，不走分档
    // 表——主题色=前端偏好（THEME_KEY），退出方式=js_api 读写 ui_pref.json。
    // 浏览器形态（无 pywebview）下退出方式禁用置灰。


    function appendUiPrefsSection() {
        if (!settingsListEl) return;
        const title = document.createElement('div');
        title.className = 'settings-group-title';
        title.textContent = '界面偏好（本机）';
        settingsListEl.appendChild(title);
        // 主题色
        const themeField = document.createElement('label');
        themeField.className = 'first-run-field settings-field';
        const themeCap = document.createElement('span');
        themeCap.textContent = '主题色';
        themeField.appendChild(themeCap);
        const themeSel = document.createElement('select');
        themeSel.className = 'settings-input';
        themeSel.id = 'ui-pref-theme';
        [['', '深蓝（默认）'], ['orange', '暖橘 🦊']].forEach(function (pair) {
            const o = document.createElement('option');
            o.value = pair[0];
            o.textContent = pair[1];
            themeSel.appendChild(o);
        });
        themeSel.value = getStoredTheme() || '';
        themeSel.addEventListener('change', function () {
            applyTheme(themeSel.value);   // 复用既有主题设施（data-theme 切换）
            try {
                if (themeSel.value) localStorage.setItem(THEME_KEY, themeSel.value);
                else localStorage.removeItem(THEME_KEY);
            } catch (e) { /* localStorage 不可用时仅本次会话生效 */ }
            showToast('主题已切换');
        });
        themeField.appendChild(themeSel);
        settingsListEl.appendChild(themeField);
        // 退出方式
        const exitField = document.createElement('label');
        exitField.className = 'first-run-field settings-field';
        const exitCap = document.createElement('span');
        exitCap.textContent = '退出方式（勾过「记住」后生效；改回「每次询问」恢复弹窗）';
        exitField.appendChild(exitCap);
        const exitSel = document.createElement('select');
        exitSel.className = 'settings-input';
        exitSel.id = 'ui-pref-exit';
        [['ask', '每次询问'], ['backend_only', '直接退窗口（后端与 NapCat 保留）'],
         ['full_exit', '直接完全退出（含 NapCat）']].forEach(function (pair) {
            const o = document.createElement('option');
            o.value = pair[0];
            o.textContent = pair[1];
            exitSel.appendChild(o);
        });
        exitField.appendChild(exitSel);
        settingsListEl.appendChild(exitField);
        const api = window.pywebview && window.pywebview.api;
        if (!api || typeof api.get_exit_pref !== 'function') {
            exitSel.disabled = true;
            exitSel.title = '浏览器形态不可用（桌面窗口内生效）';
            return;
        }
        api.get_exit_pref().then(function (pref) {
            exitSel.value = pref || 'ask';
        }).catch(function () { exitSel.disabled = true; });
        exitSel.addEventListener('change', function () {
            window.pywebview.api.set_exit_pref(exitSel.value).then(function (r) {
                showToast(r && r.ok ? '✅ 退出方式已保存' : '⚠️ 保存失败');
            }).catch(function (err) { showToast('保存失败: ' + err.message); });
        });
    }

    function renderSettingsItems(data) {
        if (!settingsListEl) return;
        SETTINGS_STATE.level = data && data.level;
        const items = (data && Array.isArray(data.items)) ? data.items : [];
        SETTINGS_STATE.original = {};
        // #264 B2c 修正：关于条目已移进滚动容器（settings-list 内部），
        // innerHTML 清空前先摘出来，重渲染后放回列表尾
        const aboutRow = document.getElementById('settings-about');
        if (aboutRow && aboutRow.parentElement === settingsListEl) {
            aboutRow.remove();
        }
        // 人格卡（批 4）同款保护：不清空即被抹，重渲染后放回（关于之前）
        const personaCard = document.getElementById('persona-card');
        if (personaCard && personaCard.parentElement === settingsListEl) {
            personaCard.remove();
        }
        settingsListEl.innerHTML = '';
        appendUiPrefsSection();   // #264 B2d④ 静态本地组（与 API 组并列，始终渲染）
        if (!items.length) {
            appendSettingsTip('暂无可见设置项（当前等级或分档表限制）');
            applyDevSwitchRow();   // 开关行恢复（空列表路径）
            if (personaCard) settingsListEl.appendChild(personaCard);
            if (aboutRow) settingsListEl.appendChild(aboutRow);
            return;
        }
        const groups = [];
        const byTier = {};
        items.forEach(function (it) {
            const tier = it.tier || 'other';
            if (!byTier[tier]) { byTier[tier] = []; groups.push(tier); }
            byTier[tier].push(it);
        });
        // #264 B2c 收尾（用户拍板）：admin 组藏进开发者模式——
        // dev_mode_on=false 时跳过渲染（藏/显是 UI 门；能不能改仍由后端
        // level 管=双门，此处只影响可见性）
        const devOn = DEV_STATE.mode_on === true;
        groups.forEach(function (tier) {
            if (tier === 'admin' && !devOn) return;   // 藏：拨开发者模式 ON 才出现
            const title = document.createElement('div');
            title.className = 'settings-group-title';
            title.textContent = SETTINGS_TIER_LABELS[tier] || tier;
            if (tier === 'danger') {
                title.style.color = 'var(--color-danger, #e0433f)';   // #264 B2c c：高危组红色标识
            }
            settingsListEl.appendChild(title);
            byTier[tier].forEach(function (it) {
                settingsListEl.appendChild(buildSettingsField(it));
            });
        });
        if (personaCard) settingsListEl.appendChild(personaCard);   // 人格卡放回（关于之前）
        if (aboutRow) settingsListEl.appendChild(aboutRow);   // 关于放回列表尾
        applyDevSwitchRow();   // #264 B2c：开关行按 ui_pref 恢复（渲染尾）（滚动内容一部分）
    }

    function loadSettings() {
        if (!settingsListEl) return;
        const seq = ++settingsFetchSeq;   // 竞态守卫（与终端页同口径）：慢响应丢弃
        fetch('/api/settings')
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (seq !== settingsFetchSeq) return;
                if (!body || body.code !== 200) {
                    const aboutRow = document.getElementById('settings-about');
                    if (aboutRow) aboutRow.remove();
                    settingsListEl.innerHTML = '';
                    appendUiPrefsSection();   // 静态组不依赖 API 成败
                    applyDevSwitchRow();   // 开关行恢复（失败路径）
                    if (aboutRow) settingsListEl.appendChild(aboutRow);
                    appendSettingsTip('设置读取失败' +
                        (body && body.error ? ('：' + body.error) : ''));
                    return;
                }
                renderSettingsItems(body);
            })
            .catch(function (err) {
                if (seq !== settingsFetchSeq) return;
                const aboutRow = document.getElementById('settings-about');
                if (aboutRow) aboutRow.remove();
                settingsListEl.innerHTML = '';
                appendUiPrefsSection();   // 静态组不依赖 API 成败
                applyDevSwitchRow();   // 开关行恢复（catch 路径）
                if (aboutRow) settingsListEl.appendChild(aboutRow);
                appendSettingsTip('设置读取失败: ' + err.message);
            });
        loadPersonaCard();   // 人格卡（#271 批 4）：独立容器，与 settings-list 成败互不牵连
    }

    // ==================== 人格卡（#271 批 4，2026-10-15） ====================
    // 纯状态展示批铁律：只展示+手动锁+开关，零触发层改动；文案=行为层
    // 描述（用户化翻译，禁止标签化/临床表述）；权限预检=state 自带 level，
    // 低于 3 → 置灰 + 提示，不渲染任何可点击 UI。
    const PERSONA_MODE_PHRASES = {
        banter: '爱跟你拌嘴，像老朋友损你',
        familiar: '自来熟，说话不绕弯',
        caring: '爱操心，嘘寒问暖',
        dependent: '爱粘着你，有事没事找你聊',
        polite: '客客气气，保持一点距离'
    };
    const PERSONA_MODE_LABELS = {
        banter: '斗嘴型', familiar: '熟络型', caring: '照顾型',
        dependent: '依赖型', polite: '客气型'
    };
    const PERSONA_SWITCH_UI = {
        banter: { label: '爱拌嘴', on: '一定要拌嘴', off: '别拌嘴' },
        clingy: { label: '偶尔撒娇', on: '撒娇管够', off: '不撒娇' },
        tsundere: { label: '嘴硬心软', on: '傲娇上线', off: '直来直去' },
        quiet_companion: { label: '安静陪着', on: '多陪少说', off: '该说说' },
        proactive_care: { label: '主动问冷暖', on: '会主动问', off: '先别主动' },
        proactive_banter: { label: '主动找你斗嘴', on: '会来找茬', off: '安分点' }
    };
    const PERSONA_AUTO_TEXT = '跟着感觉走';

    function personaSourceText(state) {
        if (state.manual) return '这是你亲手定的';
        if (state.source === 'auto') {
            const pct = Math.round((state.confidence || 0) * 100);
            return '这是它自己判断的' + (pct > 0 ? ('（把握 ' + pct + '%）') : '');
        }
        return '还没摸熟，先客客气气相处';
    }

    function loadPersonaCard() {
        const box = document.getElementById('persona-card');
        if (!box) return;
        const seq = ++personaFetchSeq;   // 独立竞态守卫（共用会挤掉 settings 渲染）
        fetch('/api/persona/state')
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (seq !== personaFetchSeq) return;
                renderPersonaCard(box, body || {});
            })
            .catch(function () {
                if (seq !== personaFetchSeq) return;
                box.hidden = false;
                box.classList.add('persona-locked');
                box.textContent = '人格状态读取失败，稍后再试。';
            });
    }

    function renderPersonaCard(box, body) {
        box.hidden = false;
        box.innerHTML = '';
        const hasLevel = body.level !== undefined;
        const level = Number(body.level || 0);
        if (hasLevel && level < 3) {
            // 权限预检（D13=Lv3）：未达标置灰+提示，不渲染可点击 UI
            box.classList.add('persona-locked');
            const tip = document.createElement('div');
            tip.className = 'persona-sub';
            tip.textContent = '人格设置需要 Lv.3' +
                (level > 0 ? ('（当前 Lv.' + level + '）') : '') +
                '——提升等级后可以查看和调整小橘的相处状态。';
            box.appendChild(tip);
            return;
        }
        box.classList.remove('persona-locked');
        const state = body.state || {};
        const title = document.createElement('div');
        title.className = 'persona-title';
        title.textContent = '人格';
        box.appendChild(title);

        const main = document.createElement('div');
        main.className = 'persona-mode-main';
        main.textContent = PERSONA_MODE_PHRASES[state.mode] ||
            '还在摸脾气的阶段';
        box.appendChild(main);

        const sub = document.createElement('div');
        sub.className = 'persona-sub';
        const label = PERSONA_MODE_LABELS[state.mode] || '';
        sub.textContent = personaSourceText(state) +
            (label ? ('（' + label + '）') : '');
        box.appendChild(sub);

        const lockRow = document.createElement('div');
        lockRow.className = 'persona-modes';
        Object.keys(PERSONA_MODE_PHRASES).forEach(function (mode) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = PERSONA_MODE_PHRASES[mode];
            if (state.mode === mode && state.manual) btn.classList.add('active');
            btn.addEventListener('click', function () {
                postPersona('manual_mode', { mode: mode });
            });
            lockRow.appendChild(btn);
        });
        const autoBtn = document.createElement('button');
        autoBtn.className = 'persona-auto-btn';
        autoBtn.textContent = '恢复自动判断';
        if (!state.manual) autoBtn.classList.add('active');
        autoBtn.addEventListener('click', function () {
            postPersona('manual_mode', { clear: true });
        });
        lockRow.appendChild(autoBtn);
        box.appendChild(lockRow);

        const switches = document.createElement('div');
        switches.className = 'persona-switches';
        Object.keys(PERSONA_SWITCH_UI).forEach(function (name) {
            const ui = PERSONA_SWITCH_UI[name];
            const cur = (state.switches && state.switches[name]) || {};
            const value = cur.value || 'auto';
            const row = document.createElement('div');
            row.className = 'persona-switch-row';
            const labelEl = document.createElement('span');
            labelEl.textContent = ui.label;
            row.appendChild(labelEl);
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = value === 'auto' ? PERSONA_AUTO_TEXT
                : (value === 'on' ? ui.on : ui.off);
            btn.addEventListener('click', function () {
                const next = value === 'auto' ? 'on'
                    : (value === 'on' ? 'off' : 'auto');
                postPersona('switch', { name: name, value: next });
            });
            row.appendChild(btn);
            switches.appendChild(row);
        });
        box.appendChild(switches);

        const meta = document.createElement('div');
        meta.className = 'persona-sub';
        meta.textContent = '你们已经聊了 ' + (state.interactions || 0) +
            ' 次。' + (state.expression_ready
                ? '个性语气已上线。'
                : '还在熟悉中（聊满 50 次后个性语气上线，当前 ' +
                  (state.interactions || 0) + ' 次）。');
        box.appendChild(meta);
    }

    function postPersona(action, payload) {
        const box = document.getElementById('persona-card');
        if (!box) return;
        fetch('/api/persona/' + action, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(function (res) { return res.json(); })
          .then(function (body) {
              // 错误路径一律 toast + 卡片原样保留（批 4 验收 Bug 2：
              // POST 响应无 level 曾把整卡抹成置灰提示）
              if (body && body.code === 403) {
                  showToast('⚠️ 权限不足（需要 Lv.3）');
                  return;
              }
              if (!body || body.code !== 200 || !body.state) {
                  showToast('⚠️ 保存失败，稍后再试');
                  return;
              }
              renderPersonaCard(box, {
                  level: body.level,          // 后端回传（同 GET 口径）
                  state: body.state
              });
          })
          .catch(function () { showToast('⚠️ 保存失败，稍后再试'); });
    }

    function collectSettingsUpdates() {
        const updates = {};
        if (!settingsListEl) return updates;
        settingsListEl.querySelectorAll('.settings-input').forEach(function (input) {
            const key = input.dataset.key;
            if (!key) return;
            const orig = SETTINGS_STATE.original[key];
            if (input.dataset.type === 'bool') {
                if (input.checked !== settingsChecked(orig)) {
                    updates[key] = input.checked ? '1' : '0';
                }
            } else if (String(orig === null || orig === undefined ? '' : orig) !== input.value) {
                updates[key] = input.value;
            }
        });
        return updates;
    }

    function settingsDenyText(body) {
        if (body && body.error === 'level_insufficient') {
            return '权限不足（需要 Lv.' + (body.required || '?') + '）';
        }
        if (body && body.error === 'childlock_off_requires_lv4_totp') {
            return '关闭儿童锁需要 Lv.4 + TOTP 验证';
        }
        if (body && body.error === 'totp_required') return '需要 TOTP 验证';
        if (body && body.error === 'totp_invalid') return 'TOTP 验证码无效';
        return '权限不足';
    }

    function saveSettings() {
        const updates = collectSettingsUpdates();
        const keys = Object.keys(updates);
        if (!keys.length) { showToast('没有修改项'); return; }
        // #264 B2c b：改动含 danger 档 → 先 TOTP 验证（前端卡片）再提交
        const dangerKeys = keys.filter(function (k) {
            return SETTINGS_STATE.tiers[k] === 'danger';
        });
        if (dangerKeys.length) {
            openTotpDialog(updates, dangerKeys);
            return;
        }
        submitSettingsUpdates(updates, null);
    }

    // 危险项后果文案（按项区分，设计稿 §三 4：高危保存弹确认含后果）
    const DANGER_CONSEQUENCES = {
        LOCAL_MODEL: '改主模型会影响所有对话的模型调用',
        CLOUD_MODEL: '改云模型会影响云端脑对话',
        XIAOJU3_PERSONALITY: '改人格档会影响说话风格与自称',
        HA_URL: '改 HA 地址会影响全屋智能联动',
        ONEBOT_API_URL: '改 OneBot 地址会影响 QQ 通道收发',
        VISION_API_URL: '改视觉地址会影响看图能力',
        WORKSPACE: '改工作区路径会影响文件读写位置（重启生效）',
    };

    function submitSettingsUpdates(updates, totp) {
        const payload = { updates: updates };
        if (totp) payload.totp = totp;
        fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(function (res) {
                return res.json().then(function (body) {
                    return { status: res.status, body: body };
                });
            })
            .then(function (r) {
                const body = r.body || {};
                if (r.status === 403 || body.code === 403) {
                    if (body.error === 'totp_invalid') {
                        showToast('⚠️ TOTP 验证码错误，请重试');
                        openTotpDialog(updates, Object.keys(updates).filter(function (k) {
                            return SETTINGS_STATE.tiers[k] === 'danger';
                        }), totp);   // 带上次的码便于改一位重试
                        return;
                    }
                    showToast('⚠️ ' + settingsDenyText(body));
                    return;
                }
                if (r.status !== 200 && body.code !== 200) {
                    showToast('保存失败' + (body.error ? ('：' + body.error) : ''));
                    return;
                }
                const written = Array.isArray(body.written) ? body.written : [];
                const applied = Array.isArray(body.applied) ? body.applied : [];
                const restart = written.filter(function (k) {
                    return applied.indexOf(k) === -1;
                });
                let msg = '✅ 已保存 ' + written.length + ' 项';
                if (applied.length) msg += '，' + applied.length + ' 项已生效';
                if (restart.length) msg += '，' + restart.length + ' 项重启后生效';
                showToast(msg);
                loadSettings();   // 保存后重拉：值与可见性以后端为真相
            })
            .catch(function (err) { showToast('保存失败: ' + err.message); });
    }

    // ==================== 高危 TOTP 验证卡（#264 B2c b） ====================
    // danger 项保存前置验证：6 位码+按项后果文案；403 totp_invalid →
    // 带旧码重开卡便于改一位重试；成功走 submitSettingsUpdates 常规链。
    let totpDialogEl = null;

    function closeTotpDialog() {
        if (totpDialogEl) {
            totpDialogEl.remove();
            totpDialogEl = null;
        }
    }

    function openTotpDialog(updates, dangerKeys, prefill) {
        closeTotpDialog();
        const overlay = document.createElement('div');
        overlay.id = 'totp-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483000;'
            + 'background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;';
        const card = document.createElement('div');
        card.style.cssText = 'background:var(--color-card,#fff);color:var(--color-text,#222);'
            + 'border:1px solid var(--color-danger,#e0433f);border-radius:10px;padding:20px 24px;'
            + 'width:min(420px,92vw);box-shadow:0 8px 30px rgba(0,0,0,.35);font-size:14px;';
        const title = document.createElement('div');
        title.textContent = '🛠️ 高危操作验证';
        title.style.cssText = 'font-size:16px;font-weight:700;color:var(--color-danger,#e0433f);margin-bottom:10px;';
        card.appendChild(title);
        dangerKeys.forEach(function (k) {
            const line = document.createElement('div');
            line.style.cssText = 'margin:4px 0;';
            line.textContent = '⚠️ ' + k + '：' + (DANGER_CONSEQUENCES[k] || '即将修改该项配置');
            card.appendChild(line);
        });
        const hint = document.createElement('div');
        hint.textContent = '请输入 6 位动态码（TOTP）确认操作：';
        hint.style.cssText = 'margin:12px 0 6px;';
        card.appendChild(hint);
        const input = document.createElement('input');
        input.type = 'text';
        input.inputMode = 'numeric';
        input.maxLength = 6;
        input.value = prefill || '';
        input.autocomplete = 'off';
        input.style.cssText = 'width:100%;box-sizing:border-box;padding:8px;border:1px solid rgba(127,127,127,.4);'
            + 'border-radius:6px;font-family:Consolas,monospace;font-size:18px;letter-spacing:.4em;text-align:center;';
        card.appendChild(input);
        const errTip = document.createElement('div');
        errTip.className = 'first-run-error';
        errTip.hidden = true;
        card.appendChild(errTip);
        const btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex;gap:10px;justify-content:flex-end;margin-top:12px;';
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'header-btn';
        cancelBtn.textContent = '取消';
        cancelBtn.addEventListener('click', closeTotpDialog);
        const okBtn = document.createElement('button');
        okBtn.className = 'header-btn';
        okBtn.textContent = '确认执行';
        okBtn.addEventListener('click', function () {
            const code = input.value.trim();
            if (!/^\d{6}$/.test(code)) {
                errTip.textContent = '请输入 6 位数字动态码';
                errTip.hidden = false;
                return;
            }
            closeTotpDialog();
            submitSettingsUpdates(updates, code);
        });
        btnRow.appendChild(cancelBtn);
        btnRow.appendChild(okBtn);
        card.appendChild(btnRow);
        overlay.appendChild(card);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closeTotpDialog();
        });
        document.body.appendChild(overlay);
        totpDialogEl = overlay;
        input.focus();
    }

    // ==================== 开发者模式暗入口（#264 B2c，持久化拍板） ====================
    // 状态=ui_pref.json 两字段（dev_unlocked/dev_mode_on，后端文件——
    // localStorage 关窗即焚禁用）；解锁永久、开关永久，F5/重启读文件恢复，
    // 无任何重置路径（用户拍板推翻设计稿原「会话级」口径）。连点=解锁仪式
    // （已解锁则提示开关在下方）；开关行拨 ON/OFF 独立持久化+审计；
    // LV3+ 每次触发写一条审计（js_api dev_audit → settings_log）。
    let devTapCount = 0;
    let devTapTimer = null;

    const DEV_STATE = { unlocked: false, mode_on: false };   // #264 B2c 收尾：内存镜像（真源=ui_pref.json）

    function applyDevBadges(on) {
        // 🛠️ 徽标统一挂/摘（「关于」条目标题+关于卡内版本号）
        const aboutLabel = document.querySelector('#settings-about .settings-about-label');
        if (aboutLabel) {
            const has = aboutLabel.textContent.indexOf('🛠️') !== -1;
            if (on && !has) aboutLabel.textContent += ' 🛠️';
            if (!on && has) aboutLabel.textContent = aboutLabel.textContent.replace(' 🛠️', '');
        }
        const cardVer = document.querySelector('#about-overlay .about-version');
        if (cardVer) {
            const has = cardVer.textContent.indexOf('🛠️') !== -1;
            if (on && !has) cardVer.textContent += ' 🛠️';
            if (!on && has) cardVer.textContent = cardVer.textContent.replace(' 🛠️', '');
        }
        // footer 版本号：解锁态橙字+浅橙底块（F5/重启恢复）
        const fv = document.getElementById('footer-version');
        if (fv) {
            fv.style.color = on ? 'var(--color-primary, #d96f2b)' : '';
            fv.style.background = on ? 'rgba(217, 111, 43, 0.15)' : '';
            fv.style.padding = on ? '1px 8px' : '';
            fv.style.borderRadius = on ? '6px' : '';
            fv.style.fontWeight = on ? '700' : '';
        }
    }

    function setDevMode(on, reason) {
        // 开发者模式开/关（持久化拍板）：写 ui_pref.json + 徽标 + 审计
        const api = window.pywebview && window.pywebview.api;
        if (!api || typeof api.set_dev_pref !== 'function') return;
        api.set_dev_pref(null, on).then(function (r) {
            if (!(r && r.ok)) return;
            DEV_STATE.mode_on = on;
            applyDevBadges(on);
            applyDevSwitchRow();
            showToast((on ? '🛠️ 开发者模式已开启' : '开发者模式已关闭')
                + (reason ? ('（' + reason + '）') : ''));
            if (api.dev_audit) api.dev_audit('dev_mode ' + (on ? 'enter' : 'exit') + ' ' + (reason || ''));
        }).catch(function () { showToast('保存失败'); });
    }

    function handleDevTap() {
        devTapCount += 1;
        clearTimeout(devTapTimer);
        devTapTimer = setTimeout(function () { devTapCount = 0; }, 3000);
        if (devTapCount < 7) return;
        devTapCount = 0;
        const level = SETTINGS_STATE.level;
        const api = window.pywebview && window.pywebview.api;
        if (level === null || level === undefined) {
            showToast('⚠️ 权限未知（请先打开设置页读取）');
            return;
        }
        if (level < 3) {
            showToast('⚠️ 权限不足（Lv.' + level + '）');
            return;
        }
        if (!api || typeof api.get_dev_pref !== 'function') {
            showToast('桌面窗口未就绪（浏览器形态不可用）');
            return;
        }
        api.get_dev_pref().then(function (pref) {
            if (pref && pref.unlocked) {
                // 已解锁：不重复仪式，指路开关行
                showToast('开发者模式开关已在下方（设置页底部）');
                if (api.dev_audit) api.dev_audit('tap7 already-unlocked level=' + level);
                return;
            }
            // 首次解锁：unlocked+mode_on 同写 true + 徽标 + 开关行 + 审计
            api.set_dev_pref(true, true).then(function (r) {
                if (!(r && r.ok)) { showToast('解锁失败'); return; }
                DEV_STATE.unlocked = true;
                DEV_STATE.mode_on = true;
                applyDevBadges(true);
                applyDevSwitchRow();
                markFooterVersionUnlocked();
                showToast('🔓 开发者模式已解锁（设置页底部展开「开发者模式」）');
                if (api.dev_audit) api.dev_audit('dev_mode enter tap7 level=' + level);
            }).catch(function () { showToast('解锁失败'); });
            }).catch(function () { showToast('桌面窗口未就绪'); });
    }
    // 解锁瞬间视觉反馈：footer 版本号变橙（#UI修复 2026-10-13）
    function markFooterVersionUnlocked() {
        const fv = document.getElementById('footer-version');
        if (fv) {
            // D 拍板：浅橙背景块（一眼可见）；C 图标砍掉
            fv.style.background = 'rgba(217, 111, 43, 0.15)';
            fv.style.color = 'var(--color-primary, #d96f2b)';
            fv.style.padding = '1px 8px';
            fv.style.borderRadius = '6px';
            fv.style.fontWeight = '700';
        }
    }

    // 连点绑定（#264 B2c 收尾）：关于卡内版本号（藏得更深=暗入口语义）；
    // 事件委托挂 body——卡是动态节点，开卡后即可连点
    document.body.addEventListener('click', function (e) {
        if (e.target && e.target.classList &&
            e.target.classList.contains('about-version')) {
            handleDevTap();
        }
        // #UI修复 2026-10-13：第二触发点=页面底部版本号（更显眼的自然位）
        if (e.target && e.target.id === 'footer-version') {
            handleDevTap();
        }
    });
    // ==================== 开发者模式开关行（#264 B2c 持久化） ====================
    // 位置=设置页「关于」条目上方；dev_unlocked=true 才显示；拨 ON/OFF 独立
    // 持久化（dev_mode_on）+徽标+审计；F5/重启按文件恢复（无重置路径）。
    function buildDevSwitchRow() {
        // 折叠式交互（2026-10-13 拍板）：标题行「开发者模式」+原生 details
        // 折叠（默认收起；将来开发者选项都收纳进此 details）
        const row = document.createElement('details');
        row.className = 'settings-about-row';
        row.id = 'dev-switch-row';
        const sum = document.createElement('summary');
        sum.style.cssText = 'cursor:pointer;font-weight:700;font-size:13px;'
            + 'list-style:revert;';
        sum.textContent = '开发者模式';
        row.appendChild(sum);
        const body = document.createElement('div');
        body.style.cssText = 'padding:6px 0 2px;';
        const sw = document.createElement('label');
        sw.style.cssText = 'display:flex;align-items:center;gap:6px;cursor:pointer;';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.id = 'dev-mode-switch';
        input.addEventListener('change', function () {
            setDevMode(input.checked, 'switch');
        });
        sw.appendChild(input);
        const txt = document.createElement('span');
        txt.style.cssText = 'font-size:12px;opacity:.7;';
        txt.textContent = '高危项 TOTP 验证+审计';
        sw.appendChild(txt);
        body.appendChild(sw);
        row.appendChild(body);
        return row;
    }

    function applyDevSwitchRow() {
        const api = window.pywebview && window.pywebview.api;
        const list = document.getElementById('settings-list');
        if (!api || typeof api.get_dev_pref !== 'function' || !list) return;
        api.get_dev_pref().then(function (pref) {
            DEV_STATE.unlocked = !!(pref && pref.unlocked);
            DEV_STATE.mode_on = !!(pref && pref.mode_on);
            let row = document.getElementById('dev-switch-row');
            if (!(pref && pref.unlocked)) {
                if (row) row.remove();   // 未解锁：开关行不显示
                applyDevBadges(false);
                return;
            }
            const on = !!(pref && pref.mode_on);
            if (!row) {
                row = buildDevSwitchRow();
                const about = document.getElementById('settings-about');
                if (about) list.insertBefore(row, about);   // 关于条目上方
                else list.appendChild(row);
            }
            const input = row.querySelector('#dev-mode-switch');
            if (input) input.checked = on;
            applyDevBadges(on);   // F5/重启恢复徽标
        }).catch(function () {});
    }

    // 「关于」条目 click → openAbout（复用 B2d 桌宠菜单同卡）
    const aboutRow = document.getElementById('settings-about');
    if (aboutRow) aboutRow.addEventListener('click', function () { openAbout(); });

    // ==================== 8. 缩成加速球（2026-10-03 口径：⌄ 缩桌宠成球） ====================
    // 与桌宠（desktop-pet.js）的协作：本节只切换 body 的 xiaoju3-pet-minimized
    // 类与球体显隐/定位，不注入/不修改桌宠任何节点（桌宠隐藏由 CSS 类驱动）。
    // 球体为 index.html 静态节点 #xiaoju3-ball（60px 圆形、橘色 Q 版边框、
    // 小橘头像）；控制台主体（.sidebar + .chat-area）永不隐藏（口径①）。
    // 球跟桌宠走（口径②）：进入最小化时从 __xiaoju3Pet.getPos() 实时取桌宠
    // 坐标重放球位（球心对齐桌宠心），位置不由球记忆（无 localStorage 持久化）；
    // 互切幂等（重复最小化/恢复不报错、不抖动），球体挂载点缺失时全部静默
    // 跳过，无 JS 报错路径。（PET_BALL_FIX_DESIGN）
    const PET_MINIMIZE_CLASS = 'xiaoju3-pet-minimized';
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

    // （位置持久化已退役：口径②球跟桌宠走，位置不由球记忆——每次进入
    // 最小化都按 __xiaoju3Pet.getPos() 实时原位重放，拖拽仅会话内生效）

    // 球跟桌宠（PET_BALL_FIX_DESIGN §2/§3）：从桌宠单例实时取坐标重放球位
    // （球心对齐桌宠心）；桌宠单例缺失/坐标异常时保持现状（回退 CSS 兜底位）
    function replayBallAtPet() {
        const pos = (window.__xiaoju3Pet && typeof window.__xiaoju3Pet.getPos === 'function')
            ? window.__xiaoju3Pet.getPos() : null;
        if (!pos || typeof pos.x !== 'number' || typeof pos.y !== 'number') return;
        const w = (typeof pos.w === 'number' && pos.w > 0) ? pos.w : BALL_SIZE;
        const h = (typeof pos.h === 'number' && pos.h > 0) ? pos.h : BALL_SIZE;
        applyBallPos({
            x: pos.x + (w - BALL_SIZE) / 2,
            y: pos.y + (h - BALL_SIZE) / 2,
        });
    }

    // 桌宠最小化/恢复互切（幂等）：已是目标状态直接返回，不重复操作。
    // 最小化 = 桌宠缩成球（CSS 类驱动桌宠隐藏 + 球显示），控制台永不缩
    function setPetMinimized(minimized) {
        const ball = getBallEl();
        if (!ball) return;   // 球体挂载点缺失：静默跳过，无 JS 报错路径
        const isMin = document.body.classList.contains(PET_MINIMIZE_CLASS);
        if (isMin === minimized) return;
        if (minimized) replayBallAtPet();   // 先重放球位（桌宠尚可见，尺寸取真实值）
        document.body.classList.toggle(PET_MINIMIZE_CLASS, minimized);
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
            if (!moved) {
                setPetMinimized(false);   // 未拖动＝点击恢复桌宠
            }
            // 拖动＝会话内自由摆位（applyBallPos 已实时落位）；不持久化，
            // 下次进入最小化按桌宠实时原位重放
        });
        // 拖拽被系统打断（来电/手势竞争）：复位拖拽态，不误判为点击
        ball.addEventListener('pointercancel', function () { dragging = false; });
        // 窗口尺寸变化：最小化态下按桌宠当前原位重放球位并钳制在视口内
        window.addEventListener('resize', function () {
            if (document.body.classList.contains(PET_MINIMIZE_CLASS)) {
                replayBallAtPet();
            }
        });
    }

    // #264 B2d ②：⌄ 原为「桌宠缩球」入口，现改齿轮=设置 tab（缩球功能
    // 迁入桌宠右键菜单「缩小」项，经 __xiaoju3Console.setPetMinimized 调用）；
    // 菜单批次的桥与 setPetMinimized 全保留，本处只换入口语义
    const settingsEntryBtn = document.getElementById('console-settings-entry');
    if (settingsEntryBtn) {
        settingsEntryBtn.addEventListener('click', function () {
            switchChatTab('settings');
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

    // ==================== 首装引导覆盖层（安装器方案步 A4b/C） ====================
    // 跳过语义（方案 C）：后端文件承载（xiaoju3_data/.first_run_skipped），
    // 彻底弃用 localStorage——浏览器/WebView2 容器差异免疫。
    function setFirstRunError(msg) {
        const el = document.getElementById('first-run-error');
        if (!el) return;
        if (msg) { el.textContent = msg; el.hidden = false; }
        else { el.textContent = ''; el.hidden = true; }
    }

    function closeFirstRunOverlay() {
        const overlay = document.getElementById('first-run-overlay');
        if (overlay) overlay.hidden = true;
    }

    function initFirstRun() {
        // 弹与不弹由后端 status 判定（.env 与跳过标记两个文件，容器无关）
        fetch('/api/first_run/status')
            .then(res => res.json())
            .then(res => {
                if (!(res.code === 200 && res.data && res.data.first_run)) return;
                // 安装器意向报告并行独立拉取（步 B3 消费端）：自带 catch 独立降级，
                // 不合并等待——报告慢/缺失绝不拖累探针弹出
                fetch('/api/first_run/installer_report')
                    .then(r3 => r3.json())
                    .then(r3 => { renderInstallerReport(r3 && r3.data); })
                    .catch(() => { /* 报告缺失降级：hints 块保持隐藏 */ });
                return fetch('/api/first_run/probes')
                    .then(r2 => r2.json())
                    .then(r2 => { showFirstRun(r2.data && r2.data.probes); });
            })
            .catch(() => { /* 引导层静默降级：控制台照常使用 */ });
    }

    function showFirstRun(probes) {
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

    function renderInstallerReport(data) {
        // 安装器意向报告只读展示（步 B3 消费端）：铁律=不预填表单、不写 .env、
        // 不预勾自启、不因意向跳过任何探针、不碰 DEVICE_TIER（真档位归
        // hardware_profiler 复测）。内容一律 textContent，绝不拼 HTML。
        const box = document.getElementById('first-run-install-hints');
        if (!box) return;
        box.innerHTML = '';
        box.hidden = true;
        const d = (data && typeof data === 'object') ? data : {};
        if (!d.available) return;
        const intents = (d.intents && typeof d.intents === 'object') ? d.intents : {};
        const labels = { ollama: '本地 Ollama', napcat: 'QQ(NapCat)', ha: 'HA 心跳' };
        const picked = Object.keys(labels).filter(function (k) {
            return intents[k] === true;
        });
        const metaBits = [];
        if (d.installed_at) metaBits.push('安装于 ' + d.installed_at);
        if (d.tier_hint) metaBits.push('安装器建议：' + d.tier_hint + '（真实档位以本机复测为准）');
        if (!picked.length && !metaBits.length) return;   // available 但三项全无：保持隐藏
        if (picked.length) {
            const badge = document.createElement('div');
            badge.textContent = '安装时勾选：' + picked.map(function (k) {
                return labels[k];
            }).join(' / ');
            box.appendChild(badge);
        }
        if (metaBits.length) {
            const meta = document.createElement('div');
            meta.textContent = metaBits.join('；');
            box.appendChild(meta);
        }
        box.hidden = false;
    }

    function submitFirstRun(skip) {
        if (skip) {
            // 跳过：后端写跳过标记文件（.env 不写），first_run 自然翻转为 false
            fetch('/api/first_run/skip', { method: 'POST' })
                .then(res => res.json())
                .then(res => {
                    if (res.code === 200) {
                        closeFirstRunOverlay();
                        if (typeof showToast === 'function') {
                            showToast('已跳过首装引导，可稍后编辑 xiaoju3_data\\.env');
                        }
                    } else {
                        setFirstRunError(res.error || '跳过失败，请重试');
                    }
                })
                .catch(() => setFirstRunError('网络异常，请重试'));
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
                closeFirstRunOverlay();
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

    // ==================== 关于卡 + 退出 stub + 桥（#264 B2d 第①批） ====================
    // 关于卡=极简拍板（名称+版本+一句话+Apache 2.0）；退出=stub 占位（双方法
    // 确认弹窗+js_api 全退链随第③批界面偏好组落地，设计稿第五节）；桥=桌宠
    // 右键菜单跨 IIFE 调用入口（镜像 __xiaoju3Pet 反向桥模式，方法缺失时
    // desktop-pet.js 侧 console.warn 兜底）。
    function openAbout() {
        const exist = document.getElementById('about-overlay');
        if (exist) { exist.hidden = false; return; }
        const overlay = document.createElement('div');
        overlay.id = 'about-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483000;'
            + 'background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;';
        const card = document.createElement('div');
        card.style.cssText = 'background:var(--color-card,#fff);color:var(--color-text,#222);'
            + 'border:1px solid var(--color-primary,#d96f2b);border-radius:10px;padding:22px 26px;'
            + 'width:min(340px,92vw);box-shadow:0 8px 30px rgba(0,0,0,.35);text-align:center;font-size:14px;';
        const logo = document.createElement('div');
        logo.textContent = '🦊 小橘3号';
        logo.style.cssText = 'font-size:20px;font-weight:700;margin-bottom:6px;';
        const verText = window.__xiaoju3Version || '';
        const ver = document.createElement('div');
        ver.className = 'about-version';   // 连点 7 次=开发者暗入口（B2c 收尾）
        ver.textContent = verText ? ('v' + verText) : 'v1.0.4';
        ver.title = '连点 7 次查看权限状态';
        ver.style.cssText = 'opacity:.75;margin-bottom:10px;cursor:default;user-select:none;';
        const desc = document.createElement('div');
        desc.textContent = '长期主线的本地优先智能体——桌宠+控制台+QQ 三通道。';
        desc.style.cssText = 'margin-bottom:10px;';
        const lic = document.createElement('div');
        lic.textContent = '开源许可：Apache License 2.0';
        lic.style.cssText = 'font-size:12px;opacity:.65;margin-bottom:14px;';
        const closeBtn = document.createElement('button');
        closeBtn.className = 'header-btn';
        closeBtn.textContent = '关闭';
        closeBtn.addEventListener('click', function () { overlay.hidden = true; });
        card.appendChild(logo);
        card.appendChild(ver);
        card.appendChild(desc);
        card.appendChild(lic);
        card.appendChild(closeBtn);
        overlay.appendChild(card);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) overlay.hidden = true;
        });
        document.body.appendChild(overlay);
    }

    function quitApp() {
        // #264 B2d④：真实现——与主窗 X 统一弹窗（双方法 radio+记住选择，
        // Python closing 拦截经 evaluate_js 调同一弹窗； remembering 走
        // js_api 存 ui_pref.json——localStorage 关窗即焚禁用）
        __xiaoju3OpenQuitDialog();
    }

    // ==================== 退出弹窗（#264 B2d④） ====================
    // 双方法 radio（只退窗口/完全退出）+「记住我的选择」（经 js_api 存
    // agent_state/ui_pref.json）；桌宠菜单 quitApp 与主窗 X（Python
    // closing 拦截 evaluate_js）统一走 __xiaoju3OpenQuitDialog。已记住
    // 时（pref≠ask）两端都不弹、直接按记住的方法退出。
    let quitDialogEl = null;

    function closeQuitDialog() {
        if (quitDialogEl) {
            quitDialogEl.remove();
            quitDialogEl = null;
        }
    }

    function showQuitDialog() {
        if (quitDialogEl) { quitDialogEl.hidden = false; return; }
        const overlay = document.createElement('div');
        overlay.id = 'quit-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483000;'
            + 'background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;';
        const card = document.createElement('div');
        card.style.cssText = 'background:var(--color-card,#fff);color:var(--color-text,#222);'
            + 'border:1px solid var(--color-primary,#d96f2b);border-radius:10px;padding:20px 24px;'
            + 'width:min(400px,92vw);box-shadow:0 8px 30px rgba(0,0,0,.35);font-size:14px;';
        const title = document.createElement('div');
        title.textContent = '是否退出小橘3号？';
        title.style.cssText = 'font-size:16px;font-weight:700;margin-bottom:10px;';
        card.appendChild(title);
        let selected = 'backend_only';
        [['backend_only', '只退窗口（后端与 NapCat 继续运行）'],
         ['full_exit', '完全退出（前端+后端+NapCat 全部关闭）']].forEach(function (r, i) {
            const lab = document.createElement('label');
            lab.style.cssText = 'display:block;margin:8px 0;cursor:pointer;';
            const input = document.createElement('input');
            input.type = 'radio';
            input.name = 'quit-mode';
            input.value = r[0];
            input.checked = i === 0;
            input.addEventListener('change', function () { selected = r[0]; });
            lab.appendChild(input);
            lab.appendChild(document.createTextNode(' ' + r[1]));
            card.appendChild(lab);
        });
        const rememberLab = document.createElement('label');
        rememberLab.style.cssText = 'display:block;margin:10px 0;font-size:12px;opacity:.8;cursor:pointer;';
        const remember = document.createElement('input');
        remember.type = 'checkbox';
        rememberLab.appendChild(remember);
        rememberLab.appendChild(document.createTextNode(' 记住我的选择，下次不再询问'));
        card.appendChild(rememberLab);
        const btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex;gap:10px;justify-content:flex-end;margin-top:12px;';
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'header-btn';
        cancelBtn.textContent = '取消';
        cancelBtn.addEventListener('click', closeQuitDialog);
        const okBtn = document.createElement('button');
        okBtn.className = 'header-btn';
        okBtn.textContent = '确认退出';
        okBtn.addEventListener('click', function () {
            const api = window.pywebview && window.pywebview.api;
            if (!api || typeof api.quit_app !== 'function') {
                showToast('桌面窗口未就绪（浏览器形态请在窗口上退出）');
                return;
            }
            api.quit_app(selected, remember.checked);
            closeQuitDialog();
            showToast(remember.checked ? '已记住退出方式，正在退出…' : '正在退出…');
        });
        btnRow.appendChild(cancelBtn);
        btnRow.appendChild(okBtn);
        card.appendChild(btnRow);
        overlay.appendChild(card);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closeQuitDialog();
        });
        document.body.appendChild(overlay);
        quitDialogEl = overlay;
    }

    function __xiaoju3OpenQuitDialog() {
        const api = window.pywebview && window.pywebview.api;
        if (api && typeof api.get_exit_pref === 'function') {
            api.get_exit_pref().then(function (pref) {
                if (pref === 'backend_only' || pref === 'full_exit') {
                    api.quit_app(pref);   // 记住过：两端都不弹，按记住的方法直接走
                    return;
                }
                showQuitDialog();
            }).catch(function () { showQuitDialog(); });
            return;
        }
        showToast('桌面窗口未就绪（浏览器形态请在窗口上退出）');
    }
    window.__xiaoju3OpenQuitDialog = __xiaoju3OpenQuitDialog;   // Python closing 拦截入口

    // ==================== 密钥管理（#264 B2b，方案 A） ====================
    // 数据=GET /api/keys → {code,level,items:[{key,masked,set}]}：掩码由
    // 后端拼好（前3+****+后4），**前端零明文接触**（渲染只用 masked/set，
    // 铁律=设计稿第五节）；覆盖=POST {key,value,confirm:true}（二次确认
    // window.confirm——设计稿拍板防误操作）；LV3+ 门=页面加载探针
    // （403→🔑 hidden，后端 403 双保险）。
    let keysFetchSeq = 0;

    function appendKeysTip(text) {
        const tip = document.createElement('div');
        tip.className = 'settings-empty';
        tip.textContent = text;
        keysListEl.appendChild(tip);
    }

    function buildKeysRow(it) {
        const row = document.createElement('div');
        row.className = 'first-run-field settings-field keys-field';
        const cap = document.createElement('span');
        cap.textContent = it.key;
        row.appendChild(cap);
        const maskRow = document.createElement('div');
        maskRow.className = 'keys-row';
        const masked = document.createElement('span');
        masked.className = 'keys-masked';
        masked.textContent = it.set ? (it.masked || '****') : '未配置';
        masked.style.cssText = it.set ? '' : 'opacity:.55;';
        maskRow.appendChild(masked);
        const editBtn = document.createElement('button');
        editBtn.className = 'header-btn';
        editBtn.textContent = '改';
        editBtn.title = '覆盖 ' + it.key;
        editBtn.addEventListener('click', function () { startKeyEdit(row, it); });
        maskRow.appendChild(editBtn);
        row.appendChild(maskRow);
        return row;
    }

    function renderKeysItems(data) {
        if (!keysListEl) return;
        const items = (data && Array.isArray(data.items)) ? data.items : [];
        keysListEl.innerHTML = '';
        if (!items.length) {
            appendKeysTip('暂无可见密钥项');
            return;
        }
        items.forEach(function (it) { keysListEl.appendChild(buildKeysRow(it)); });
    }

    function startKeyEdit(row, it) {
        const existing = row.querySelector('.keys-edit');
        if (existing) { existing.querySelector('input').focus(); return; }
        const edit = document.createElement('div');
        edit.className = 'keys-edit';
        edit.style.cssText = 'margin-top:6px;';
        const input = document.createElement('input');
        input.type = 'password';
        input.autocomplete = 'off';
        input.placeholder = '粘贴新值（只写不读，保存后仅显示掩码）';
        input.style.cssText = 'width:100%;box-sizing:border-box;padding:6px 8px;'
            + 'border:1px solid rgba(127,127,127,.4);border-radius:6px;';
        const btns = document.createElement('div');
        btns.style.cssText = 'display:flex;gap:8px;margin-top:6px;justify-content:flex-end;';
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'header-btn';
        cancelBtn.textContent = '取消';
        cancelBtn.addEventListener('click', function () { edit.remove(); });
        const saveBtn = document.createElement('button');
        saveBtn.className = 'header-btn';
        saveBtn.textContent = '保存';
        saveBtn.addEventListener('click', function () {
            const value = input.value;
            if (!value.trim()) { showToast('新值不能为空'); return; }
            // 二次确认（设计稿第五节拍板：防误操作，旧值不可恢复）——现代弹窗
            showConfirm('覆盖密钥', '确认覆盖 ' + it.key + ' 吗？旧值不可恢复。', function () {
                fetch('/api/keys', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: it.key, value: value, confirm: true })
                })
                .then(function (res) {
                    return res.json().then(function (body) {
                        return { status: res.status, body: body };
                    });
                })
                .then(function (r) {
                    const body = r.body || {};
                    if (r.status === 403 || body.code === 403) {
                        showToast('⚠️ 权限不足（需要 Lv.3）');
                        return;
                    }
                    if (r.status === 400 || body.code === 400) {
                        showToast('保存失败：' + (body.error || '参数错误'));
                        return;
                    }
                    if (r.status !== 200 && body.code !== 200) {
                        showToast('保存失败');
                        return;
                    }
                    input.value = '';   // 明文即清，不缓存
                    edit.remove();
                    showToast('✅ 已保存 ' + it.key);
                    loadKeys();          // 刷新掩码显示
                })
                .catch(function (err) { showToast('保存失败: ' + err.message); });
            }, { confirmText: '覆盖' });
        });
        btns.appendChild(cancelBtn);
        btns.appendChild(saveBtn);
        edit.appendChild(input);
        edit.appendChild(btns);
        row.appendChild(edit);
        input.focus();
    }

    function loadKeys() {
        if (!keysListEl) return;
        const seq = ++keysFetchSeq;   // 竞态守卫（与设置页同口径）
        fetch('/api/keys')
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (seq !== keysFetchSeq) return;
                if (!body || body.code !== 200) {
                    keysListEl.innerHTML = '';
                    appendKeysTip('权限不足（需要 Lv.3）或读取失败');
                    return;
                }
                renderKeysItems(body);
            })
            .catch(function (err) {
                if (seq !== keysFetchSeq) return;
                keysListEl.innerHTML = '';
                appendKeysTip('密钥读取失败: ' + err.message);
            });
    }

    // 入口探针（LV3+ 门，页面加载即定）：200 → 显 🔑 并预取渲染；
    // 403 → 🔑 hidden（与后端 403 双保险）。
    function probeKeysAccess() {
        if (!keysEntryBtn) return;
        fetch('/api/keys')
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (body && body.code === 200) {
                    keysEntryBtn.hidden = false;
                    SETTINGS_STATE.level = body.level;   // #264 B2c a：连点判级用（早于设置页）
                    renderKeysItems(body);   // 预取渲染（pane 打开即有内容）
                } else {
                    keysEntryBtn.hidden = true;
                }
            })
            .catch(function () { keysEntryBtn.hidden = true; });
    }

    window.__xiaoju3Console = {
        switchTab: switchChatTab,
        setPetMinimized: setPetMinimized,
        toggleTheme: toggleTheme,
        openAbout: openAbout,
        quitApp: quitApp,
    };

    const PROACTIVE_REASON_LABELS = {
        daily_quota: '今日次数已用完', cooldown: '刚聊过（冷却中）',
        quiet_hours: '深夜时段', rejected: '刚被拒绝过',
        user_busy: '主人忙碌', explicit_stop: '主人说了别烦',
    };

    // ---- 审计三层视图（2026-10-13：不看流水，看"每天干了什么"）----
    // 层 1 日汇总（默认）→ 层 2 当日区间（同分类合并）→ 层 3 原始行。
    function classifyAudit(item) {
        if (item.decision === 'fire') {
            return { key: 'fire', icon: '🔥', label: '出手' };
        }
        const r = item.reason || '';
        if (r.indexOf('quiet_hours') !== -1) {
            return { key: 'quiet', icon: '💤', label: '深夜静默' };
        }
        if (r.indexOf('daily_quota') !== -1) {
            return { key: 'quota', icon: '🚫', label: '配额拦截' };
        }
        if (r.indexOf('explicit_stop') !== -1) {
            return { key: 'stop', icon: '🚫', label: '主人说了别烦' };
        }
        if (r.indexOf('rejected') !== -1) {
            return { key: 'rej', icon: '🚫', label: '被拒后抑制' };
        }
        if (r.indexOf('cooldown') !== -1) {
            return { key: 'cool', icon: '⏸', label: '冷却' };
        }
        if (r.indexOf('user_busy') !== -1) {
            return { key: 'busy', icon: '⏸', label: '主人忙碌' };
        }
        return { key: 'hold', icon: '🟡', label: '按住' };
    }

    function groupAuditByDay(itemsAsc) {
        // ASC 时序 → [{date, items}]（保持 ASC，渲染层再倒序天）
        const days = [];
        itemsAsc.forEach(function (it) {
            const day = (it.ts || '').slice(0, 10);
            if (!days.length || days[days.length - 1].date !== day) {
                days.push({ date: day, items: [] });
            }
            days[days.length - 1].items.push(it);
        });
        return days;
    }

    function mergeAuditRuns(itemsAsc) {
        // 同分类连续 → 区间 {cls, start, end, count}
        const runs = [];
        itemsAsc.forEach(function (it) {
            const cls = classifyAudit(it);
            const last = runs[runs.length - 1];
            if (last && last.cls.key === cls.key) {
                last.end = it.ts;
                last.count += 1;
                last.items.push(it);
            } else {
                runs.push({ cls: cls, start: it.ts, end: it.ts,
                            count: 1, items: [it] });
            }
        });
        return runs;
    }

    function renderProactiveInto(bodyEl) {
        // 面板版主动性监控：三层视图（limit=2000 跨天聚合）
        fetch('/api/proactive/recent?limit=2000')
            .then(function (r) { return r.json(); })
            .then(function (j) {
                const d = (j && j.data) || {};
                bodyEl.textContent = '';
                if (!d.enabled) {
                    bodyEl.textContent = '主动性引擎未启用';
                    return;
                }
                const noteEl = document.createElement('div');
                noteEl.style.cssText = 'font-size:12px;opacity:.7;margin-bottom:6px;';
                noteEl.textContent = '内账观察期：「出手」=仅写审计记录，暂不发真消息。';
                bodyEl.appendChild(noteEl);
                const head = document.createElement('div');
                head.className = 'settings-empty';
                head.textContent = '今日出手 ' + (d.today_fire_count || 0) + '/' +
                    (d.daily_limit || 5) + ' · 当前张力 ' + (d.tension || 0);
                bodyEl.appendChild(head);
                // 频率调节（迁移保全：/api/proactive/config admin 门）
                const tuneRow = document.createElement('div');
                tuneRow.style.cssText = 'display:flex;gap:6px;align-items:center;margin:4px 0 8px;';
                const num = document.createElement('input');
                num.type = 'number'; num.min = '1'; num.max = '50';
                num.value = d.daily_limit || 5;
                num.style.cssText = 'width:70px;';
                tuneRow.appendChild(num);
                const tuneBtn = document.createElement('button');
                tuneBtn.textContent = '保存每天最多主动次数';
                tuneBtn.style.cssText = 'font-size:12px;cursor:pointer;';
                tuneBtn.addEventListener('click', function () {
                    fetch('/api/proactive/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ daily_limit: parseInt(num.value, 10) }),
                    }).then(function (r) {
                        return r.json().then(function (j) { return { ok: r.ok, j: j }; });
                    }).then(function (res) {
                        showToast(res.ok ? ('已保存（' + res.j.data.daily_limit + ' 次/天）')
                                          : (res.j.error || '保存失败'));
                        renderProactiveInto(bodyEl);
                    }).catch(function () { showToast('保存失败'); });
                });
                tuneRow.appendChild(tuneBtn);
                bodyEl.appendChild(tuneRow);

                // ---- 三层聚合（recent DESC → 反转 ASC 处理）----
                const itemsAsc = (d.recent || []).slice().reverse();
                const days = groupAuditByDay(itemsAsc).slice().reverse();
                days.forEach(function (day) {
                    const runs = mergeAuditRuns(day.items);
                    const per = {};
                    day.items.forEach(function (it) {
                        const k = classifyAudit(it).key;
                        per[k] = (per[k] || 0) + 1;
                    });
                    const iconOrder = [['fire', '🔥', '出手'], ['hold', '🟡', '按住'],
                                       ['quiet', '💤', '深夜'], ['cool', '⏸', '冷却'],
                                       ['quota', '🚫', '配额'], ['rej', '🚫', '被拒'],
                                       ['stop', '🚫', '别烦'], ['busy', '⏸', '忙碌']];
                    const parts = iconOrder
                        .filter(function (p) { return per[p[0]]; })
                        .map(function (p) { return p[1] + ' ' + p[2] + ' ' + per[p[0]] + ' 次'; });
                    const dayDetail = document.createElement('details');
                    dayDetail.style.cssText = 'margin:4px 0;border:1px solid '
                        + 'var(--color-border,#e0e4ec);border-radius:8px;padding:6px 8px;';
                    const daySum = document.createElement('summary');
                    daySum.style.cssText = 'cursor:pointer;font-size:13px;';
                    daySum.textContent = '📅 ' + day.date + '　' + parts.join(' · ');
                    dayDetail.appendChild(daySum);
                    runs.forEach(function (run) {
                        const st = (run.start || '').slice(11, 16);
                        const en = (run.end || '').slice(11, 16);
                        const mins = Math.round(
                            (new Date(run.end.replace('T', ' ').replace('-', '/'))
                             - new Date(run.start.replace('T', ' ').replace('-', '/'))) / 60000);
                        const runDetail = document.createElement('details');
                        runDetail.style.cssText = 'margin:3px 0 3px 12px;';
                        const runSum = document.createElement('summary');
                        runSum.style.cssText = 'cursor:pointer;font-size:12px;';
                        runSum.textContent = run.cls.icon + ' ' + st + ' - ' + en +
                            '　' + run.cls.label + (run.count > 1
                            ? '（' + run.count + ' 条' +
                              (mins > 0 ? ' / ' + mins + ' 分钟' : '') + '）' : '');
                        runDetail.appendChild(runSum);
                        run.items.forEach(function (it) {
                            const raw = document.createElement('div');
                            raw.style.cssText = 'font-size:11px;opacity:.75;'
                                + 'margin:2px 0 2px 14px;';
                            raw.textContent = (it.ts || '').slice(11) + ' · ' +
                                (it.reason || '') +
                                (it.events ? ' · ' + it.events : '');
                            runDetail.appendChild(raw);
                        });
                        dayDetail.appendChild(runDetail);
                    });
                    bodyEl.appendChild(dayDetail);
                });
            })
            .catch(function () { bodyEl.textContent = '审计读取失败'; });
    }

    function buildToolCard(title, hint, onClick) {
        const card = document.createElement('div');
        card.className = 'tool-card';
        card.style.cssText = 'background:var(--color-card,#fff);'
            + 'border:1px solid var(--color-border,#e0e4ec);'
            + 'border-radius:var(--radius-card,12px);padding:14px 16px;'
            + 'cursor:pointer;box-shadow:var(--shadow-card,0 2px 8px rgba(0,0,0,.06));';
        card.addEventListener('click', onClick);
        const t = document.createElement('div');
        t.style.cssText = 'font-weight:700;font-size:14px;margin-bottom:4px;';
        t.textContent = title;
        card.appendChild(t);
        const h = document.createElement('div');
        h.style.cssText = 'font-size:12px;opacity:.65;';
        h.textContent = hint;
        card.appendChild(h);
        return card;
    }

    function toggleToolBody(bodyId, loader) {
        let body = document.getElementById(bodyId);
        const overlay = document.getElementById('tools-overlay');
        if (!overlay) return;
        if (!body) {
            body = document.createElement('div');
            body.id = bodyId;
            body.hidden = true;   // 新建默认收起，走下方统一展开+加载
            body.style.cssText = 'margin:10px 0 20px;background:var(--color-card,'
                + '#fff);border:1px solid var(--color-border,#e0e4ec);'
                + 'border-radius:var(--radius-card,12px);padding:12px 14px;'
                + 'max-height:60vh;overflow-y:auto;';
            overlay.appendChild(body);
        }
        if (!body.hidden) {
            body.hidden = true;
            return;
        }
        body.hidden = false;
        loader(body);
    }

    function loadMemoryInto(body) {
        body.textContent = '加载中…';
        fetch('/api/memory/list').then(function (r) { return r.json(); })
            .then(function (j) {
                const items = (j.data && j.data.items) || [];
                body.textContent = '';
                if (!items.length) {
                    body.textContent = '长期记忆为空（对我说「记住…」即可积累）';
                    return;
                }
                items.forEach(function (m) {
                    const line = document.createElement('div');
                    line.style.cssText = 'font-size:12px;padding:4px 0;'
                        + 'border-bottom:1px dashed var(--color-border,#e0e4ec);';
                    const sink = m.sink_status === 'pending_sink' ? ' 💤沉睡' : '';
                    const emo = m.emotion_tag !== 'neutral'
                        ? ' 🏷' + m.emotion_tag : '';
                    line.textContent = '· [' + m.category + '] ' + m.content +
                        '（权重 ' + (m.weight || 1) + emo + sink + '）';
                    body.appendChild(line);
                });
            })
            .catch(function () { body.textContent = '记忆读取失败'; });
    }

    // 🔌 插件管理面板（2026-10-28 一期）：列表+独立启停开关（POST toggle
    // → loader 原子换装即时生效）；禁用区单独渲染（可重新启用）。操作反馈
    // 即时（toast+重拉清单），不触碰核心后台进程。
    function loadPluginsManageInto(body) {
        body.textContent = '加载中…';
        fetch('/api/plugins').then(function (r) { return r.json(); })
            .then(function (d) {
                body.textContent = '';
                const wrap = document.createElement('div');
                const mkRow = function (p, enabled) {
                    const row = document.createElement('div');
                    row.style.cssText = 'display:flex;align-items:center;'
                        + 'gap:10px;padding:7px 0;border-bottom:1px dashed '
                        + 'var(--color-border,#e0e4ec);';
                    const info = document.createElement('div');
                    info.style.cssText = 'flex:1;min-width:0;';
                    info.innerHTML = '🧩 <b>' + escapeHtml(p.name) + '</b>'
                        + ' <span class="dp-sub">v' + escapeHtml(p.version || '')
                        + ' · 工具 ' + (p.tools || 0) + '</span><br>'
                        + '<span class="dp-sub">' + escapeHtml(p.desc || '')
                        + '</span>';
                    const badge = document.createElement('span');
                    badge.style.cssText = 'font-size:11px;padding:2px 8px;'
                        + 'border-radius:10px;'
                        + (enabled ? 'background:#e6f6ea;color:#1a7f37;'
                                   : 'background:#f0f0f2;color:#888;');
                    badge.textContent = enabled ? '已启用' : '已停用';
                    const btn = document.createElement('button');
                    btn.className = 'btn btn-small';
                    btn.textContent = enabled ? '停用' : '启用';
                    btn.addEventListener('click', function () {
                        btn.disabled = true;
                        btn.textContent = '切换中…';
                        fetch('/api/plugins/toggle', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({name: p.name,
                                                  enabled: !enabled})
                        }).then(function (r) { return r.json(); })
                          .then(function (j) {
                              if (j.ok) {
                                  showToast('插件 ' + p.name + ' 已'
                                            + (j.enabled ? '启用' : '停用'));
                              } else {
                                  showToast('切换失败：' + (j.error || '未知'));
                              }
                              loadPluginsManageInto(body);   // 重拉即时反馈
                          })
                          .catch(function () {
                              showToast('切换请求失败');
                              loadPluginsManageInto(body);
                          });
                    });
                    row.appendChild(info);
                    row.appendChild(badge);
                    row.appendChild(btn);
                    return row;
                };
                (d.plugins || []).forEach(function (p) {
                    wrap.appendChild(mkRow(p, true));
                });
                (d.disabled || []).forEach(function (name) {
                    wrap.appendChild(mkRow({name: name, version: '',
                                            desc: '（停用中：工具/意图/后台'
                                                  + '线程全部停摆）', tools: 0},
                                           false));
                });
                if (!(d.plugins || []).length && !(d.disabled || []).length) {
                    wrap.innerHTML = '<div class="dp-sub">暂无外部插件</div>';
                }
                const tip = document.createElement('div');
                tip.className = 'dp-sub';
                tip.style.marginTop = '8px';
                tip.textContent = '停用=卸载插件（工具/意图/后台线程全停，'
                                + '持久化重启不回弹）；启用=即时换装。'
                                + '拒绝载入：'
                                + ((d.plugins || []).length ? '' : '见上方')
                                + (d.disabled || []).length + ' 项禁用中。';
                wrap.appendChild(tip);
                body.appendChild(wrap);
            })
            .catch(function () { body.textContent = '清单获取失败'; });
    }

    // 🐾 桌宠开关（2026-10-28 队长拍板默认关）：ui_pref.desktop_pet_enabled
    // → /api/pet_pref GET/POST；切换后刷新页面生效（脚本按配置动态注入）。
    function loadHaDevicesInto(body) {
        body.textContent = '加载中…（HA 可达约需 1-10s）';
        fetch('/api/ha/devices').then(function (r) { return r.json(); })
            .then(function (j) {
                body.textContent = '';
                const pre = document.createElement('pre');
                pre.style.cssText = 'white-space:pre-wrap;font-size:12px;'
                    + 'margin:0;font-family:inherit;';
                pre.textContent = (j.data && j.data.text) || '（空）';
                body.appendChild(pre);
            })
            .catch(function (e) { body.textContent = '读取失败: ' + e; });
    }

    function closeToolsPanel() {
        const overlay = document.getElementById('tools-overlay');
        if (overlay) {
            overlay.hidden = true;
            overlay.textContent = '';
        }
    }

    function openToolsPanel() {
        const overlay = document.getElementById('tools-overlay');
        if (!overlay) return;
        overlay.hidden = false;
        overlay.style.cssText = 'position:fixed;inset:0;z-index:2147482000;'
            + 'background:var(--color-bg,#f4f6f9);overflow-y:auto;padding:18px 22px;';
        overlay.textContent = '';

        const top = document.createElement('div');
        top.style.cssText = 'display:flex;align-items:center;gap:12px;'
            + 'margin-bottom:16px;';
        const back = document.createElement('button');
        back.className = 'header-btn';
        back.textContent = '← 返回';
        back.addEventListener('click', closeToolsPanel);
        top.appendChild(back);
        const title = document.createElement('div');
        title.style.cssText = 'font-size:18px;font-weight:700;';
        title.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px;margin-right:4px"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>小工具面板';
        top.appendChild(title);
        overlay.appendChild(top);

        function sectionLabel(text) {
            const s = document.createElement('div');
            s.style.cssText = 'font-weight:700;font-size:13px;opacity:.7;'
                + 'margin:14px 0 8px;';
            s.textContent = text;
            overlay.appendChild(s);
        }
        function grid() {
            const g = document.createElement('div');
            g.style.cssText = 'display:grid;grid-template-columns:'
                + 'repeat(auto-fill,minmax(220px,1fr));gap:12px;';
            overlay.appendChild(g);
            return g;
        }
        function note(text) {
            const n = document.createElement('div');
            n.style.cssText = 'font-size:12px;opacity:.7;margin:8px 0 4px;';
            n.textContent = text;
            overlay.appendChild(n);
            return n;
        }

        // 📊 小橘监控
        sectionLabel('📊 小橘监控');
        const g1 = grid();
        const proBody = document.createElement('div');
        proBody.style.cssText = 'margin:10px 0 20px;';
        g1.appendChild(buildToolCard('主动性监控', '张力/配额/审计（跃迁日志）',
            function () {
                // 卡片点击=就地展开（二次点击收起）
                if (proBody.hidden) {
                    proBody.hidden = false;
                    renderProactiveInto(proBody);
                } else {
                    proBody.hidden = true;
                    proBody.textContent = '';
                }
            }));
        overlay.appendChild(proBody);
        proBody.hidden = true;
        g1.appendChild(buildToolCard('记忆查看', '内容+权重/状态（长期记忆清单）',
            function () { toggleToolBody('tool-memory-body', loadMemoryInto); }));
        g1.appendChild(buildToolCard('终端记录', '终端通道聊天记录（只读）',
            function () {
                closeToolsPanel();
                switchChatTab('terminal');
            }));

        // 🏠 小橘能控制什么
        sectionLabel('🏠 小橘能控制什么');
        const g2 = grid();
        g2.appendChild(buildToolCard('家电列表', 'HA 实体清单（只读，控制走对话）',
            function () { toggleToolBody('tool-ha-body', loadHaDevicesInto); }));

        // 🔌 管理
        sectionLabel('🔌 管理');
        const g3 = grid();
        g3.appendChild(buildToolCard('设置', '权限分级配置/界面偏好/密钥管理',
            function () {
                closeToolsPanel();
                switchChatTab('settings');
            }));
        g3.appendChild(buildToolCard('插件管理', '外部插件启停（停用即卸载，重启用即时换装）',
            function () { toggleToolBody('tool-plugins-body', loadPluginsManageInto); }));
        g3.appendChild(_buildPetCard());
        note('面板骨架批 1：监控三类中「主动性监控」可用；其余卡片为占位。');
    }

    // 🐾 桌宠管理卡（自包含展开式：Toggle 内嵌在卡片内，不外溢到面板底部）
    function _buildPetCard() {
        const card = document.createElement('div');
        card.style.cssText = 'background:var(--color-card,#fff);'
            + 'border:1px solid var(--color-border,#e0e4ec);'
            + 'border-radius:var(--radius-card,12px);padding:16px;'
            + 'box-shadow:var(--shadow-card,0 1px 4px rgba(0,0,0,0.06));'
            + 'cursor:pointer;user-select:none;';

        const title = document.createElement('div');
        title.style.cssText = 'font-size:14px;font-weight:700;margin-bottom:4px;';
        title.textContent = '桌面宠物';
        const hint = document.createElement('div');
        hint.style.cssText = 'font-size:12px;color:var(--color-text-hint,#999);';
        hint.textContent = '桌宠开关（默认关）▶ 点击展开';
        card.appendChild(title);
        card.appendChild(hint);

        const body = document.createElement('div');
        body.style.cssText = 'display:none;margin-top:12px;';
        card.appendChild(body);

        let expanded = false;
        let loaded = false;

        card.addEventListener('click', function () {
            expanded = !expanded;
            body.style.display = expanded ? 'block' : 'none';
            hint.textContent = expanded ? '桌宠开关（默认关）▼ 点击收起' : '桌宠开关（默认关）▶ 点击展开';
            if (expanded && !loaded) {
                loaded = true;
                _renderPetToggles(body);
            }
        });

        return card;
    }

    function _renderPetToggles(container) {
        container.textContent = '加载中…';
        fetch('/api/pet_pref').then(function (r) { return r.json(); })
            .then(function (j) {
                const d = j.data || {};
                container.textContent = '';

                const items = [
                    { key: 'desktop_pet_enabled',  label: '🐾 显示桌宠', sub: '独立窗口狐狸挂件' },
                    { key: 'desktop_pet_topmost',  label: '📌 窗口置顶', sub: '始终在最前层' },
                    { key: 'desktop_pet_drag',     label: '🖱️ 允许拖拽', sub: '按住狐狸拖到任意位置' },
                ];

                items.forEach(function (item) {
                    const enabled = !!d[item.key];
                    const row = document.createElement('div');
                    row.className = 'pet-setting-row';

                    const info = document.createElement('div');
                    const lab = document.createElement('div');
                    lab.className = 'pet-setting-label';
                    lab.textContent = item.label;
                    const sub = document.createElement('div');
                    sub.className = 'pet-setting-sub';
                    sub.textContent = item.sub;
                    info.appendChild(lab);
                    info.appendChild(sub);

                    const toggle = document.createElement('label');
                    toggle.className = 'toggle-switch';
                    const cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.checked = enabled;
                    const slider = document.createElement('span');
                    slider.className = 'toggle-slider';
                    toggle.appendChild(cb);
                    toggle.appendChild(slider);

                    cb.addEventListener('change', function () {
                        const val = cb.checked;
                        cb.disabled = true;
                        fetch('/api/pet_pref', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify([{key: item.key, value: val}])
                        }).then(function (r) { return r.json(); })
                          .then(function () { cb.disabled = false; })
                          .catch(function () { cb.checked = !val; cb.disabled = false; });
                    });

                    row.appendChild(info);
                    row.appendChild(toggle);
                    container.appendChild(row);
                });

                const tip = document.createElement('div');
                tip.className = 'pet-setting-sub';
                tip.style.marginTop = '8px';
                tip.textContent = '💡 切换后刷新页面生效（独立窗口进程由桌面启动器管理）';
                container.appendChild(tip);
            })
            .catch(function () { container.textContent = '读取失败'; });
    }

    // 🧰 入口绑定（header-actions 最前，齿轮/密钥同款 header-btn）
    const toolsEntry = document.getElementById('tools-entry');
    if (toolsEntry) {
        toolsEntry.addEventListener('click', openToolsPanel);
    }
    // 🔄 强制刷新（清缓存+重载，2026-10-29 队长要求）
    const refreshBtn = document.getElementById('force-refresh');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function () {
            window.location.reload(true);
        });
    }
})();

    // ==================== 小工具面板（MAA 式收纳，2026-10-13 批 1） ====================
    // 顶部 🧰 → 全屏 overlay 卡片墙（三分类）；主动性监控卡=首批实装
    // （从设置页迁入：折叠摘要+展开审计列表，跃迁日志后端复用）。
    // 终端记录/记忆查看/家电列表=批 2；插件管理=批 3（#312）。
