# -*- coding: utf-8 -*-
"""#319 批 3-a 锚（design_319_batch3_impl.md §五）：Pi 接收器薄壳/双端闭环/
部署物完整性。全 tmp 卷沙盒+子进程真 HTTP，零碰生产。"""
import base64
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import zipfile

import migration
import soul_sync


def _make_src_bundle(src_dir):
    """沙盒分身：核档三件→core-only 包，返回 zip bytes。"""
    for name in ("identity.json", "ui_pref.json"):
        with open(os.path.join(src_dir, name), "w", encoding="utf-8") as f:
            f.write('{"v":1}')
    con = sqlite3.connect(os.path.join(src_dir, "relationship.db"))
    con.execute("CREATE TABLE IF NOT EXISTS sample(id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    r = soul_sync.make_writeback_bundle(
        path=os.path.join(src_dir, "wb.zip"), base_dir=src_dir)
    with open(r["path"], "rb") as f:
        return f.read()


class ReceiverShellTests(unittest.TestCase):
    """receiver 薄壳（Flask test_client，tmp 卷注入）。"""

    def setUp(self):
        from unittest import mock
        import soul_core_receiver as recv
        self.recv = recv
        self.core = tempfile.mkdtemp(prefix="xj3_recv_")
        self.token = "recv-token-1"
        self._env = mock.patch.dict(os.environ, {
            "XIAOJU3_SOUL_TOKEN": self.token,
            "XIAOJU3_SOUL_CORE_BASE": self.core,
        })
        self._env.start()
        self.addCleanup(self._env.stop)
        self.client = recv.app.test_client()
        self.src = tempfile.mkdtemp(prefix="xj3_recvsrc_")
        self.bundle = _make_src_bundle(self.src)

    def test_health_blueprint_mounted(self):
        """/api/health 200（migration.health_bp 复用，PeerWatch 探测同源）。"""
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")

    def test_401_auth(self):
        self.assertEqual(self.client.post(
            "/api/soul/writeback", json={}).status_code, 401)
        self.assertEqual(self.client.post(
            "/api/soul/writeback", json={"bundle": "x"},
            headers={"X-Soul-Token": "wrong"}).status_code, 401)

    def test_202_apply_and_audit(self):
        r = self.client.post("/api/soul/writeback",
                             json={"device_id": "dev-b3", "bundle":
                                   base64.b64encode(self.bundle).decode()},
                             headers={"X-Soul-Token": self.token})
        self.assertEqual(r.status_code, 202)
        self.assertTrue(r.get_json()["ack"])
        con = sqlite3.connect(os.path.join(self.core, "soul.db"))
        rows = con.execute("SELECT device_id, result FROM"
                           " soul_writeback_log").fetchall()
        con.close()
        self.assertIn(("dev-b3", "accepted"), rows)
        self.assertTrue(os.path.isfile(os.path.join(self.core, "identity.json")))

    def test_409_tampered_same_as_dashboard(self):
        """共用函数行为一致性：receiver 与 dashboard 对同篡改包同输出 409。"""
        src = zipfile.ZipFile(io.BytesIO(self.bundle))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename == "identity.json":
                    data = b'{"v":999}'
                out.writestr(info, data)
        r = self.client.post("/api/soul/writeback",
                             json={"bundle": base64.b64encode(buf.getvalue()).decode()},
                             headers={"X-Soul-Token": self.token})
        self.assertEqual(r.status_code, 409)
        self.assertIn("sha256", r.get_json()["reason"])


class DualEndLoopTests(unittest.TestCase):
    """真双端闭环：子进程 receiver（随机端口）+笔记本 tick 投递→审计+落盘。"""

    def test_tick_delivers_to_subprocess_receiver(self):
        core = tempfile.mkdtemp(prefix="xj3_b3core_")
        token = "dual-token-1"
        port = 5917
        env = dict(os.environ, XIAOJU3_SOUL_TOKEN=token,
                   XIAOJU3_SOUL_CORE_BASE=core, PORT=str(port))
        proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        proc = subprocess.Popen(
            [sys.executable, "-c",
             "import soul_core_receiver as r; r.app.run("
             "host='127.0.0.1', port=%d, use_reloader=False)" % port],
            env=env, cwd=proj,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            up = False
            for _ in range(30):
                time.sleep(0.5)
                try:
                    with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/api/health", timeout=2) as resp:
                        if resp.status == 200:
                            up = True
                            break
                except Exception:
                    continue
            self.assertTrue(up, "receiver 未起")

            # 笔记本侧：出包→入队→tick 投递（真 process_outbox HTTP）
            src = tempfile.mkdtemp(prefix="xj3_b3src_")
            bundle = _make_src_bundle(src)
            bp = os.path.join(src, "wb.zip")
            with open(bp, "wb") as f:
                f.write(bundle)
            from unittest import mock
            with mock.patch.dict(os.environ, {
                    "XIAOJU3_SOUL_CORE": f"http://127.0.0.1:{port}",
                    "XIAOJU3_SOUL_TOKEN": token,
                    "XIAOJU3_SOUL_CORE_BASE": core,
                    "XIAOJU3_AGENT_STATE_DIR": src}, clear=False), \
                    mock.patch.object(soul_sync, "AGENT_STATE_DIR", src), \
                    mock.patch.object(soul_sync, "PROJECT_ROOT", src):
                box = soul_sync.SoulOutbox(
                    path=os.path.join(src, "soul_outbox.json"))
                box.enqueue(bp, f"http://127.0.0.1:{port}", device_id="dev-b3")
                done = soul_sync.process_outbox(box, token=token)
            self.assertEqual(done, 1)
            self.assertEqual(box.all_entries(), [])   # 出队
            con = sqlite3.connect(os.path.join(core, "soul.db"))
            rows = con.execute("SELECT device_id, result FROM"
                               " soul_writeback_log").fetchall()
            con.close()
            self.assertIn(("dev-b3", "accepted"), rows)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()


class DeployArtifactTests(unittest.TestCase):
    """部署物完整性：Dockerfile 在位+COPY 清单齐+依赖文件真实存在
    （防 scp 漏文件——批 3-b 前置）。"""

    def test_dockerfile_and_copy_list(self):
        proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        df = os.path.join(proj, "deploy", "soul_core_Dockerfile")
        self.assertTrue(os.path.isfile(df))
        content = open(df, encoding="utf-8").read()
        copied = []
        for ln in content.splitlines():
            if ln.startswith("COPY "):
                parts = ln.split()[1:]
                copied.extend(parts[:-1])   # 末 token=容器内目标目录
        for fn in copied:
            self.assertTrue(os.path.isfile(os.path.join(proj, fn)),
                            f"Dockerfile COPY 的 {fn} 不在仓库")
        for must in ("soul_core_receiver.py", "migration.py",
                     "soul_manifest.py", "paths.py", "xiaoju3.py"):
            self.assertIn(must, copied)


if __name__ == "__main__":
    unittest.main()
