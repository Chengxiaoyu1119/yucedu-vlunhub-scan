#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目边界回归测试。

这些检查把目录规范变成可执行约束：运行代码、测试、启动器、构建脚本和
生成产物各自有固定归属，旧版根目录文件重新出现时会立即暴露。
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]

ALLOWED_ROOT_ENTRIES = {
    ".artifacts",
    ".gitattributes",
    ".github",
    ".git",
    ".gitignore",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "docs",
    "launchers",
    "requirements-build.txt",
    "requirements.txt",
    "scanner_app",
    "scripts",
    "tests",
}

LEGACY_ROOT_FILES = {
    "internal_scanner.py",
    "platform_support.py",
    "range_gui.py",
    "range_internal.py",
    "range_scanner.py",
    "reports.py",
    "scanner_core.py",
    "screenshot.py",
    "test_charts.py",
    "test_platform_support.py",
    "test_report_charts.py",
    "build_windows.ps1",
    "build_windows.spec",
}


def visible_names(path: Path) -> set[str]:
    """返回目录中应纳入结构检查的名称，忽略缓存目录和系统文件。"""
    ignored = {"__pycache__", ".DS_Store", "Thumbs.db", "Desktop.ini"}
    return {item.name for item in path.iterdir() if item.name not in ignored}


class ProjectStructureTests(unittest.TestCase):
    def test_root_has_only_declared_boundaries(self):
        actual = visible_names(ROOT)
        self.assertTrue(
            actual <= ALLOWED_ROOT_ENTRIES,
            f"根目录出现未声明条目：{sorted(actual - ALLOWED_ROOT_ENTRIES)}",
        )
        self.assertFalse((ROOT / "gui").exists())
        self.assertFalse((ROOT / "launchers").is_file())

    def test_legacy_runtime_files_are_not_at_root(self):
        root_files = {item.name for item in ROOT.iterdir() if item.is_file()}
        self.assertTrue(
            root_files.isdisjoint(LEGACY_ROOT_FILES),
            f"旧版散落文件仍在根目录：{sorted(root_files & LEGACY_ROOT_FILES)}",
        )

    def test_runtime_boundaries(self):
        self.assertEqual(
            visible_names(ROOT / "scanner_app"),
            {"__init__.py", "cli", "core", "desktop"},
        )
        self.assertEqual(
            visible_names(ROOT / "scanner_app" / "cli"),
            {"__init__.py", "internal.py", "public.py"},
        )
        self.assertEqual(
            visible_names(ROOT / "scanner_app" / "desktop"),
            {"__init__.py", "gui.py", "web"},
        )
        self.assertEqual(
            visible_names(ROOT / "scanner_app" / "desktop" / "web"),
            {"app.js", "app_icon.png", "app_icon.svg", "chart.umd.min.js", "index.html", "style.css"},
        )
        self.assertEqual(
            visible_names(ROOT / "launchers"),
            {"启动靶场扫描.command", "启动靶场扫描.vbs"},
        )
        self.assertEqual(
            visible_names(ROOT / "scripts"),
            {"build_macos.sh", "build_windows.ps1", "build_windows.spec"},
        )

    def test_documentation_preview_asset_stays_outside_runtime_resources(self):
        self.assertEqual(visible_names(ROOT / "docs"), {"assets"})
        self.assertEqual(visible_names(ROOT / "docs" / "assets"), {"app-preview.png"})

    def test_open_source_project_documents_are_present(self):
        for name in (
            "README.md",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "CODE_OF_CONDUCT.md",
            "SECURITY.md",
            "LICENSE",
        ):
            self.assertTrue((ROOT / name).is_file(), f"缺少开源项目文档：{name}")

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/assets/app-preview.png", readme)
        self.assertIn("actions/workflows/ci.yml", readme)
        self.assertIn("mermaid", readme)
        self.assertIn("8000–8020", readme)

        self.assertTrue((ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").is_file())
        self.assertTrue((ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").is_file())
        self.assertTrue((ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml").is_file())
        self.assertTrue((ROOT / ".github" / "dependabot.yml").is_file())

    def test_test_files_stay_in_test_boundary(self):
        self.assertEqual(
            visible_names(ROOT / "tests"),
            {
                "__init__.py",
                "test_charts.py",
                "test_platform_support.py",
                "test_project_structure.py",
                "test_report_charts.py",
            },
        )

    def test_generated_output_has_one_home(self):
        ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".artifacts/", ignore_text)
        self.assertIn("__pycache__/", ignore_text)
        for legacy_output in ("scan_results/", "test_shots/", "playwright-report/", "test-results/", "build/", "dist/"):
            self.assertNotIn(legacy_output, ignore_text)
        from scanner_app.core.platform_support import DATA_ROOT, RESULTS_ROOT

        self.assertEqual(DATA_ROOT, ROOT / ".artifacts")
        self.assertEqual(RESULTS_ROOT, ROOT / ".artifacts" / "results")

    def test_launchers_and_build_keep_one_user_entry_per_platform(self):
        windows_launcher = (ROOT / "launchers" / "启动靶场扫描.vbs").read_text(encoding="utf-8")
        macos_launcher = (ROOT / "launchers" / "启动靶场扫描.command").read_text(encoding="utf-8")
        build_spec = (ROOT / "scripts" / "build_windows.spec").read_text(encoding="utf-8")
        macos_build = (ROOT / "scripts" / "build_macos.sh").read_text(encoding="utf-8")

        self.assertIn("shell.Run", windows_launcher)
        self.assertIn(", 0, False", windows_launcher)
        self.assertNotIn("cmd.exe", windows_launcher.lower())
        self.assertIn("scanner_app.desktop.gui", macos_launcher)
        self.assertNotIn("range_gui.py", macos_launcher)
        self.assertIn('console=False', build_spec)
        self.assertIn('scanner_app/desktop/web', build_spec)
        self.assertIn('icon=str(ICON_PATH)', build_spec)
        self.assertIn('INCLUDE_CHROMIUM', build_spec)
        build_script = (ROOT / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn('[switch]$IncludeChromium', build_script)
        self.assertIn('New-WindowsIconFromPng', build_script)
        self.assertIn('sizes = @(16, 24, 32, 48, 64, 128, 256)', build_script)
        self.assertIn('$frame.Data.Length', build_script)
        self.assertIn('VULANHUB_INCLUDE_CHROMIUM', build_script)
        self.assertIn('iconutil -c icns', macos_build)
        self.assertIn('PyInstaller', macos_build)
        self.assertIn('pyobjc-framework-WebKit', macos_build)
        self.assertNotIn('projectDir, "dist\\"', windows_launcher)
        build_requirements = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")
        self.assertNotIn('-r requirements.txt', build_requirements)

    def test_public_scan_defaults_use_8000_to_8020(self):
        from scanner_app.core import scanner_core
        from scanner_app.desktop.gui import Api

        self.assertEqual(scanner_core.DEFAULT_PUBLIC_PORT_START, 8000)
        self.assertEqual(scanner_core.DEFAULT_PUBLIC_PORT_END, 8020)
        self.assertEqual(scanner_core.run_scan.__defaults__[:2], (8000, 8020))
        self.assertEqual(Api().get_config()["port_end"], 8020)

        cli_source = (ROOT / "scanner_app" / "cli" / "public.py").read_text(encoding="utf-8")
        page_source = (ROOT / "scanner_app" / "desktop" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("DEFAULT_PUBLIC_PORT_END", cli_source)
        self.assertIn('data-ps="8000" data-pe="8020"', page_source)

    def test_no_old_path_references_remain(self):
        forbidden = (
            "range_scanner.py",
            "range_internal.py",
            "range_gui.py",
            "gui/index.html",
            "gui/style.css",
            "gui/app.js",
            "启动靶场扫描.bat",
        )
        candidates = []
        for pattern in ("*.py", "*.ps1", "*.spec", "*.md", "*.yml", "*.vbs", "*.command"):
            candidates.extend(ROOT.rglob(pattern))
        for path in candidates:
            if ".artifacts" in path.parts or ".git" in path.parts:
                continue
            if path.resolve() == Path(__file__).resolve():
                continue
            text = path.read_text(encoding="utf-8")
            for old_path in forbidden:
                self.assertNotIn(old_path, text, f"{path} 仍引用旧路径 {old_path}")


if __name__ == "__main__":
    unittest.main()
