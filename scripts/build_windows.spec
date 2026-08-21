# -*- mode: python ; coding: utf-8 -*-
"""靶场扫描助手 Windows 单文件构建配置。

默认构建为精简版：不把约 700MB 的 Chromium 浏览器压进 EXE。
设置 VULANHUB_INCLUDE_CHROMIUM=1 时才构建带截图浏览器的完整版。
"""

import os
from pathlib import Path
import importlib.util

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve().parent
INCLUDE_CHROMIUM = os.environ.get("VULANHUB_INCLUDE_CHROMIUM") == "1"
ICON_PATH = ROOT / ".artifacts" / "build" / "靶场扫描助手.ico"
if not ICON_PATH.is_file():
    raise RuntimeError(f"未找到 Windows 图标：{ICON_PATH}")

datas = [(str(ROOT / "scanner_app" / "desktop" / "web"), "scanner_app/desktop/web")]
binaries = []
hiddenimports = []

for package_name in ("webview",) + (("playwright",) if INCLUDE_CHROMIUM else ()):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

if INCLUDE_CHROMIUM:
    playwright_spec = importlib.util.find_spec("playwright")
    if playwright_spec is None or not playwright_spec.submodule_search_locations:
        raise RuntimeError("构建完整版需要 playwright")

    playwright_root = Path(next(iter(playwright_spec.submodule_search_locations)))
    bundled_browsers = playwright_root / "driver" / "package" / ".local-browsers"
    if not bundled_browsers.is_dir():
        raise RuntimeError(
            "未找到 Playwright Chromium。请先设置 PLAYWRIGHT_BROWSERS_PATH=0 "
            "并执行 python -m playwright install chromium"
        )
    datas.append((str(bundled_browsers), "playwright/driver/package/.local-browsers"))


a = Analysis(
    [str(ROOT / "scanner_app" / "desktop" / "gui.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[] if INCLUDE_CHROMIUM else ["playwright", "pyee", "greenlet"],
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
