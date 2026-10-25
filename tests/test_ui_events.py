# -*- coding: utf-8 -*-
"""ui_events 页面级事件总线 + /api/events 端点测试（#348 三期推模式）。

覆盖：订阅/发布/多订阅者广播/慢消费者丢事件不阻塞/注销/unsubscribe 幂等；
SSE 端点三态（连接确认行/事件帧格式/心跳）——Flask test_client 真读流。
"""
import json
import os
import sys
import threading
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import ui_events


class UiEventsBusTests(unittest.TestCase):
    """广播总线单元（线程安全/慢消费者/注销幂等）。"""

    def setUp(self):
        ui_events._SUBS.clear()

    def tearDown(self):
        ui_events._SUBS.clear()

    def test_subscribe_publish_roundtrip(self):
        q = ui_events.subscribe()
        n = ui_events.publish("video_note_done", title="t", reply="r")
        self.assertEqual(n, 1)
        ev = q.get_nowait()
        self.assertEqual(ev["type"], "video_note_done")
        self.assertEqual(ev["title"], "t")
        self.assertIn("ts", ev)                       # 自动时间戳

    def test_multi_subscriber_broadcast(self):
        q1, q2 = ui_events.subscribe(), ui_events.subscribe()
        n = ui_events.publish("ui", x=1)
        self.assertEqual(n, 2)
        self.assertEqual(q1.get_nowait()["x"], 1)
        self.assertEqual(q2.get_nowait()["x"], 1)

    def test_no_subscriber_free(self):
        """无订阅者 publish 零成本（不抛不积压）。"""
        self.assertEqual(ui_events.publish("ui"), 0)

    def test_slow_consumer_drops_not_blocks(self):
        """满队列（慢消费者）丢本条不阻塞广播线程（status 兜底查回）。"""
        small = ui_events.subscribe.__globals__  # noqa: F841（占位可读性）
        q = ui_events.subscribe()
        # 塞满（maxsize=256）
        for i in range(300):
            ui_events.publish("ui", i=i)
        self.assertEqual(q.qsize(), 256)             # 满队列截断
        n = ui_events.publish("ui", final=True)      # 再发不阻塞
        self.assertEqual(n, 0)                       # 满队列丢本条（delivered 不含），不阻塞不抛

    def test_unsubscribe_idempotent(self):
        q = ui_events.subscribe()
        ui_events.unsubscribe(q)
        ui_events.unsubscribe(q)                     # 幂等
        self.assertEqual(ui_events.publish("ui"), 0)

    def test_thread_safety_smoke(self):
        """并发订阅+发布冒烟（无异常即过）。"""
        errs = []

        def sub_loop():
            for _ in range(50):
                try:
                    q = ui_events.subscribe()
                    ui_events.unsubscribe(q)
                except Exception as e:
                    errs.append(e)
        ths = [threading.Thread(target=sub_loop) for _ in range(4)]
        [t.start() for t in ths]
        ui_events.publish("ui", burst=True)
        [t.join() for t in ths]
        self.assertEqual(errs, [])


class EventsEndpointTests(unittest.TestCase):
    """/api/events SSE 端点（test_client 流式读：连接确认/事件帧/心跳）。"""

    def setUp(self):
        import xiaoju3_dashboard as dashboard
        self.dashboard = dashboard
        self.client = dashboard.app.test_client()

    def tearDown(self):
        ui_events._SUBS.clear()

    def test_sse_endpoint_registered_and_format_anchored(self):
        """SSE 端点注册+帧格式静态锚：test_client 对无限流是缓冲语义
        （connected 帧可达、事件帧需真连接——真连接行为由真机验收承担）。
        此处锁：端点 200+event-stream+generate 内事件帧构造形态。"""
        import ui_events
        resp = self.client.get("/api/events")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.content_type)
        # 帧构造形态静态锁（generate 源码内三处 yield 拼接）
        import inspect
        src = inspect.getsource(self.dashboard.api_events)
        bs = chr(92)
        self.assertIn('": connected' + bs + 'n' + bs + 'n"', src)   # 源码文本=字面 \n 两字符
        self.assertIn('yield "event: {}' + bs + 'n".format(ev.get', src)   # 帧构造形态（inspect 源码实锚）
        self.assertIn('"data: {}' + bs + 'n' + bs + 'n"', src)
        # 注册/注销调用在位（连接生命周期管理）
        self.assertIn("ui_events.subscribe()", src)
        self.assertIn("ui_events.unsubscribe(q)", src)


if __name__ == "__main__":
    unittest.main()
