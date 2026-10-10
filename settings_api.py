# -*- coding: utf-8 -*-
"""#264 配置面板 · settings API（B1 骨架）。

设计稿：_dev/design_264_settings_panel.md v2 + 十三节 API 形态（B1 定稿）。
权限分档：settings_tiers.json（daily=1 / admin=3 / danger=4+TOTP /
key=3 独立密钥页）。

安全纪律：
- 密钥值绝不进日志、绝不回显（GET 只回掩码 前3+****+后4）；
- 权限门在 API 层（不改 ENV_WRITE_ALLOWLIST）；越权**整批拒绝**；
- 写 .env 一律走 xiaoju3.save_env_file（白名单+.bak+原子写+增量合并，
  安装器步 A2 遗产，零重复实现）；
- 审计只记 key 名+时间+档位（settings_log，trace.db 独立表）；
- 儿童锁特例：键档 admin，但写 false（关）需 L4+TOTP（非对称拍板）。

挂载：xiaoju3_dashboard.py 创建 app 后调 register_settings_routes(app)。
"""
import json
import os
import sqlite3

from flask import jsonify, request

import auth_lv4

AUDIT_KEEP = 500


def _tiers_path():
    """分档表路径：XIAOJU3_SETTINGS_TIERS_PATH（测试注入，进程级 env
    双实例一致）> 模块同目录（默认）。"""
    p = os.environ.get("XIAOJU3_SETTINGS_TIERS_PATH")
    if p:
        return p
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "settings_tiers.json")

# 设计取舍（2026-10-10）：_load_tiers 每次读文件、**不做模块级缓存**——
# 真机调试实锤：pytest 与 dashboard 两个 import 实例的模块级缓存状态
# 分裂（id 不同），tier 判定读到空骨架致全 403。分档表体量小（<2KB），
# 每次读盘成本可忽略；文件=单一真相源，双实例天然一致。


def _load_tiers():
    """加载分档表（每次读文件——单一真相源，见上设计取舍）。失败返回
    最小安全骨架（空 items=全部隐藏+拒绝写）。"""
    try:
        with open(_tiers_path(), encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "tiers" not in data:
            raise ValueError("bad tiers structure")
        return data
    except Exception:
        return {"tiers": {}, "items": []}


def get_level():
    """当前会话权限级（1-4）。读取失败按 Lv.1（最保守）。"""
    try:
        from permission import LEVEL_ORDER, permission_manager
        return LEVEL_ORDER.get(permission_manager.current_level, 1)
    except Exception:
        return 1


def _totp_ok(code):
    """LV4 TOTP 校验（复用 auth_lv4；secret 缺失/校验异常一律 False）。"""
    if not code:
        return False
    try:
        secret = os.environ.get("XIAOJU3_TOTP_SECRET", "")
        if not secret:
            return False
        return bool(auth_lv4.verify_totp(secret, str(code).strip()))
    except Exception:
        return False


def _audit(entry):
    """审计：只记 key 名+时间+档位，绝不记值。trace.db 独立表，静默。"""
    try:
        base = os.environ.get("AGENT_STATE_DIR") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "agent_state")
        conn = sqlite3.connect(os.path.join(base, "trace.db"))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,"
            " actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT)")
        conn.execute(
            "INSERT INTO settings_log (ts, actor, action, detail)"
            " VALUES (?, ?, ?, ?)",
            (_now(), entry.get("actor", "console"), entry["action"],
             entry.get("detail", "")))
        conn.execute(
            "DELETE FROM settings_log WHERE id NOT IN"
            " (SELECT id FROM settings_log ORDER BY id DESC LIMIT ?)",
            (AUDIT_KEEP,))
        conn.commit()
        conn.close()
    except Exception as e:
        # 显式化审计失败（此前静默 pass 掩盖环境路径问题——2026-10-10
        # 真机调试抓的图钉）；dashboard 日志可见，不影响主链
        print(f"⚠️ [settings_audit] 写入失败（忽略）: {e} | base={base!r}")


def _now():
    from datetime import datetime
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _mask(value):
    """掩码：前3+****+后4；长度<8 全星；空值=未配置。"""
    v = str(value or "")
    if not v:
        return ""
    if len(v) < 8:
        return "****"
    return v[:3] + "****" + v[-4:]


def _env_path():
    """测试/生产统一 .env 路径：XIAOJU3_SETTINGS_ENV_PATH（测试注入）>
    xiaoju3.ENV_FILE（frozen 归位生产 xiaoju3_data/.env）。绝不写生产
    之外的位置由调用方保证（测试走 env 注入隔离）。"""
    p = os.environ.get("XIAOJU3_SETTINGS_ENV_PATH")
    if p:
        return p
    try:
        import xiaoju3
        return xiaoju3.ENV_FILE
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "xiaoju3_data", ".env")


def _read_env_pairs(path):
    """轻量 .env 读取（KEY→VALUE dict；跳注释/BOM/export 前缀/剥引号）。
    与 xiaoju3._load_env_file 的写入口径对称，但不 setenv（纯读）。"""
    pairs = {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[len("export "):]
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                    v = v[1:-1]
                pairs[k.strip()] = v
    except Exception:
        pass
    return pairs


def _tier_of(key):
    for it in _load_tiers().get("items", []):
        if it["key"] == key:
            return it
    return None


def _perm_ok(tier_name, level, totp_code):
    """档位权限判定：level 达标 +（danger 档需 TOTP）。"""
    tier = _load_tiers().get("tiers", {}).get(tier_name)
    if tier is None:
        return False, None
    need = int(tier.get("level", 99))
    if level < need:
        return False, ("level_insufficient", need)
    if tier.get("totp") and not _totp_ok(totp_code):
        return False, ("totp_invalid", need)
    return True, None


def register_settings_routes(app):
    """挂载四端点到 Flask app（xiaoju3_dashboard 创建 app 后调用）。"""
    from xiaoju3 import save_env_file, _load_env_file

    @app.route("/api/settings", methods=["GET"])
    def api_settings_get():  # noqa: F811
        level = get_level()
        items = []
        for it in _load_tiers().get("items", []):
            if it.get("tier") == "key":
                continue                      # 密钥项不进 settings GET
            need = int(_load_tiers()["tiers"].get(
                it.get("tier"), {}).get("level", 99))
            if level < need:
                continue                      # 低档隐藏高档项（不整页拒绝）
            value = _read_env_pairs(_env_path()).get(it["key"], "")
            items.append({"key": it["key"], "label": it.get("label", ""),
                          "tier": it.get("tier"), "type": it.get("type", ""),
                          "value": value})
        return jsonify({"code": 200, "level": level, "items": items})

    @app.route("/api/settings", methods=["POST"])
    def api_settings_post():  # noqa: F811
        level = get_level()
        data = request.get_json(silent=True) or {}
        updates = data.get("updates") or {}
        totp = data.get("totp")
        if not isinstance(updates, dict) or not updates:
            return jsonify({"code": 400, "error": "updates_required"}), 400

        # 逐键判档——任一越权：整批拒绝（不部分写）
        tier_need = None
        for key in updates:
            it = _tier_of(key)
            if it is None:
                return jsonify({"code": 403,
                                "error": "key_not_allowed",
                                "key": key}), 403
            tier_name = it.get("tier")
            need = int(_load_tiers()["tiers"].get(tier_name, {}).get(
                "level", 99))
            if level < need:
                return jsonify({"code": 403,
                                "error": "level_insufficient",
                                "required": need}), 403
            if (_load_tiers()["tiers"].get(tier_name, {}).get("totp")
                    and not _totp_ok(totp)):
                return jsonify({"code": 403,
                                "error": "totp_required"
                                if not totp else "totp_invalid"}), 403
            tier_need = tier_name
        # 儿童锁特例（非对称拍板）：写 false（关）需 L4+TOTP
        if "CHILD_LOCK_ENABLED" in updates:
            newv = str(updates["CHILD_LOCK_ENABLED"]).strip().lower()
            if newv in ("0", "false", "off") and (level < 4
                                                  or not _totp_ok(totp)):
                return jsonify({"code": 403,
                                "error": "childlock_off_requires_lv4_totp"}), 403

        written, skipped, backup = save_env_file(updates,
                                                 path=_env_path())
        applied = []
        for k, v in updates.items():
            it = _tier_of(k)
            if it and it.get("apply") == "env" and k in written:
                os.environ[k] = str(v)   # 🟢 即改即生效（判定表 apply=env）
                applied.append(k)
        _audit({"action": "settings_update",
                "detail": f"keys={sorted(written)} tier={tier_need}"})
        return jsonify({"code": 200, "written": written,
                        "skipped": skipped,
                        "backup_path": backup or "", "applied": applied})

    @app.route("/api/keys", methods=["GET"])
    def api_keys_get():  # noqa: F811
        level = get_level()
        if level < 3:
            return jsonify({"code": 403, "error": "level_insufficient",
                            "required": 3}), 403
        items = []
        for it in _load_tiers().get("items", []):
            if it.get("tier") != "key":
                continue
            value = _read_env_pairs(_env_path()).get(it["key"], "")
            items.append({"key": it["key"], "masked": _mask(value),
                          "set": bool(value)})
        _audit({"action": "keys_view", "detail": f"level={level}"})
        return jsonify({"code": 200, "level": level, "items": items})

    @app.route("/api/keys", methods=["POST"])
    def api_keys_post():  # noqa: F811
        level = get_level()
        if level < 3:
            return jsonify({"code": 403, "error": "level_insufficient",
                            "required": 3}), 403
        data = request.get_json(silent=True) or {}
        key = data.get("key", "")
        value = data.get("value", "")
        if data.get("confirm") is not True:
            return jsonify({"code": 400, "error": "confirm_required"}), 400
        it = _tier_of(key)
        if it is None or it.get("tier") != "key":
            return jsonify({"code": 403, "error": "key_not_allowed"}), 403
        if not str(value).strip():
            return jsonify({"code": 400, "error": "value_required"}), 400
        written, skipped, backup = save_env_file({key: value},
                                                 path=_env_path())
        _audit({"action": "key_overwrite", "detail": f"key={key}"})
        return jsonify({"code": 200, "written": bool(written),
                        "backup_path": backup or ""})

    return app
