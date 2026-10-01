# ASSETS.md · 素材清单与版权口径

依据《用户界面设计文档》§5.1 与《开发日志》第八章（合规的觉醒）建立本清单：**代码 MIT 与素材版权分开表述**。

| 文件 | 用途 | 来源与版权 |
| --- | --- | --- |
| `assets/DSniang1.jpg` | 桌宠小挂件形象（网页右下角，`desktop-pet.js` 挂载） | 作者（XUN）提供的官方设定素材：AI 生成 + 人工后期编辑；**著作权归作者，他人不可商用** |
| `assets/DSniang1_full_body_sheet.jpg` | 全身设定图（正视/四分之三侧视/侧视/背视 + 发色/眼瞳/狐耳/狐尾/卫衣色卡） | 同上；仅作设定存档与创作证据归档 |
| `assets/DSniang1_character_sheet.jpg` | 角色设定表（四姿态 + 角色信息：橘狐 AI 助手 / Q 版萌系） | 同上 |
| `assets/pet/normal_half.png` | 桌宠默认半身像（`desktop-pet.js` 双版本状态机 `normal_half`） | 占位：`DSniang1.jpg` 字节副本；正式素材待即梦 AI 生成（透明背景 PNG），著作权口径同上 |
| `assets/pet/normal_full.png` | 桌宠拖拽中全身像（双版本状态机 `normal_full`） | 同上 |

## 使用约定
1. 吉祥物形象（小橘3号 / DS 娘）著作权归作者，**他人不可商用**；本仓库代码 MIT 与此约定互不覆盖。
2. 音效、动图类素材规划采用 CC0 协议（界面文档 §6.2）；当前音效由 WebAudio 程序合成，不依赖外部音频文件，无版权负担。
3. 原始素材不入 `manifest.txt` 核心哈希清单（非代码文件）；替换素材时保持文件名不变即可，无需改代码。
4. 文档口径沿革：界面文档 §5.1 标注"仓库当前无 assets/ 目录，图片将 404——素材补齐与目录规范 🔜 待确认"；本目录即该规划项的落地。

## 透明化说明（2026-10-01 桌宠去白底）

- `assets/DSniang1.jpg` 为 JPG、无透明通道，自带白色背景。代码层面已自动处理：`desktop-pet.js` 注入样式在桌宠容器上声明 `mix-blend-mode: multiply`，白色背景与页面底色相乘后在浅色页面上视觉消失（纯 CSS，零新依赖，无需手动抠图）。SVG 兜底气泡的白色填充同步改为透明填充（`fill="transparent"`），口径一致。
- 已知限制：深色主题下 multiply（乘法混合）会整体压暗形象——这是混合模式的固有特性而非缺陷。
- 追求最佳效果：可自行将 `assets/DSniang1.jpg` 替换为**透明通道 PNG 版本**，**文件名保持不变**即可（见上方使用约定第 3 条，无需改代码）；若使用新文件名，同步修改 `desktop-pet.js` 中的 `/assets/DSniang1.jpg` 引用即可获得不受主题影响的最佳透明效果。

## 双版本状态机说明（2026-10-01 拖拽换装）

`desktop-pet.js` 顶部 `PET_STATE_IMAGES` 常量表即双版本/情绪扩展接口（键 = 状态名，值 = 素材路径）：

| 状态 | 文件 | 用途 |
| --- | --- | --- |
| `normal_half` | `assets/pet/normal_half.png` | **默认**：吸附右下角只露上半身 |
| `normal_full` | `assets/pet/normal_full.png` | **拖拽中**：全身像（松手吸附回边缘自动切回半身） |
| `happy_full` | `assets/pet/happy_full.png` | 预留情绪位：素材尚未生成，放入文件后经 `window.xiaoju3SetPetState('happy_full')` 挂载 |

- **占位现状**：`normal_half.png` / `normal_full.png` 当前为 `assets/DSniang1.jpg` 的字节副本（浏览器按内容解析、与扩展名无关），等待用户用即梦 AI 生成正式素材替换，**文件名保持不变**即可、无需改代码。
- **用户指引（去白边最佳效果）**：用即梦 AI 生成**"透明背景 PNG"**（半身一张、全身一张）直接覆盖上述两个文件名；透明背景 PNG 下 `mix-blend-mode: multiply` 无副作用（透明像素不参与混合、形象原样显示），深色主题也不再压暗。若素材图内仍带白底，multiply 会在浅色页面将其消除、深色主题下压暗（同上节口径）。
- **容错链**：任一状态图 404/加载失败自动回退（状态图 → `normal_half` → `assets/DSniang1.jpg` → 内联 SVG 兜底气泡），任何情况不出现裂图；替换素材保持"半身为上半身构图、全身为完整构图、两图主体大小接近"即可获得自然换装效果。
