# -*- coding: utf-8 -*-
"""小橘3号 · 灵魂核心接收器（#319 批 3：Pi 侧精简服务，design_319_batch3_impl）。

定位：核心侧常驻小服务——只做"收灵魂包+报健康"，不带大脑/通道/UI。
与笔记本 dashboard 的 writeback 端点**共用 migration 校验/落盘函数**
（verify_soul_bundle_payload / apply_soul_bundle_to_core 同源，防双实现漂移）。

多端预留（roadmap §十）：REST 形态+device_id/protocol_version 字段+token 独立
于设备+角色由配置定——将来各终端 App 直接 HTTP 调用，不焊死"笔记本↔Pi"拓扑。

环境变量：
- XIAOJU3_SOUL_TOKEN      回写令牌（缺省空=恒 401 端点关闭）
- XIAOJU3_SOUL_CORE_BASE  数据目录（缺省 /data/agent_state，容器卷挂载点）
- PORT                    监听端口（缺省 9100）

数据域：/data/agent_state/（收包落盘）+ soul.db（审计+conflicts，SOUL_CORE
审计跟人走——可随下次回写包流动）。本文件跑在 Pi（ARM Linux），依赖闭包
=flask+requests+migration/soul_manifest/paths/xiaoju3（全纯 python）。
"""
import os

from flask import Flask, jsonify, request

import migration
from migration import health_bp

app = Flask(__name__)
app.register_blueprint(health_bp)   # GET /api/health（PeerWatch 探测同源）


def _core_base():
    """数据目录：env 直控（容器卷挂载点），与批 2 端点同款注入钩子。"""
    return (os.environ.get("XIAOJU3_SOUL_CORE_BASE", "").strip()
            or "/data/agent_state")


@app.route("/api/soul/writeback", methods=["POST"])
def soul_writeback():
    """收包薄壳（P3-1+用户 2026-10-16 补充拍板：鉴权/解包也走 migration
    共用解析 parse_writeback_request——两侧零鉴权代码漂移面）。"""
    body = request.get_json(silent=True) or {}
    err, reason, zip_bytes, device_id = migration.parse_writeback_request(
        body, request.headers.get("X-Soul-Token", ""),
        (os.environ.get("XIAOJU3_SOUL_TOKEN", "") or "").strip())
    if err is not None:
        return jsonify({"ack": False, "reason": reason}), err
    base_dir = _core_base()
    try:
        result = migration.apply_soul_bundle_to_core(
            zip_bytes, base_dir=base_dir, device_id=device_id,
            db_path=os.path.join(base_dir, "soul.db"))
    except ValueError as e:
        return jsonify({"ack": False, "reason": str(e)}), 409
    except Exception as e:
        return jsonify({"ack": False, "reason": f"内部异常: {e}"}), 500
    return jsonify({"ack": True, "protocol_version": 1, **result}), 202


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9100"))
    # 0.0.0.0=容器内必需（Tailscale/内网经端口映射进来）；公网不可达由
    # Pi 防火墙现状保证（9100 未开放），令牌为第二道门。
    app.run(host="0.0.0.0", port=port, use_reloader=False)
