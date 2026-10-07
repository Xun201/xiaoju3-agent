# 小橘3号 开发变更记录 · 2026-10-07

> 本文为 2026-10-07 当日提交的事实清单，格式对齐 dev_changelog_20261002.md。
> 时间均为 git 实际提交时间。

---

## 深夜（05ff42a：黑框根治强化，待推）

### `05ff42a` fix(logger): 黑框根治强化——_QuietChildWindows 从 setdefault creationflags 改为强制 CREATE_NO_WINDOW 并移除 playwright 自带 startupinfo(SW_HIDE)

- **根因**：playwright 库 `_impl/_transport.py` 自带 `startupinfo(STARTF_USESHOWWINDOW|SW_HIDE)`，项目补丁 `_QuietChildWindows` 只 `setdefault` creationflags——**SW_HIDE 与 CREATE_NO_WINDOW 两机制并存**，conhost 先按"可见"分配窗口再被隐藏 = 闪现（提取期间 conhost×2 监视实锤）。
- **改动**：`_quiet_exec` 强制覆盖 creationflags=CREATE_NO_WINDOW + `pop("startupinfo")`（两机制取一，无窗创建即无闪现）。
- **测试**：test_brain +2 锚（HA 超时×5 不熔断且 streaks=0 / 权限×3 照常熔断——熔断口径改进同车）。
- **状态**：**未推**（等真机黑框验证通过后随批推）。

---

## 未提交（工作树态，随时可收）

- **QQ 通道 3001→3000 端口修复**：`.env` ONEBOT_API_URL 改 3000（NapCat 实际服务口）+ ONEBOT_TOKEN 从 NapCat 配置同步——修后模拟私聊"在吗"日志实锤"准备发送回复"且零发送失败。** NapCat 网络组件后又两死（17:47/20:09），配置全对组件未起，需 WebUI 手动触发或升级新版——已立待办跟踪。**
- **HA 实体改名"小米灯"**：WebSocket `config/entity_registry/update` 改 entity name=小米灯（friendly_name 干净化，原"桌面学习灯  灯"拼接瑕疵消除）；控灯双说法真机 PASS（"打开小米灯"/"打开桌面学习灯"均命中，灯真翻转 on）。
- **HA 设备改名**：`name_by_user=小米灯`（WebSocket `config/device_registry/update`）；original_name=' 灯' 三连改（容器直写/停机 sed/容器内直写）均被 miot 集成启动重灌——确认 HA 硬限制，现状保留。
- **Pi 拔电重启**（用户操作）：恢复后 Tailscale direct 110.53.217.192 → 192.168.1.2 LAN 直连恢复，HA version=2026.9.4， NapCat NapCat.52230.Shell 目录确认（OneKey 完整解包含 QQ 9.9.33-52230）。
- **todos.db**：#261（纯文字待办入口 P1）/ #262（链接失效文案 P2）/ #263（自启动检测 P2）/ #264（统一设置面板 P2）/ #265（DeskBox 思路 P4）/ #266（NapCat 稳定性 P2）/ #270（待办怎么做意图 P2）/ #271（情感状态机 P2）/ #272（黑框验证 P1）逐条入库，note 均含完整上下文。

## 当日真机验证记录（非提交，事实清单）

- **HA 实体改名**：`config/entity_registry/update` name=小米灯 → friendly_name 干净化（"小米灯"）；`config/device_registry/update` name_by_user=小米灯。
- **控灯双说法真机**：☁️ 云端 (工具) 路由 → light.xiaomi_cn_..._s_2_light 真翻转（"打开小米灯"/"打开桌面学习灯"均命中）。
- **黑框监视（唯一次）**：node=0 / chrome-headless=0 / conhost=1 → **FAIL/未触发**（Playwright 未启动——非修复无效证据，是验证无效：提取未走到）。
- **提取管线**：旧链接 8ghetebj 重发→36 行抓取→1/1 分片→0 条（内容无待办，正确行为）。
- **环境事实**：Pi LAN=192.168.1.2（档案 31.82 过时）；NapCat WebUI=6099；QQ 12 进程=QQNT 架构常态；Pi 磁盘 102G 空闲。
