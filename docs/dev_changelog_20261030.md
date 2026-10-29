# 开发者日志 2026-10-30

## 批三 — tweak(侧栏默认宽 320→400)（v2.2.1 内部补丁，生产热同步部署）

### 改了什么
- v0 `.sidebar` width 320px→400px（队长拍板区间 380/400 取 400）；用户拖宽仍走 ui_pref 覆盖，双击复位=回 400。
- 清生产 ui_pref.json 旧宽度记忆 sidebar_width=325（备份 .bak-20261030-width400）——不清则桌面端永远读旧值，新默认永不生效。

### 怎么验证的
- 全仓 pytest 2911+5 全绿；生产重启后真浏览器默认宽实测 400（无测试锚依赖 320，零锚改动）。

### 回滚
- git revert 本笔；ui_pref.json.bak-20261030-width400 还原；index.html.bak-20261030-width400。

## 批一 — fix(蓝线贴线根因根除:resizer 白底融白区+border 方案定稿)（v2.2.1 内部补丁，生产热同步部署）

### 改了什么
- **根因实锤**（真浏览器几何量测）：`#sidebar-resizer` 是 10px 透明热区夹在侧栏与右区之间，透出 body 灰底 #e5e5e5——灰白交界的物理位置在热区**右缘**（330px），而此前所有画线方案（`::after` left:50%/left:0）都把线画在热区左缘附近（320px）——**怎么调都差一个热区宽度**，这就是队长三连实锤"蓝线不贴交界"的真根因。
- **修法（队长指令：最粗暴简单）**：分界线渲染权移交 `.sidebar border-right`（2px solid transparent，hover 侧栏/悬浮热区/拖拽中染 #2563eb）——border 是 sidebar 盒最右条带，右缘物理=灰白交界，**结构性零偏移**（跟 box-sizing/拖宽都无关）。
- `#sidebar-resizer` 底色 transparent→**#ffffff**（热区整条融入白区，交界物理移到 sidebar 右缘=蓝线位置）；::after 规则物理删除；热区 10px 保持好抓。
- 清理尸体：基础 `.sidebar` 块内被 v0 覆盖的死声明 `border-right: 1px solid var(--color-border)` 删除；2026-10-27 过时注释块（负外边距/狐毛橙描述）重写为当前事实。
- console.js：拖拽起止加/摘 `.sidebar` 的 `divider-dragging` class（拖拽中蓝线常亮，上个会话已写、本批纳入提交）。
- test_sidebar_resize 锚随新契约（flex 10px/背景 #ffffff/border 方案/hover 选择器组/divider-dragging；`::after` 三锚改版+assertNotIn 禁回归）。

### 怎么验证的（真浏览器像素级铁证，烟雾服 5099+IAB）
- 几何：sidebar [0..320] 灰、resizer [320..330] **纯白**、chat [330..1280] 白——交界=320=蓝线位置。
- PIL 扫描线（y=360）：常态交界精确 x=320、零蓝像素、零第三色；hover 蓝能量 [318..320) 右缘=320=交界，左灰右白。
- 真鼠标拖宽 320→420：sidebarRight==resizerLeft==420，蓝能量 [418..420) 右缘=420=新交界——**拖到哪贴到哪**。
- 拖拽态计算样式=rgb(37,99,235) 精确 #2563eb（截图偏浅系合成层截图重采样伪影，DOM 实色精确）。
- 双击复位 320 回归。全仓 pytest **2911 passed, 5 skipped, 0 失败**。
- 截图三件：_dev/shot_seam_{normal,hover,wide_hover}_20261030.png。

### 回滚
- 代码：git revert 本笔；index.html 备份 .bak-20261030-blueline（仓库）+ 生产 .bak 同日戳。

## 批二 — feat(社交池灌好友+保命双雷修复)（v2.2.1 内部补丁，生产热部署）

### 改了什么
- **NapCat get_friend_list 实拉**：小橘（1706205831）好友 5 个——排除主人 3779888268（走专属唤醒通道带全量记忆，绝不进社交池）与 bot 自己，**3 好友入池**。生产 .env：`XIAOJU3_SOCIAL_POOL=f:3075461518,f:1598998793,f:1773609145,g:1061438268`（备份 .env.bak-20261030-socialpool）。
- **保命双雷修复（2026-10-30 实锤，灌池前必须修否则红线纸糊）**：
  ① `social_visit` 日限计数按 `meta(key,value)` 列名读写，实际表是 `meta(k,v)`——OperationalError 被 except 吞、计数永远 0，**全局日限 3 从不生效**；
  ② `social_log` 表全仓零建表语句——24h 冷却同样静默失效。
  修=`_ensure_social_tables` 幂等建表（meta+social_log）+读写统一 meta_get/meta_set（k/v）+计数读不到改 **fail-closed**（宁可不出手）。
- 主人豁免代码化：目标循环跳过 `XIAOJU3_OWNER_QQ`（防误配进池）。
- `_SOCIAL_DELAY=(3,6)` 接线：发送前拟人打字延迟 3-6s（旧版定义了从未用）。
- 新增 tests/test_waker_social.py 11 枚：池解析五形态/日限 3 真实计数+第 4 次阻断/fail-closed/主人豁免/冷却落账/隐私红线原文/场景隔离 prompt/延迟区间。

### 怎么验证的
- 全仓 pytest 2911+5 全绿（+10）；社交安全四件（日限/豁免/fail-closed/冷却）全部异常用例覆盖。
- NapCat get_friend_list retcode 0 实拉（列条目见战报）。

### 回滚
- .env：还原备份 .bak-20261030-socialpool；waker.py：.bak-20261030-socialdelay；代码 git revert 本笔。
