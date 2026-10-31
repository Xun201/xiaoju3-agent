# 开发者日志 2026-10-26（修复批：交接三遗留①②）

> 本日主任务：v2.1.0 发版后交接三遗留中的①前端点击②麦克风 -9999（③Hindsight 挂起队长自行处理）。
> 生产车 exe **f19697ab**（0d17fb6 构建 10:2x，三进程 10:27 全新）；全仓 **2548+4**；origin/main=0d17fb6 待推 0。

## 一、前端点击修复（交接遗留①）

- **根因（真机实锤+代码实锤双确认）**：console.js 外点关闭器只豁免 `.input-dock` 类，但 index.html 里**没有任何元素带这个类**——＋/⚡技能/🧩插件按钮自己的点击也冒泡进 closeAll，**同一次 click 内浮层开了又关** = 肉眼"点击无响应"。UI 一期上线时此交互从未真机点过（交接档"扩展栏双目检待验"挂账即此）。
- **修法**：外点关闭豁免清单改显式选择器 `#dock-plus, #dock-skills, #dock-plugins, .context-tags-bar` + 两浮层类，一处收口（console.js）。
- **"已提取文档"标签点不开**：非遮挡非事件丢失——原设计就是纯 `<span>` 零事件绑定（状态展示），队长预期可点开。补全产品行为：`/api/plugins` 新增 `context.docs`（DISTINCT doc_path+标题+块数，MAX(rowid) 最近摄取序，上限 20），前端标签改 `context-tag--link` 可点态，点击弹文档清单浮层；**事件委托绑 bar 父级**（标签条子元素 30s 重渲染会抹子元素监听，委托绑静态父级不丢）。
- 队长提的两条假设判定：事件委托——对文档标签成立（已做）；遮罩层 z-index/pointer-events——排查后无遮罩（root cause 是同 click 开关竞态，非覆盖）。

## 二、麦克风 -9999 简化定稿（交接遗留②）

- **背景**：PortAudio 五坑链（MME -9999→hostapi -1→-9997 采样率→-9996 虚拟设备→枚举重试）后仍 -9999，当时判"系统级"；本日系统录音机恢复，队长拍板"是代码问题，废弃花活"。
- **修法（xiaoju3_dashboard.py 重写 STT 段）**：
  - `device=None` 系统默认设备一发开流；`samplerate=None`=设备自身默认率（sounddevice 内建回退实锤：`_get_stream_parameters` 里 None→`info['default_samplerate']`，-9997 教训收编为缺省语义）；stop 统一 np.interp 重采样 16k。
  - `_stt_close_stream()` 无条件收口：start 半途失败/stop 任何路径（含外层 finally 双保险）都必达 close——流泄漏占设备正是反复开关出 -9999 的温床。
  - pyaudio 兜底引擎 `_stt_open_pyaudio`（阻塞读线程模拟回调，包装流与 sounddevice 同构零分支）：**Python 3.14 无官方 wheel（pip download 只有 sdist，源码构建实测失败）**——缺席时人话报错不装死，如实挂账。
- **实测**：dev（5005）两轮开关流 PASS；**生产 frozen（5003）两轮开关流 PASS，第二轮转写出真实环境语音**——五坑链时代从未在生产录出过字。

## 三、验证与部署（证据链）

- 全仓回归 **2548 passed + 4 skipped，0 failed**（基线 2547→2548，+1=test_dock_click_fix 回归锚；首轮 1 败=node 语法门 subprocess 撞进程饥饿抖动，低负载重跑全绿）。
- node 运行时烟雾 **12/12 PASS**（`_dev/smoke_dock_click_20261026.js` 可复跑；最小 DOM 桩+事件冒泡+dataset 语义，跑真实 console.js 提取的 initInputDock；IAB 浏览器 guest 挂不上走此预案）。
- 部署：deploy_shutil 正档（copied=4 kept_same=1518 locked_diff=0，exe/console.js/index.html md5 双端 MATCH，插件同步 3 项）→ schtasks 拉起 → 三进程 StartTime 10:27 全新 → health ok。
- 生产冒烟：/api/plugins（三插件+22 技能+docs 清单 2 份真文档）+ /api/stt 两轮全 PASS。
- 提交三笔：37cb44c（#312 R1-a 收尾遗留）/ dba063c（思维笔记渗流相变遗留）/ **0d17fb6（本修复批）**；专利筛查通过（常规工程修复，无方法级新点）。

## 四、挂账

- **pyaudio 兜底依赖缺席**：py3.14 无 wheel，兜底代码在、依赖不在——若 sounddevice 将来再死且需硬兜底，选项=py3.12 venv 或等 PyAudio 出 cp314 wheel。
- **队长真机目检**（唯一剩人眼项）：点＋看菜单弹出、点📚标签看文档清单、🎤录一段说话看转写。
- 首轮全仓 node 语法门"进程饥饿抖动"一现——同窗口 bash fork 亦炸（cygwin Resource temporarily unavailable），暂记观察不作缺陷。

---

# 追加：语音转写二轮双修（2026-10-26 午，518bcd8 已推，生产车 exe cf935777）

> 队长真机反馈两瑕疵：转写出繁体"幫我機個帶班明天買咖啡"（预期"帮我记个待办明天买咖啡"）。四指令全落地+超指令两件。

## 落地五件（518bcd8）

1. **initial_prompt 引导词**（`_STT_PROMPT`）：强制简体声明+高频指令词汇表（小橘/记待办/添加日程/总结视频/系统自检）——实测繁体与同音字双杀的主解。
2. **opencc t2s 兜底**（`_stt_t2s`）：opencc-python-reimplemented 装进 dev/生产 _deps（各 +1MB，sha256 口径 t2s 转换验证过）；缺席时原文返回不 500。
3. **模型 base→small**（env `XIAOJU3_STT_MODEL` 可调回 base）：int8 CPU。
4. **镜像超时回落本地缓存**：`local_files_only=True` 二段加载——hf-mirror 挂时缓存齐全仍 LocalEntryNotFoundError 实锤（eval 亲证），产品级堵雷。
5. **静音双闸**（生产实测暴露的新缺陷当场修）：近静音喂 whisper 会复读 initial_prompt 尾巴（"请使用简体中文输出。"实锤）→RMS<0.005 门+剥标点后引导词子串回声门，双双返回"未检测到语音"。

## TTS 四象限实证（_dev/_stt_eval.py 可复跑；Huihui zh-CN 合成 9.4s 测试语音）

| 配置 | 转写耗时 | 内存 | 结果 |
|---|---|---|---|
| base 无引导 | 0.5s | 169MB | 繁体+同音字错（复现队长瑕疵）|
| base+引导 | 0.5s | 169MB | 简体✓ 大部分对（漏"明"多"添"）|
| small 无引导 | 1.6s | 447MB | 简体但同音字错（寄/记、代办/待办）|
| **small+引导** | **1.8s** | **447MB** | **逐字节全对 HIT** |

结论：引导词管简体+词汇锚定，small 管识别力，缺一不可；速度远快于实时，内存无压力。

## hf-mirror 断供绕道（运维资产）

hf-mirror.com 当日连接超时（baidu/github/modelscope 全通=单点故障）→**ModelScope 官方 Systran/faster-whisper-small 镜像**四文件下载（model.bin 461MB sha256 校验一致）→手工组装 HF 缓存布局（refs/main+snapshots/<sha>/）→WhisperModel 离线加载零感。脚本 _dev/_stt_tts_make.py（TTS 造语音）+_stt_eval.py（四象限）留档。

## 验证链

全仓 **2548+4 全绿**（+5 stt 新锚）；生产侧直烟 HIT（small 离线加载+转写+t2s 全对）；生产 frozen **真人语音"小橘，帮我记个待办，"简体全对**；静音场景双闸复测 PASS；三 md5 MATCH+StartTime 10:5x/11:0x 全新。生产车 exe **cf935777**。

---

# 追加 2：真机点击不出字双断点修复（2026-10-26 午后，10d0647 已推，生产车 exe 0bc4da1c）

> 队长真机反馈：点麦克风说一段话，输入框无文字。生产 dashboard 日志 11:37 序列实锤双断点。

## 断点定案（生产日志铁证）

```
11:37:19 start 200 / 11:37:28 start 200 / 11:37:37 start 200 / 11:37:55 start 200
11:38:00 stop 200 / 11:39:40 stop 200
```

- **断点①前端状态脱同步**：后端 11:37:19 已完成 start 并 200，但 webview 前端对响应的处理迟滞（40 秒后才翻转 recording）——期间队长每次点击都被当"开始"重发，后端 409"已在录音中"而前端不认账（recording 停留 false）。41 秒后才真正 stop，录到"说话+大段噪音"。
- **断点②回声门自摆乌龙**：前一轮为治"静音复读引导词"加的回声门（剥标点后是引导词子串→丢弃）是**全响度**判定——而引导词教的就是高频指令，"小橘帮我记个待办"这类转写必然⊆引导词 → **真说话被整句误杀**。41 秒长音频转写若只出短语（whisper 尾部截断常见），恰好掉进误杀区。

## 修三处（10d0647）

1. **start 幂等语义**：已在录音中返回 200+note（不再 409）——前端任何脱同步自此对齐后端真相；前端配套 busy 在飞守卫（响应迟滞期忽略连点）+按后端应答采纳状态+stop 409 语义化轻提示（"当前没有录音了"）。
2. **回声门收窄到低响度带**（rms<0.015 才判回声）：真说话响度 0.05~0.2，结构性不可能被吃；纯底噪（rms≈0.005）的 prompt 复读仍被精准拦截。
3. **静音 RMS 门 0.005→0.003**（队长口径：误吃说话宁可放宽）+`[stt]` 响度/结果插桩进 dashboard 日志（生产实锤 rms=0.0047 回声被拦，以后调阈值有数据）。

## 验证（行为级，非静态）

- `_dev/_stt_gate_check.py`（可复跑）：flask test client 注入 int16 真音频走**真 /api/stt/stop 端点**——①幂等 start ②短句"帮我记个待办"（⊆引导词=旧门必杀形态）存活 ③队长验收句逐字节全对 ④静音拦截——**4/4 ALL PASS**。教训：注入必须 int16（端点按 int16 约定 /32768，注 float32=人为静音化假绿）。
- 全仓 **2548+4 全绿**；生产车 **0bc4da1c** 三 md5 MATCH；生产四连实证：双 start 幂等（第二个 200+已在录音中）→静音 stop 走回声门（"只有杂音，没听清"）→重复 stop 409 语义化。
- **待队长真机终验**：点麦克风→说话→点停止→文字入框。

---

## 深夜批：两阻断 Bug 修复 + 知识库文档管理器（bf3f254 已推，生产车 1cbe0a24）

### 病灶定案（真机日志实锤）
- **附件 Bug 真凶=幽灵滞留态，不是"消费后不清"**：`_take_doc_attachments` 取出即清空一直正常；真机时间线=22:16 上传《道诡异仙》未发消息（且同书传两次=append 双份）→22:21 刷新页面芯片 DOM 即焚（用户视角：没有附件了）→22:21:51 发纯链路测试"请回复OK"被注入 5 分钟前的 2500 字修仙小说。芯片是附件就绪的唯一信标，后端全局态却跨刷新滞留。
- **发送按钮**：代码里从无 disabled 逻辑，空输入常亮可点。

### 修了什么
1. **发送按钮置灰联动**：input 监听+disabled 切换（opacity .4+not-allowed）；发送清空经 `__xj3SyncSendBtn` 同步回灰；Enter/点击同源 trim 判定；`value||''` 防御（node 运行时冒烟抓的 undefined.trim 雷——静态门查不出，运行时是唯一可靠门，再验）。
2. **附件阅后即焚闭环三刀**：①upload 改替换语义 `_doc_attach_replace`（一次上传=一批，后到为准，与截图互斥同构；stash 全空不动作防幽灵反转）②页面加载 init 同步清空 `_DOC_ATTACH`/`_SHOT_ATTACH`（刷新即对表，封死幽灵注入）③首行隐藏已有（发送即焚）。
3. **知识库文档管理器（队长拍板"死数据变活工具"）**：📚 标签浮层每行=文件名（点击即一键重挂为 📎 附件：原文件在走 `_extract_text` 同链，不在从 chunks 按 chunk_index 拼回，source 如实标注）+大小/段数/入库时间+↻重挂+🗑删除（confirm 后 DELETE 切片行，embedding BLOB 同行同删零残留）；`/api/knowledge/doc/remount|delete` 两新端点；清单增强 size（原文件真大小）+ingested_at（doc_ingest 幂等加列+INSERT 写时间，旧数据如实空）。

### 部署时序雷（本轮新坑）
- dashboard 清单 SQL 引用 `ingested_at`，但列要等插件首次摄取才由 `_ensure_ingested_at_col` 补——旧库先查就 `no such column` 被 `except: pass` 吞成**空清单**。修=dashboard 清单查询前幂等 ALTER（schema 自愈），不依赖插件先跑。

### 验证（Evidence）
- 全仓 **2581+4 全绿**（+18 锚：test_knowledge_doc_manager.py 行为级 18 用例——替换语义三态/remount file+chunks 双源/delete 真删/旧库自愈/静态锚）；node --check 过；AST 双过。
- 真浏览器实测（IAB 连生产车）：置灰四态全过（初始灰/打字蓝/删字蓝/删光灰+not-allowed+opacity0.4）；幽灵态 staged 2500 字→reload→日志 `[attach] cleared: 1 item(s)`；浮层列表 4 行（名+大小·段·时间+双钮）；重挂芯片复活（"25 字符"由切片拼回）；删除 confirm→计数 4→3→库零残留；**页面端到端 staged→发送→`[attach] injected 2500 字`→芯片即焚**全链。
- 受控双链复现：同步链+流式链 staged→injected 各一实锤。

### 没验证/挂账
- 23:04:58 一次"发送后零注入"未能还原（当时 items 意外为空；此后三条链受控+端到端全部复现成功，判定一次性事件，如实挂账）。
- 队长真机终验：传书语义问答边界+纯净闲聊边界（本轮交付正为此铺路）。
- 回滚：`index.html.bak-20261026-sendbtn` / `console.js.bak-20261026-sendbtn` / `xiaoju3_dashboard.py.bak-20261026-attach` / `agent_state/plugins/doc_ingest.py.bak-20261026-docmgr`；生产旧 exe=F:\XUNandxiaoju3\xiaoju3.exe.oldA2。
