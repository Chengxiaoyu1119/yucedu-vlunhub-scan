# 靶场扫描助手

一个面向靶场环境的双模式信息收集工具，提供 macOS 和 Windows 桌面启动方式，也支持命令行运行。

## 功能

- 公网 Web 靶场：Ping、TCP 端口扫描、HTTP/HTTPS 标题与 Server 识别、HTML 快照、首页截图和 favicon。
- 内网穿透靶场：ICMP + TCP 存活发现、TTL/端口指纹/SSH Banner/HTTP 标题辅助系统判断、ARP MAC 地址读取。
- 桌面界面：进度、日志、站点卡片、搜索排序、截图灯箱、离线图表和历史记录。
- 每次扫描生成 `report.html`、`report.md`、`report.csv`、`report.json`。

## 环境

- Python 3.10 或更高版本。
- GUI 依赖：`pywebview`。
- 首页截图和图表测试依赖：`playwright` 及 Chromium 浏览器。
- Windows 的 pywebview 会优先使用 EdgeChromium，未安装 Edge Runtime 时回退到系统可用的 MSHTML 渲染器。
- Windows 使用系统自带的 `ping`、`arp`、文件管理器和提示音；macOS 原有的通知、Finder、Dock 图标和提示音行为保留。

## 安装

在项目根目录打开 PowerShell、命令提示符或 Terminal。下面的 `python` 是 Python 解释器，用来安装项目依赖并启动程序。

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

如果只需要端口扫描、不需要截图，可以不安装 Chromium；程序会自动跳过截图。

## 启动

Windows：双击 `启动靶场扫描.bat`，启动器会保留控制台以显示依赖或运行错误；程序正常关闭后窗口自动退出。也可以执行：

```powershell
python range_gui.py
```

macOS：双击原有的 `启动靶场扫描.command`，或执行：

```bash
python3 range_gui.py
```

命令行公网扫描：

```bash
python range_scanner.py --targets TARGET --port-start 8000 --port-end 8099
```

命令行内网扫描：

```bash
python range_internal.py --cidrs 192.168.3.0/24,192.168.4.0/24
```

启动入口会先切换到项目目录。默认结果统一写入项目根目录下的 `scan_results/`，显式传入 `--output` 时使用指定目录。

## 项目结构

```text
range_gui.py          # pywebview 桌面 GUI 与 JS API 桥接
scanner_core.py       # 公网扫描核心
internal_scanner.py   # 内网发现核心
platform_support.py   # 路径、Ping/ARP、通知、文件管理器等平台适配
screenshot.py         # Playwright 异步截图池
reports.py            # HTML/Markdown/CSV/JSON 报告
range_scanner.py      # 公网 CLI
range_internal.py     # 内网 CLI
gui/                  # HTML/CSS/JavaScript/本地 Chart.js
启动靶场扫描.command  # macOS 启动器，保留
启动靶场扫描.bat     # Windows 启动器
```

## 验证

```bash
python -m compileall -q .
python -m unittest -v test_platform_support.py
python test_charts.py
python test_report_charts.py
```

两个 Playwright 测试需要先执行 `python -m playwright install chromium`。

## 版本管理

扫描结果、测试截图、缓存和 macOS/Windows 系统文件已加入 `.gitignore`，不会进入版本库。项目保留原有 macOS 启动器，同时将平台差异集中在 `platform_support.py`，便于后续维护。
