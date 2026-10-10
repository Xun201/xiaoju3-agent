# 开发者日志 · 2026-10-10（深夜跨天批：战略转向落地 + #282 可观测性）

> 承接 dev_changelog_20261009.md（该文件记至 3b19cff；10-09 深夜至
> 10-10 凌晨的跨天批记入本文件）。

## 一、跨天批总账（10-09 深夜 ~ 10-10 凌晨）

| 提交/产物 | 内容 |
|---|---|
| 5a657f1/9cc5ec1/b021b43/f33fe93（实验室仓） | exp04 记忆固化/睡眠回放 MVP（四件套闭环收官）+ 路线图正档/镜像同步 + 记忆长文归档 + 战略转向蓝图同步 |
| 19b99a9（主仓已推） | README 门面优化 + MIT/Apache 2.0 矛盾修正（#294 初稿） |
| 0f76c88（主仓已推） | **#271① mood 状态机 M1**（PAD 三维+OCC 规则表+基线回归，14 锚，全仓 1923+4→1937+4）；M2/#297 两设计稿拍板存档 |
| 20e9306（主仓已推） | **#282 Turn/Step 可观测性 M1**（见下节） |
| 私有文档批 | 战略转向 7 文件+2 镜像 / 记忆长文 3186 字 / 本地模型调研+实施报告 / #271① M1+M2 / #297 / #282 五份设计稿（全部 info/exclude） |
| 运维实操作 | llmfit 安装+硬件实测 / medium 档 .env 升 1.5b+生产车重启验证（后续 2026-10-09 晚批） |
| 测试基线 | 1923+4 → 1937+4（mood +14）→ **1946+4**（trace +9） |
| 待办库 | 66 行（pending 57+done 9）：#293/#294/#295/#296/#297 五条新落；#271/#282 提前 P1；比赛类降 P2；P0 档清空 |

**战略转向（用户拍板）**：小橘3号=长期主线项目，比赛/软著=顺手产出，
工程迭代优先不为外部节点让路——比赛期冻结/材料优先/新功能走实验
轨道约束全部取消（AGENTS.md 无比赛条款零改动；PROJECT_CONTEXT/
ENVIRONMENT/顾问本/记忆区 roadmap+northstar/实验室镜像七处落地）。

## 二、#282 Turn/Step 可观测性完整交付（20e9306）

- **交付物**：turn_trace.py（contextvars 多线程隔离 + agent_state/
  trace.db 两表 turns/steps + TurnTimer with 包装 + 2000/10000 滚动
  清理）+ trace_stats.py（CLI 摘要）+ test_trace.py（+9 锚）+
  brain.py 六处挂钩（smart_ask/stream 改名 _impl+计时包装——原函数
  体零改动；ask_local/ask_cloud step 记录，eval_count Ollama 实测
  token 顺带落；工具解析两处 record_tool 名字级）；
- **边界纪律**：只记元数据（时长/来源/状态/工具名）零消息内容零
  参数值；XIAOJU3_TRACE_ENABLED 缺省开；模块可整体删除（顶层
  ImportError=None 旁路）；静态 import 无需 hiddenimports；
- **设计稿**：_dev/design_282_turn_step_observability.md——0 个用户
  产品决策、3 个工程推定（SQLite 两表/改名包装/开关缺省开），按
  "决策点少且明确可实施"精神完成交付；
- **消费端**：`python trace_stats.py [天数]`——turns/平均耗时/local
  占比/错误/工具 TOP；控制台面板留 M2 级（随重建车批次）。

## 三、事故记录（两起，均已修复并验证）

### 事故 1：模块名 trace.py 撞 stdlib trace（落地前发现，未造成损害）

- **经过**：M1 实现按设计稿命名 `trace.py`，Write 完成后自审发现与
  Python 标准库 `trace`（性能分析器）**模块名冲突**——`import trace`
  命中哪个取决于 sys.modules 缓存状态：若同进程其他依赖先 import
  过 stdlib trace，缓存命中后我们的模块**永远 import 不到**，且
  该故障是环境依赖的偶发（本地测试可能全绿、frozen 包才炸）；
- **修复**：落地前改名 `turn_trace.py`（mv 一行，零沉没成本）；
- **教训入册**：新模块命名前先查 stdlib 撞名（trace/logging/
  types/test 一族都是雷）；与"动态引用插件补 hiddenimports"同级的
  命名纪律候选。

### 事故 2：跨 docstring 的改名 Edit 切断 docstring（SyntaxError，当场修复）

- **经过**：smart_ask_stream 改名包装的 Edit 中，old_string 只含
  def 行+docstring 前两行、new_string 的新短 docstring 已闭合三引号
  ——原 docstring 主体（事件协议/行为对齐口径等 9 行）被留在闭合
  引号之外，成为**裸代码**（语法错误，文件不可导入）；
- **发现**：Read 回现场确认断裂形态 → 整段重写（包装函数+impl def
  +完整 docstring 一次到位）→ `ast.parse` 全文件语法检查通过 →
  9 锚+全仓 1946+4 复验；
- **教训入册**：跨 docstring/多行结构的 Edit，old_string 必须覆盖
  到结构闭合点；结构性改动后立即 `python -c "import ast; ast.parse(...)"`
  快速验证，不等测试套件暴露。

## 四、当前挂起队列（等用户回电脑）

1. **M1 部署**（deploy_onedir.ps1 重建车）→ mood M1 + trace 自动
   开始积累；
2. **M1 真机验证** → `🧡 [mood]` 日志行 + trace_stats 出数；
3. M2 语气注入开工（拍板稿已存，XIAOJU3_MOOD_TONE 手动开）；
4. #297 记忆系统并入开工（拍板稿已存，与 M1 部署解耦可并行）；
5. medium 档 1.5b 真机验证（窗口=真实 medium 场景）。

## 五、测试与推送

- 基线演进：1923+4 → 1937+4（mood）→ **1946+4**（trace）；
- 推平：… → 19b99a9 → 0f76c88 → **20e9306（现 HEAD，待推 0）**；
- 本地领先：0 笔。

## 六、真机部署与对比测试补账（10-10 午后）

- **生产部署两轮**：首轮（56969e6 车）冒烟暴露 **frozen 路径 bug**（三模块 _db_path 的 __file__ fallback 在 onedir 下误落 dev 仓——生产三 db 曾误建 F:\Orangepi_number3gent_state）当场修 **c6dc178**（fallback 优先 xiaoju3.AGENT_STATE_DIR +3 锚）→重部署复测三 db 正确落位生产 agent_state；
- **对比测试（4 消息：天气/夸/骂/待办）暴露双缺口** → **9fbb929**：①mood_rules.json/mood_tone.json 未进 spec datas——frozen 静默回退最小词表，用户「聪明/笨」全落 small_talk（relationship 词表代码内置故同句正常命中 scolded，同句两模块判定分裂即铁证）→spec datas 补两数据文件；②stream 链 record_step 未挂——控制台走 stream 端点 turns 全 steps=0/brain_source=None→_ask_local_stream/_ask_cloud_stream 补挂（eval_count 顺带落）；
- **复测 PASS**：「你真厉害」→ mood praised P 0.2→0.48（dp+0.28 连击×1.00）/A 0.55、turn steps=1 eval_count=30；词表语义分离确认（「厉害」=mood 被夸命中、「非道谢」不计 relationship affinity——两词表语义本不同，调优项非 bug）；
- **判读记录**：待办查询走意图直达不经 LLM（无 mood/trace 记录=设计语义待议）；测试基线 1969+4；本地领先 origin 4 笔（…→9fbb929）待推。

## 七、10-10 晚真机验收收官（四条清单 PASS + 生产账本增量证据）

- **验收结论**：四条清单全过——①天气 A+B 全链（位置已知→☁️ 云端真
  搜索+诚实应答「不瞎编糊弄」；/clear→反问城市→回答→user_location.
  json 确定性落盘→再问全链）②思考卡无残留（正常消息干净收尾）③
  时间戳连发首条戳符合（history_console ts 落库）④M2 未开（拍板
  缺省关）——**#271① 全链+#282 生产活体验收完成**。
- **生产账本增量证据（M1 机制五连实证）**：①M1 回归曲线（15:07 夸
  奖 P 0.48 峰值 → 9 次对话 α=0.10 回归 → 0.309）；②闲置回归 β 首例
  （15:58:33 rate=0.15 含 1.8h 加成）；③rel 日帽防极化首例（14:55 骂
  -1.0 用满帽 → 18:14 再骂 delta=0「日帽已满」）；④两本账语义分离
  （「你真厉害」mood praised 进/rel thanks 不进；「小橘你真笨」双账
  同命中交叉验证）；⑤天气强路由云端真搜+确定性位置落盘。
- **状态**：origin/main = 7bd9d37 待推 0；生产车 = 419091ce 活体；
  测试基线 1969+4；本地待推 0。
