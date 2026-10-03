# 安装器步 A4 实施设计：引导覆盖层 + complete 端点 + 自启键

> 状态：设计稿（2026-10-03），**未动代码**。总方案 `docs/INSTALLER_PLAN.md`，前置设计 `docs/INSTALLER_STEP_A_DESIGN.md`（§3.4 生效机制已定稿：完成页 window.close() 关窗重开）。
> 前置已落地：A1 版本下发、A2 `save_env_file`（四防线）、A3 探针模块与两端点。

---

## 一、引导覆盖层 UI（前端）

### 1.1 地形与共存方式
- `console.js`（1459 行）是 **IIFE 单例**：函数平铺 + 事件绑定 + `setInterval(fetchStatus, 2000)`；已有 `showToast()` 可复用为操作反馈。
- `index.html` **无 overlay/modal 先例**，但有既有约定 `[hidden] { display: none !important; }`（:61）——覆盖层显隐**走 hidden 属性**，与加速球最小化态同口径。
- 共存方案：`index.html` 新增 `<div id="first-run-overlay" hidden>`（全屏遮罩 + 引导卡片，`position: fixed` 置顶），默认 `hidden`——**非 first_run 场景零视觉变化**；`console.js` IIFE 内新增 `initFirstRun()`，在启动序列调用一次。

### 1.2 触发时机：自动弹（判定在 A3 端点）
`initFirstRun()`：`GET /api/first_run/status` → `data.first_run === true` 才移除 overlay 的 `hidden`（首次可见时再 `GET /api/first_run/probes` 渲染探针亮灯，避免非引导用户白跑探针）。完成/跳过后重新 `hidden` + `localStorage(xiaoju3_first_run_done)` 兜底防闪（单一事实源仍是 `.env` 文件存在性，storage 只防"写盘前后端未重启"的闪烁）。

### 1.3 卡片内容（探针亮灯 + 5 键表单）
- 四探针行：名称 + 🟢/🟡/🔴（`ok` 布尔 + `detail` 文案直出，A3 聚合顺序 ollama→napcat→home_assistant→deepseek）。
- 表单 5 键（A 设计稿 §3.3 定稿）：`DEEPSEEK_API_KEY`（password 输入框 + 本地格式校验 sk- 前缀，红字提示不发送）、`HA_URL`、`HA_TOKEN`（可选项，留空即灰显该项）、`LOCAL_URL`（预填 `http://127.0.0.1:11434/api/chat`）、`USER_CITY`（可选）。
- 自启勾选：「开机自动启动小橘3号」checkbox（默认勾选）→ 随 complete 提交。
- 底部按钮：「完成并保存」（提交）与「跳过，稍后在 .env 配置」（只记 done 不写盘）。
- 完成成功 → `showToast("配置已保存")` + 按 §3.4 弹「关闭窗口重新打开即生效」→ `window.close()` 按钮。
- 涉及文件：`index.html`（overlay DOM + CSS ~30 行）、`console.js`（`initFirstRun`/`renderProbes`/`submitFirstRun` 三函数 ~80 行）。

## 二、/api/first_run/complete 端点（后端落盘）

- 路由：`POST /api/first_run/complete`，body `{"env": {...≤5 键}, "autostart": bool}`。
- 落盘：`save_env_file(body["env"])`——**白名单复用 A2 的 39 键过滤**，前端多塞键自动进 skipped；表单暴露面就是前端那 5 键（后端不重复设限，白名单是硬边界）。其余配置走 `.env.example` 手工路径（安装器 [Files] 已装该模板）。
- 自启：`body["autostart"] === true` 时调 `autostart.write()`（见三）；false 时**不动注册表**（不主动删——用户可能装时已由 Inno 写入，程序侧只做增量变更）。
- first_run 翻转：`.env` 一旦落盘，`is_first_run()` 自然返回 false——**无需任何状态重置代码**（A3 判定即文件存在性）。
- **失败反馈**：`save_env_file` 抛 `OSError`（A2 设计）→ 端点捕获取 `500` + `{"code": 500, "error": "配置保存失败：<原错误>"}`——前端红字展示原文件未损（A2 原子性保证）；`autostart.write()` 失败**不落 500**（自启非关键路径），返回体带 `warning` 字段。
- 返回体：`{"code": 200, "data": {"written": [...], "skipped": [...], "first_run": false, "warning": str|None}}`。

## 三、自启键读写（注册表 HKCU Run）

### 3.1 具体调用（新 `autostart.py`，winreg 延迟 import + 平台守卫）
`SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"`，`VALUE_NAME = "Xiaoju3"`：

- **read**：`winreg.OpenKey(HKCU, SUBKEY)` → `QueryValueEx(k, VALUE_NAME)` → 返回命令串或 None（`FileNotFoundError` 吞掉）。
- **write**：`winreg.CreateKey(HKCU, SUBKEY)` → `SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, target_command())` → `CloseKey`。
- **remove**：`winreg.OpenKey(HKCU, SUBKEY, 0, winreg.KEY_SET_VALUE)` → `DeleteValue(k, VALUE_NAME)`（不存在吞 `FileNotFoundError`）→ 幂等删除。
- **is_enabled**：`read() is not None`。

### 3.2 target_command()（写什么命令）
- frozen（exe）：`sys.executable`（desktop 角色免参数——开机即弹控制台窗口）。
- 非 frozen（python 直跑）：复用 `desktop_launcher._windowless_python()` + `desktop_launcher.py` 全路径（pythonw 无黑框，口径与启动链一致）。
- **平台守卫**：模块内 `winreg` 延迟 import + 四函数入口 `if os.name != "nt": return False/None`——香橙派 Linux 侧零操作（项目双平台口径，与 `ensure_napcat` 的 POSIX 跳过同款）。

### 3.3 触发点分工
- **装时写**：Inno `[Registry]`（安装器层职责，INSTALLER_PLAN §5 已定）——Inno 与程序写同一键同一名，安装器装完用户勾选即生效。
- **程序内改**：A4 的 complete 勾选（首装）/后续设置页（复用同四函数）。
- **卸载清**：Inno `[UninstallRun]` 删值（容错）。
- 程序内 write 与 Inno 写入冲突：同键同格式，最后写入者胜，无互斥问题。

## 四、新增测试清单（tests/test_first_run.py 续加 + 新 autostart 测试）

| # | 用例 | 归属 |
|---|---|---|
| 1 | complete 成功：tmp `.env` 落盘断言（5 键内容）+ 返回 written/first_run=false | 后端 |
| 2 | complete 白名单：body 塞非法键 → skipped、不落盘 | 后端 |
| 3 | complete 失败：mock save_env_file 抛 OSError → 500 + error 中文串 + 原文件不损 | 后端 |
| 4 | complete 自启：autostart=true 调 `autostart.write`（mock），false 不调 | 后端 |
| 5 | autostart 四函数：mock winreg（write 用 CreateKey/SetValueEx 断言、remove 幂等删不存在值、read 命中/未命中） | autostart |
| 6 | autostart 平台守卫：os.name != "nt" 时全函数零 winreg 调用 | autostart |
| 7 | autostart target_command：frozen（mock sys.frozen/executable）与非 frozen 两形态 | autostart |
| 8 | UI 静态锚：index.html 含 `first-run-overlay` 与 5 表单键 name/id；console.js 含 `initFirstRun` 调用；overlay 默认带 `hidden`（非引导零视觉变化锚） | 前端 |
| 9 | 非引导零变化总锚（复用 A1 口径）：`ENV_FILE` 存在时 /console 页与 /api/status 输出不变 | 前端 |

预估 +9~11 用例。

## 五、子步拆分（每子步收尾全仓全绿、可独立提交）

| 子步 | 内容 | 文件 | 预估用例 |
|---|---|---|---|
| **A4a** | autostart.py（四函数 + 平台守卫 + target_command）+ complete 端点 + 测试#1-7 | autostart.py、xiaoju3_dashboard.py、tests/test_first_run.py | +7 |
| **A4b** | 引导覆盖层（index.html overlay/CSS + console.js 三函数）+ 测试#8-9 | index.html、console.js、tests/test_first_run.py | +2~4 |

顺序 A4a → A4b（UI 依赖端点）。A4b 收尾即步 A 收官（A1-A4 全落）。

## 六、最高风险子块判断：**UI 覆盖层（A4b）**

理由：complete 后端是 A2 已验证函数的薄包装（风险=参数校验面小，且 OSError 语义已在 A2 锁死）；autostart 是全新但**纯函数式**的小模块（winreg 可 mock、平台守卫简单）。A4b 则要**在 1459 行 IIFE 里动刀**：覆盖层显隐与既有 `[hidden]` 兜底、加速球 `body.xiaoju3-minimized` 口径、2 秒轮询的交互时序都可能相互影响，且 **UI 行为不可离线单测**（只能静态锚 + 真机看）——视觉回归与脚本错误（改崩 console.js 全控制台瘫痪）的风险都在这块。缓解：overlay 全部逻辑收敛在独立三函数、不碰既有函数体；静态锚锁定 DOM 存在性；真机验收列冒烟项（首启弹层/跳过不再弹/完成关窗重开读新配置）。
