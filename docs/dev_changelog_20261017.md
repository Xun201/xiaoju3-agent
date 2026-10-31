# 开发者日志 20261017（日期快照式，按提交逐条）

## 一、凌晨：批 3-b 主门全通（#319 多端灵魂链路打通里程碑）

- **23:14 窗口**：b3_deploy.py（Tailscale 路径）撞上——六文件重传+**docker build 完成**（镜像 xiaoju3-soul-core:1 落成）；docker run 报容器名冲突=**LAN 状态机已先行 run 起容器**（双循环撞车但结果正确）
- **主门三连实抓**：Pi 审计行 ('Xun-tx5','recv','accepted',6) / 落盘六件（identity/long_term/persona_pref/relationship/soul.db/user_location）/幂等二次 idempotent skipped 6 件——**笔记本灵魂完整写到 Pi 核心**（Tailscale 21ms 通道+令牌鉴权+sha256+staging 原子落盘）
- **坑库 #36**：多路循环各自读令牌快照→双侧不一致 401（LAN 状态机 17:45 读旧值 j6g4 vs .env 新值 7UuO）——修法=令牌单点生成+广播，跨进程匹配凭据两侧同批更新；以容器为准同步 .env 修复
- **双路 9100 全 OPEN**（Tailscale+局域网口都通——与"LAN 口防火墙拒"旧记录不符，待 #340 固网时一并核）

## 二、守夜自动战布局（夜间继续）

- LAN 状态机（auth-timeout 分类修复版）+Tailscale 部署循环照跑；退出 flush 自动化测试+断连模拟（令牌指向法，零权限）待跑

## 三、断连恢复场景自动化（令牌指向法，零权限零物理）

原理：把笔记本 SOUL_CORE 临时指向不可达端口（模拟 Pi 失联）→ tick 产生积压（outbox）→ 指回真实地址 → 自动补投。全程文件层操作，不碰防火墙。
（脚本 _dev/regress_b3_disconnect.py，跑完 .env 还原，细节见脚本头注。）

## 四、断连恢复场景 5/5 全 PASS（三场景之二自动化完成）

- 正向真实投递 202（局域网直连 Pi receiver）/失联积压 5 件（不可达 URL 模拟）/积压生活化告警触发（软化文案实出）/恢复后自动补投 5 件+outbox 清空
- 脚本 _dev/regress_b3_disconnect.py 留档可复跑；剩余"退出 flush"场景=真实重启车时自然验证（process_outbox sync=True 10s 上限），不单独造

## 五、物理验收结果 + 车重启（用户实操）

- **断连恢复**：用户断 WiFi 2 分钟→重连 ✓（物理版）；自动化版 5/5 PASS（regress_b3_disconnect.py）——**场景闭环**。Pi 侧审计行核验因 Pi SSH 抖未完成（HTTP 9100 可达、22 抖），待补一轮
- **退出 flush**：生产车为旧版（D5C32E59，批 3-b 代码未上车）——**生产验证需等 rebuild 上车后**（下次部署的新车自带退出 flush+心跳回写）；代码级 process_outbox(sync=True) 逻辑已在断连场景覆盖
- **车已重启恢复生产**：三进程+health ok（旧版继续服役）

## 六、2.0 打包前置清单（中午敲定用）

1. **版本号**：xiaoju3.py `XIAOJU3_VERSION` 1.0.5.1 → **2.0.0**（单一来源）
2. **需要 rebuild**：是——生产车 D5C32E59 不含批 3-b/温度一期/#331/#322（全部在 main 未部署）；`build_exe.bat` 从 main 构建=全量上车
3. **Release 步骤**：bump 版本号→commit+push→`build_exe.bat`（exe+setup 双产物）→tag v2.0.0→GitHub Release（资产 setup.exe+sha256 双端核验）→真机冒烟（health/温度显示/回写主门）
4. **前置检查清单**：全仓测试 2449+4 全绿/#303 例外说明/坑库 37 条入库/2.0 交付物清单（见下）/护城河七条均值评估（若 <85% 补齐或调整口径）

## 七、2.0.0 构建启动崩修复 + 生产部署 + tag/Release（凌晨~早晨）

- **启动崩实锤**：2.0.0 首次构建启动即崩 `No module named '_socket'`（pyi_rth_multiprocessing 运行时钩子需底层 C 扩展，自动收集漏——用户 Pi 旁报 Traceback 实锤）
- **修复**：spec hiddenimports 显式 +_socket/socket/_multiprocessing + 主入口 import _socket+freeze_support 双兜底；PYZ 无 _socket 正常（C 扩展进 _internal .pyd——物理存在实锤）
- **部署插曲**：deploy_onedir robocopy 卡死 20min（半部署态）+ 残进程占 VCRUNTIME——shutil 全量部署+双端 md5 核验（exe/VCRUNTIME 全 MATCH）
- **生产冒烟全绿**：三进程+health ok+**温度 52°C（一期 pynvml 首秀）**+版本 2.0.0
- **tag v2.0.0 已推**+setup.exe（72,729,466B，sha256 c72ed93d…）——GitHub Release 网页创建待用户（或已可由 CI/gh 创建——待用户指令）
- 批 3-b 三场景：主门 ✅+断连恢复 ✅（5/5 自动化+物理 WiFi 断连试验）/退出 flush ⏳（新车已带，用户下次正常退出即验）

## 八、晚间收官：答辩材料归档 + 比赛提交确认 + 双循环停（用户拍板今晚不折腾硬件）

- **答辩五话术归档**：_dev/defense_qa_prep.md（双脑热切换/工具白名单/五事件流式/危险实体三道闸/灵魂回写——每段核心句+展开要点+代码索引+答辩预警：10-25 队长能到、10-24 缺席，提醒办保险/盖章/群核对双赛道时间）
- **比赛状态**：双赛道材料已提交（测试数字统一/软著流水号 2026R11L3453611/删 v1.0.1 歧义句四硬伤全改）；真实性承诺需**打印手签**（不能纯打字）
- **循环全停**（用户拍板今晚不折腾硬件）：LAN 状态机+Tailscale 部署循环停；Pi 侧六文件+rc.local 自愈保留（自生自灭不损失）
- **待推 0**：坑库 #34~#38+changelog 全推平（origin/main=675ad08）
- **明天开局**：用户换新电源（根修）→ deploy_home.py 一键 → 诊断七件 → 批 3-b 尾巴收 → 2.0 收官文档终版
