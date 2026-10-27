# -*- coding: utf-8 -*-
"""表情包图库一键安装（#354 切片 b 收尾，2026-10-27）。

用法：
  python _dev/install_sticker_pack.py <zip包或文件夹> [--mood-by-name] [--vision]

行为：
- 输入 zip：解压到临时目录后按文件夹处理；
- 遍历输入内全部图片（png/jpg/jpeg/gif/webp）；
- 分类优先级：
  ① 路径中含情绪目录名（happy/sad/shy/angry/neutral/开心/生气/委屈/害羞…）
     → 映射到 stickers/<tier>/<mood>/（tier 由路径含 base/user/cache 判定，
     默认 user）；
  ② 文件名含情绪关键词（中英）→ 同上；
  ③ [ --vision ] 视觉分类：GLM-4V 按 8 类情绪判断（每图一次调用，较慢）；
  ④ 兜底 → stickers/user/unsorted/（不进发送池，人工/后续视觉整理）；
- 去重：目标库内按内容 md5（跨格式同图不重复）；同名文件覆盖确认。
- 只读源：绝不修改/删除输入文件。

示例：
  python _dev/install_sticker_pack.py D:\\downloads\\表情包.zip
  python _dev/install_sticker_pack.py D:\\pics --mood-by-name --vision
"""
import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import zipfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_STICKERS = os.path.join(PROJECT_ROOT, "agent_state", "plugins",
                               "qq_lifemate", "stickers")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

# 情绪目录（三轨下统一）：目录名白名单
MOODS = ("happy", "sad", "shy", "angry", "neutral", "sleepy")

# 中文情绪 → 目录名
CN_MOOD = {"开心": "happy", "高兴": "happy", "笑": "happy", "可爱": "happy",
           "难过": "sad", "伤心": "sad", "哭": "sad", "委屈": "sad",
           "害羞": "shy", "脸红": "shy", "生气": "angry", "愤怒": "angry",
           "困": "sleepy", "累": "sleepy", "无语": "neutral", "中性": "neutral"}

# 英文/拼音文件名关键词 → 目录名
EN_MOOD = {"happy": "happy", "smile": "happy", "laugh": "happy", "cute": "happy",
           "sad": "sad", "cry": "sad", "shy": "shy", "angry": "angry",
           "mad": "angry", "sleepy": "sleepy", "tired": "sleepy",
           "neutral": "neutral"}

VISION_PROMPT = (
    "这是一张 QQ 聊天表情包。判断它的主导情绪，只输出一个英文单词，"
    "从这些里选：happy / sad / shy / angry / sleepy / neutral。")


def file_md5(path):
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_by_path(rel_path):
    """按相对路径+文件名猜 mood。返回目录名或 None。"""
    low = rel_path.lower()
    for tier in ("base", "user", "cache"):
        if ("/%s/" % tier) in low.replace("\\", "/").lower():
            pass  # tier 判定另做
    for cn, mood in CN_MOOD.items():
        if cn in rel_path:
            return mood
    for en, mood in EN_MOOD.items():
        if en in os.path.basename(low):
            return mood
    return None


def classify_by_vision(path):
    """GLM-4V 视觉分类（--vision 时）。失败返回 None。"""
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from vision_tools import vision_ask_image
        ans = str(vision_ask_image(path, VISION_PROMPT) or "").lower()
        for mood in MOODS:
            if mood in ans:
                return mood
    except Exception as e:
        print(f"  ⚠️ 视觉分类失败（跳过）: {e}")
    return None


def iter_images(root):
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(IMAGE_EXTS):
                yield os.path.join(dirpath, name)


def existing_md5s():
    """目标库现有图 md5 集合（跨 tier 全扫，内容级去重）。"""
    seen = set()
    if not os.path.isdir(PLUGIN_STICKERS):
        return seen
    for path in iter_images(PLUGIN_STICKERS):
        try:
            seen.add(file_md5(path))
        except OSError:
            pass
    return seen


def install(src, use_vision=False, tier_default="user"):
    if not os.path.exists(src):
        print(f"❌ 输入不存在：{src}")
        return 1
    work = src
    tmp = None
    if src.lower().endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="lm_pack_")
        print(f"📦 解压 {src} → {tmp}")
        with zipfile.ZipFile(src) as zf:
            zf.extractall(tmp)
        work = tmp
    seen = existing_md5s()
    counts = {"installed": 0, "dup": 0, "unsorted": 0, "fail": 0}
    for img in iter_images(work):
        rel = os.path.relpath(img, work)
        digest = file_md5(img)
        if digest in seen:
            counts["dup"] += 1
            continue
        mood = classify_by_path(rel)
        if not mood and use_vision:
            mood = classify_by_vision(img)
        tier = tier_default
        low = rel.replace("\\", "/").lower()
        for t in ("base", "user", "cache"):
            if ("/%s/" % t) in low:
                tier = t
                break
        if not mood:
            mood_dir = os.path.join(PLUGIN_STICKERS, tier, "unsorted")
            counts["unsorted"] += 1
        else:
            mood_dir = os.path.join(PLUGIN_STICKERS, tier, mood)
        os.makedirs(mood_dir, exist_ok=True)
        ext = os.path.splitext(img)[1].lower()
        dst = os.path.join(mood_dir, digest[:12] + ext)
        shutil.copy2(img, dst)
        seen.add(digest)
        counts["installed"] += 1
        print(f"  ✅ {rel} → {os.path.relpath(dst, PLUGIN_STICKERS)}")
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n📊 完成：安装 {counts['installed']} / 去重跳过 {counts['dup']} "
          f"/ 未分类 {counts['unsorted']} / 失败 {counts['fail']}")
    print(f"   图库根：{PLUGIN_STICKERS}")
    print("   提示：unsorted/ 不进发送池；可人工挪到情绪目录或跑 --vision 重分。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="qq_lifemate 表情包图库一键安装")
    ap.add_argument("source", help="zip 包或图片文件夹")
    ap.add_argument("--vision", action="store_true",
                    help="用 GLM-4V 视觉分类无信息的图（每图一次调用）")
    ap.add_argument("--tier", default="user", choices=("base", "user", "cache"),
                    help="默认轨（路径未指明时），默认 user")
    args = ap.parse_args()
    return install(args.source, use_vision=args.vision,
                   tier_default=args.tier)


if __name__ == "__main__":
    sys.exit(main())
