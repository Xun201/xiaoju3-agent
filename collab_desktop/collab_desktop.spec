# -*- mode: python ; coding: utf-8 -*-
"""小橘协作工作台 打包 spec（独立桌面应用，onedir）"""
import os
from PyInstaller.utils.hooks import collect_data_files

from PyInstaller.utils.hooks import collect_data_files
wv_datas = collect_data_files('webview')   # WebView2Loader.dll/.NET 绑定/js 全收

a = Analysis(
    ['app.py'],
    pathex=[SPECPATH, os.path.dirname(SPECPATH)],
    binaries=[],
    datas=[(os.path.join(SPECPATH, 'ui', 'index.html'), 'ui')] + wv_datas,
    hiddenimports=[
        'webview',
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
        'webview.platforms.mshtml',
        'clr',                      # pythonnet（WebView2 绑定，主项目同款链）
        'collab_hub',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='小橘协作工作台',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # 无黑窗
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='小橘协作工作台',
)
