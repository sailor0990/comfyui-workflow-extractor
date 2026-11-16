# -*- mode: python ; coding: utf-8 -*-
# Windows 打包 spec：单文件 EXE（WebView2 / EdgeChromium 后端）
# 用法：pyinstaller --noconfirm --clean "ComfyUI Workflow Extractor-windows.spec"

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('index.html', '.')],
    hiddenimports=[
        'webview',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'clr',
        'clr_loader',
        'pythonnet',
        'http.server',
        'socketserver',
        'mimetypes',
        'urllib.request',
        'email',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ComfyUI-Workflow-Extractor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
