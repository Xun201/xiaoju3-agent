# 加速球口径修复设计：⌄ 缩桌宠成球（球跟桌宠走），控制台永不缩

> 状态：设计稿（2026-10-03），**未动代码**。按「先设计稿、后动代码」老规矩执行。
> 侦察结论（已闭，见开发记忆）：缩球逻辑只有一套——`#console-minimize` ⌄ 按钮 →
> `setConsoleMinimized(true)` → body 挂 `xiaoju3-minimized` 类 → CSS 隐藏
> `.sidebar`/`.chat-area` 并显示球；桌宠侧零逻辑。根因 = 产品口径（2026-10-02 桌宠
> 回归）与旧实现（任务 7"网页内缩略模式"，控制台整体缩球）拧反。
> **用户拍板口径**：① 不保留控制台缩球——⌄ 只缩桌宠，控制台永远显示；
> ② 桌宠缩成球后，球在桌宠原位（球跟着桌宠走，不固定右下角）。

## 0. 一句话

把"最小化"的定义从**控制台缩球**改为**桌宠缩球**：`xiaoju3-minimized` 类退役，
新类 `xiaoju3-pet-minimized` 只做两件事——隐藏桌宠节点、显示球；球的位置在进入
最小化时由 JS 从桌宠单例实时取坐标写入（球中心对齐桌宠中心），控制台侧
`.sidebar`/`.chat-area` 的隐藏规则整条删除。

## 1. 语义层：函数与类名

| 项 | 旧 | 新 | 理由 |
|---|---|---|---|
| 函数 | `setConsoleMinimized(minimized)` | **`setPetMinimized(minimized)`** | 名字里 "Console" 与新语义（最小化的对象是桌宠）拧着——正是本次 bug 的读码陷阱；改名一次把语义钉死。调用点仅 3 处（⌄ 按钮 / 球点击 / showFirstRun 防御段——见 §5，该段整体删除后剩 2 处），改名成本可控 |
| 类名 | `xiaoju3-minimized` | **`xiaoju3-pet-minimized`** | 同上；且避免与未来可能的"控制台最小化"语义撞名 |
| 常量 | `MINIMIZE_CLASS` | **`PET_MINIMIZE_CLASS`** | 随类名 |

**连锁影响（零触碰锚）**：`tests/test_first_run.py:307-313 / 570-577` 的零触碰锚
断言"首装块内不得出现 `classList.add/remove('xiaoju3-minimized'`"——类名退役后旧
字面量永假，锚会"自动绿"但失去防护。**必须同步把锚内字符串改为
`'xiaoju3-pet-minimized'`**，继续锁"首装流程不得直操桌宠缩球类"。

## 2. CSS 层：类效果重定义（index.html）

- **整条删除**（旧口径核心）：`body.xiaoju3-minimized > .sidebar, body.xiaoju3-minimized > .chat-area { display: none; }`（:443-444）——控制台永不隐藏。
- 改写 :462 → `body.xiaoju3-pet-minimized #xiaoju3-ball { display: block; }`。
- **新增**：`body.xiaoju3-pet-minimized #xiaoju3-root { display: none; }`——桌宠隐藏
  走类驱动（与"球显隐由 CSS 类管"的既有家规一致，desktop-pet.js 不做 display 控制）。
  桌宠节点 = desktop-pet.js 运行时注入 `#xiaoju3-root`（index.html:591-592 挂载点）。
- **球定位（口径②核心）**：静态 CSS 做不到"跟桌宠走"——桌宠坐标是运行时动态值
  （拖拽/吸附/出生位都变）。方案：球 CSS 的 `right: 24px; bottom: 24px` 默认位
  **保留**（仅作 JS 未生效时的视觉兜底），进入最小化时由 JS 写
  `style.left/top` 并置 `right/bottom = auto`（复用既有 `applyBallPos` 同款写法），
  坐标取"桌宠当时原位的中心对齐"（见 §3 接口）。每次**进入**最小化态都重放一次
  （桌宠位置变了球就跟到新原位）；最小化态内的 resize 重钳制沿用既有逻辑
  （console.js:1427-1431，改读新常量）。

## 3. 桌宠侧：坐标来源与响应

**侦察实锤**：桌宠节点 position: fixed（desktop-pet.js:100），逻辑坐标在模块内
变量 `state = { scale, left, top }`（:348），`express()`（:353-356）把 state 写到
`root.style.left/top`；拖拽/吸附/翻转全在 desktop-pet.js 内部闭环；**坐标不持久化**
（刷新即回出生位 initPosition()：贴右缘、底边停在输入框上方，:379-402）。
全局单例 `window.__xiaoju3Pet` 已存在（test_cot_render_v2 有锚锁定）。

- **响应方式：纯 CSS 类驱动，desktop-pet.js 零显示控制**——`display:none` 的节点
  `state.left/top` 从未改变，移除类即原位恢复，**无需记录原位**。
- **唯一 JS 新增：单例暴露坐标接口** `__xiaoju3Pet.getPos()` →
  `{ x: state.left, y: state.top, w: <当前宽>, h: <当前高> }`（w/h 取
  `getBoundingClientRect`，注意 left 有 .16s 过渡但 style.left 是即时投影，
  state 即真源）。console.js 拿到后算球位：`ballLeft = x + (w-60)/2`、
  `ballTop = y + (h-60)/2`（球中心对齐桌宠中心），再过 `clampBallPos` 钳制视口。
- **实现注意（风险点）**：`display:none` 下 `getBoundingClientRect` 返回 0——
  桌宠隐藏期间的 `initPosition()`（img load / resize 触发）须早退或跳过重算，
  防止隐藏态用 0 尺寸算出垃圾坐标、恢复后桌宠跳位。

## 4. 交互层

| 交互 | 旧行为 | 新行为 |
|---|---|---|
| ⌄ 按钮（#console-minimize） | `setConsoleMinimized(true)`，toast「已缩成加速球，点击小球恢复」 | `setPetMinimized(true)`；title 改「最小化：桌宠缩成加速球」；toast 改「桌宠已缩成加速球，点击小球恢复」 |
| 球点击（未拖动） | 展开控制台 | `setPetMinimized(false)` 恢复桌宠（球隐、桌宠在原位重现） |
| 球拖拽 | 位移平方>9 判拖，松手存 `xiaoju3_ball_pos` 持久化 | **保留拖拽**（最小化态内自由摆位），**持久化退役**：每次进入最小化都以桌宠实时原位重放，拖拽位置不跨会话记忆——口径②"球跟着桌宠走"的本义即位置不由球记忆。`loadBallPos/saveBallPos` 与 `BALL_POS_KEY` 整体退役删除 |

## 5. 首装浮层兼容

侦察实锤：首装流程**碰过**最小化状态——console.js:1494-1497（showFirstRun 开头）：

```js
// 防御：最小化态先展开（复用既有幂等函数，不直接操作 body 类）
if (document.body.classList.contains('xiaoju3-minimized')) {
    setConsoleMinimized(false);
}
```

该防御的目的是"控制台缩球后浮层弹在看不见的主 UI 上"。**新口径下控制台永不缩，
防御对象消失 → 这 4 行整体删除**（连同注释）。首装链其余（status→probes∥
installer_report→浮层渲染）零变化；`test_first_run.py` 零触碰锚改锁新类名后
继续有效（首装块本就只 contains 不 add/remove，删除后连 contains 也没有）。

## 6. 测试计划（逐条：改 / 留 / 增）

**test_web_ux.py BallWidgetTests（282 起）**：

| 用例 | 处置 |
|---|---|
| test_minimize_button_in_header | **留**（⌄ 存在+接线顺序锚不变；title 文案未锁，改 title 自由） |
| test_ball_markup_with_mascot | **留**（球节点+normal_half 头像，口径无关） |
| test_ball_avatar_fallback_chain | **留**（兜底链与显隐无关） |
| test_ball_css_round_60px_hidden_by_default | **改**：删 `right: 24px / bottom: 24px` 断言（默认位降级为兜底，仍可保留断言，二选一）；**删** `body.xiaoju3-minimized > .sidebar / > .chat-area` 两条隐藏断言；**增** `body.xiaoju3-pet-minimized #xiaoju3-ball` 与 `body.xiaoju3-pet-minimized #xiaoju3-root { display: none; }` 正向锚 |
| test_toggle_class_and_idempotency | **改**：`MINIMIZE_CLASS = 'xiaoju3-pet-minimized'`、`function setPetMinimized`、toggle 行同步 |

**test_cot_render_v2.py 桌宠回归组（258 起）**：

| 用例 | 处置 |
|---|---|
| test_desktop_pet_script_enabled / test_pet_file_kept_on_disk_with_fallback_chain / test_no_other_floating_pet_elements | **留**（加载面/文件本体/唯一静态 img，与口径无关） |
| test_mount_comment_updated_to_regression | **改**：`assertIn("仅最小化态显示", html)` → 注释改写后同步新口径短语（如「最小化=桌宠缩球」） |
| test_ball_kept_in_html | **改**：`body.xiaoju3-minimized #xiaoju3-ball` → 新类名 |
| test_ball_logic_kept_in_console_js | **改**：字面锁 `setConsoleMinimized(false);   // 未拖动＝点击展开回完整控制台` → 新函数名+新注释；`localStorage.setItem(BALL_POS_KEY…)` 断言随持久化退役**删除**；其余（拖拽阈值/setPointerCapture/console-minimize）保留 |

**test_first_run.py:307-313 / 570-577**：**改**——反向锚字符串 `'xiaoju3-minimized'`
→ `'xiaoju3-pet-minimized'`（防回归语义不变：首装块不得直操桌宠缩球类）。

**新增锚（锁新口径）**：① 控制台永不缩反向锚：index.html 全文
`assertNotIn("xiaoju3-minimized >")`（旧规则不得回流）；② 球跟桌宠原位：
console.js 锁 `getPos()` 调用 + 进入最小化路径含钳制重放（函数名级锚）；③
`window.__xiaoju3Pet` 单例暴露 `getPos` 接口锚（desktop-pet.js）；
④ ⌄ 按钮 title 新文案锚。

## 7. 验收

**离线可测（unittest 静态锚）**：§6 全部——类效果重定义、旧规则禁回流、接口存在、
按钮接线、首装块零触碰。全仓 1613 不减（改锚等量替换）。

**必须真机（桌面窗口，BUILD_BRIEF 纪律）**：

1. 拖桌宠到非常规位置（如左上）→ 点 ⌄ → 桌宠消失、球出现且**中心对齐桌宠原位**、控制台照常显示；
2. 点球 → 桌宠在原位恢复（球隐）；
3. 最小化态拖球到别处 → 点球恢复 → 再点 ⌄ → 球**重新出现在桌宠当前原位**（拖拽不跨会话）；
4. 首装态（删 .env）弹浮层时点 ⌄ → 浮层照常、桌宠缩球互不干扰；
5. 窗口 resize 后重复 1 ——球钳制在视口内。

**离线测不了**：像素级"球心=桌宠心"的对齐观感、拖拽手感、隐藏/恢复的过渡动画。
