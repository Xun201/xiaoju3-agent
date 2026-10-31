/* =========================================================
 * xj3_network_core.js — 小橘3号 双端共享网络核心（唯一实现）
 * 队长红线（2026-10-31）：纯网络通信+流式解析只写一次——桌面 console.js 与
 * 移动端 mobile.js 都经 <script> 引入本文件，杜绝人肉拷贝漂移（防双端 Bug 不同步）。
 * 本文件零 DOM 依赖：只做 探活/流式编排/帧解析/看门狗，渲染全部留在调用方回调。
 *
 * 溯源：编排逻辑拷贝自 console.js@7897bbc sendMessageStream（L5042-5278）与
 * probeBase（L2687），提取为纯网络形态；提取后由桌面真链路 E2E 回归护航。
 * 同步清单：_dev/mobile_sync_checklist.md（本文件=唯一实现，清单降级为"谁在消费"）。
 * ========================================================= */
(function () {
    'use strict';

    var XJ3Net = {};

    /* ---------- 探活（桌面/移动共用；默认 5s 超时，可传 timeoutMs） ---------- */
    XJ3Net.probeBase = function (base, timeoutMs) {
        var ctl = new AbortController();
        var timer = setTimeout(function () { ctl.abort(); }, timeoutMs || 5000);
        return fetch((base || '') + '/api/health', { signal: ctl.signal })
            .then(function (r) { return r.json(); })
            .then(function (j) { return !!(j && j.status === 'ok'); })
            .catch(function () { return false; })
            .finally(function () { clearTimeout(timer); });
    };

    /* ---------- 流式对话编排 ----------
     * opts = {
     *   message: string                     用户消息原文
     *   base: ''|url                        API 前缀（同源传 ''）
     *   aborter: AbortController|null       调用方-owned 总闸（桌面排队条"立即执行"
     *                                       经 __xj3Abort.abort() 中断；看门狗也走它）
     *   onFrame: fn(etype, data)            每帧回调（think/tool/answer/done/error）
     * }
     * 返回 Promise：流干净结束 → resolve({ok:true})；
     *              失败 → reject(Error)，看门狗触发时 err.xj3Watchdog=true。
     * 看门狗口径（桌面同款）：首帧 30s / 帧间 90s（每帧喂狗）/ 总闸 190s。
     * 帧解析：按 \n\n 切帧 → event:/data: 行 → JSON.parse（坏帧抛错=调用方处置）。 */
    XJ3Net.chatStream = function (opts) {
        return new Promise(function (resolve, reject) {
            var watchdogFired = false;
            var aborter = opts.aborter || new AbortController();
            var firstTimer = setTimeout(function () { fireWatchdog(); }, 30000);
            var frameTimer = firstTimer;
            var totalTimer = setTimeout(function () { fireWatchdog(); }, 190000);

            function fireWatchdog() {
                watchdogFired = true;
                try { aborter.abort(); } catch (e) { /* 已中断 */ }
            }
            function pat() {
                clearTimeout(frameTimer);
                frameTimer = setTimeout(function () { fireWatchdog(); }, 90000);
            }
            function clearAll() {
                clearTimeout(firstTimer);
                clearTimeout(frameTimer);
                clearTimeout(totalTimer);
            }

            fetch((opts.base || '') + '/api/chat/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: opts.message }),
                signal: aborter.signal
            }).then(function (res) {
                if (!res.ok || !res.body) {
                    throw new Error('stream unavailable');
                }
                var reader = res.body.getReader();
                var decoder = new TextDecoder();
                var buf = '';

                function pump() {
                    return reader.read().then(function (chunk) {
                        if (chunk.done) {
                            clearAll();
                            resolve({ ok: true });
                            return;
                        }
                        buf += decoder.decode(chunk.value, { stream: true });
                        var idx;
                        while ((idx = buf.indexOf('\n\n')) !== -1) {
                            var frame = buf.slice(0, idx);
                            buf = buf.slice(idx + 2);
                            var etype = 'message';
                            var payload = '';
                            frame.split('\n').forEach(function (l) {
                                if (l.indexOf('event:') === 0) { etype = l.slice(6).trim(); }
                                else if (l.indexOf('data:') === 0) { payload += l.slice(5).trim(); }
                            });
                            if (!payload) { continue; }
                            pat();
                            opts.onFrame(etype, JSON.parse(payload));
                        }
                        return pump();
                    });
                }
                return pump();
            }).catch(function (err) {
                clearAll();
                var e = (err instanceof Error) ? err : new Error(String(err));
                if (watchdogFired) { e.xj3Watchdog = true; }
                reject(e);
            });
        });
    };

    window.XJ3Net = XJ3Net;
    /* 桩环境（node 烟雾/非浏览器宿主）兜底：window 与全局对象可能不是
     * 同一对象——裸标识符 XJ3Net 必须可达（console.js 裸引用） */
    if (typeof globalThis !== 'undefined') {
        try { globalThis.XJ3Net = XJ3Net; } catch (e) { /* 忽略 */ }
    }
})();
