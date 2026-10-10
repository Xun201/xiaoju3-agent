# -*- mode: python ; coding: utf-8 -*-
"""小橘3号 · PyInstaller 打包规格（方案 docs/EXE_PACKAGING_PLAN.md 步 4，§4）。

- 入口 desktop_launcher.py（onefile，console=False 即 -w 无控制台）；
  spawn-self 三角色已由 argv 标志在代码层分流（步 2），spec 无需额外处理：
  desktop_launcher 顶层 import xiaoju3_dashboard（全链收录），分流分支内
  延迟 import xiaoju3_launcher——两者均被静态分析收录进 PYZ。
- datas 只放"运行期只读"资源（资源根 _MEIPASS 口径，步 1b 双根）：
  assets/、前端三件套、.env.example。plugins 不进 datas——插件为静态
  import（main.py from plugins.xxx import），列 hiddenimports 进 PYZ
  （对方案 §4 的一处实施修正）。
- playwright 收录（2026-10-04 拍板②方案 A）：lib + driver 进包（实测
  107.5MB），待办提取/链接日志的 DeepSeek 分享页抓取在冻结形态可用；
  Chromium 浏览器**不打包**（ms-playwright 缓存实测 705.6MB，远超拍板
  体积带）——运行期走目标机 ms-playwright 用户缓存目录（LOCALAPPDATA
  下；无缓存机器触发 link_logger 既有优雅降级文案，需自备浏览器缓存
  或设 PLAYWRIGHT_BROWSERS_PATH 环境变量指向缓存目录）。
- 产物 dist/xiaoju3.exe 不入库（*.exe 拒绝规则，b8507dc 口径）。
"""

from PyInstaller.utils.hooks import collect_all

# playwright lib+driver 收录（无官方 hook，hooks-contrib 2026.8 零命中；
# collect_all 覆盖包数据 + driver 二进制 + 全部子模块）
pw_datas, pw_binaries, pw_hiddenimports = collect_all('playwright')

a = Analysis(
    ['desktop_launcher.py'],
    pathex=[],
    binaries=pw_binaries,
    datas=[
        ('assets', 'assets'),              # 桌宠素材（pet/normal_half|full）+ ASSETS.md
        ('index.html', '.'),               # 前端三件套（dashboard 从资源根直读）
        ('console.js', '.'),
        ('desktop-pet.js', '.'),
        ('.env.example', '.'),             # 首启配置模板（数据根引导用）
        ('mood_rules.json', '.'),          # #271① M1 规则表（缺它 frozen 静默回退最小词表——20261010 真机实锤）
        ('mood_tone.json', '.'),           # #271① M2 语气映射表（缺它 M2 静默失效）
    ] + pw_datas,
    hiddenimports=[
        # ── pywebview Windows 后端链（6.x 默认 WinForms + WebView2 via pythonnet）──
        'webview',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'webview.platforms.mshtml',
        'clr',                              # pythonnet（WebView2 绑定）
        # ── pywin32 / wmi（温度读取、Windows API）──
        'wmi',
        'win32api',
        'win32con',
        'win32com',
        'win32com.client',
        # ── 第三方直接依赖 ──
        'psutil',
        'psutil._pswindows',
        'edge_tts',
        'openai',
        'bs4',
        'flask_cors',
        'requests',
        # ── 项目主链与延迟导入模块（显式列防漏收）──
        'paths',
        'xiaoju3',
        'xiaoju3_launcher',                 # spawn-self launcher 角色入口
        'xiaoju3_dashboard',
        'main',
        'brain',
        'prompts',
        'tools',
        'permission',
        'home_tools',
        'heartbeat',
        'migration',
        'emoji_manager',
        'run_link_log',
        'search_tools',
        'vision_tools',
        'android_ui_tools',
        'adb_tools',
        'auth_lv4',
        'intent_router',
        'web_sanitize',
        'hardware_profiler',
        'agent_state.state_manager',
        # ── plugins 包（静态 import，进 PYZ 而非 datas）──
        'plugins.accounting',
        'plugins.batch_logger',
        'plugins.context_manager',
        'plugins.ebook_export',
        'plugins.help_menu',
        'plugins.link_logger',
        'plugins.qq_send_image',
        'plugins.todo_extractor',
        'plugins.todo_aging',    # heartbeat 函数内 lazy import（modulegraph 可扫，显式列保险）
        'plugins.todo_text',     # #261：intent_router 字符串动态引用（importlib 对静态分析不可见，必须显式列）
        'plugins.todo_query',    # todo_query 意图（查待办直达）：intent_router 字符串动态引用，同上铁律
    ] + pw_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'pytest',
        'IPython',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,                  # onedir：二进制/数据由 COLLECT 落盘
    name='xiaoju3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=False,                          # -w 无控制台（桌面窗口即主入口）
    version='version_info.txt',             # 步 B1：bat 预生成（版本抓自 xiaoju3.py）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/xiaoju3.ico',              # 步 B1：make_build_assets.py 生成（源 pet/normal_half.png）
)

# onedir 收集（2026-10-07 冷启动根治拍板）：产物 dist\xiaoju3\（exe + _internal\），
# 三进程共享同一份磁盘文件、零解压——替代 onefile 的每次启动三进程×186MB 解压
# （_MEI 临时目录实测残留 46 个/8.3GB，且冷启动 83s 大头）。回滚：revert 本段
# 恢复 onefile 形态（paths.py 双根对两种形态均兼容，PyInstaller 6 onedir 亦设 _MEIPASS）。
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='xiaoju3',
)
