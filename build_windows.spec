# -*- mode: python ; coding: utf-8 -*-
"""靶场扫描助手 Windows 单文件构建配置。"""

from pathlib import Path
import importlib.util

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve()
datas = [(str(ROOT / "gui"), "gui")]
binaries = []
hiddenimports = []

for package_name in ("webview", "playwright"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

playwright_spec = importlib.util.find_spec("playwright")
if playwright_spec is None or not playwright_spec.submodule_search_locations:
    raise RuntimeError("构建环境缺少 playwright")

playwright_root = Path(next(iter(playwright_spec.submodule_search_locations)))
bundled_browsers = playwright_root / "driver" / "package" / ".local-browsers"
if not bundled_browsers.is_dir():
    raise RuntimeError(
        "未找到 Playwright Chromium。请先设置 PLAYWRIGHT_BROWSERS_PATH=0 "
        "并执行 python -m playwright install chromium"
    )
datas.append((str(bundled_browsers), "playwright/driver/package/.local-browsers"))


a = Analysis(
    [str(ROOT / "range_gui.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
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
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
