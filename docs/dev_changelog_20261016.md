# 开发者日志 20261016（日期快照式，按提交逐条）

## 一、凌晨段：开局三件收官（接 10-15 深夜会话，含 C.2 部署）

- **①C.2 部署+location 真机回归全毕**：新车 04D682B7（ad88973 全量构建）；部署三坑当场拦——Git Bash 吞 `cmd /c` 参数（/c→C:\ 路径转换，bat 静默不跑但 exit 0 假象，**险拿 18:26 旧车当新车**，PYZ 三锁验证救场，须 MSYS_NO_PATHCONV=1）+robocopy VCRUNTIME 卡死三现（shutil 绕锁 402+21=423 对账零孤儿）+schtasks 拉起三进程 StartTime 核验；location 回归四连过（set 双通道/json 落盘活体/clear/文件清除实抓，原长沙天心区还原）；回归脚本 _dev/regress_227c2_location.py 留档
- **②C.3 前置 diff 报告落盘**（_dev/recon_227c3_arg_after_diff.md）：_arg_after 双副本**函数体逐字节零漂移**（STATE 旧记"已漂移"实为 docstring 层）；C.3 口径=todo_handler 借 permission_handler 版+SHARE_PREFIX 随迁+main 副本 C.3 后不可退役（soul×2 范围外）
- **③Hindsight 开机自启注册**（HKCU Run=cmd /c F:\Hindsight\start.bat）+AGENTS.md 纪律命令行修正（裸 exe 缺 5 env 起即退实锤写入纪律）——ad88973 已推
- **提交两笔推平**：b8e967f（批 B 黄金 39 条补账——扩样漏 add 尾巴清账）+ad88973（纪律修正）；origin/main=ad88973 待推 0

## 二、自启 7 项拍板执行收官（用户逐项拍板，6 禁 2 留）

- **拍板**：Steam 留（**中途改判**——Wallpaper Engine 小红车依赖 Steam 后台，禁则壁纸崩；ZCode 已误删当场按备份原值恢复）/uu远程 留/坚果云 留/AMD 降噪 禁/Steamcommunity_302 禁/StartCN+StartDVR 禁/GenuineService 禁
- **执行全绿**：AMDNoiseSuppression reg delete ✓+GenuineService.lnk 备份后删 ✓（破案=Autodesk 正版验证非服务——333 服务枚举零匹配，仅启动夹 lnk）+Steam 恢复 ✓——三项复验实抓
- **破案两项**：StartCN/StartDVR=AMD Adrenalin 官方计划任务（cncmd.exe/RSServCmd.exe，CNext 目录=UI 栈同族，与已清理 AMD UI 层同判）
- **三任务禁用撞权限墙**：schtasks /Change /DISABLE 拒绝访问×3（任务注册在管理员权限下）——**并入用户管理员命令组 5 条**（三任务+NI 两条，恢复命令全记台账 §六）
- 台账 startup_audit_20261015.md 增 §六拍板执行段（含全部恢复命令）；_dev/autostart_backup_20261016/ 备份 lnk

## 三、管理员命令组执行毕——自启清理全案终态（用户执行+ZCode 复验实抓）

- **用户管理员窗口执行 5 条完毕**：三任务（Steamcommunity_302/StartCN/StartDVR）/DISABLE+NI stop（报 1062=服务本就未起，假错误无害）+NI config disabled
- **ZCode 复验实抓全绿**：三任务 CSV"已禁用"×3+NI START_TYPE=4 DISABLED+STATE STOPPED
- **至此：自启 7 项（6 禁 2 留）+管理员 5 条全部落地**——:8080 裸奔面消除终态（NI WebServer 双保险禁用）；台账 §六 终态版（.bak-20261016-exec2 在案）
- 恢复命令全在台账 §六（任务 /ENABLE、NI sc start、Steam reg add 原值、GenuineService lnk 从备份拷回）

## 四、挂账

- 重启后验 9 项自启清理（6 项旧账+今晚 AMD 降噪/GenuineService/NI 新账）
- C.3 todo 本体搬家=明日开（前置 diff 报告已齐）

## 五、晨段：重启复验 12 项全绿 + 新硬规矩 + C.3 全链落地（8:00-11:40 用户不在档）

- **重启后复验 12 项全绿（挂账④消）**：6 旧自启全无（Edge×2/Chrome/UC/Quark Run 键+Tabbit+TypeEasyNotify 禁用态）+3 新全禁（三计划任务 CSV"已禁用"+GenuineService.lnk 无）+HKLM 保险扫零残留；附带三件：Hindsight 开机自启生效实锤（重启后 healthy+connected 零手动拉起）+生产车三进程 7:19 开机时刻全新（Run 键双通道自启恢复）+NI 保持 STOPPED+DISABLED
- **AGENTS.md 新硬规矩**（84427d5）：用户不在电脑前时除必须物理操作外一切能推的活都推——不等不挂账不空转（侦察/设计稿/代码/测试/文档/commit 均不卡人）
- **C.3 实施设计稿**：_dev/design_227c_batch_c3_todo.md（侦察 D1-D4 决策全带推荐：_notify_todo_done 随迁/cb 退役内聚直调/SHARE_PREFIX 删 main 副本/import 行清理）
- **C.3 全链落地（6c897fc，按新规矩预授权动工，停在部署前）**：todo_handler.py 新建（152+48 行脚本切割 ast 级逐字节迁移）；_arg_after 借 permission_handler+SHARE_PREFIX 随迁；content_handler cb 退役内聚直调（G2 同款）；dashboard 两通道+main 预分流改指；**测试门连环拦截两盲区**：dashboard:1387 gen_log 跨模块消费 main.SHARE_PREFIX（侦察漏网）+from-import 双绑定（测试须注入 todo_handler.state_manager/requests/permission_manager 防读写生产库）；锚 +6 全仓 2408→**2414+4**（#303 除外全绿，黄金 39 咬合）；main 1499→1290（-209）
- **待推 2**（84427d5+6c897fc）：GitHub 443 超时×2+晨间 Connection reset——网络侧故障，本地安全

## 六、停点（等用户）

- **C.3 部署+真机回归**（下一辆车随最终 rebuild；回归清单=QQ 发 DeepSeek 链接受理提取/控制台 /todos+/todos done/dashboard 双通道 /todos）
- 批 C 全毕（C.1/C.2/C.3）——#227 解耦三件套收官在望，剩 soul 域（G4 范围外单列）

## 五、晚段：批 3-b 实战拉锯 + Pi 掉线根因定案（用户回家实操）

- **批 3-b 实战**：WiFi 切 31.x ✓→免密通→六文件 sftp 传毕（/home/orangepi/soul-core/）→docker build 两次被掉线打断——**build 拉镜像负载→欠压→掉线=欠压病理实时表演**
- **途中修部署脚本三 bug**：finally-return 陷阱（return 前 close 连接返回已关 client）/exec 作用域（函数内 exec 须传 globals()）/deploy_home GBK 解码——坑库候选
- **路径修正**：/opt→/home/orangepi/soul-core（orangepi 无 /opt 写权限；docker 组可用已验）
- **双路自动战布好**：pw_loop_lan_deploy.py（LAN 智能状态机 2h：连上→查镜像→run+health→断则重启 build）+Tailscale 撞窗循环兜底（8:00 硬闸）

## 六、Pi 掉线根因定案（用户实操发现，全链闭环）

- **根因=电源线老化欠压**（非 HDMI/非系统盘/非软件）：原装 5V/3A 充电头被换成"带开关细黑 USB 线+USB 插座"（9-25）——细线压降+开关接触电阻→空载 4.5V 能用、负载上来电压崩→循环重启
- **换手机充电线后 Pi 正常启动**——当场定案
- **SMART 物证**：Unsafe Shutdowns **338/370=91% 非正常关机**、平均开机 2.1h；SSD 自身健康（PASS/3%/32°C）
- **v1.1 有线网卡已知 bug**（卖家文档）：io 五命令开机自愈丢失时有线无法获取 IP——重装若丢自愈配置=IP 漂移（1.2↔31.82）真因；**到家第一查=io 自愈配置还在吗**
- **考古修正**：SSD 一直有（"10-11 到手"行与口供冲突待核）；ENVIRONMENT 19/25 行矛盾已清理（统一"漂移史+以实测为准"）
- **坑库 #35**：Pi 欠压死机=高负载下必掉线（空载正常+负载必掉=供电不足口诀）；#34 同族（硬件问题披软件外衣）
- **#340 三增补**：固网优先（静态 IP+单段+防火墙显式规则=第一交付物）/重装恢复清单 runbook 化（7 项打勾）/电源条目（换 5V3A 一体式+get_throttled 欠压计数器物证）

## 七、同日侦察三件（零代码）

- **AI 伴侣开源生态**（recon_ai_companion_ecosystem.md）：Mem0/Zep/Letta/Generative Agents+SillyTavern World Info+LangGraph HITL+SentiCore OCC——结论=小橘三域深度超多数开源，增量借鉴四条（reflection 合成/关键词触发注入/时序失效边/审计回放），反向印证两条（recall 三乘子/放权三态与业界同构）
- **Pi SSH 稳定性考古**（recon_pi_ssh_stability.md，§一~§十一）：变化点≈10-05；复合变化 C1 拓扑漂移/C2 负载/C3 电源SD/C4 防火墙；Tailscale 嫌疑排除（温度计非病原）；重装恢复清单 runbook 化进 #340
- **诊断脚本预置**：diag_pi_after_power.py（全段扫 22+诊断七件）/deploy_home.py（局域网一键）/b3_deploy.py（paramiko 容忍版）
