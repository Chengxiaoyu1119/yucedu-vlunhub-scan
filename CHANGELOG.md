# 更新日志

项目遵循面向用户的版本记录。每个发行版同时发布 Windows 和 macOS 的可下载资产，并在 Release 页面记录校验值和已知限制。

## [Unreleased]

- 持续完善跨平台打包、文档和社区协作入口。

## [v2.1.1] - 2026-08-21

- 公网扫描默认端口范围统一为 `8000–8020`。
- 修复 Windows EXE 的多尺寸 VLUN 图标嵌入，避免资源管理器回退显示通用图标。
- 增加 macOS Apple Silicon 和 Intel 应用包的自动构建与上传流程。
- 增加 README 首页预览图和文档素材目录。

## [v2.1.0] - 2026-08-21

- 整理运行代码、桌面资源、启动器、构建脚本和测试目录。
- Windows 默认构建精简版 EXE，不内置 Chromium。
- 统一 Windows/macOS 页面视觉和交互细节。
- 增加跨平台 CI、项目结构回归测试和 Windows 构建检查。

## [v2.0.0] - 2026-08-20

- 完成 macOS / Windows 双平台启动入口和平台适配。
- 提供 Windows 便携式桌面发行包。
- 公网 Web 与内网发现共用扫描核心，输出 HTML、Markdown、CSV、JSON 报告。

[Unreleased]: https://github.com/Chengxiaoyu1119/yucedu-vlunhub-scan/compare/v2.1.1...HEAD
[v2.1.1]: https://github.com/Chengxiaoyu1119/yucedu-vlunhub-scan/releases/tag/v2.1.1
[v2.1.0]: https://github.com/Chengxiaoyu1119/yucedu-vlunhub-scan/releases/tag/v2.1.0
[v2.0.0]: https://github.com/Chengxiaoyu1119/yucedu-vlunhub-scan/releases/tag/v2.0.0
