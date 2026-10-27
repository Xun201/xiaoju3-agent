# -*- coding: utf-8 -*-
"""qq_lifemate · express：表现力编排（切片 b，2026-10-27 队长拍板 M1）。

语音主链 Edge-TTS（音质好才拟人）/ SAPI(pyttsx3 Huihui) 离线兜底；
表情包 stickers/ 情绪标签图库；文字必发，语音/表情低概率附加（拟人
不机械+防刷屏风控——连续语音不超过 1 条/次唤醒）。

发送直接走 OneBot send_private_msg 的 CQ 码消息（notify_master 只收
纯文本；本模块需要 [CQ:record]/[CQ:image]）。
"""
import os
import random
import tempfile

# 表现力概率（低频拟人；改动须过 tests/test_qq_lifemate_express.py 契约锚）
VOICE_PROB = 0.30
STICKER_PROB = 0.25
EDGE_VOICE = "zh-CN-XiaoxiaoNeural"   # 人类少女音（dashboard 同款表内）


def _onebot_api():
    api = (os.environ.get("ONEBOT_API_URL", "").strip()
           or os.environ.get("NAPCAT_API_URL", "").strip()
           or "http://127.0.0.1:3001").rstrip("/")
    owner = (os.environ.get("XIAOJU3_OWNER_QQ", "") or "").strip()
    return api, owner


def send_cq(cq_message):
    """发 CQ 码消息给队长（语音/表情共用）。返回是否成功。"""
    api, owner = _onebot_api()
    if not owner:
        print("🦊 [express] 未配置 XIAOJU3_OWNER_QQ，跳过。")
        return False
    try:
        import requests
        headers = {}
        token = (os.environ.get("ONEBOT_TOKEN", "") or "").strip()
        if token:   # NapCat access_token 校验（2026-10-27 真机 403 实锤）
            headers["Authorization"] = f"Bearer {token}"
        r = requests.post(f"{api}/send_private_msg",
                          json={"user_id": owner, "message": cq_message},
                          headers=headers, timeout=8)
        ok = r.status_code == 200
        if not ok:
            print(f"🦊 [express] CQ 发送失败: HTTP {r.status_code} {r.text[:80]}")
        return ok
    except Exception as e:
        print(f"🦊 [express] CQ 发送异常: {e}")
        return False


# ────────────────────────── 语音（Edge-TTS 主 / SAPI 兜底） ──────────────────────────

def synthesize_speech(text):
    """文本 → 语音文件路径。Edge-TTS 主链（mp3）；失败 pyttsx3 SAPI 兜底
    （wav，Huihui）；都失败返回 None（本轮放弃语音，文字仍在）。"""
    text = (text or "").strip()
    if not text:
        return None
    out_dir = tempfile.gettempdir()
    try:
        import edge_tts
        import asyncio
        mp3 = os.path.join(out_dir, f"lifemate_{os.getpid()}_{random.randint(1000, 9999)}.mp3")

        async def _run():
            com = edge_tts.Communicate(text, EDGE_VOICE)
            await com.save(mp3)

        asyncio.run(_run())
        if os.path.isfile(mp3) and os.path.getsize(mp3) > 0:
            return mp3
    except Exception as e:
        print(f"🦊 [express] Edge-TTS 失败（转 SAPI 兜底）: {e}")
    try:
        import pyttsx3
        engine = pyttsx3.init()
        wav = os.path.join(out_dir, f"lifemate_{os.getpid()}_{random.randint(1000, 9999)}.wav")
        engine.save_to_file(text, wav)
        engine.runAndWait()
        if os.path.isfile(wav) and os.path.getsize(wav) > 0:
            return wav
    except Exception as e:
        print(f"🦊 [express] SAPI 兜底也失败（放弃语音）: {e}")
    return None


def send_voice(text):
    """合成并发送语音（CQ:record，file:// 绝对路径——NapCat 内部转 silk）。"""
    path = synthesize_speech(text)
    if not path:
        return False
    try:
        ok = send_cq(f"[CQ:record,file=file:///{path}]")
        return ok
    finally:
        try:
            os.remove(path)   # 发完即焚（ NapCat 异步读盘竞态窗口小，失败降文字）
        except OSError:
            pass


# ────────────────────────── 表情包（情绪标签图库） ──────────────────────────

def sticker_root():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "stickers")


def pick_sticker(mood=""):
    """按情绪标签挑表情（mood 目录优先，无匹配回退全库随机）。返回绝对
    路径或 None（图库空）。"""
    root = sticker_root()
    if not os.path.isdir(root):
        return None
    candidates = []
    mood_dir = os.path.join(root, (mood or "").strip().lower())
    if mood and os.path.isdir(mood_dir):
        candidates = _list_images(mood_dir)
    if not candidates:
        candidates = _list_images(root)
    return random.choice(candidates) if candidates else None


def _list_images(directory):
    exts = (".jpg", ".jpeg", ".png", ".gif", ".webp")
    out = []
    try:
        for name in os.listdir(directory):
            if name.lower().endswith(exts):
                out.append(os.path.join(directory, name))
    except OSError:
        pass
    return out


def send_sticker(mood=""):
    path = pick_sticker(mood)
    if not path:
        print("🦊 [express] 图库空（stickers/ 无图片），跳过表情。")
        return False
    return send_cq(f"[CQ:image,file=file:///{path}]")


# ────────────────────────── 编排（概率附加） ──────────────────────────

def maybe_express(text_sent, mood="neutral", rng=None):
    """文字发完后按概率附加语音/表情。返回描述串（日志/测试用）。
    rng 注入保证可测；生产传 None 用全局 random。"""
    r = rng or random
    acts = []
    if r.random() < VOICE_PROB:
        if send_voice(text_sent):
            acts.append("voice")
    if r.random() < STICKER_PROB:
        if send_sticker(mood):
            acts.append("sticker")
    return "+".join(acts)
