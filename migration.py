# -*- coding: utf-8 -*-
"""小橘3号 · 设备自动迁移 + 多设备互相守望。

按《架构设计文档》§8"设备自动迁移"（手机死机/没电/损坏时经局域网把
"自己是谁、记得什么、喜欢什么、设置成什么样"同步到家里其他设备，多设备
互相守望、谁出问题另一台顶上）、功能文档 §12 路线图、开发日志第十章
参照系（状态外置层 agent_state/ + 互相守望 + 故障顶替）。

1. export_bundle(path=None)：把"自己是谁、记得什么、喜欢什么、设置成
   什么样"打包为单一 zip（命名 xiaoju3_soul_*.zip）：agent_state/ 下的
   identity.json、history_*.json、conversations/、long_term.db、
   emoji_links.json，以及项目根 .env 的**存在性记录但不打包内容**——
   密钥不进包；包内 MANIFEST.txt 列明应手工迁移的密钥/配置清单（只列
   键名，不含值）。
2. import_bundle(zip_path, overwrite=False)：解包恢复到 agent_state/；
   冲突默认跳过、overwrite=True 才覆盖；恢复后输出需用户手工核对的
   密钥清单提示。成员路径做防穿越校验（绝对路径 / .. 一律拒绝）。
3. PeerWatch：多设备守望——对端列表来自 env XIAOJU3_PEERS（逗号分隔
   http://host:port），check_peers() 逐个 GET {peer}/api/health
   （requests，超时 3 秒）记录存活快照；watch_loop(interval=60) 连续
   N 次（默认 3）失联触发 on_peer_down 回调并打日志。默认回调 = 中文
   告警日志 + 可选 export_bundle 留最新备份；**不自动抢班**——文档的
   "自动接管"需配合部署编排（如 systemd / MQTT 节点发现 / 独立看门狗，
   开发日志第十章参照系），扩展路径：在 on_peer_down 回调内触发编排层
   抢班（拉起服务/切换 DNS/通知对端 self-heal），本模块只提供钩子与
   最新灵魂备份。
4. health_bp：/api/health 的 Flask Blueprint，返回
   {"status":"ok", "device":<hostname>, "ts":<unix秒>}，供对端守望探测。

【main.py 一行接入（接线方 S5）】
    from migration import health_bp
    app.register_blueprint(health_bp)

import 本模块零副作用（除 flask/requests 常规 import）；env 在函数调用
时读取，便于测试注入。
"""
import json
import os
import posixpath
import shutil
import socket
import time
import zipfile

import requests
from flask import Blueprint, jsonify

from xiaoju3 import AGENT_STATE_DIR, PROJECT_ROOT

# ==================== 配置（本模块自读 env；键名已报主控补 .env.example） ====================

# 多设备守望对端列表（逗号分隔 http://host:port）
PEERS_ENV = "XIAOJU3_PEERS"

# 灵魂包命名（主控会把该模式补进 .gitignore：xiaoju3_soul_*.zip）
SOUL_PREFIX = "xiaoju3_soul_"
MANIFEST_NAME = "MANIFEST.txt"

# 对端健康探测路径与超时（秒）
PEER_HEALTH_PATH = "/api/health"
PEER_TIMEOUT = 3

# 需手工迁移的密钥/配置键名清单（只列键名，值永不打包）
SECRET_KEYS = [
    "DEEPSEEK_API_KEY", "WEB_API_KEY", "HA_URL", "HA_TOKEN",
    "VISION_MODEL", "VISION_KEY",
    "XIAOJU3_TOTP_SECRET", "XIAOJU3_PEERS", "XIAOJU3_HUMIDITY_THRESHOLD",
]


def _peers_from_env():
    """解析 XIAOJU3_PEERS（逗号分隔）→ 对端列表。"""
    raw = os.environ.get(PEERS_ENV, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


# ==================== 灵魂备份：export / import ====================

def _soul_targets(base_dir):
    """收集要打包的"灵魂"文件（相对 agent_state 的 posix 风格路径列表）。"""
    targets = []
    if not os.path.isdir(base_dir):
        return targets
    # 固定清单：身份 / 长期记忆库 / 表情链接
    for name in ("identity.json", "long_term.db", "emoji_links.json"):
        if os.path.isfile(os.path.join(base_dir, name)):
            targets.append(name)
    # 双通道会话记忆：history_*.json
    for name in sorted(os.listdir(base_dir)):
        full = os.path.join(base_dir, name)
        if name.startswith("history_") and name.endswith(".json") and os.path.isfile(full):
            targets.append(name)
    # 会话归档目录：conversations/（递归）
    conv = os.path.join(base_dir, "conversations")
    if os.path.isdir(conv):
        for root, _dirs, files in os.walk(conv):
            for fn in sorted(files):
                rel = os.path.relpath(os.path.join(root, fn), base_dir)
                targets.append(rel.replace(os.sep, "/"))
    return targets


def _build_manifest(base_dir, files, env_exists):
    """生成 MANIFEST.txt（打包说明 + 手工迁移密钥清单，不含任何密钥值）。"""
    lines = [
        "小橘3号 · 灵魂备份清单（xiaoju3_soul_*.zip）",
        "=" * 46,
        f"打包时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"源设备主机名：{socket.gethostname()}",
        f"源 agent_state：{base_dir}",
        f".env 存在性记录：{'是（存在）' if env_exists else '否（未找到）'}"
        "——.env 内容未打包，密钥不进包，需按下方清单手工迁移。",
        "",
        "包内文件：",
    ]
    lines += [f"- {f}" for f in files] if files else ["- （源 agent_state 为空）"]
    lines += [
        "",
        "需在新设备手工迁移的密钥/配置（键名，值见源设备 .env）：",
        "、".join(SECRET_KEYS),
        "",
        f"恢复方式：migration.import_bundle('<本包路径>', overwrite=False)",
    ]
    return "\n".join(lines)


def export_bundle(path=None, base_dir=None, env_file=None):
    """打包灵魂为单一 zip，返回包路径。

    - base_dir 缺省取统一配置 xiaoju3.AGENT_STATE_DIR（状态外置层）；
    - env_file 缺省取项目根 .env：只记录存在性，内容绝不打包；
    - path 缺省落项目根，命名 xiaoju3_soul_<时间戳>.zip。
    """
    base_dir = base_dir or AGENT_STATE_DIR
    env_file = env_file or os.path.join(PROJECT_ROOT, ".env")
    if path is None:
        path = os.path.join(PROJECT_ROOT, f"{SOUL_PREFIX}"
                            f"{time.strftime('%Y%m%d_%H%M%S')}.zip")
    files = _soul_targets(base_dir)
    env_exists = os.path.isfile(env_file)
    manifest = _build_manifest(base_dir, files, env_exists)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            zf.write(os.path.join(base_dir, *rel.split("/")), arcname=rel)
        zf.writestr(MANIFEST_NAME, manifest)
    print(f"💾 [迁移] 灵魂备份完成：{path}（{len(files)} 个文件；密钥不进包，见 {MANIFEST_NAME}）")
    return os.path.abspath(path)


def _safe_member(name):
    """zip 成员路径防穿越校验：非法（绝对路径 / 盘符 / .. 上跳）返回 None。"""
    norm = posixpath.normpath(str(name).replace("\\", "/"))
    if norm.startswith("/") or norm.startswith("..") or ":" in norm.split("/", 1)[0]:
        return None
    return norm


def import_bundle(zip_path, overwrite=False, base_dir=None):
    """解包灵魂到 agent_state/，返回 {"restored": [...], "skipped": [...], "report": 文案}。

    - 冲突默认跳过；overwrite=True 才覆盖已有文件；
    - MANIFEST.txt 为说明文件不落盘；不安全路径（.. / 绝对路径）拒绝并记录；
    - 恢复完成后 report 附密钥手工核对清单提示。
    """
    base_dir = base_dir or AGENT_STATE_DIR
    os.makedirs(base_dir, exist_ok=True)
    restored, skipped = [], []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            if name == MANIFEST_NAME:
                continue
            safe = _safe_member(name)
            if safe is None:
                skipped.append(f"{name}（不安全路径，已拒绝）")
                continue
            target = os.path.join(base_dir, *safe.split("/"))
            if os.path.exists(target) and not overwrite:
                skipped.append(safe)
                continue
            os.makedirs(os.path.dirname(target) or base_dir, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            restored.append(safe)

    report = (f"✅ 灵魂恢复完成：新恢复 {len(restored)} 项，跳过 {len(skipped)} 项"
              "（冲突默认跳过；如需覆盖请 overwrite=True）。\n")
    if restored:
        report += "恢复明细：" + "、".join(restored) + "\n"
    if skipped:
        report += "跳过明细：" + "、".join(skipped) + "\n"
    report += ("⚠️ 密钥不随包迁移：请在新设备 .env 手工核对以下键是否已配置：\n"
               + "、".join(SECRET_KEYS) + "\n（详见包内 MANIFEST.txt）")
    print(f"📥 [迁移] {report.splitlines()[0]}")
    return {"restored": restored, "skipped": skipped, "report": report}


# ==================== 多设备互相守望（PeerWatch） ====================

class PeerWatch:
    """多设备互相守望：谁出问题另一台顶上（架构设计文档 §8）。

    - 对端：peers 缺省读 env XIAOJU3_PEERS（逗号分隔 http://host:port）；
    - 探测：check_peers() 逐个 GET {peer}/api/health（超时默认 3 秒），
      记录并返回存活快照列表 [{peer, alive, detail, fail_count, ts}]；
    - 告警：连续 fail_threshold（默认 3）次失联触发 on_peer_down(peer)
      回调并打日志（恢复在线后重新计数，可再次触发）；
    - 默认回调 = 中文告警日志 + backup_on_down=True 时调 export_bundle()
      留最新灵魂备份；**不自动抢班**。
    """

    def __init__(self, peers=None, fail_threshold=3, on_peer_down=None,
                 backup_on_down=False, timeout=PEER_TIMEOUT):
        self.peers = list(peers) if peers is not None else _peers_from_env()
        self.fail_threshold = max(1, int(fail_threshold))
        self.timeout = timeout
        self.backup_on_down = backup_on_down
        self.on_peer_down = on_peer_down or self._default_on_peer_down
        self._fail_counts = {}      # peer -> 连续失联次数
        self._down_notified = set() # 已触发告警且尚未恢复的 peer

    # 默认回调：告警日志 + 可选最新备份。不自动抢班——
    # 扩展路径：传入自定义 on_peer_down，在其中接入部署编排
    # （systemd/MQTT 节点发现/独立看门狗，开发日志第十章参照系），
    # 由编排层决定"另一台顶上"的具体方式（拉起服务/切流量/通知人工）。
    def _default_on_peer_down(self, peer):
        print(f"🚨 [守望] 对端连续 {self.fail_threshold} 次失联：{peer}")
        print("🚨 [守望] 该设备可能死机/断电/损坏，请人工检查；"
              "如需自动接管请在 on_peer_down 回调接入部署编排（本程序不自动抢班）。")
        if self.backup_on_down:
            try:
                path = export_bundle()
                print(f"💾 [守望] 已留下最新灵魂备份：{path}")
            except Exception as e:
                print(f"⚠️ [守望] 留存灵魂备份失败：{e}")

    def check_peers(self):
        """逐个探测对端健康，更新连续失联计数；达到阈值触发回调（恢复前只触发一次）。"""
        snapshots = []
        for peer in self.peers:
            url = peer.rstrip("/") + PEER_HEALTH_PATH
            try:
                resp = requests.get(url, timeout=self.timeout)
                alive = getattr(resp, "status_code", 0) == 200
                detail = f"HTTP {getattr(resp, 'status_code', 0)}"
            except Exception as e:
                alive, detail = False, str(e)

            if alive:
                if peer in self._down_notified:
                    print(f"💚 [守望] 对端恢复在线：{peer}")
                self._down_notified.discard(peer)
                self._fail_counts[peer] = 0
            else:
                self._fail_counts[peer] = self._fail_counts.get(peer, 0) + 1
                if (self._fail_counts[peer] >= self.fail_threshold
                        and peer not in self._down_notified):
                    self._down_notified.add(peer)
                    try:
                        self.on_peer_down(peer)
                    except Exception as e:
                        print(f"⚠️ [守望] on_peer_down 回调异常：{e}")

            snapshots.append({
                "peer": peer, "alive": alive, "detail": detail,
                "fail_count": self._fail_counts[peer], "ts": time.time(),
            })
        return snapshots

    def watch_loop(self, interval=60, max_rounds=None):
        """守望循环：每 interval 秒巡检一轮（max_rounds 仅供测试限定轮数）。"""
        print(f"👀 [守望] 多设备互相守望已启动，每 {interval} 秒巡检 "
              f"{len(self.peers)} 台对端...")
        rounds = 0
        while True:
            try:
                self.check_peers()
            except Exception as e:
                print(f"⚠️ [守望] 巡检异常：{e}")
            rounds += 1
            if max_rounds is not None and rounds >= max_rounds:
                break
            time.sleep(interval)


# ==================== /api/health（供对端守望探测本机） ====================

health_bp = Blueprint("xiaoju3_health", __name__)


@health_bp.route("/api/health")
def health():
    """GET /api/health → {"status":"ok","device":<hostname>,"ts":<unix秒>}。

    main.py 一行接入：`from migration import health_bp; app.register_blueprint(health_bp)`
    """
    return jsonify({"status": "ok", "device": socket.gethostname(), "ts": time.time()})


if __name__ == "__main__":
    # 便捷 CLI：python migration.py export [路径] / python migration.py import <zip>
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "export":
        export_bundle(sys.argv[2] if len(sys.argv) >= 3 else None)
    elif len(sys.argv) >= 3 and sys.argv[1] == "import":
        import_bundle(sys.argv[2], overwrite="--overwrite" in sys.argv[3:])
    else:
        print("用法：python migration.py export [输出路径] | python migration.py import <zip> [--overwrite]")
