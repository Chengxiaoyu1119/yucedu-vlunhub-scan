# 参与贡献

感谢关注靶场扫描助手。项目欢迎文档改进、跨平台兼容性修复、测试补充和界面体验优化。

## 开始之前

请先阅读：

- [README](README.md)：功能边界、安装方式、项目结构和验证命令。
- [安全策略](SECURITY.md)：安全问题的私下报告方式。
- [行为准则](CODE_OF_CONDUCT.md)：参与讨论和提交代码时的基本要求。

## 本地开发

```bash
python -m venv .venv
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Windows 构建工具：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

macOS 构建工具：

```bash
RELEASE_VERSION=local bash ./scripts/build_macos.sh
```

## 修改原则

- 保持 Windows 和 macOS 的功能、交互和视觉语言一致。
- 扫描核心放在 `scanner_app/core/`；桌面桥接放在 `scanner_app/desktop/`；CLI 放在 `scanner_app/cli/`。
- 新生成物写入 `.artifacts/`，不要把 EXE、截图、日志、缓存或虚拟环境提交到版本库。
- 默认只实现本地靶场和安全教学所需的发现能力，不加入凭据爆破、漏洞利用、持久化或规避检测功能。
- 修改默认配置时，同时更新 GUI、CLI、测试和 README 中的说明。

## 提交前验证

```bash
python -B -m compileall -q scanner_app tests
python -B -m unittest -v tests.test_platform_support tests.test_project_structure
python -B -m tests.test_charts
python -B -m tests.test_report_charts
git diff --check
```

## Pull Request 清单

- [ ] 说明修改目的、影响范围和用户可见变化。
- [ ] 增加或更新了能够阻止回归的测试。
- [ ] 已运行与修改相关的最小验证，以及 README 中的项目检查。
- [ ] 没有提交 `.artifacts/`、缓存、日志、扫描结果、截图或本地环境。
- [ ] 如果修改跨平台行为，已分别说明 Windows 和 macOS 的验证情况。

提交标题建议使用简短动词开头，例如 `Fix Windows app icon`、`Improve README quick start`。
