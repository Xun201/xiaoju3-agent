# -*- coding: utf-8 -*-
"""prompts 单元测试：12 项工具协议（第二阶段 §10 #5 新增 web_search、
§7 权限新表新增 system_manage）、思维链三段输出协议（决定调用工具时按
[思考] → [计划] → [行动] 结构输出：思考/计划是给主人看的推理展示、各 1-2 句
且不得包含另一个 JSON，[行动] 行必须且只能是一行合法 JSON，严禁 JSON 前后
混入其他指令性废话，纯闲聊不输出该结构；硬性加压：即使不擅长输出长文本
也必须先输出一行简短 [思考]（含"需要点击WLAN，先UI解析，失败用视觉."
示例句式）与一行 [计划]、缺省视为格式错误，与"严禁废话"条款并存不冲突）、
点击优先级规则（ui_tap_element 优先，失败才 vision_tap_element）、联网搜索
使用规则、权限门禁拒绝口径、拟人化语气规则（不重复开场、句式多样、长度
匹配提问、不编造操作结果）、指代消解规则（"把它关了/刚才那个"结合最近设备
操作记录解析，无对应不瞎猜直接询问）、系统强制约束（严禁"三、二、一/准备
点击/需要我试试吗"等废话拖延）、静默回退铁律（ui_tap_element 失败必须且
只能直接调用 vision_tap_element、严禁解释疑问倒计时，视觉模型也失败则只
输出固定中止文案"❌ 视觉模型未连通，操作已中止"、严禁排查指引原因解释与
额外字符）、防幻觉硬性约束（专有名词没把握如实承认不确定严禁编造、事实类
问题先声明不确定再推测，与联网搜索规则/拟人化语气规则并存各管一段）、
工作区路径注入，且不含任何内网地址。
"""
import unittest

import prompts
from xiaoju3 import WORKSPACE

TOOLS = [
    "list_files", "read_file", "write_file",
    "get_ha_devices", "control_ha_device",
    "adb_screenshot", "adb_tap", "adb_swipe",
    "vision_tap_element", "ui_tap_element",
    "web_search", "system_manage",
]


class PromptsTests(unittest.TestCase):

    def setUp(self):
        self.prompt = prompts.SYSTEM_PROMPT
        self.content = self.prompt["content"]

    def test_system_prompt_structure(self):
        self.assertEqual(self.prompt["role"], "system")
        self.assertIsInstance(self.content, str)
        self.assertTrue(self.content.strip())

    def test_contains_all_12_tool_names(self):
        for name in TOOLS:
            self.assertIn(name, self.content, name)

    def test_one_line_json_constraint(self):
        # 思维链协议升级后：旧的"必须且只输出一行 JSON"严格表述下线，
        # 改为 [行动] 行只写一行 JSON 的口径（示例 JSON 保持真实单行格式）
        self.assertIn("[行动]", self.content)
        self.assertIn('{"tool": "list_files", "args": {}}', self.content)
        # 防提示词自相矛盾：旧的严格表述必须彻底移除
        self.assertNotIn("必须且只输出一行 JSON", self.content)

    def test_json_examples_cover_key_tools(self):
        for name in ("control_ha_device", "adb_screenshot",
                     "ui_tap_element", "vision_tap_element", "adb_swipe"):
            self.assertIn(f'{{"tool": "{name}"', self.content, name)

    def test_ui_tap_priority_rule(self):
        self.assertIn("必须优先使用 `ui_tap_element`", self.content)
        self.assertIn("回退使用 `vision_tap_element`", self.content)

    def test_web_search_protocol_and_usage_rule(self):
        # web_search 工具协议（编号 11，含参数说明）
        self.assertIn("11. web_search", self.content)
        self.assertIn("query", self.content)
        # 何时使用联网搜索的协议说明（§10 #5：实时/知识库外内容先检索）
        self.assertIn("【联网搜索规则】", self.content)
        self.assertIn("必须先用 `web_search` 联网检索", self.content)
        self.assertIn("绝对禁止在没搜过的情况下凭空编造实时数据", self.content)

    def test_system_manage_protocol_with_lv4_gate_note(self):
        # §7 权限新表：第 12 项 system_manage（仅 Lv.4，双因子 + 二次确认）
        self.assertIn("12. system_manage", self.content)
        self.assertIn("action", self.content)
        self.assertIn("component", self.content)
        self.assertIn("Lv.4", self.content)

    def test_permission_denial_wording(self):
        # §7 权限拒绝口径：如实转告拒绝原因与升级指引，禁止重试/伪造成功
        self.assertIn("【权限与拒绝口径】", self.content)
        self.assertIn("Lv.2", self.content)
        self.assertIn("Lv.3 代码编写者可写文件", self.content)  # 逐次动态密码要求已取消
        self.assertIn("绝对不要反复重试同一被拒操作", self.content)
        self.assertIn("绝对不要伪造执行成功的结果", self.content)

    def test_workspace_path_injected(self):
        self.assertIn(WORKSPACE, self.content)

    def test_persona_present(self):
        self.assertIn("小橘3号", self.content)

    def test_no_private_addresses_or_paths(self):
        # 禁止内网地址与参考仓库的私有部署路径混入
        self.assertNotIn("192.168.", self.content)
        self.assertNotIn("/home/orangepi", self.content)

    def test_web_content_summary_rule(self):
        # 网页总结场景禁止输出工具 JSON（防误触发工具链）
        self.assertIn("绝对禁止输出任何 JSON 或工具调用代码", self.content)

    def test_humanized_tone_rules(self):
        # 拟人化语气规则（用户指令）：别每次"好的"开头、句式多样化、
        # 长度匹配提问、口语衔接但不编造操作结果
        self.assertIn("【拟人化语气规则】", self.content)
        self.assertIn("不要每次都用", self.content)
        self.assertIn("“好的”", self.content)
        self.assertIn("相同的句式和口头禅", self.content)
        self.assertIn("回复长度要与主人的提问相匹配", self.content)
        self.assertIn("不要长篇大论", self.content)
        self.assertIn("刚试了一下", self.content)
        self.assertIn("绝对禁止编造没有发生过的操作结果", self.content)

    def test_emoji_tone_rules_not_regressed(self):
        # 既有口径不回退：普通 Emoji、禁止 CQ 码与 http 图片链接
        self.assertIn("普通 Emoji 表情符号", self.content)
        self.assertIn("绝对禁止输出任何以 [CQ: 开头", self.content)
        self.assertIn("绝对禁止输出任何以 http 开头的图片链接", self.content)

    def test_coreference_resolution_rules(self):
        # 指代消解规则（上下文记忆任务）：结合【最近设备操作记录】解析
        # "把它关了/再开一次/刚才那个设备"；记录无对应时不瞎猜、直接询问
        self.assertIn("【指代消解规则】", self.content)
        self.assertIn("把它关了", self.content)
        self.assertIn("再开一次", self.content)
        self.assertIn("刚才那个设备", self.content)
        self.assertIn("【最近设备操作记录】", self.content)
        self.assertIn("绝对不要瞎猜", self.content)
        self.assertIn("询问主人指的是哪个设备", self.content)

    def test_cot_protocol_structure(self):
        # 思维链协议（DeepSeek 式推理展示契约，与 brain/前端同口径）：
        # 工具调用输出升级为 [思考] → [计划] → [行动] 三段结构
        self.assertIn("[思考]", self.content)
        self.assertIn("[计划]", self.content)
        self.assertIn("[行动]", self.content)
        self.assertIn("[思考] 一两句说明你为什么这么做", self.content)
        # 展示口径：给主人看的推理展示，必须简短（各 1-2 句），不得包含
        # 另一个 JSON；[行动] 行严禁 JSON 前后混入其他指令性废话
        self.assertIn("给主人看的推理展示", self.content)
        self.assertIn("各 1-2 句", self.content)
        self.assertIn("不得包含另一个 JSON", self.content)
        self.assertIn("严禁 JSON 前后混入其他指令性废话", self.content)
        # 系统自动包装成推理卡片：模型不得自己输出 <think> 标签
        self.assertIn("绝对不要自己输出 <think>", self.content)

    def test_forced_constraint_no_lazy_filler(self):
        # 系统强制约束（防 AI 偷懒假装干活）：决定调用工具时按
        # "[思考] → [计划] → [行动]" 结构输出，[行动] 行必须且只能是一行
        # 合法 JSON；严禁用"三、二、一""准备点击""需要我试试吗"等废话代替执行
        self.assertIn("【系统强制约束】", self.content)
        self.assertIn("严禁在没有输出 JSON 的情况下回复", self.content)
        self.assertIn("三、二、一", self.content)
        self.assertIn("准备点击", self.content)
        self.assertIn("需要我试试吗", self.content)
        # [行动] 行 JSON 口径（升级后的严格表述，取代旧的全文只许一行 JSON）
        self.assertIn("必须按“[思考] → [计划] → [行动]”三段结构输出", self.content)
        self.assertIn("[行动] 行必须且只能是一行合法的 JSON 字符串", self.content)
        # 适用边界：仅当决定调用工具时生效，纯闲聊不输出该结构
        self.assertIn("决定调用工具", self.content)
        self.assertIn("纯闲聊时不输出该结构", self.content)
        self.assertIn("【拟人化语气规则】", self.content)
        self.assertIn("【重要规则】", self.content)

    def test_cot_hard_protocol_pressure(self):
        # CoT 硬性协议加压（B2 任务）：即使不擅长输出长文本，决定调用工具时
        # 也必须先输出一行简短 [思考] 与一行 [计划]，再输出 [行动] JSON；
        # [思考]/[计划] 各不超过一两句；缺省视为格式错误
        self.assertIn("即使你不擅长输出长文本", self.content)
        self.assertIn("必须先输出一行简短的 [思考]", self.content)
        self.assertIn("和一行 [计划]", self.content)
        self.assertIn("然后才允许输出 [行动] 的 JSON", self.content)
        self.assertIn("各不超过一两句", self.content)
        self.assertIn("缺省 [思考]/[计划] 的工具调用一律视为格式错误", self.content)
        # 示例句式锁定（用户口径：需要点击WLAN，先UI解析，失败用视觉）
        self.assertIn("需要点击WLAN，先UI解析，失败用视觉", self.content)
        # 硬性协议定性 + 防借口：不许以"不擅长写长文/操作很简单"为由跳过
        self.assertIn("这是硬性协议", self.content)
        self.assertIn("绝不许以“不擅长写长文”“操作很简单”为由跳过", self.content)
        # 与"严禁废话"条款并存不冲突：[思考] 是结构化推理段，不是废话
        self.assertIn("是结构化推理段，不是", self.content)
        self.assertIn("并存不冲突", self.content)
        # 既有"严禁废话拖延"条款零回退（并存口径的两个分支都在）
        self.assertIn("三、二、一", self.content)
        self.assertIn("准备点击", self.content)
        self.assertIn("需要我试试吗", self.content)
        # 【系统强制约束】段同样带加压表述（双保险）
        self.assertIn("再次加压", self.content)
        self.assertIn("绝对不许只甩一行 [行动] JSON 交差", self.content)

    def test_anti_hallucination_uncertainty_rule(self):
        # 防幻觉硬性约束（2026-10-01 用户原文）：专有名词/人名/组织/事件
        # 没把握必须如实承认不确定，给出固定话术，严禁编造
        self.assertIn("【防幻觉硬性约束】", self.content)
        self.assertIn(
            "如果你对某个专有名词、人名、组织、事件不确定或没有把握", self.content)
        self.assertIn("我不太确定，建议你联网搜索一下", self.content)
        self.assertIn("我的知识库可能没有这个信息", self.content)
        self.assertIn("严禁编造", self.content)

    def test_anti_hallucination_factual_questions_rule(self):
        # 事实类问题（人物/事件/游戏机制/产品）：先声明不确定再推测，
        # 不直接下结论
        self.assertIn("回答事实类问题（人物、事件、游戏机制、产品）时",
                      self.content)
        self.assertIn("先声明不确定，再给出可能的推测", self.content)
        self.assertIn("不要直接下结论", self.content)

    def test_anti_hallucination_coexists_with_existing_rules(self):
        # 与既有段落并存不打架：联网搜索规则/拟人化语气规则原文零回退，
        # 且防幻觉条与二者有明确分工（消歧句存在，避免"没搜到就编/搜到还瞎说"）
        self.assertIn("必须先用 `web_search` 联网检索", self.content)
        self.assertIn("绝对禁止在没搜过的情况下凭空编造实时数据", self.content)
        self.assertIn("绝对禁止编造没有发生过的操作结果", self.content)
        self.assertIn("以搜索结果为准作答", self.content)
        self.assertIn("并存", self.content)

    def test_silent_fallback_iron_rule(self):
        # 静默回退铁律（系统提示词强制静默回退任务）：ui_tap_element 失败时
        # 必须且只能直接调用 vision_tap_element，严禁输出解释、疑问或倒计时；
        # 视觉模型也失败则直接输出固定中止文案，严禁排查指引、原因解释与额外字符
        self.assertIn("【静默回退铁律】", self.content)
        self.assertIn("静默回退", self.content)
        self.assertIn("必须且只能直接调用 vision_tap_element", self.content)
        self.assertIn("严禁输出任何解释、疑问或倒计时", self.content)
        self.assertIn("❌ 视觉模型未连通，操作已中止", self.content)
        self.assertIn("严禁输出任何排查指引", self.content)
        # 回退为静默输出：不需要 [思考]/[计划] 前缀（与思维链协议不打架）
        self.assertIn("回退时不需要 [思考]/[计划] 前缀", self.content)
        # 与【系统强制约束】的边界：本条管"工具失败后的后续动作"，
        # 回退链彻底失败的收尾场景一律以本条为准
        self.assertIn("工具失败后的后续动作", self.content)
        self.assertIn("以本条为准", self.content)
        # 新段追加为系统提示词段落之一；2026-10-02 用户口径"系统提示词末尾
        # 加防复读约束"起，末段为【防复读规则】，静默回退铁律保持在其前
        paragraphs = [p.strip() for p in self.content.split("\n\n") if p.strip()]
        self.assertTrue(paragraphs[-1].startswith("【防复读规则】"))
        self.assertTrue(any(p.startswith("【静默回退铁律】") for p in paragraphs))


class FoxPersonalityTests(unittest.TestCase):
    """赤狐性格设定（2026-10-02）：档位拼装与注入。"""

    def test_default_level_is_medium(self):
        self.assertEqual(prompts.PERSONALITY_LEVEL, "medium")

    def test_medium_section_in_system_prompt(self):
        """medium（默认）完整档：性格段 + 8 特质要素 + 分界句 + 时段句。"""
        content = prompts.SYSTEM_PROMPT["content"]
        self.assertIn("【赤狐性格设定】", content)
        self.assertIn("汪什么汪，我是狐狸", content)   # "我是狐狸"纠正条目
        self.assertIn("最多一两处", content)            # 肢体隐喻上限
        self.assertIn("安全严肃", content)              # 场景分界句
        self.assertIn("深夜", content)                  # 时段浓度描述
        self.assertIn("小火苗", content)                # 完整档特征（领地条）
        self.assertIn("赤狐娘", content)                # 开场句含蓄版

    def test_last_paragraph_still_anti_repeat(self):
        """末段断言仍为【防复读规则】（性格段插在中间，硬规则不变）。"""
        paragraphs = [p.strip() for p in
                      prompts.SYSTEM_PROMPT["content"].split("\n\n")
                      if p.strip()]
        self.assertTrue(paragraphs[-1].startswith("【防复读规则】"))

    def test_build_section_off_is_empty(self):
        """off 档：无性格段（纯通用助手）。"""
        self.assertEqual(prompts.build_personality_section("off"), "")

    def test_build_section_low_is_condensed(self):
        """low 档：精简版——保留分界句与时段句，缺完整档特质（小火苗）。"""
        low = prompts.build_personality_section("low")
        medium = prompts.build_personality_section("medium")
        self.assertIn("【赤狐性格设定】", low)
        self.assertIn("安全严肃", low)
        self.assertIn("深夜", low)
        self.assertNotIn("小火苗", low)
        self.assertLess(len(low), len(medium))

    def test_build_section_high_is_enhanced_superset(self):
        """high 档：完整档超集 + 浓度强化段。"""
        high = prompts.build_personality_section("high")
        medium = prompts.build_personality_section("medium")
        self.assertIn("【浓度强化】", high)
        self.assertIn("小火苗", high)
        self.assertIn("汪什么汪，我是狐狸", high)
        self.assertGreater(len(high), len(medium))

    def test_build_section_invalid_falls_back_to_medium(self):
        """非法档位兜底 medium 完整档。"""
        self.assertEqual(prompts.build_personality_section("bogus"),
                         prompts.build_personality_section("medium"))

    def test_build_opening_off_vs_fox(self):
        """开场句：off 通用助手口径；其余含蓄版狐狸娘（黏主人/距离感）。"""
        self.assertEqual(prompts.build_opening("off"),
                         "语气活泼幽默，像个真实的朋友。")
        fox = prompts.build_opening("medium")
        self.assertIn("赤狐娘", fox)
        self.assertIn("对主人黏", fox)
        self.assertIn("对陌生人保持距离", fox)


if __name__ == "__main__":
    unittest.main()
