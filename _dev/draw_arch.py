# -*- coding: utf-8 -*-
"""AIC 技术方案图 2-1:小橘3号四层系统架构图(PIL 绘制,中文微软雅黑)。"""
from PIL import Image, ImageDraw, ImageFont

W, H = 1560, 1130
FONT = "C:/Windows/Fonts/msyh.ttc"
f_title = ImageFont.truetype(FONT, 44)
f_layer = ImageFont.truetype(FONT, 34)
f_mod = ImageFont.truetype(FONT, 26)
f_small = ImageFont.truetype(FONT, 22)

img = Image.new("RGB", (W, H), "#FBFBFD")
d = ImageDraw.Draw(img)
d.text((W // 2, 56), "小橘3号(xiaoju3-agent)系统架构", font=f_title,
       fill="#1F2A44", anchor="mm")

LAYERS = [
    ("入口层", "#EAF2FF", "#4A7DDB",
     ["QQ(OneBot 11 协议)", "网页控制台 :5003/console", "CLI 终端"]),
    ("大脑层", "#FFF6E8", "#E8963C",
     ["smart_ask 双脑决策:本地 Ollama 优先,云端 DeepSeek 兜底,异常自动热切换",
      "思维链状态机 [思考]/[计划]/[行动] · 熔断器 · 记忆管理"]),
    ("执行层", "#EAF9F0", "#3C9E6E",
     ["15 项工具白名单:文件 · 家电 · 手机(ADB) · 联网搜索 · 系统 · 待办提取",
      "统一门禁:Lv.1~Lv.4 等级矩阵 · 危险实体自动升档 · 儿童锁人在环路"]),
    ("存储层", "#F5EFFF", "#8B6FD8",
     ["todos.db(待办,双版本共享) · long_term.db(长期记忆)",
      "identity.json(身份/记忆) · history_*.json(各通道对话)"]),
]

top = 130
layer_h = 190
gap = 62
for i, (name, bg, border, mods) in enumerate(LAYERS):
    y = top + i * (layer_h + gap)
    d.rounded_rectangle((90, y, W - 90, y + layer_h), radius=18,
                        fill=bg, outline=border, width=3)
    d.text((130, y + layer_h // 2), name, font=f_layer, fill=border, anchor="lm")
    for j, m in enumerate(mods):
        d.text((300, y + 44 + j * 56), m, font=f_mod, fill="#2B2F3A", anchor="lm")
    # 层间箭头
    if i < 3:
        ay1 = y + layer_h + 8
        ay2 = y + layer_h + gap - 8
        cx = W // 2
        d.line((cx, ay1, cx, ay2), fill="#8A93A6", width=4)
        d.polygon([(cx - 12, ay2 - 14), (cx + 12, ay2 - 14), (cx, ay2)],
                  fill="#8A93A6")

# 右侧注释
notes = [
    (top + layer_h + gap // 2, "SSE 五事件流\nthink/tool/answer/done/error"),
    (top + 2 * (layer_h + gap) // 2 + layer_h // 2, None),  # 占位对齐
]
d.text((W - 300, top + layer_h + gap // 2), "五事件 SSE 流\nthink/tool/answer/\ndone/error",
       font=f_small, fill="#5A6478", anchor="mm")
d.text((W - 300, top + 2 * layer_h + gap + gap // 2 + 30),
       "门禁前置\n白名单校验\n熔断保护", font=f_small, fill="#5A6478", anchor="mm")
d.text((W - 300, top + 3 * layer_h + 2 * gap + gap // 2),
       "拆库设计\ntodos 双版本共享\n灵魂各自独立", font=f_small, fill="#5A6478", anchor="mm")

d.text((W // 2, H - 36), "全仓 1862 项自动化测试 · v1.0.4 · 开源:github.com/Xun201/xiaoju3-agent",
       font=f_small, fill="#8A93A6", anchor="mm")

img.save("F:/Orangepi_number3/docs/img/architecture.png")
print("architecture.png 已生成", img.size)
