# 启动体验优化设计稿（快速出界面 + 骨架屏，学 QQ/微信）

> 状态：**设计稿，待评审**（本轮零代码改动）
> 日期：2026-10-04
> 诉求：不要"优化到 5.8s"，要"感知上秒开"——参考 QQ/微信：先出主界面，功能后台加载
> 关联：docs/STARTUP_OPTIMIZATION_DESIGN.md（import 剖析与延迟加载，共享时序数据）

---

## 一、现状侦察（实测时序，v13 冻结包）

```
T0        双击/Start-Process
+0→1.9s   onefile 解包 173.5MB（85MB 压缩态；playwright 占 62%）
+1.9s     主进程 python 起 → import desktop_launcher（顶层拖入 dashboard 全链 ≈1.1s）
+~3.8s    webview.create_window(占位页「🍊 正在启动主程序…」)  ← 窗口出现（实测 webview2 链 @5.4s）
          并 spawn dashboard 子进程（自身再走 ≈1.1s import + Flask）
+7.7s     5003 就绪 → wait_for_dashboard_ready 通过 → load_url 切控制台
+7.7s+    控制台前端加载，fetch 全通
```

### 1.1 现状结论（三问三答）

| 问 | 答 | 证据 |
|---|---|---|
| 有没有 splash？ | **有雏形**——desktop_launcher 占位窗（PLACEHOLDER_HTML 深色"🍊 正在启动主程序…"），先出窗后导航（端口修复 P2） | desktop_launcher.py:92/376 |
| 为什么 5.4s 才见窗？ | 占位窗创建排在 **import desktop_launcher 之后**——顶层 `from xiaoju3_dashboard import app`（≈1.1s 全链）+ 解包 1.9s 全在它前面 | desktop_launcher.py:70 顶层 import；STARTUP_OPTIMIZATION §1.2 |
| 首次请求失败怎么显示？ | 控制台切换发生在**服务就绪后**（wait_for_dashboard_ready），正常无失败窗口；边缘竞态下 fetchStatus/loadTodos 失败仅 console.error，UI 显示 "--%" / "暂无待办"，**2s/30s 轮询自动自愈**（无"失败"红字，也无"加载中"提示） | console.js fetchStatus/loadTodos catch |

---

## 二、方案评估

### 方案 A：启动画面（Splash）——**已存在雏形，本稿做"提前 + 增强"**

| 项 | 内容 |
|---|---|
| 现状 | 占位窗 ≈3.8s 才出现——**被顶层 dashboard import 拖住** |
| 增强 1（提前） | **desktop_launcher 顶层 `from xiaoju3_dashboard import app` 移除**（STARTUP_OPTIMIZATION §2.2）——占位窗提前 ≈0.7-1.1s；收录已由 spec hiddenimports 静态保证，:435 serve 分支已有延迟导入先例 |
| 增强 2（品牌化骨架） | 占位页升级：深色底 + 橘色 fox 元素 + 三步进度文案（"解包资源 → 启动服务 → 打开界面"——进度由 launcher 轮询状态驱动，纯静态文案亦可） |
| 改动量 | desktop_launcher.py ~15 行（import 移除 + PLACEHOLDER_HTML 文案） |
| 风险 | 低——延迟导入有 :435 先例；收录走 spec 已核 |

### 方案 B：骨架屏（Skeleton）——**控制台切换后场景弱化，做"加载态小补"**

| 项 | 内容 |
|---|---|
| 现状 | 控制台在服务就绪后才被 load_url 加载 → 首屏 fetch 即通，骨架屏**没有失败场景可救** |
| 边缘场景 | 轮询竞态/服务冷启动卡顿时，卡片显示 "--%" / "暂无待办" 停留 ≤2s/30s |
| 小补 | fetchStatus/loadTodos 失败 catch 里把文本置"连接中…"（1-2 行），失败态不再像"没数据" |
| 改动量 | console.js ~4 行 |
| 风险 | 无 |

> 结论：**完整骨架屏（灰块+淡出）不做**——控制台加载时后端已就绪，真实内容即到，骨架无载体；"占位窗"已承担骨架职责（增强走 A）。

### 方案 C：请求重试 + 加载态——**轮询机制已天然自愈，仅补提示文案**

| 项 | 内容 |
|---|---|
| 现状 | fetchStatus 2s 轮询 / loadTodos 30s 轮询——失败后下一轮自动重试，**自愈已存在** |
| 小补 | 与 B 合并（"连接中…"文案 + 轮询不变） |
| 结论 | 并入 B，独立方案不立 |

---

## 三、推荐组合与预期时间线

**推荐 = A（占位窗提前 + 品牌化）+ B/C 小补（失败加载态文案）**，与 STARTUP_OPTIMIZATION_DESIGN（vision_tools/延迟加载，压服务就绪）**互补不冲突**——两者作用于不同段（本稿改"窗出现前"，彼稿改"服务就绪前"）。

| 时点 | 现状 | 组合实施后 |
|---|---|---|
| 窗口出现（占位/骨架） | ≈3.8-5.4s | **≈2.6-2.9s**（解包 1.9 + 轻量 import ≈0.2 + create_window ≈0.4） |
| 控制台可见 | 7.7s | 7.7s（服务就绪决定；A 不改变此值） |
| 完全就绪 | 7.7s | **≈6.5-7.1s**（STARTUP_OPTIMIZATION vision_tools −0.6~1.2s） |
| 失败观感 | 静默停旧值 | "连接中…"提示 |

> 若要"控制台可见"也进 5s 档：需叠加 **onedir**（解包归零，STARTUP_OPTIMIZATION 方案 1）——分发形态变 zip，**另行拍板**，不在本稿。

---

## 四、改动清单汇总

| 文件 | 改动 | 归属 |
|---|---|---|
| desktop_launcher.py | 顶层 dashboard import 移除（≈15 行内）+ 占位页文案升级 | A 增强 1/2 |
| console.js | fetchStatus/loadTodos 失败 catch 置"连接中…"（~4 行） | B/C 小补 |
| xiaoju3.spec | 无改动（hiddenimports 已静态收录） | — |
| tests | desktop_launcher 顶层 import 静态锚（防回流）+ console.js 失败文案锚 | 回归 |

（vision_tools 延迟导入属 STARTUP_OPTIMIZATION_DESIGN §2.1，彼稿文件。）

## 五、测试影响

- 全仓 1749 只增不减；新增锚 2-3 条（见上）
- 既有 P2 端口修复锚（占位窗→就绪导航链）不受影响（只改文案与 import 位置，链路不变）

## 六、待拍板

1. A 增强与 B/C 小补是否照此实施（推荐：是）
2. 占位页品牌化文案的具体措辞（可先按"三步进度"文案实施，视觉后续替换）
3. onedir 是否立项（影响"控制台可见 7.7s"这条硬线，独立决策）
