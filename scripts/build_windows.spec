# -*- mode: python ; coding: utf-8 -*-
"""靶场扫描助手 Windows 构建配置。

构建把 Playwright Python/协议运行时放进 EXE，把 Chromium 和 Node 驱动放到
EXE 同级的 playwright-browsers/、playwright-runtime/ 目录，保证截图功能可用且 EXE 保持精简。
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve().parent
ICON_PATH = ROOT / ".artifacts" / "build" / "靶场扫描助手.ico"
if not ICON_PATH.is_file():
    raise RuntimeError(f"未找到 Windows 图标：{ICON_PATH}")

datas = [(str(ROOT / "scanner_app" / "desktop" / "web"), "scanner_app/desktop/web")]
webview_datas, webview_binaries, webview_hiddenimports = collect_all("webview")
datas += webview_datas
binaries = webview_binaries
hiddenimports = webview_hiddenimports


a = Analysis(
    [str(ROOT / "scanner_app" / "desktop" / "gui.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "scripts" / "pyinstaller_hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="靶场扫描助手",
    icon=str(ICON_PATH),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
