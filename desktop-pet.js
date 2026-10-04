// 小橘3号 · 桌宠小挂件（IIFE 单例注入，防重复注入）
// 二阶段增强（界面文档 §5 / §6.2 / §7 / §10.4 中期项落地）：
// - 挂载真实素材 /assets/DSniang1.jpg（修复 §5.1 标注的 404 已知问题）；
//   素材自带空白思考气泡区（实测 1280×1280，气泡区中心约在图宽 36%、高 29%
//   处），文字优先绝对定位渲染在素材气泡区域内（随 --pet-scale 缩放跟随）；
//   素材加载失败时回退到内联 SVG 气泡（测试不依赖定位细节）。
// - 去白底：素材 JPG 无透明通道，注入样式以 mix-blend-mode: multiply 让
//   白底在浅色页面视觉消失（纯 CSS 零依赖；深色主题会压暗，换透明 PNG 最佳，
//   详见 assets/ASSETS.md 透明化说明）。
// - 左右翻转：面向由桌宠中心 x 相对屏幕中线决定（左半边朝右、右半边朝左，
//   始终朝向屏幕中心；吸附校正后按最终位置重算一次），scaleX(-1) 镜像
//   （翻转层与按压形变层分离，避免 transform 组合顺序冲突；文字覆盖层不翻转
//   保持可读）。
// - 边缘吸附：松手后距屏幕左/右边缘 < 24px 磁吸贴边。
// - 随机台词气泡：内置台词库与余额/今日已用轮换展示（60s 余额轮询保留）。
// - 移动端缩放：视口 <600px 时按比例缩小（复用 --pet-scale 机制）。
// - 音效：WebAudio 程序合成按压音/提示音（零外部音频文件，ASSETS.md 的
//   CC0 合规口径）；总开关 localStorage 记忆；不支持 AudioContext 静默降级。
// - 双版本状态机（2026-10-01 用户口径）：默认半身像 normal_half.png（吸附
//   右下角只露上半身），拖拽中自动切换全身像 normal_full.png，释放吸附回
//   边缘后切回半身像；任一状态图加载失败自动回退（状态图 → 半身 → 官方
//   JPG 素材 → SVG 兜底气泡），绝不出现裂图。PET_STATE_IMAGES 常量表即
//   情绪扩展接口：后续新增情绪（如 happy_full）只需补素材 + 表内登记 +
//   window.xiaoju3SetPetState('happy_full') 挂载即可。
(function() {
    if (window.__xiaoju3Pet) return;
    window.__xiaoju3Pet = { getPos: getPos };   // getPos 为 IIFE 内函数声明（提升可用），真身见 state 定义处

    // ==================== 0. 双版本状态图常量表（情绪扩展接口） ====================
    // 键 = 状态名（后续情绪按此表挂载），值 = 素材路径；素材由即梦 AI 生成
    // 的透明背景 PNG（占位阶段为官方 JPG 字节副本，浏览器按内容解析、与
    // 扩展名无关）。happy_full 为预留位：素材尚未生成，挂载前先放入
    // assets/pet/happy_full.png（未放时 setPetState 加载失败自动回退，不裂图）。
    const PET_STATE_IMAGES = {
        normal_half: '/assets/pet/normal_half.png',   // 默认：半身（吸附右下角露上半身）
        normal_full: '/assets/pet/normal_full.png',   // 拖拽中：全身
        happy_full: '/assets/pet/happy_full.png',     // 预留：开心全身（情绪扩展接口）
    };
    const PET_DEFAULT_STATE = 'normal_half';
    // 状态图全缺时的最终兜底素材（官方设定图 JPG，白底由 multiply 去除）
    const PET_FALLBACK_IMAGE = '/assets/DSniang1.jpg';

    // ==================== 音效引擎（WebAudio 程序合成，零外部音频文件） ====================
    const SOUND_KEY = 'xiaoju3_sound';
    const Sound = (function() {
        let ctx = null;
        function enabled() {
            try { return (localStorage.getItem(SOUND_KEY) || 'on') !== 'off'; }
            catch (e) { return true; }   // localStorage 不可用时默认开启
        }
        function ensureCtx() {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;        // 浏览器不支持 AudioContext：静默降级
            try {
                if (!ctx) ctx = new AC();
                if (ctx.state === 'suspended') ctx.resume().catch(() => {});
                return ctx.state === 'running' ? ctx : null;
            } catch (e) { return null; }
        }
        // 短促合成音：单振荡器 + 指数衰减包络
        function tone(freq, dur, delay, type, vol) {
            const c = ensureCtx();
            if (!c) return;
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
        }
        return {
            enabled,
            press() {                    // 按压音效：短促三角波
                if (enabled()) tone(660, 0.07, 0, 'triangle', 0.05);
            },
            ding() {                     // 回复提示音：两音上行
                if (!enabled()) return;
                tone(880, 0.10, 0, 'sine', 0.07);
                tone(1318.5, 0.16, 0.09, 'sine', 0.06);
            },
            toggle() {
                const next = enabled() ? 'off' : 'on';
                try { localStorage.setItem(SOUND_KEY, next); } catch (e) {}
                return enabled();
            },
        };
    })();
    window.xiaoju3Sound = Sound;   // 供 console.js 在回复到达时播提示音

    // ==================== 1. 注入基础样式 ====================
    const style = document.createElement('style');
    style.textContent = `
        .xiaoju-root {
            position: fixed;
            right: 0;
            bottom: 0;
            --pet-scale: 1;
            --pet-base: calc(250px * var(--pet-scale));
            --u: calc(var(--pet-base) / 1026);
            width: var(--pet-base);
            height: var(--pet-base);
            pointer-events: none;
            user-select: none;
            z-index: 99999;
            transition: left .16s ease, top .16s ease, transform .3s ease;
            /* 去白底（占位 JPG 白底 + SVG 兜底气泡白底统一处理）：multiply
               混合让白色在浅色页面视觉消失（纯 CSS 零依赖）。注意声明必须落在
               .xiaoju-root 上——fixed 定位容器自成堆叠上下文（隔离组），在内部
               元素（如 .xiaoju-img）上声明 multiply 无法穿透容器混到页面底色；
               双版本状态图换成透明背景 PNG 后 multiply 无副作用（透明像素不
               参与混合、形象原样显示），深色主题也不再压暗；占位 JPG 阶段
               深色主题会压暗，最佳效果用即梦 AI 透明背景 PNG 替换（文件名
               不变即可，详见 assets/ASSETS.md） */
            mix-blend-mode: multiply;
        }
        .xiaoju-body {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            transform-origin: 50% 100%;
            transition: transform .22s cubic-bezier(.34,1.56,.64,1);
        }
        /* 镜像翻转层：独立于按压形变层（形变在 .xiaoju-body、翻转在此层），
           两层 transform 分离互不干扰；文字覆盖层不在翻转层内，保持可读 */
        .xiaoju-flip {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            transition: transform .25s ease;
        }
        .xiaoju-root.facing-right .xiaoju-flip { transform: scaleX(-1); }
        .xiaoju-img {
            position: absolute;
            right: 0;
            bottom: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
            pointer-events: auto;
            cursor: grab;
        }
        .xiaoju-root.dragging .xiaoju-body { cursor: grabbing; }

        /* 气泡覆盖层（渲染在素材自带空白气泡区内，随 --pet-scale 缩放跟随） */
        .xiaoju-overlay {
            position: absolute;
            left: 36%;
            top: 29%;
            width: 52%;
            height: 36%;
            transform: translate(-50%, -50%);
            display: none;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            color: var(--color-text-secondary, #536ba9);
            line-height: 1.2;
            pointer-events: none;
            opacity: 0;
            transition: opacity .16s ease .2s;
            z-index: 2;
        }
        .xiaoju-root.facing-right .xiaoju-overlay { left: 64%; }  /* 镜像后气泡区在右上 */
        .xiaoju-root.img-ok .xiaoju-overlay { display: flex; }
        .xiaoju-root.img-ok .xiaoju-pop { display: none; }        /* 素材可用时隐藏 SVG 兜底气泡 */
        .xiaoju-root.pop-open .xiaoju-overlay { opacity: 1; }
        .xiaoju-overlay .label { font-size: calc(var(--u) * 52); font-weight: 600; letter-spacing: .04em; }
        .xiaoju-overlay .amount { font-size: calc(var(--u) * 92); font-weight: 800; line-height: 1.05; }
        .xiaoju-overlay .line { font-size: calc(var(--u) * 60); font-weight: 600; }
        .xiaoju-overlay .hint { font-size: calc(var(--u) * 46); color: var(--color-text-hint, #9fb0d9); margin-top: calc(var(--u) * 6); }
        /* 空槽位不占位 */
        .xiaoju-overlay .label:empty, .xiaoju-overlay .amount:empty,
        .xiaoju-overlay .line:empty, .xiaoju-overlay .hint:empty,
        .xiaoju-text .label:empty, .xiaoju-text .amount:empty,
        .xiaoju-text .line:empty, .xiaoju-text .hint:empty { display: none; }

        /* SVG 兜底气泡（素材缺失时回退使用） */
        .xiaoju-pop {
            position: absolute;
            left: -25%;   /* 从 -45% 收到 -25%：气泡更贴近角色 */
            top: -35%;    /* 从 -60% 收到 -35%：气泡整体下移 */
            width: 100%;
            aspect-ratio: 1026/700;
            pointer-events: none;
            z-index: 1;
        }
        .xiaoju-root.facing-right .xiaoju-pop { left: auto; right: -25%; }
        .xiaoju-pop svg {
            display: block;
            width: 100%;
            height: 100%;
            pointer-events: none;
        }
        .xiaoju-pop svg path, .xiaoju-pop svg ellipse {
            pointer-events: none;
            cursor: pointer;
        }
        .xiaoju-root.pop-open svg path, .xiaoju-root.pop-open svg ellipse {
            pointer-events: visiblePainted;
        }
        .xiaoju-pop .bshape, .xiaoju-pop .b1, .xiaoju-pop .b2 {
            opacity: 0;
            transform: scale(.7);
            transform-box: fill-box;
            transform-origin: 50% 50%;
            transition: opacity .2s ease, transform .2s ease;
        }
        .xiaoju-root.pop-open .bshape, .xiaoju-root.pop-open .b1, .xiaoju-root.pop-open .b2 {
            opacity: 1;
            transform: none;
        }
        .xiaoju-text {
            position: absolute;
            left: 44.25%;
            top: 36%;
            width: 66%;
            height: 64%;
            transform: translate(-50%, -50%);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            color: var(--color-text-secondary, #536ba9);
            line-height: 1.15;
            pointer-events: none;
            opacity: 0;
            transition: opacity .16s ease .36s, transform .3s ease;
        }
        .xiaoju-root.pop-open .xiaoju-text {
            opacity: 1;
        }
        .xiaoju-text .label { font-size: calc(var(--u) * 66); font-weight: 600; letter-spacing: .06em; }
        .xiaoju-text .amount { font-size: calc(var(--u) * 128); font-weight: 800; line-height: 1.05; }
        .xiaoju-text .line { font-size: calc(var(--u) * 72); font-weight: 600; }
        .xiaoju-text .hint { font-size: calc(var(--u) * 56); color: var(--color-text-hint, #9fb0d9); letter-spacing: .02em; margin-top: calc(var(--u) * 9); }
    `;
    document.head.appendChild(style);

    // ==================== 2. 构建 DOM 结构 ====================
    const root = document.createElement('div');
    root.className = 'xiaoju-root';

    const body = document.createElement('div');
    body.className = 'xiaoju-body';

    // 翻转层包裹形象图（scaleX(-1) 只作用于形象，不翻转文字覆盖层）
    const flipBox = document.createElement('div');
    flipBox.className = 'xiaoju-flip';

    const img = document.createElement('img');
    img.className = 'xiaoju-img';
    img.src = PET_STATE_IMAGES[PET_DEFAULT_STATE]; // 默认半身像（吸附右下角只露上半身）
    img.alt = '小橘3号吉祥物';
    img.draggable = false;
    flipBox.appendChild(img);

    // 素材气泡覆盖层（与 SVG 兜底气泡同构：label/amount/line/hint 四槽位）
    const overlay = document.createElement('div');
    overlay.className = 'xiaoju-overlay';
    overlay.innerHTML = `
        <div class="label"></div>
        <div class="amount"></div>
        <div class="line"></div>
        <div class="hint"></div>
    `;

    // SVG 兜底气泡（素材加载失败时回退）
    // 去白底：气泡填充由白色改为透明（fill="transparent"），页面底色自然透出，
    // 与形象图 multiply 去白底口径一致；描边保留维持气泡轮廓
    const pop = document.createElement('div');
    pop.className = 'xiaoju-pop';
    pop.innerHTML = `
        <svg viewBox="0 0 1026 700" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
            <path class="bshape" fill="transparent" stroke="#203170" stroke-width="18" stroke-linejoin="round" stroke-linecap="round" d="M 827 248 A 373 232 0 1 0 81 246 A 373 232 0 0 0 301 465 A 57 32 10 0 0 413 484 A 373 232 0 0 0 827 248 Z"/>
            <ellipse class="b1" cx="352" cy="561" rx="37.5" ry="26" fill="transparent" stroke="#203170" stroke-width="18"/>
            <ellipse class="b2" cx="442" cy="646" rx="24.5" ry="18" fill="transparent" stroke="#203170" stroke-width="18"/>
        </svg>
        <div class="xiaoju-text">
            <div class="label">deepseek余额</div>
            <div class="amount">…</div>
            <div class="line"></div>
            <div class="hint">正在连接...</div>
        </div>
    `;

    body.appendChild(flipBox);
    body.appendChild(overlay);
    body.appendChild(pop);
    root.appendChild(body);
    document.body.appendChild(root);

    // 素材可用性：加载成功 → 覆盖层模式；失败（404/断网）→ SVG 兜底气泡
    function refreshImgMode() {
        if (img.complete && img.naturalWidth > 0) root.classList.add('img-ok');
        else root.classList.remove('img-ok');
    }

    // ==================== 双版本状态机（half 默认 / 拖拽 full / 吸附回 half） ====================
    let petState = PET_DEFAULT_STATE;
    const failedStateUrls = new Set();   // 已加载失败的状态图 URL（防 onerror 死循环/裂图）

    // 状态切换（情绪扩展挂载点）：按 PET_STATE_IMAGES 常量表换 src；未登记
    // 的状态名拒绝；登记过但曾加载失败的 URL 不再重复请求（保持当前兜底图）
    function setPetState(next) {
        const url = PET_STATE_IMAGES[next];
        if (!url) return false;                            // 未登记状态：拒绝
        petState = next;
        root.dataset.petState = next;                      // 供后续按状态挂 CSS（半身/全身尺寸差异）
        if (failedStateUrls.has(url)) return false;        // 曾加载失败：保持兜底图
        if (img.getAttribute('src') !== url) img.src = url; // 同图不重复触发加载
        return true;
    }
    // 情绪扩展接口（对外只读挂载）：后续 happy_full 等情绪由外部按表调用
    window.xiaoju3SetPetState = setPetState;

    // 读取失败自动回退链（绝不裂图）：当前非半身 → 退半身；半身也失败 →
    // 兜底官方 JPG；JPG 仍失败 → refreshImgMode 移除 img-ok，SVG 兜底气泡接管
    img.addEventListener('error', () => {
        failedStateUrls.add(img.getAttribute('src'));
        if (petState !== 'normal_half' &&
            !failedStateUrls.has(PET_STATE_IMAGES.normal_half)) {
            setPetState('normal_half');                    // ① 状态图缺失：回退半身
            return;
        }
        if (img.getAttribute('src') !== PET_FALLBACK_IMAGE &&
            !failedStateUrls.has(PET_FALLBACK_IMAGE)) {
            img.src = PET_FALLBACK_IMAGE;                  // ② 半身也缺：官方 JPG 兜底
            return;
        }
        refreshImgMode();                                  // ③ 全缺：SVG 兜底气泡
    });
    img.addEventListener('load', () => { refreshImgMode(); initPosition(); });
    refreshImgMode();

    // ==================== 3. 核心交互逻辑 ====================
    let state = { scale: 1, left: 0, top: 0 };
    let positionInitialized = false;   // 出生位只定一次：换图 load 不再重置坐标（拖拽回弹修复）
    let drag = null;
    let isDragging = false;
    let facing = 'left';   // 素材原始朝向：角色面朝左侧气泡区；面向由位置相对屏幕中线决定

    function express() {
        root.style.left = state.left + 'px';
        root.style.top = state.top + 'px';
    }

    // 坐标接口（PET_BALL_FIX_DESIGN §3）：加速球定位的真源——state 即逻辑
    // 坐标（style.left/top 是其投影），w/h 取当前渲染尺寸（缺省兜底 250）
    function getPos() {
        const rect = root.getBoundingClientRect();
        return {
            x: state.left,
            y: state.top,
            w: rect.width || 250,
            h: rect.height || 250,
        };
    }

    function applyFacing() {
        root.classList.toggle('facing-right', facing === 'right');
    }

    // 翻转判定（修复拖到屏幕右侧吸附时翻错方向）：面向由桌宠中心 x 相对
    // 屏幕中线决定——左半边朝右、右半边朝左，始终朝向屏幕中心，与拖拽
    // 位移方向无关；吸附校正可能改变最终位置，松手后按最终位置再重算一次
    // （见 pointerup）。用逻辑坐标 state.left 判定（left 有 .16s 过渡，
    // rect.left 会滞后于目标位置）。
    function updateFacingByPosition() {
        const rect = root.getBoundingClientRect();
        const centerX = state.left + rect.width / 2;
        const midLine = window.innerWidth / 2;   // 屏幕中线
        facing = centerX < midLine ? 'right' : 'left';
        applyFacing();
    }

    // 移动端缩放（界面 §7 规划落地）：视口 <600px 时按视口比例缩小（复用 --pet-scale）
    function applyPetScale() {
        const vw = window.innerWidth || document.documentElement.clientWidth;
        const scale = vw < 600 ? Math.max(0.5, Math.min(1, vw / 600)) : 1;
        root.style.setProperty('--pet-scale', scale.toFixed(2));
    }

    function initPosition() {
        // 隐藏态（桌宠缩球）早退守卫：display:none 下 getBoundingClientRect
        // 全 0，会把垃圾坐标写进 state 导致恢复后跳位（PET_BALL_FIX_DESIGN §3）。
        // 判据用 getComputedStyle——root 是 position:fixed，offsetParent 恒为
        // null（与可见性无关），不能用
        if (getComputedStyle(root).display === 'none') return;
        // 出生位只定一次守卫：换图（拖拽切全身像 / 松手切回半身像）会重放
        // img load——无此守卫每次 load 都会把桌宠重置回出生位（拖拽回弹
        // bug 根因）。隐藏态守卫在先：隐藏态不初始化也不置位，下次可见时
        // （load）才能初始化
        if (positionInitialized) return;
        applyPetScale();
        const rect = root.getBoundingClientRect();
        const petWidth = rect.width || 250;
        const petHeight = rect.height || 250;

        // 出生位置：右下角，输入框正上方
        // 1) 水平：贴屏幕右边
        state.left = window.innerWidth - petWidth;

        // 2) 垂直：底边停在输入框上方（不留空隙）
        let limitBottom = window.innerHeight;
        const inputArea = document.querySelector('.chat-input-area');
        if (inputArea) {
            limitBottom = inputArea.getBoundingClientRect().top;
        }
        state.top = Math.max(0, limitBottom - petHeight);

        express();
        // 出生/校准位置后按位置定面向（默认出生右下角 → 朝左即朝向屏幕中心）
        updateFacingByPosition();
        positionInitialized = true;   // 成功定位后置位：后续换图 load 只刷渲染模式，不再动坐标
        captureViewport();            // 出生位即视口记忆基线（resize 锚点对比用）
    }

    function pressDown() { body.style.transform = 'scaleY(0.88) scaleX(1.05)'; }
    function pressUp() { body.style.transform = 'scaleY(1) scaleX(1)'; }

    // ==================== 气泡内容（余额 / 今日已用 / 随机台词轮换） ====================
    let lastBalance = null;   // 最近一次 /api/balance 数据缓存
    let bubbleView = 'balance';
    let bubbleTurn = 0;       // 轮换计数：偶数次余额/今日已用，奇数次随机台词
    let popTimer = null;

    // 覆盖层与 SVG 兜底气泡同构同步填充
    function fillBubble(label, amount, line, hint) {
        root.querySelectorAll('.xiaoju-text, .xiaoju-overlay').forEach(box => {
            box.querySelector('.label').textContent = label;
            box.querySelector('.amount').textContent = amount;
            box.querySelector('.line').textContent = line;
            box.querySelector('.hint').textContent = hint;
        });
    }

    function updateBalanceBubble() {
        if (lastBalance) {
            const d = lastBalance;
            fillBubble('DeepSeek余额', '¥ ' + d.balance.toFixed(2), '',
                       '今日已用 ¥' + d.today_usage.toFixed(2));
        } else {
            fillBubble('DeepSeek余额', '…', '', '正在连接...');
        }
    }

    // 随机台词库（界面 §5.3 / §10.2 规划落地）：与余额/今日已用轮换展示
    const PET_LINES = [
        '今天也要元气满满哦~',
        '主人，记得多喝水呀',
        '服务器一切正常喵！',
        'CPU 和内存都在小橘的守护之下',
        '戳我一下，告诉你余额~',
        '可以拖着我放到喜欢的地方',
        '有什么想让我做的，尽管说！',
        '别担心，小橘一直都在',
        '今天想吃什么呀？',
        '夜深了，早点休息哦',
    ];

    function showBubble() {
        if (bubbleTurn % 2 === 1) {
            const line = PET_LINES[Math.floor(Math.random() * PET_LINES.length)];
            fillBubble('', '', line, '');
            bubbleView = 'line';
        } else {
            updateBalanceBubble();
            bubbleView = 'balance';
        }
        bubbleTurn++;
        root.classList.add('pop-open');
        clearTimeout(popTimer);
        popTimer = setTimeout(() => { root.classList.remove('pop-open'); }, 5000);
    }

    img.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        img.setPointerCapture(e.pointerId);
        const rect = root.getBoundingClientRect();
        drag = { startX: e.clientX, startY: e.clientY, origLeft: rect.left, origTop: rect.top, moved: false };
        isDragging = true;
        root.classList.add('dragging');
        pressDown();
        Sound.press();   // 按压音效（界面 §6.2 / §9.1：指针按下播按压音）
    });

    // 🌟 拖拽移动逻辑（关键：动态判断底部边界）
    window.addEventListener('pointermove', (e) => {
        if (!drag || !isDragging) return;
        const dx = e.clientX - drag.startX;
        const dy = e.clientY - drag.startY;
        if (dx * dx + dy * dy > 9) {
            drag.moved = true;
            // 拖拽中：切换全身像（超过拖拽阈值才算真拖拽，点击不换装）
            if (petState !== 'normal_full') setPetState('normal_full');
        }

        state.left = drag.origLeft + dx;
        state.top = drag.origTop + dy;

        const rect = root.getBoundingClientRect();

        // 左边界：聊天区域左边缘
        let limitLeft = 0;
        const chatArea = document.querySelector('.chat-area');
        if (chatArea) {
            limitLeft = chatArea.getBoundingClientRect().left;
        }

        // 下边界：紧贴输入框上沿
        let limitBottom = window.innerHeight;
        const inputArea = document.querySelector('.chat-input-area');
        if (inputArea) {
            limitBottom = inputArea.getBoundingClientRect().top;
        }

        state.left = Math.max(limitLeft, Math.min(state.left, window.innerWidth - rect.width));
        state.top = Math.max(0, Math.min(state.top, limitBottom - rect.height));

        express();
        // 拖拽中实时按当前位置更新面向（相对屏幕中线，跨中线即翻转）
        updateFacingByPosition();
    });

    // 🌟 边缘吸附（界面 §5.2 规划落地）：松手后距屏幕左/右边缘 < 24px 磁吸贴边
    const SNAP_THRESHOLD = 24;
    function snapToEdge() {
        const rect = root.getBoundingClientRect();
        let limitLeft = 0;
        const chatArea = document.querySelector('.chat-area');
        if (chatArea) limitLeft = chatArea.getBoundingClientRect().left;
        const rightLimit = window.innerWidth - rect.width;

        if (state.left - limitLeft < SNAP_THRESHOLD) {
            state.left = limitLeft;      // 吸附至有效左界（无聊天区钳制时即屏幕左缘）
        } else if (rightLimit - state.left < SNAP_THRESHOLD) {
            state.left = rightLimit;     // 吸附至屏幕右缘
        }
        express();
    }

    // 🌟 拖拽结束逻辑（必须恢复状态，否则会卡死）
    window.addEventListener('pointerup', (e) => {
        if (!drag) return;
        isDragging = false;
        root.classList.remove('dragging');
        pressUp();
        if (!drag.moved) {
            showBubble();
        } else {
            snapToEdge();
            // 吸附校正可能改变最终位置：按最终位置重算一次面向（朝向屏幕中心）
            updateFacingByPosition();
        }
        // 释放并吸附到边缘后：切回默认半身像（未离身则同图跳过；状态图缺失
        // 时 setPetState 内部保持兜底图，不裂图）
        if (petState !== 'normal_half') setPetState('normal_half');
        drag = null;
    });

    // ==================== 窗口缩放几何（2026-10-04 尾巴 3+4 重写） ====================
    // 视口记忆：resize 前后对比基准——右/下贴边锚点需要"旧窗下"的距离；
    // initPosition 与本处理器末尾各 capture 一次。
    let lastViewport = { w: window.innerWidth, h: window.innerHeight, inputTop: null };

    function captureViewport() {
        const inputArea = document.querySelector('.chat-input-area');
        lastViewport = {
            w: window.innerWidth,
            h: window.innerHeight,
            inputTop: inputArea ? inputArea.getBoundingClientRect().top : null,
        };
    }

    window.addEventListener('resize', () => {
        // 缩球态守卫：display:none 下 rect 全 0，会把垃圾坐标写进 state
        // （与 initPosition 守卫同口径）
        if (getComputedStyle(root).display === 'none') {
            captureViewport();
            return;
        }
        applyPetScale();
        const rect = root.getBoundingClientRect();

        // 旧窗基准下的右/下缘距离（底界含输入框上沿——与拖拽/出生位同口径）
        const oldLimitBottom = lastViewport.inputTop !== null
            ? Math.min(lastViewport.h, lastViewport.inputTop)
            : lastViewport.h;
        const distRight = lastViewport.w - (state.left + rect.width);
        const distBottom = oldLimitBottom - (state.top + rect.height);

        // 新窗可用域：底界取输入框上沿（尾巴 A 根因即旧代码此处漏算输入框，
        // 缩窗后桌宠被 window.innerHeight 收钳压进发送条）
        let limitBottom = window.innerHeight;
        const inputArea = document.querySelector('.chat-input-area');
        if (inputArea) limitBottom = inputArea.getBoundingClientRect().top;
        let limitLeft = 0;
        const chatArea = document.querySelector('.chat-area');
        if (chatArea) limitLeft = chatArea.getBoundingClientRect().left;
        const maxX = window.innerWidth - rect.width;
        const maxY = limitBottom - rect.height;

        // 右/下贴边锚点跟随（尾巴 B）：缩窗时贴着右/下边的桌宠，放大窗口后
        // 保持贴边——旧代码只做 Math.min 收钳，放大后旧坐标原样保留，桌宠
        // 滞留"中间"（ε=2px 容差判定"贴边"，吸附后的贴边距恒 0）
        const ANCHOR_EPSILON = 2;
        state.left = (distRight <= ANCHOR_EPSILON) ? maxX
            : Math.max(limitLeft, Math.min(state.left, maxX));
        state.top = (distBottom <= ANCHOR_EPSILON) ? maxY
            : Math.max(0, Math.min(state.top, maxY));

        express();
        updateFacingByPosition();   // 窗口剧变可能导致所在半区变化，按新位置重算
        captureViewport();
    });

    // 请求后端获取真实余额（余额 + 今日已用）
    function fetchBalance() {
        fetch('/api/balance')
            .then(res => res.json())
            .then(res => {
                if (res.code === 200 && res.data) {
                    lastBalance = res.data;
                    // 气泡正开着且处于台词视图时不打断展示
                    if (!root.classList.contains('pop-open') || bubbleView === 'balance') {
                        updateBalanceBubble();
                    }
                } else {
                    // 无 KEY / 后端返回错误结构：给出失败提示
                    if (!root.classList.contains('pop-open') || bubbleView === 'balance') {
                        fillBubble('DeepSeek余额', '…', '', '连接失败，请检查后端 5003 端口');
                    }
                }
            })
            .catch(err => {
                console.error('获取余额失败，请确认后端是否在运行', err);
                if (!root.classList.contains('pop-open') || bubbleView === 'balance') {
                    fillBubble('DeepSeek余额', '…', '', '连接失败，请检查后端 5003 端口');
                }
            });
    }

    // 先初始化一次
    initPosition();
    updateBalanceBubble();

    // 等页面完全加载后再校准一次（防止输入框还没渲染）
    window.addEventListener('load', initPosition);
    // 图片加载完后也校准一次（防止尺寸不对）
    img.addEventListener('load', initPosition);
    // 再兜底延迟 300ms 重试一次
    setTimeout(initPosition, 300);

    // 启动时请求一次，之后每 60 秒请求一次
    fetchBalance();
    setInterval(fetchBalance, 60000);
    console.log('小橘3号桌宠已启动！');
})();
