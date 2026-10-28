# 开发者日志 2026-10-28（秘书直连+QQ 唤醒抢修）

## 晨批：三拍板落地 + QQ 唤醒 Bug 抢修（73185e5 已推，生产车 65f8396d 三进程在线）

- **待办入库**：#357/#358 入生产共享库（note 404/321 字回读一致）；坑一条=仓库根跑 StateManager 缺省落本地 long_term.db，须 env 重定向生产库。
- **任务1 ask_deepseek.py**（B-极简拍板落地）：env 读生产 .env Key（零新增配置）+黑名单扫描（sk-/PRIVATE KEY/TOKEN= 命中拒发）+三闸（单向拓扑/日 15 次/同题第 3 次拒）+ai_consult_log.md 留痕。真实调用验证：109 tokens/0.83s，回答诚实"不确定"（反编造生效）。**自查抓 own bug**：重复闸 off-by-one（写成已有 3 块才拒=放行到第 4 次），修正为 `dup >= DUP_REJECT_AT - 1` 并函数级重验。
- **任务2 #357 note 拍板追加**：notice-hub 不碰代码（PolyForm 法务红线）只借鉴三思想；vidsum 三思路（PyAV/CUDA DLL 挂载/零转写不调模型）列为 video_ingest 二期方向；GPU 显存竞争挂账。
- **任务3 QQ 唤醒 Bug 三刀根治**（截图实锤"小橘： 主人，你最近喜欢《明日方舟》吗？"）：
  - **根因**：waker.qq_recent_digest 注入材料自己拼"小橘：xxx"轮次行 → r1 1.5b 模仿格式复读标签进正文；助手腔（"我可以帮助你一起规划"）=历史 assistant 带 <think> 落盘+助手惯性。
  - **治本**：①digest 改引述式"X说过：「…」"（模仿性消除）②QQ_PERSONA 加人称死命令（禁助手腔/禁角色名标签开头）③_WAKE_PROMPT 红线扩同款。
  - **治标**：出口消毒双层——waker.strip_prefix_noise 加 6 种标签形态；main._sanitize_qq_reply 新增 _strip_role_name_prefix（^ 锚 count=1 只剥开头，正文中间不碰；剥空→SANITIZED_EMPTY_FALLBACK 诚实兜底）。真机同款五连冒烟全中。
  - +8 锚（sanitizer 6+lifemate 2）=全仓 2691+4；测试→构建→deploy_shutil（md5 MATCH+插件同步）→Run 键拉起→health ok。
- 回滚：`git revert 73185e5`+重建；main.py/waker.py `.bak-20261028-roleprefix` 在案；ask_deepseek 不入生产车（_dev 本地），回滚=删文件。
