"""桌宠去白底 + 翻转吸附修复 单元测试（纯静态断言，离线零依赖）。

覆盖口径（2026-10-01 修复）：
1. 形象图白底：注入样式含 mix-blend-mode: multiply（实际声明在 .xiaoju-root
   上——fixed 容器自成堆叠上下文，元素级 multiply 会被隔离无法混到页面底色）；
2. 气泡 SVG 去白底：fill 白色改为 transparent（页面底色自然透出）；
3. 翻转吸附修复：面向由桌宠中心 x 相对屏幕中线（innerWidth / 2）决定，
   吸附校正后按最终位置重算一次；旧的"拖拽位移方向决定面向"已移除。
"""
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PET_JS = BASE / "desktop-pet.js"
ASSETS_MD = BASE / "assets" / "ASSETS.md"


class DesktopPetWhiteBgTests(unittest.TestCase):
    """任务 1：去白底。"""

    @classmethod
    def setUpClass(cls):
        cls.js = PET_JS.read_text(encoding="utf-8")

    def _injected_style(self) -> str:
        """提取注入的 CSS（style.textContent 模板串）。"""
        marker = "style.textContent = `"
        start = self.js.index(marker) + len(marker)
        end = self.js.index("`;", start)
        return self.js[start:end]

    def test_multiply_in_injected_style(self):
        # 形象图白底：multiply 混合已注入样式（声明于 .xiaoju-root 整组）
        style = self._injected_style()
        self.assertIn("mix-blend-mode: multiply", style)
        self.assertIn("mix-blend-mode: multiply", self.js)

    def test_svg_bubble_no_white_fill(self):
        # 气泡 SVG 无白色填充；实际值：透明填充 ×3（bshape/b1/b2）
        svg_start = self.js.index("<svg viewBox")
        svg_end = self.js.index("</svg>", svg_start)
        svg = self.js[svg_start:svg_end]
        self.assertNotIn("FFFFFF", svg.upper())
        self.assertEqual(svg.count('fill="transparent"'), 3)

    def test_assets_md_transparent_note(self):
        # ASSETS.md 末尾"透明化说明"：代码自动处理 + 用户可替换透明 PNG
        md = ASSETS_MD.read_text(encoding="utf-8")
        self.assertIn("透明化说明", md)
        self.assertIn("mix-blend-mode", md)
        self.assertIn("透明通道 PNG", md)
        self.assertIn("文件名保持不变", md)


class DesktopPetFlipSnapTests(unittest.TestCase):
    """任务 2：翻转方向按屏幕中线判定 + 吸附后重算。"""

    @classmethod
    def setUpClass(cls):
        cls.js = PET_JS.read_text(encoding="utf-8")

    def test_flip_decided_by_midline(self):
        # 翻转判定含屏幕中线逻辑（innerWidth / 2）
        self.assertIn("window.innerWidth / 2", self.js)
        self.assertIn("updateFacingByPosition", self.js)
        # 核心判定：centerX < 中线 → 朝右（左半边朝右、右半边朝左，朝向中心）
        self.assertRegex(self.js, r"centerX\s*<\s*midLine\s*\?\s*'right'\s*:\s*'left'")


class DesktopPetResizeGeometryTests(unittest.TestCase):
    """窗口缩放几何（2026-10-04 尾巴 3+4）：底界含输入框 + 右/下贴边锚点跟随
    + 缩球态守卫 + 视口记忆基线。"""

    @classmethod
    def setUpClass(cls):
        cls.js = PET_JS.read_text(encoding="utf-8")

    def _resize_body(self):
        start = self.js.index("window.addEventListener('resize'")
        end = self.js.index("});", start)
        return self.js[start:end]

    def test_resize_bottom_limit_uses_input_area(self):
        # 尾巴 A：resize 收钳底界与拖拽/出生位同口径（输入框上沿），
        # 不得再出现裸 window.innerHeight 直接收钳 top 的旧写法
        body = self._resize_body()
        self.assertIn("chat-input-area", body)
        self.assertIn("limitBottom", body)

    def test_resize_anchor_follows_edges(self):
        # 尾巴 B：右/下贴边锚点跟随（旧窗距离 + ε 容差 + 贴边保持）
        body = self._resize_body()
        self.assertIn("distRight", body)
        self.assertIn("distBottom", body)
        self.assertIn("ANCHOR_EPSILON", body)

    def test_resize_guard_and_viewport_memory(self):
        # 缩球态守卫（display:none 早退）+ lastViewport 视口记忆基线
        body = self._resize_body()
        self.assertIn("display === 'none'", body)
        self.assertIn("captureViewport()", self.js)
        self.assertIn("lastViewport", self.js)

    def test_old_drag_direction_flip_removed(self):
        # 旧的"拖拽水平位移方向决定面向"逻辑已移除（翻错方向的根因）
        self.assertNotIn("dx > 0 ? 'right' : 'left'", self.js)

    def test_recalc_facing_after_snap(self):
        # pointerup 内：先 snapToEdge 吸附校正，再按最终位置重算面向
        up = self.js.index("addEventListener('pointerup'")
        snap = self.js.index("snapToEdge();", up)
        self.assertIn("updateFacingByPosition();", self.js[snap:snap + 200])

    def test_facing_called_in_drag_and_snap(self):
        # 拖拽中实时更新 + 松手吸附后重算：至少两处调用 + 一处定义
        self.assertGreaterEqual(self.js.count("updateFacingByPosition()"), 3)
        self.assertGreaterEqual(self.js.count("function updateFacingByPosition()"), 1)

    def test_existing_specs_untouched(self):
        # 既有规格零回退（与 test_dashboard 口径对齐的抽样）
        for token in ("window.__xiaoju3Pet", "SNAP_THRESHOLD = 24", "snapToEdge",
                      "facing-right", "xiaoju-flip", "scaleX(-1)", "PET_LINES",
                      "/assets/DSniang1.jpg", "img-ok", "xiaoju-overlay",
                      "xiaoju-pop", "dx * dx + dy * dy > 9"):
            self.assertIn(token, self.js)


if __name__ == "__main__":
    unittest.main()
