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
import threading

# 表现力概率（低频拟人；改动须过 tests/test_qq_lifemate_express.py 契约锚）
VOICE_PROB = 0.30
STICKER_PROB = 0.25
EDGE_VOICE = "zh-CN-XiaoyiNeural"    # 晓伊：更活泼元气（2026-10-27 队长拍板换档）


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


# ────────────────────────── 表情包（三轨图库，2026-10-27） ──────────────────────────
# base=只读精选底座 / user=队长上传 / cache=API 抓取经 GLM-4V 视觉质检
# （≥7 分）的沉淀。发送优先级：base+user 随机 → cache → API 搜图（质检门）。

STICKER_TIERS = ("base", "user", "cache")
STICKER_API_ENABLED = True   # API 搜图总开关（False=只走本地三轨）
QA_THRESHOLD = 7             # 视觉质检及格线（1-10 打分制，≥7 才入 cache+发送）
QA_FAIL_RETRY = 1            # 质检不过的重搜次数（重搜仍不过=放弃本次表情）

_QA_PROMPT = (
    "这是一张用于二次元 AI 少女聊天的表情包。请按以下标准打 1-10 分并给出"
    "一句话理由：10=极佳（可爱、清晰、非常契合二次元少女）；7-9=良好（正常"
    "的搞笑/情绪图，画质不错）；4-6=一般（稍微有点老或模糊，勉强能用）；"
    "1-3=极差（古早包浆图、猎奇辣眼睛、带广告、文字杂乱）。"
    "输出格式严格为：分数数字 + 空格 + 一句话理由（例：8 画风可爱清晰）。"
)


def sticker_root():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "stickers")


def pick_sticker(mood=""):
    """三轨挑表情（base/user 优先，cache 次之）：轨内 mood 子目录优先→
    轨根随机。unsorted/ 不进随机池（待人工/视觉分类）。返回绝对路径或
    None（全轨空）。"""
    root = sticker_root()
    mood = (mood or "").strip().lower()
    for tier in STICKER_TIERS:
        tier_dir = os.path.join(root, tier)
        if not os.path.isdir(tier_dir):
            continue
        candidates = []
        mood_dir = os.path.join(tier_dir, mood)
        if mood and os.path.isdir(mood_dir):
            candidates = _list_images(mood_dir)
        if not candidates:
            candidates = _list_images(tier_dir)
        if candidates:
            return random.choice(candidates)
    return None


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


# ────────────────── 表情搜索（切片 b+：主源小尘+备选慕名+自沉淀） ──────────────────

_SEARCH_XCVTS = "https://api.xcvts.cn/api/img/qqbqbss"       # 主源（QQ 官方 gtimg 源）
_SEARCH_MUMING = "https://xiaoapi.cn/v1/meme.php"             # 备选（独立封装站）

# mood → 关键词回退映射（模型标注解析失败时兜底）
MOOD_KEYWORDS = {"neutral": "猫猫", "happy": "开心", "angry": "生气",
                 "sad": "委屈", "shy": "害羞", "sleepy": "困"}


def search_sticker(keyword, page=None):
    """按关键词搜表情图 URL：主源小尘（sticker_url）→ 备选慕名（img_url）。
    page 随机化由调用方传（1/2 页随机避免每次同一张）。失败返回 None。"""
    keyword = (keyword or "").strip()
    if not keyword:
        return None
    pg = page or random.randint(1, 2)
    try:
        import requests
        r = requests.get(_SEARCH_XCVTS, params={"msg": keyword, "page": pg},
                         timeout=10)
        items = (r.json() or {}).get("data") or []
        urls = [x.get("sticker_url") for x in items if x.get("sticker_url")]
        if urls:
            return random.choice(urls)
    except Exception as e:
        print(f"🦊 [express] 主源搜索失败（转备选）: {e}")
    try:
        import requests
        r = requests.get(_SEARCH_MUMING, params={"msg": keyword, "page": pg},
                         timeout=10)
        items = (r.json() or {}).get("data") or []
        urls = [x.get("img_url") for x in items if x.get("img_url")]
        if urls:
            return random.choice(urls)
    except Exception as e:
        print(f"🦊 [express] 备选源也失败: {e}")
    return None


def stash_sticker(url, mood, tier="cache"):
    """异步下载沉淀（三轨制：API 质检通过→cache/<mood>/）。URL md5 去重，
    失败静默。"""
    mood = (mood or "neutral").strip().lower() or "neutral"

    def _dl():
        try:
            import requests
            r = requests.get(url, timeout=15)
            if r.status_code != 200 or not r.content:
                return
            ext = ".gif" if "gif" in r.headers.get("content-type", "") else (
                ".jpg" if "jpeg" in r.headers.get("content-type", "") else ".png")
            d = os.path.join(sticker_root(), tier, mood)
            os.makedirs(d, exist_ok=True)
            import hashlib
            path = os.path.join(d, hashlib.md5(url.encode()).hexdigest()[:12] + ext)
            if os.path.exists(path):
                return   # 已沉淀过（URL md5 去重）
            with open(path, "wb") as f:
                f.write(r.content)
        except Exception as e:
            print(f"🦊 [express] 沉淀失败（静默）: {e}")

    threading.Thread(target=_dl, daemon=True).start()


def qa_score(image_path):
    """GLM-4V 视觉质检（1-10 打分制，队长口径）：返回 (分数, 理由)。
    解析失败默认 5 分（<7=不过）；视觉链异常返回 (0, 原因)。"""
    try:
        from vision_tools import vision_ask_image
        ans = str(vision_ask_image(image_path, _QA_PROMPT) or "")
    except Exception as e:
        return 0, f"视觉链异常: {e}"
    import re
    m = re.search(r"([1-9]|10)", ans)
    score = int(m.group(1)) if m else 5   # 解析失败按 5（<7 拒，宁缺毋滥）
    reason = ans.strip()[:60]
    return score, reason


def _download_temp(url):
    """图片 URL → 临时文件（质检用）。失败返回 None。"""
    try:
        import requests
        r = requests.get(url, timeout=15)
        if r.status_code != 200 or not r.content:
            return None
        fd, path = tempfile.mkstemp(suffix=".img")
        with os.fdopen(fd, "wb") as f:
            f.write(r.content)
        return path
    except Exception:
        return None


def send_api_sticker(keyword, mood="neutral"):
    """API 搜图 + 视觉质检门（≥7 分才发+入 cache）：搜→下载→打分→
    发送+沉淀；不过关重搜，重搜尽仍不过=放弃本次表情（宁缺毋滥）。
    API 双源挂/总开关关 → 降级本地图库。返回是否真发。"""
    if not STICKER_API_ENABLED:
        return send_sticker(mood)
    mood = (mood or "neutral").strip().lower() or "neutral"
    for attempt in range(1 + QA_FAIL_RETRY):
        url = search_sticker(keyword)
        if not url:
            break   # 双源挂：走本地降级
        tmp = _download_temp(url)
        if tmp is None:
            continue
        try:
            score, reason = qa_score(tmp)
            print(f"🦊 [express] 质检 {keyword}#{attempt + 1}: {score} 分（{reason}）")
            if score < QA_THRESHOLD:
                continue   # 不过关：重搜
            ok = send_cq(f"[CQ:image,file={url}]")
            if ok:
                stash_sticker(url, mood, tier="cache")
            return ok
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    print("🦊 [express] 质检无合格图，降级本地图库")
    return send_sticker(mood)
