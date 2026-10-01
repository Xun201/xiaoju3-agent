# -*- coding: utf-8 -*-
"""系统温度真实读取 + 后台日志刷屏抑制 单元测试（全部离线，独立于 test_dashboard）。

覆盖（并行组 C 任务口径）：
- 温度三平台优先级链（get_cpu_temp）：
  ① psutil.sensors_temperatures → ② Windows wmi（MSAcpi_ThermalZoneTemperature，
  开尔文×10 → (值/10)-273.15 摄氏度）→ ③ Linux/香橙派 /sys/class/thermal/
  thermal_zone*/temp（÷1000，取第一个可解析有效值）；全失败回退字符串
  "暂无温度"（替换旧恒 0.0），数值时为 float。
  mock 口径：wmi 以假模块注入 sys.modules（缺失场景注入 None 使 import 失败）、
  /sys 用 tmp 目录文件 + glob mock、psutil 按模块属性 mock——结束全部自动还原。
- /api/status 契约：temperature 为 "暂无温度"/float 两态、tts_voice 字段下发
  （组 B 前端契约，xiaoju3.TTS_VOICE）。
- 日志刷屏抑制：
  - xiaoju3_dashboard._PollAccessFilter：/api/status、/api/balance 访问日志
    被拦截（filter 返回 False，含带查询串形态），/api/chat、/console、
    /api/history 与非访问日志（werkzeug 启动信息）保留；werkzeug logger
    已挂过滤器 + 级别 INFO 保底；经 logger 实发的端到端抑制。
  - main._HeartbeatAccessFilter：/onebot 收到 meta_event 打一次性线程标记 →
    心跳那一次访问日志被拦截、标记消费后不再误拦；/chat 与消息类记录保留；
    消息类 /onebot 不打标记。

mock 注意：全部走 mock.patch / patch.dict（结束即还原），不污染 sys.modules
与全局 logger 状态；不发任何网络/子进程请求。
"""
import io
import contextlib
import logging
import os
import sys
import tempfile
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import main  # noqa: E402  访问日志心跳过滤器与 /onebot 标记（与 test_main 同款 import）
import xiaoju3_dashboard as dashboard  # noqa: E402


@contextlib.contextmanager
def _quiet():
    """吞掉 /onebot 链路的进度 print，保持测试输出干净。"""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _make_record(msg, level=logging.INFO, name="werkzeug"):
    """构造一条与 werkzeug 访问日志同形的 LogRecord（logger 级 filter 单测用）。"""
    return logging.LogRecord(name=name, level=level, pathname=__file__,
                             lineno=1, msg=msg, args=(), exc_info=None)


def _failing_psutil():
    """模拟 Windows 上的 psutil：cpu/memory 正常，sensors 未实现（NotImplementedError）。"""
    fake = mock.Mock()
    fake.cpu_percent.return_value = 12.5
    fake.virtual_memory.return_value = mock.Mock(percent=34.5)
    fake.sensors_temperatures.side_effect = NotImplementedError(
        "sensors not supported on Windows")
    return fake


# ---------------------------------------------------------------------------
# 温度：Windows wmi（开尔文×10 → 摄氏度）
# ---------------------------------------------------------------------------

class WmiTempTests(unittest.TestCase):
    """_temp_from_wmi：延迟导入、开尔文×10 转换、异常优雅跳过。"""

    def _fake_wmi_module(self, current):
        fake_module = mock.Mock()
        zone = mock.Mock(CurrentTemperature=current)
        fake_module.WMI.return_value.MSAcpi_ThermalZoneTemperature.return_value = [zone]
        return fake_module

    def test_wmi_kelvin_tenth_to_celsius(self):
        """CurrentTemperature=3010（301.0 K）→ (3010/10)-273.15 = 27.85°C。"""
        with mock.patch.dict(sys.modules, {"wmi": self._fake_wmi_module(3010)}):
            self.assertAlmostEqual(dashboard._temp_from_wmi(), 27.85)

    def test_wmi_missing_returns_none(self):
        """wmi 未安装（sys.modules 注 None → ImportError）：返回 None 优雅跳过。"""
        with mock.patch.dict(sys.modules, {"wmi": None}):
            self.assertIsNone(dashboard._temp_from_wmi())

    def test_wmi_call_failure_returns_none(self):
        """WMI 调用异常（无传感器/权限不足）：返回 None 不抛。"""
        fake = mock.Mock()
        fake.WMI.side_effect = OSError("wmi unavailable")
        with mock.patch.dict(sys.modules, {"wmi": fake}):
            self.assertIsNone(dashboard._temp_from_wmi())

    def test_wmi_zero_current_skipped(self):
        """CurrentTemperature=0（无效读数）跳过：无其余 zone → None。"""
        with mock.patch.dict(sys.modules, {"wmi": self._fake_wmi_module(0)}):
            self.assertIsNone(dashboard._temp_from_wmi())


# ---------------------------------------------------------------------------
# 温度：Linux/香橙派 /sys/class/thermal
# ---------------------------------------------------------------------------

class SysThermalTempTests(unittest.TestCase):
    """_temp_from_sys_thermal：÷1000 换算、第一个有效值语义、无 zone 回退。"""

    def _zone_file(self, tmp, name, content):
        path = os.path.join(tmp, name, "temp")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_reads_temp_divide_1000(self):
        """temp=45820（毫摄氏度）→ 45.82°C。"""
        with tempfile.TemporaryDirectory() as tmp:
            zone = self._zone_file(tmp, "thermal_zone0", "45820\n")
            with mock.patch.object(dashboard.glob, "glob", return_value=[zone]):
                self.assertAlmostEqual(dashboard._temp_from_sys_thermal(), 45.82)

    def test_first_invalid_then_second_used(self):
        """第一个 zone 读取失败（文件消失）→ 跳过取下一个有效值。"""
        with tempfile.TemporaryDirectory() as tmp:
            good = self._zone_file(tmp, "good", "52731")
            gone = os.path.join(tmp, "gone", "temp")   # 不存在 → OSError
            with mock.patch.object(dashboard.glob, "glob",
                                   return_value=[gone, good]):
                self.assertAlmostEqual(dashboard._temp_from_sys_thermal(), 52.731)

    def test_non_numeric_value_skipped(self):
        """非数字内容（驱动未就绪）按无效值跳过。"""
        with tempfile.TemporaryDirectory() as tmp:
            bad = self._zone_file(tmp, "bad", "")
            good = self._zone_file(tmp, "good", "41000")
            with mock.patch.object(dashboard.glob, "glob",
                                   return_value=[bad, good]):
                self.assertAlmostEqual(dashboard._temp_from_sys_thermal(), 41.0)

    def test_no_thermal_zone_returns_none(self):
        """无 thermal_zone（如 Windows）：glob 空列表 → None。"""
        with mock.patch.object(dashboard.glob, "glob", return_value=[]):
            self.assertIsNone(dashboard._temp_from_sys_thermal())


# ---------------------------------------------------------------------------
# 温度：get_cpu_temp 三平台优先级链
# ---------------------------------------------------------------------------

class CpuTempChainTests(unittest.TestCase):
    """get_cpu_temp：psutil → wmi → /sys 优先级与全失败占位。"""

    def test_psutil_sensors_first_priority(self):
        """psutil sensors 可用（Linux 首选路径）→ 直接采用，后续不再探测。"""
        fake_psutil = mock.Mock()
        fake_psutil.sensors_temperatures.return_value = {
            "coretemp": [mock.Mock(current=52.3)]}
        with mock.patch.object(dashboard, "psutil", fake_psutil), \
                mock.patch.object(dashboard, "_temp_from_wmi") as m_wmi, \
                mock.patch.object(dashboard, "_temp_from_sys_thermal") as m_sys:
            self.assertAlmostEqual(dashboard.get_cpu_temp(), 52.3)
        m_wmi.assert_not_called()
        m_sys.assert_not_called()

    def test_windows_wmi_second_priority(self):
        """psutil 未实现（Windows 行为）→ wmi 读取摄氏值，/sys 不再探测。"""
        with mock.patch.object(dashboard, "psutil", _failing_psutil()), \
                mock.patch.object(dashboard, "_temp_from_wmi",
                                  return_value=27.85) as m_wmi, \
                mock.patch.object(dashboard, "_temp_from_sys_thermal") as m_sys:
            self.assertAlmostEqual(dashboard.get_cpu_temp(), 27.85)
        m_wmi.assert_called_once_with()
        m_sys.assert_not_called()

    def test_wmi_missing_falls_to_sys_thermal(self):
        """wmi 缺失（注入 None）→ Linux /sys 真实文件值（tmp 目录构造）。"""
        with tempfile.TemporaryDirectory() as tmp:
            zone = os.path.join(tmp, "thermal_zone0", "temp")
            os.makedirs(os.path.dirname(zone))
            with open(zone, "w", encoding="utf-8") as f:
                f.write("45820")
            with mock.patch.object(dashboard, "psutil", _failing_psutil()), \
                    mock.patch.dict(sys.modules, {"wmi": None}), \
                    mock.patch.object(dashboard.glob, "glob", return_value=[zone]):
                self.assertAlmostEqual(dashboard.get_cpu_temp(), 45.82)

    def test_all_fail_returns_placeholder(self):
        """全失败：返回字符串 "暂无温度"。"""
        with mock.patch.object(dashboard, "psutil", _failing_psutil()), \
                mock.patch.dict(sys.modules, {"wmi": None}), \
                mock.patch.object(dashboard.glob, "glob", return_value=[]):
            result = dashboard.get_cpu_temp()
        self.assertEqual(result, "暂无温度")
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# /api/status：温度占位 / 数值两态 + tts_voice 契约
# ---------------------------------------------------------------------------

class StatusApiTempContractTests(unittest.TestCase):
    """/api/status 温度字段与 tts_voice（组 B 前端消费）契约。"""

    def setUp(self):
        self.client = dashboard.app.test_client()

    def test_temperature_placeholder_when_all_fail(self):
        """三平台全失败：temperature == "暂无温度"，接口不 500。"""
        with mock.patch.object(dashboard, "psutil", _failing_psutil()), \
                mock.patch.dict(sys.modules, {"wmi": None}), \
                mock.patch.object(dashboard.glob, "glob", return_value=[]):
            resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["temperature"], "暂无温度")

    def test_temperature_float_when_wmi_succeeds(self):
        """Windows wmi 成功：temperature 为 float 摄氏度。"""
        fake_wmi = mock.Mock()
        zone = mock.Mock(CurrentTemperature=3010)
        fake_wmi.WMI.return_value.MSAcpi_ThermalZoneTemperature.return_value = [zone]
        with mock.patch.object(dashboard, "psutil", _failing_psutil()), \
                mock.patch.dict(sys.modules, {"wmi": fake_wmi}), \
                mock.patch.object(dashboard.glob, "glob", return_value=[]):
            data = self.client.get("/api/status").get_json()["data"]
        self.assertIsInstance(data["temperature"], float)
        self.assertAlmostEqual(data["temperature"], 27.85)

    def test_tts_voice_field_present(self):
        """/api/status 下发 tts_voice（env TTS_VOICE，组 B 前端契约）。"""
        with mock.patch.object(dashboard, "TTS_VOICE", "Google 普通话"), \
                mock.patch.object(dashboard, "psutil", _failing_psutil()), \
                mock.patch.dict(sys.modules, {"wmi": None}), \
                mock.patch.object(dashboard.glob, "glob", return_value=[]):
            data = self.client.get("/api/status").get_json()["data"]
        self.assertEqual(data["tts_voice"], "Google 普通话")


# ---------------------------------------------------------------------------
# 日志刷屏抑制：仪表盘 _PollAccessFilter
# ---------------------------------------------------------------------------

class PollAccessFilterTests(unittest.TestCase):
    """仪表盘：/api/status、/api/balance 访问日志拦截，其余照常。"""

    def _filter(self):
        return dashboard._PollAccessFilter()

    def test_status_access_log_blocked(self):
        line = '127.0.0.1 - - [01/Oct/2026 12:00:00] "GET /api/status HTTP/1.1" 200 -'
        self.assertFalse(self._filter().filter(_make_record(line)))

    def test_balance_access_log_blocked(self):
        line = '127.0.0.1 - - [01/Oct/2026 12:00:00] "GET /api/balance HTTP/1.1" 200 -'
        self.assertFalse(self._filter().filter(_make_record(line)))

    def test_query_string_still_blocked(self):
        """带查询串（前端 fetch 加时间戳等形态）同样按路径拦截。"""
        line = '127.0.0.1 - - [01/Oct/2026 12:00:00] "GET /api/status?_=1727750400 HTTP/1.1" 200 -'
        self.assertFalse(self._filter().filter(_make_record(line)))

    def test_chat_and_console_and_history_logs_kept(self):
        """/api/chat、/console、/api/history 等其余访问日志保留（filter True）。"""
        f = self._filter()
        for line in ('127.0.0.1 - - [x] "POST /api/chat HTTP/1.1" 200 -',
                     '127.0.0.1 - - [x] "GET /console HTTP/1.1" 200 -',
                     '127.0.0.1 - - [x] "GET /api/history HTTP/1.1" 200 -',
                     '127.0.0.1 - - [x] "GET /api/health HTTP/1.1" 200 -'):
            self.assertTrue(f.filter(_make_record(line)), line)

    def test_prefix_semantics_documented(self):
        """任务口径为"以 /api/status、/api/balance 开头"即 startswith 语义：
        同前缀的其它路径（如不存在的 /api/statuspage）一并拦截。"""
        f = self._filter()
        line = '127.0.0.1 - - [x] "GET /api/statuspage HTTP/1.1" 404 -'
        self.assertFalse(f.filter(_make_record(line)), line)

    def test_non_access_log_kept(self):
        """非访问日志（werkzeug 启动信息等）不误伤。"""
        f = self._filter()
        self.assertTrue(f.filter(_make_record(" * Running on http://127.0.0.1:5003")))

    def test_filter_attached_and_level_baseline(self):
        """过滤器已挂 werkzeug logger，且级别保底 INFO。"""
        wz = logging.getLogger("werkzeug")
        self.assertTrue(any(isinstance(x, dashboard._PollAccessFilter)
                            for x in wz.filters))
        self.assertEqual(wz.level, logging.INFO)

    def test_end_to_end_suppression_via_logger(self):
        """端到端：经 werkzeug logger 实发——/api/status 不达 handler，
        /api/chat 正常到达（filter 返回 False 即整条记录不再输出）。"""
        wz = logging.getLogger("werkzeug")
        records = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        capture = _Capture(level=logging.NOTSET)
        wz.addHandler(capture)
        try:
            wz.info('127.0.0.1 - - [x] "GET /api/status HTTP/1.1" 200 -')
            wz.info('127.0.0.1 - - [x] "POST /api/chat HTTP/1.1" 200 -')
        finally:
            wz.removeHandler(capture)
        self.assertEqual(len(records), 1)
        self.assertIn("/api/chat", records[0].getMessage())


# ---------------------------------------------------------------------------
# 日志刷屏抑制：main._HeartbeatAccessFilter 与 /onebot 心跳标记
# ---------------------------------------------------------------------------

class HeartbeatAccessFilterTests(unittest.TestCase):
    """main：meta_event 心跳访问日志拦截（一次性线程标记），消息类保留。"""

    def setUp(self):
        # 防御性清标记：上游用例（如 test_main 的 meta_event 用例）可能在线程
        # 上残留 is_meta_event=True（测试客户端不发访问日志、无人消费）
        self.local = main._onebot_meta_local
        self.local.__dict__.pop("is_meta_event", None)
        self.filter = main._HeartbeatAccessFilter()

    def tearDown(self):
        # mock 自动还原：清掉本线程可能残留的心跳标记
        self.local.__dict__.pop("is_meta_event", None)

    def test_meta_event_request_blocked_once(self):
        """心跳请求标记 → 访问日志拦截；标记一次性消费，后续不误拦。"""
        self.local.is_meta_event = True
        onebot_line = '127.0.0.1 - - [x] "POST /onebot HTTP/1.1" 200 -'
        self.assertFalse(self.filter.filter(_make_record(onebot_line)))
        self.assertTrue(self.filter.filter(_make_record(onebot_line)))

    def test_chat_log_kept(self):
        """/chat 访问日志保留。"""
        line = '127.0.0.1 - - [x] "POST /chat HTTP/1.1" 200 -'
        self.assertTrue(self.filter.filter(_make_record(line)))

    def test_filter_attached_and_level_baseline(self):
        """过滤器已挂 werkzeug logger，且级别保底 INFO。"""
        wz = logging.getLogger("werkzeug")
        self.assertTrue(any(isinstance(x, main._HeartbeatAccessFilter)
                            for x in wz.filters))
        self.assertEqual(wz.level, logging.INFO)

    def test_onebot_meta_event_marks_thread(self):
        """/onebot 收到 meta_event（heartbeat）：视图打线程标记并返回 ok。"""
        client = main.app.test_client()
        resp = client.post("/onebot", json={"post_type": "meta_event",
                                            "meta_event_type": "heartbeat",
                                            "self_id": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        # 标记已打（真实部署中由 werkzeug 同线程的访问日志消费拦截）
        self.assertTrue(self.local.is_meta_event)

    def test_onebot_message_event_no_mark(self):
        """/onebot 消息事件不打标记：消息类访问日志照常保留。"""
        client = main.app.test_client()
        with mock.patch.object(main, "handle_message", return_value="你好呀"), \
                mock.patch.object(main, "requests"), _quiet():
            resp = client.post("/onebot", json={"post_type": "message",
                                                "raw_message": "你好",
                                                "user_id": 123})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(getattr(self.local, "is_meta_event", None))


if __name__ == "__main__":
    unittest.main()
