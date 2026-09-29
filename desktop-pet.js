(function() {
    if (window.__xiaoju3Pet) return;
    window.__xiaoju3Pet = true;

    // 1. 注入基础样式
    const style = document.createElement('style');
    style.textContent = `
        .xiaoju-root {
            position: fixed;
            right: 0;
            bottom: 0;
            --pet-scale: 1;
            --pet-base: calc(250px * var(--pet-scale));
            width: var(--pet-base);
            height: var(--pet-base);
            pointer-events: none;
            user-select: none;
            z-index: 99999;
            transition: left .16s ease, top .16s ease, transform .3s ease;
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
        
        /* 气泡样式 */
        .xiaoju-pop {
            position: absolute;
            left: -25%;   /* 从 -45% 收到 -25%：气泡更贴近角色 */
            top: -35%;    /* 从 -60% 收到 -35%：气泡整体下移 */
            width: 100%;
            aspect-ratio: 1026/700;
            pointer-events: none;
            z-index: 1;
            --u: calc(var(--pet-base) / 1026);
        }
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
        .xiaoju-pop.pop-open svg path, .xiaoju-pop.pop-open svg ellipse {
            pointer-events: visiblePainted;
        }
        .xiaoju-pop .bshape, .xiaoju-pop .b1, .xiaoju-pop .b2 {
            opacity: 0;
            transform: scale(.7);
            transform-box: fill-box;
            transform-origin: 50% 50%;
            transition: opacity .2s ease, transform .2s ease;
        }
        .xiaoju-pop.pop-open .bshape, .xiaoju-pop.pop-open .b1, .xiaoju-pop.pop-open .b2 {
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
            color: #536ba9;
            line-height: 1.15;
            pointer-events: none;
            opacity: 0;
            transition: opacity .16s ease .36s, transform .3s ease;
        }
        .xiaoju-pop.pop-open .xiaoju-text {
            opacity: 1;
        }
        .xiaoju-text .label { font-size: calc(var(--u) * 66); font-weight: 600; letter-spacing: .06em; }
        .xiaoju-text .amount { font-size: calc(var(--u) * 128); font-weight: 800; line-height: 1.05; }
        .xiaoju-text .hint { font-size: calc(var(--u) * 56); color: #9fb0d9; letter-spacing: .02em; margin-top: calc(var(--u) * 9); }
    `;
    document.head.appendChild(style);

    // 2. 构建 DOM 结构
    const root = document.createElement('div');
    root.className = 'xiaoju-root';
    
    const img = document.createElement('img');
    img.className = 'xiaoju-img';
    img.src = '/assets/DSniang1.png'; // 👈 这里已经指向你的图片
    img.alt = '小橘3号吉祥物';
    img.draggable = false;

    // 气泡和文字
    const pop = document.createElement('div');
    pop.className = 'xiaoju-pop';
    pop.innerHTML = `
        <svg viewBox="0 0 1026 700" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
            <path class="bshape" fill="#FFFFFF" stroke="#203170" stroke-width="18" stroke-linejoin="round" stroke-linecap="round" d="M 827 248 A 373 232 0 1 0 81 246 A 373 232 0 0 0 301 465 A 57 32 10 0 0 413 484 A 373 232 0 0 0 827 248 Z"/>
            <ellipse class="b1" cx="352" cy="561" rx="37.5" ry="26" fill="#FFFFFF" stroke="#203170" stroke-width="18"/>
            <ellipse class="b2" cx="442" cy="646" rx="24.5" ry="18" fill="#FFFFFF" stroke="#203170" stroke-width="18"/>
        </svg>
        <div class="xiaoju-text">
            <div class="label">deepseek余额</div>
            <div class="amount">…</div>
            <div class="hint">正在连接...</div>
        </div>
    `;
    
    const body = document.createElement('div');
    body.className = 'xiaoju-body';
    body.appendChild(img);
    body.appendChild(pop);
    root.appendChild(body);
    document.body.appendChild(root);

    // 3. 核心交互逻辑
    let state = { scale: 1, left: 0, top: 0 };
    let drag = null;
    let isDragging = false;

    function express() {
        root.style.left = state.left + 'px';
        root.style.top = state.top + 'px';
    }

    function initPosition() {
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
    }

    function pressDown() { body.style.transform = 'scaleY(0.88) scaleX(1.05)'; }
    function pressUp() { body.style.transform = 'scaleY(1) scaleX(1)'; }

    function showBubble() {
        pop.classList.add('pop-open');
        setTimeout(() => { pop.classList.remove('pop-open'); }, 5000);
    }

        img.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        img.setPointerCapture(e.pointerId);
        const rect = root.getBoundingClientRect();
        drag = { startX: e.clientX, startY: e.clientY, origLeft: rect.left, origTop: rect.top, moved: false };
        isDragging = true;
        root.classList.add('dragging');
        pressDown();
    });

    // 🌟 拖拽移动逻辑（关键：动态判断底部边界）
    window.addEventListener('pointermove', (e) => {
        if (!drag || !isDragging) return;
        const dx = e.clientX - drag.startX;
        const dy = e.clientY - drag.startY;
        if (dx * dx + dy * dy > 9) drag.moved = true;

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
    });

    // 🌟 拖拽结束逻辑（必须恢复状态，否则会卡死）
    window.addEventListener('pointerup', () => {
        if (!drag) return;
        isDragging = false;
        root.classList.remove('dragging');
        pressUp();
        if (!drag.moved) showBubble();
        drag = null;
    });

    window.addEventListener('resize', () => {
        const rect = root.getBoundingClientRect();
        state.left = Math.min(state.left, window.innerWidth - rect.width);
        state.top = Math.min(state.top, window.innerHeight - rect.height);
        express();
    });

    // 请求后端获取真实余额
    function fetchBalance() {
        fetch('/api/balance')
            .then(res => res.json())
            .then(res => {
                if (res.code === 200) {
                    const d = res.data;
                    const amountEl = pop.querySelector('.amount');
                    const hintEl = pop.querySelector('.hint');
                    const labelEl = pop.querySelector('.label');
                    
                    if (labelEl) labelEl.textContent = 'DeepSeek余额';
                    if (amountEl) amountEl.textContent = '¥ ' + d.balance.toFixed(2);
                    if (hintEl) hintEl.textContent = '今日已用 ¥' + d.today_usage.toFixed(2);
                }
            })
            .catch(err => {
                console.error('获取余额失败，请确认后端是否在运行', err);
                const hintEl = pop.querySelector('.hint');
                if (hintEl) hintEl.textContent = '连接失败，请检查后端 5005 端口';
            });
    }

    // 先初始化一次
    initPosition();

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