# -*- coding: utf-8 -*-
"""构建资产生成器（安装器方案步 B1）：版本资源 + exe 图标。

build_exe.bat 调用；也可独立运行（python make_build_assets.py）。产物：
- version_info.txt    PyInstaller 版本资源（版本号抓自 xiaoju3.py 的
                      XIAOJU3_VERSION——单一事实源；抓取失败退出码 1，
                      不带版本出包）
- assets/xiaoju3.ico  exe/安装器图标（源 assets/pet/normal_half.png 方形
                      中心裁切 + 圆角透明；现素材为 JPG 字节占位，
                      真透明 PNG 落地后重跑本脚本即换）

version_info.txt 为构建中间产物（gitignore），不入仓库。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION_RE = re.compile(r'XIAOJU3_VERSION\s*=\s*"([^"]+)"')


def grab_version():
    """从 xiaoju3.py 抓版本号（单一事实源）；抓不到退出码 1。"""
    with open(os.path.join(HERE, "xiaoju3.py"), encoding="utf-8") as f:
        m = VERSION_RE.search(f.read())
    if not m:
        print("❌ 未能从 xiaoju3.py 抓取 XIAOJU3_VERSION——不带版本不出包。",
              file=sys.stderr)
        sys.exit(1)
    return m.group(1)


def version_tuple(version):
    """'1.0.0' → (1, 0, 0, 0)（VSVersionInfo 需四段整数）。"""
    parts = [int(x) for x in version.split(".") if x.strip().isdigit()]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def write_version_info(version):
    """生成 version_info.txt（PyInstaller VSVersionInfo 格式，
    中文语言块 080404b0 / Translation 2052-1200）。"""
    filevers = version_tuple(version)
    content = (
        "# UTF-8\n"
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers={filevers},\n"
        f"    prodvers={filevers},\n"
        "    mask=0x3f,\n"
        "    flags=0x0,\n"
        "    OS=0x40004,\n"
        "    fileType=0x1,\n"
        "    subtype=0x0,\n"
        "    date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo(\n"
        "      [\n"
        "      StringTable('080404b0', [\n"
        "        StringStruct('CompanyName', 'XUN'),\n"
        "        StringStruct('FileDescription', '小橘3号 · 家庭私人 AI 智能体'),\n"
        f"        StringStruct('FileVersion', '{version}'),\n"
        "        StringStruct('InternalName', 'xiaoju3'),\n"
        "        StringStruct('LegalCopyright', 'Copyright (C) 2026 XUN'),\n"
        "        StringStruct('OriginalFilename', 'xiaoju3.exe'),\n"
        "        StringStruct('ProductName', '小橘3号'),\n"
        f"        StringStruct('ProductVersion', '{version}')])\n"
        "      ]),\n"
        "    VarFileInfo([VarStruct('Translation', [2052, 1200])])\n"
        "  ]\n"
        ")\n"
    )
    out = os.path.join(HERE, "version_info.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    return out


def make_icon():
    """生成 assets/xiaoju3.ico：源图方形中心裁切 → 256px → 圆角透明 →
    多尺寸（16/32/48/64/128/256）。现素材 JPG 字节占位无 alpha，圆角外
    走透明兜底；真透明 PNG 落地后重跑即换。"""
    from PIL import Image, ImageDraw

    src = Image.open(os.path.join(HERE, "assets", "pet",
                                  "normal_half.png")).convert("RGB")
    side = min(src.size)
    left = (src.width - side) // 2
    top = (src.height - side) // 2
    square = src.crop((left, top, left + side, top + side)).resize(
        (256, 256), Image.LANCZOS)
    mask = Image.new("L", square.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 255, 255), radius=48,
                                           fill=255)
    square.putalpha(mask)
    out = os.path.join(HERE, "assets", "xiaoju3.ico")
    square.save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                            (128, 128), (256, 256)])
    return out


def main():
    version = grab_version()
    info_path = write_version_info(version)
    print(f"✅ version_info.txt 已生成（版本 {version}）：{info_path}")
    icon_path = make_icon()
    print(f"✅ assets/xiaoju3.ico 已生成：{icon_path}"
          f"（{os.path.getsize(icon_path)} 字节）")


if __name__ == "__main__":
    main()
