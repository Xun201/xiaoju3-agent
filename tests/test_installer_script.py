# -*- coding: utf-8 -*-
"""xiaoju3.iss [Code] 段静态锚（安装器步 B3 修复，docs/INSTALLER_STEP_B3_CODE_FIX_DESIGN.md §6）。

锁定时序重构不回退：裸 StrToInt64 禁令 / InitializeSetup 钩子体禁建页与
Wizard* / WizardWasCreated 旗三锚 / InitializeWizard 建页 / 无法预判降级文案 /
磁盘 WQL DriveType=3 / UTF-8 BOM + 纯 CRLF 编码防回归，外加报告五行格式红线锁
（消费端 parse_installer_report 590e7d8 按此解析）。
静态锚只防回退，真机行为归 B3b 演练（BUILD_BRIEF 纪律：行为与静态分开计数）。
"""
import os
import re
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_iss_bytes():
    with open(os.path.join(PROJECT_ROOT, "xiaoju3.iss"), "rb") as f:
        return f.read()


def _code_section(text):
    """切 [Code] 段（末段）：段头行起至文件尾。"""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == "[Code]")
    return "\n".join(lines[start:])


def _func_body(code_text, signature):
    """按函数边界精确切：签名行起，至首个顶格 end;（含）。
    不从 [Code] 段头起切——节头起切会把历史注释扫进断言范围的教训
    （P2 手术坑④同族：注释里的词会撞反向锚）。"""
    lines = code_text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(signature))
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "end;")
    return "\n".join(lines[start:end + 1])


def _strip_pascal_comments(text):
    """剥 { ... } 注释——反向锚（assertNotIn）必须打在剥注释后的代码上：
    注释里的文档性字面量（如禁令本身写成"禁止再出现裸 StrToInt64(..."）
    会撞自家反锚（本 session 三度实锤的注释字面量坑）。"""
    return re.sub(r"\{[^}]*\}", "", text)


class InstallerScriptAnchorTests(unittest.TestCase):
    """B3 修复七锚（对应设计稿 §6，锚序一致）+ 报告红线加码锁。"""

    @classmethod
    def setUpClass(cls):
        cls.code = _code_section(_read_iss_bytes().decode("utf-8-sig"))

    def test_anchor1_no_bare_strtoint64_outside_helper(self):
        """锚①：裸 StrToInt64( 全段禁绝（数值转换收敛 WmiFirstInt 单咽喉，
        StrToInt64Def( 恰一处）；探测调用点全走 WmiFirstInt(。
        断言打在剥注释后的代码上（注释含禁令文档字面量，不作数）。"""
        bare = _strip_pascal_comments(self.code)
        self.assertNotIn("StrToInt64(", bare)
        body = _strip_pascal_comments(
            _func_body(self.code, "function WmiFirstInt("))
        self.assertIn("StrToInt64Def(Trim(", body)
        self.assertGreaterEqual(bare.count("WmiFirstInt("), 2)

    def test_anchor2_initialize_setup_bans_wizard_and_page_creation(self):
        """锚②：InitializeSetup 函数体（按函数边界精确切 + 剥注释）禁建页
        与 Wizard*。"""
        body = _strip_pascal_comments(
            _func_body(self.code, "function InitializeSetup(): Boolean;"))
        for token in ("CreateOutputMsgPage", "CreateCustomPage", "CreateInputPage",
                      "WizardForm", "WizardSelectComponents",
                      "WizardIsComponentSelected"):
            self.assertNotIn(token, body)

    def test_anchor3_wizard_was_created_flag(self):
        """锚③：旗声明 + InitializeWizard 置 True（先于建页）+ Deinit 守卫
        + 写盘 ForceDirectories 前置（设计稿 §3）。"""
        self.assertIn("WizardWasCreated: Boolean;", self.code)
        initwiz = _func_body(self.code, "procedure InitializeWizard();")
        self.assertIn("WizardWasCreated := True;", initwiz)
        self.assertLess(initwiz.index("WizardWasCreated := True;"),
                        initwiz.index("CreateOutputMsgPage"))
        deinit = _func_body(self.code, "procedure DeinitializeSetup();")
        self.assertIn("if not WizardWasCreated then", deinit)
        self.assertIn("ForceDirectories(", deinit)

    def test_anchor4_initialize_wizard_creates_page(self):
        """锚④：InitializeWizard 存在且建自检页，锚点文案原样平移。"""
        initwiz = _func_body(self.code, "procedure InitializeWizard();")
        self.assertIn("CreateOutputMsgPage(wpInfoBefore,", initwiz)
        self.assertIn("'硬件自检'", initwiz)
        self.assertIn("'检测结果仅用于推荐安装形态'", initwiz)

    def test_anchor5_degraded_copy_no_lite_from_sentinel(self):
        """锚⑤：无法预判文案在（分档 + 内存/显卡/磁盘三行），且降级分支
        先于轻量版分支出现（哨兵路径不再触达轻量版）。"""
        self.assertIn("无法预判（程序首次运行将自动复测）", self.code)
        for line in ("内存：无法预判", "显卡：无法预判",
                     "安装目标盘可用空间：无法预判"):
            self.assertIn(line, self.code)
        self.assertLess(self.code.index("无法预判"),
                        self.code.index("推荐轻量版"))

    def test_anchor6_disk_native_query_no_wmi(self):
        """锚⑥（§8.2 修正）：磁盘走 Inno 原生 GetSpaceOnDisk64（不经 WMI
        服务，免疫安装瞬间未就绪）；WMI 磁盘查询退役禁回流。"""
        body = _func_body(self.code, "function InitializeSetup(): Boolean;")
        self.assertIn("GetSpaceOnDisk64(ExpandConstant('{localappdata}')", body)
        self.assertNotIn("DriveType=3", self.code)
        self.assertNotIn("Win32_LogicalDisk", self.code)

    def test_anchor8_wmi_retry_and_budget_gate(self):
        """§8.1 锚：WMI 重试 + 预算闸——MAX_WMI_ATTEMPTS 常量、Sleep(400)
        退避落在 WmiFirstValue 内、WmiUnavailable 先判后置（重试耗尽置位）。"""
        self.assertIn("MAX_WMI_ATTEMPTS = 3;", self.code)
        body = _func_body(self.code, "function WmiFirstValue(")
        self.assertIn("Sleep(400)", body)
        self.assertIn("if WmiUnavailable then", body)
        self.assertIn("WmiUnavailable := True", body)
        self.assertLess(body.index("if WmiUnavailable then"),
                        body.index("WmiUnavailable := True"))

    def test_anchor9_memory_fallback_dll(self):
        """§8.2 锚：内存备用 kernel32 GlobalMemoryStatusEx 导入声明 +
        备用函数接线（record 对齐真机实测一次，见 §8.2）。"""
        self.assertIn("GlobalMemoryStatusEx@kernel32.dll", self.code)
        self.assertIn("function TotalPhysKBBackup", self.code)
        body = _func_body(self.code, "function InitializeSetup(): Boolean;")
        self.assertIn("RamKb := TotalPhysKBBackup()", body)

    def test_anchor7_utf8_bom_and_pure_crlf_intact(self):
        """锚⑦：字节级 UTF-8 带 BOM + 纯 CRLF（Inno 中文 [Code] 官方要求
        + 本轮红线归一）。"""
        raw = _read_iss_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertGreater(raw.count(b"\n"), 0)
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))

    def test_report_five_line_format_red_line(self):
        """红线锚（七锚之外）：报告五行格式一字不改——时间戳口径、
        '硬件自检建议: ' 前缀（半角冒号+空格）、三布尔行、覆写落盘，
        消费端 parse_installer_report（590e7d8）按此解析。"""
        deinit = _func_body(self.code, "procedure DeinitializeSetup();")
        self.assertIn("GetDateTimeString('yyyy/mm/dd hh:nn:ss', '-', ':')", deinit)
        self.assertIn("'硬件自检建议: '", deinit)
        for key in ("ollama", "napcat", "ha"):
            self.assertIn(f"'{key}=' + YesNoStr(WizardIsComponentSelected('{key}'))",
                          deinit)
        self.assertIn("installer_report.txt", deinit)
        self.assertIn("Report, False);", deinit)

    def test_deinit_except_block_silent(self):
        """提前取消防线（2026-10-03 真机 Runtime error 23:118 教训）：app 常量
        在用户未走过选目录页 wpSelectDir 时未初始化——报告写入整体 try 包裹，
        except 静默跳过且段内绝不允许 ExpandConstant / ForceDirectories /
        SaveStringToFile 回流（except 内调 ExpandConstant 正是炸点）。
        断言打在剥注释后的代码面（注释里的禁令文档字样不作数，同锚①②口径）。"""
        deinit = _strip_pascal_comments(
            _func_body(self.code, "procedure DeinitializeSetup();"))
        except_idx = deinit.index("except")
        except_seg = deinit[except_idx:deinit.index("end;", except_idx)]
        self.assertNotIn("ExpandConstant", except_seg)
        self.assertNotIn("ForceDirectories", except_seg)
        self.assertNotIn("SaveStringToFile", except_seg)


if __name__ == "__main__":
    unittest.main()
