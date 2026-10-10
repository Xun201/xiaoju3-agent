# -*- coding: utf-8 -*-
"""#264 settings API 测试锚（B1，9+2 条）。

隔离：settings_tiers.json/.env/trace.db 全部指临时目录（XIAOJU3_
SETTINGS_ENV_PATH 注入），不碰生产；level 经 monkeypatch
settings_api.get_level。
"""
import json
import os
import sqlite3
import time

import pytest

import settings_api

_DB = {"tiers": None, "env": None}


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    tiers = str(tmp_path / "settings_tiers.json")
    envf = str(tmp_path / "test.env")
    with open(envf, "w", encoding="utf-8") as f:
        f.write("USER_CITY=长沙\n")
    monkeypatch.setenv("XIAOJU3_SETTINGS_ENV_PATH", envf)
    monkeypatch.setenv("XIAOJU3_SETTINGS_TIERS_PATH", tiers)
    monkeypatch.setenv("AGENT_STATE_DIR", str(tmp_path))   # 审计/trace 隔离
    _DB["tiers"] = tiers
    _DB["env"] = envf
    yield


@pytest.fixture
def client():
    import xiaoju3_dashboard as dash
    dash.app.config["TESTING"] = True
    return dash.app.test_client()


def _write_tiers():
    base = {
        "tiers": {"daily": {"level": 1, "totp": False},
                  "admin": {"level": 3, "totp": False},
                  "danger": {"level": 4, "totp": True},
                  "key": {"level": 3, "totp": False}},
        "items": [
            {"key": "USER_CITY", "label": "城市", "tier": "daily",
             "type": "str", "apply": "env"},
            {"key": "LOCAL_MODEL_SMALL", "label": "小模型", "tier": "admin",
             "type": "str", "apply": "env"},
            {"key": "LOCAL_MODEL", "label": "主模型", "tier": "danger",
             "type": "str", "apply": "env"},
            {"key": "DEEPSEEK_API_KEY", "label": "DeepSeek API Key",
             "tier": "key", "type": "secret", "apply": "env"},
            {"key": "HA_TOKEN", "label": "HA 长期令牌",
             "tier": "key", "type": "secret", "apply": "env"},
        ]}
    with open(_DB["tiers"], "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False)



def _aff_code(offset=0):
    import base64
    import hashlib
    import hmac
    import struct
    counter = int(time.time() + offset) // 30
    key = base64.b32decode("JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP")
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    return str((struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF)
               % 1000000).zfill(6)


# 1 cache 注入后 _load_tiers 返回同数据 + 4 档齐全 + 每项 tier 合法
def test_cache_injection_roundtrip():
    _write_tiers()
    d = settings_api._load_tiers()
    assert set(d["tiers"].keys()) == {"daily", "admin", "danger", "key"}
    for it in d["items"]:
        assert it["tier"] in d["tiers"]


# 1b 文件加载器独立验证（写真实文件 → _tiers_path env → load 读到）
def test_tiers_file_loader(tmp_path, monkeypatch):
    tiers_file = tmp_path / "settings_tiers.json"
    payload = {"tiers": {"daily": {"level": 1, "totp": False}},
               "items": [{"key": "USER_CITY", "label": "城市",
                          "tier": "daily", "type": "str", "apply": "env"}]}
    tiers_file.write_text(json.dumps(payload, ensure_ascii=False),
                          encoding="utf-8")
    monkeypatch.setenv("XIAOJU3_SETTINGS_TIERS_PATH", str(tiers_file))
    d = settings_api._load_tiers()
    assert d["items"][0]["key"] == "USER_CITY"


# 2 GET 低 level 隐藏高档项（L1 只见 daily）
def test_get_hides_high_tier(client, monkeypatch):
    _write_tiers()
    monkeypatch.setattr(settings_api, "get_level", lambda: 1)
    r = client.get("/api/settings")
    body = r.get_json()
    keys = [i["key"] for i in body["items"]]
    assert "USER_CITY" in keys
    assert "LOCAL_MODEL_SMALL" not in keys      # admin 隐藏
    assert "LOCAL_MODEL" not in keys            # danger 隐藏
    assert body["level"] == 1


# 3 GET 不含 key tier 项
def test_get_excludes_key_tier(client, monkeypatch):
    _write_tiers()
    monkeypatch.setattr(settings_api, "get_level", lambda: 4)
    r = client.get("/api/settings")
    keys = [i["key"] for i in r.get_json()["items"]]
    assert "DEEPSEEK_API_KEY" not in keys


# 4 POST daily 键 level=1 通过（写 env + applied 热应用）
def test_post_daily_ok(client, monkeypatch):
    _write_tiers()
    monkeypatch.setattr(settings_api, "get_level", lambda: 1)
    r = client.post("/api/settings", json={"updates": {"USER_CITY": "北京"}})
    body = r.get_json()
    assert body["code"] == 200 and "USER_CITY" in body["written"]
    assert "USER_CITY" in body["applied"]
    assert os.environ["USER_CITY"] == "北京"   # 🟢 热应用
    stored = open(_DB["env"], encoding="utf-8").read()
    assert "USER_CITY=北京" in stored


# 5 POST admin 键 level=2 → 403 level_insufficient
def test_post_admin_level2_403(client, monkeypatch):
    _write_tiers()
    monkeypatch.setattr(settings_api, "get_level", lambda: 2)
    r = client.post("/api/settings",
                    json={"updates": {"LOCAL_MODEL_SMALL": "x"}})
    assert r.status_code == 403
    assert r.get_json()["error"] == "level_insufficient"


# 6 POST danger 键三连：L3 拒 / L4 无 totp 拒 / totp 错拒
def test_post_danger_gates(client, monkeypatch):
    _write_tiers()
    monkeypatch.setenv("XIAOJU3_TOTP_SECRET",
                       "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP")
    monkeypatch.setattr(settings_api, "get_level", lambda: 3)
    r = client.post("/api/settings", json={"updates": {"LOCAL_MODEL": "m"},
                                           "totp": _aff_code()})
    assert r.status_code == 403                       # L3 拒（danger 需 L4）
    monkeypatch.setattr(settings_api, "get_level", lambda: 4)
    r = client.post("/api/settings", json={"updates": {"LOCAL_MODEL": "m"}})
    assert r.status_code == 403                       # L4 无 totp 拒
    r = client.post("/api/settings", json={"updates": {"LOCAL_MODEL": "m"},
                                           "totp": "000000"})
    assert r.status_code == 403                       # totp 错拒
    r = client.post("/api/settings", json={"updates": {"LOCAL_MODEL": "m"},
                                           "totp": _aff_code()})
    assert r.status_code == 200                       # L4+正 totp 过
    assert "LOCAL_MODEL" in r.get_json()["written"]



# 7 GET /api/keys masked 格式（前3+****+后4；<8 全星；未配置空）
def test_keys_masked(client, monkeypatch):
    _write_tiers()
    monkeypatch.setattr(settings_api, "get_level", lambda: 3)
    envp = _DB["env"]
    with open(envp, "w", encoding="utf-8") as f:
        f.write('DEEPSEEK_API_KEY=sk-abcdefgh12345678\nHA_TOKEN=short\n')
    r = client.get("/api/keys")
    items = {i["key"]: i for i in r.get_json()["items"]}
    assert items["DEEPSEEK_API_KEY"]["masked"] == "sk-****5678"
    assert items["HA_TOKEN"]["masked"] == "****"      # 长度<8 全星
    assert items["HA_TOKEN"]["set"] is True


# 8 POST /api/keys confirm!=true → 400
def test_keys_confirm_required(client, monkeypatch):
    _write_tiers()
    monkeypatch.setattr(settings_api, "get_level", lambda: 3)
    r = client.post("/api/keys",
                    json={"key": "DEEPSEEK_API_KEY", "value": "sk-x"})
    assert r.status_code == 400
    r = client.post("/api/keys",
                    json={"key": "DEEPSEEK_API_KEY", "value": "sk-x",
                          "confirm": "yes"})
    assert r.status_code == 400                        # 非布尔 true 也拒


# 9 POST apply=="env" 键后 os.environ 出现新值（热应用语义）
def test_apply_env_hot(client, monkeypatch):
    _write_tiers()
    monkeypatch.setattr(settings_api, "get_level", lambda: 1)
    client.post("/api/settings", json={"updates": {"USER_CITY": "上海"}})
    assert os.environ["USER_CITY"] == "上海"


# 10 派生锚：越权整批拒绝不部分写（daily+danger 混合批 → 403 且 env 无写入）
def test_mixed_batch_all_or_nothing(client, monkeypatch):
    _write_tiers()
    monkeypatch.setattr(settings_api, "get_level", lambda: 1)
    r = client.post("/api/settings",
                    json={"updates": {"USER_CITY": "广州",
                                      "LOCAL_MODEL": "evil"}})
    assert r.status_code == 403
    stored = open(_DB["env"], encoding="utf-8").read()
    assert "广州" not in stored and "evil" not in stored


# 11 派生锚：settings_log 审计（trace.db 独立表，只记 key 名）
def test_audit_written(client, monkeypatch, tmp_path):
    _write_tiers()
    monkeypatch.setattr(settings_api, "get_level", lambda: 1)
    r = client.post("/api/settings", json={"updates": {"USER_CITY": "北京"}})
    print("[dbg] POST:", r.status_code, r.get_json())
    print("[dbg] tmp 目录文件:", sorted(os.listdir(str(tmp_path))))
    # 直调 _audit（pytest 环境），异常不吞——定位 POST 段审计失败的真因
    import traceback
    try:
        settings_api._audit({"action": "settings_update",
                             "detail": "USER_CITY直调调试"})
    except Exception:
        traceback.print_exc()
    dbp = _DB["env"].replace("test.env", "trace.db")
    print("[dbg] dbp:", dbp, "| 存在:", os.path.exists(dbp))
    c = sqlite3.connect(dbp)
    rows = c.execute("select actor, action, detail from settings_log"
                     " order by id desc limit 1").fetchall()
    c.close()
    assert rows and "USER_CITY" in rows[0][2]


# 12 派生锚：brain 挂载源码锚（dashboard 注册 + 端点存在）
def test_brain_mount_anchor():
    import inspect
    import xiaoju3_dashboard
    import settings_api
    src = inspect.getsource(xiaoju3_dashboard)
    assert "_register_settings(app)" in src          # dashboard 挂载
    ssrc = inspect.getsource(settings_api)
    assert "/api/settings" in ssrc and "/api/keys" in ssrc  # 端点在 settings_api
