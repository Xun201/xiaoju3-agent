# -*- coding: utf-8 -*-
"""ui_events · 页面级 UI 事件广播总线（#348 三期推模式，2026-10-25）。

**架构定位**：与请求级 SSE（/api/chat/stream，发完即关）正交的**页面级**
常驻事件通道——后台任务（插件转写等）完成后经 publish() 广播，所有打开
控制台的页面经 /api/events SSE 长连接实时收到并渲染新气泡。

**与现有机制零冲突**（评估结论）：
- 请求级 SSE 看门狗（190s AbortController）只管发送链，不碰本连接；
- ThreadingWSGIServer 每连接一线程，events 长连接 daemon 常驻无害；
- 插件后台线程 publish → queue.put 线程安全（每订阅者独立 Queue）。

**用法**：
    后端任务：from ui_events import publish; publish("video_note_done", {...})
    dashboard：/api/events SSE 端点订阅（generator 消费 subscribe 队列）
    前端：EventSource("/api/events") 收事件渲染新气泡
"""
import queue
import threading
import time

# 订阅者队列集合（每个 /api/events 连接一个）；线程安全：_SUBS_LOCK 保护
_SUBS = set()
_SUBS_LOCK = threading.Lock()


def subscribe():
    """注册订阅者：返回独立 Queue（断开时 unsubscribe）。"""
    q = queue.Queue(maxsize=256)
    with _SUBS_LOCK:
        _SUBS.add(q)
    return q


def unsubscribe(q):
    """注销订阅者（连接断开/页面刷新时）。"""
    with _SUBS_LOCK:
        _SUBS.discard(q)


def publish(event_type, **payload):
    """广播事件到全部订阅者（无订阅者=静默丢弃零成本）。

    payload 自动附 ts（服务端时间戳）。满队列丢该订阅者本条（慢消费者
    不拖累广播线程——转写结果可经 status 兜底查回，丢推送不丢数据）。"""
    payload = dict(payload or {})
    payload["type"] = event_type
    payload["ts"] = time.time()
    with _SUBS_LOCK:
        subs = list(_SUBS)
    delivered = 0
    for q in subs:
        try:
            q.put_nowait(payload)
            delivered += 1
        except queue.Full:
            pass   # 慢消费者：丢事件不阻塞（status 兜底可查回）
    return delivered


def subscriber_count():
    """当前订阅者数（诊断）。"""
    with _SUBS_LOCK:
        return len(_SUBS)
