(function() {
    console.log('小橘3号控制台逻辑已启动');

    // 1. 定时请求后端系统状态，更新左侧面板
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
                        cpuBar.style.backgroundColor = d.cpu > 80 ? '#e0433f' : '#2fa24c';
                    }

                    const memText = document.getElementById('mem-text');
                    const memBar = document.getElementById('mem-bar');
                    if (memText && memBar) {
                        memText.textContent = d.memory + '%';
                        memBar.style.width = d.memory + '%';
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

    // 2. 聊天发送逻辑
    window.sendMessage = function() {
        const input = document.getElementById('chat-input');
        const history = document.getElementById('chat-history');
        if (!input || !history) return;

        const text = input.value.trim();
        if (!text) return;

        const userMsg = document.createElement('div');
        userMsg.className = 'message user-message';
        userMsg.textContent = text;
        history.appendChild(userMsg);
        history.scrollTop = history.scrollHeight;
        input.value = '';

        const loadingMsg = document.createElement('div');
        loadingMsg.className = 'message bot-message';
        loadingMsg.style.color = '#9fb0d9';
        loadingMsg.textContent = '小橘3号正在思考... 🧠';
        history.appendChild(loadingMsg);
        history.scrollTop = history.scrollHeight;

        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        })
        .then(res => res.json())
                .then(res => {
            history.removeChild(loadingMsg);
            if (res.code === 200) {
                const botMsg = document.createElement('div');
                botMsg.className = 'message bot-message';
                // 👇 这里只放 HTML/SVG 结构，绝对不要把 JS 代码塞进来！
                botMsg.innerHTML = `
                    <div style="display:flex; flex-direction:column; gap:5px;">
                        <div class="bubble-content">${res.data.reply}</div>
                        <div class="msg-tools">
                            <span class="tool-btn" onclick="copyText(this)" title="复制">
                                <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                            </span>
                            <span class="tool-btn" onclick="alert('🔄 刷新功能开发中')" title="刷新">
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
                            <span class="tool-btn" onclick="alert('↗️ 转发功能开发中')" title="转发">
                                <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path><polyline points="16 6 12 2 8 6"></polyline><line x1="12" y1="2" x2="12" y2="15"></line></svg>
                            </span>
                        </div>
                    </div>
                `;
                history.appendChild(botMsg);
                history.scrollTop = history.scrollHeight;
            } else {
                throw new Error(res.error || '未知错误');
            }
        })
        .catch(err => {
            if (history.contains(loadingMsg)) history.removeChild(loadingMsg);
            const errMsg = document.createElement('div');
            errMsg.className = 'message bot-message';
            errMsg.style.color = '#e0433f';
            errMsg.textContent = '（请求失败：' + err.message + '）';
            history.appendChild(errMsg);
            history.scrollTop = history.scrollHeight;
        });
    };

    // === 3. 工具按钮的对应全局函数（这些必须写在外面，不能塞进 innerHTML！） ===

    // 复制
    window.copyText = function(el) {
        const text = el.closest('.message').querySelector('.bubble-content').innerText;
        navigator.clipboard.writeText(text).then(() => alert('✅ 已复制'));
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

})();