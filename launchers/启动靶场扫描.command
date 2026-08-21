#!/bin/bash
# 靶场扫描助手 · 双击启动器
# 双击本文件即可启动图形界面（无需打开终端敲命令）
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
nohup python3 -m scanner_app.desktop.gui >/dev/null 2>&1 &
disown
exit 0
