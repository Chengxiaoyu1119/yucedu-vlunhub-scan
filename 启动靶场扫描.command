#!/bin/bash
# 靶场扫描助手 · 双击启动器
# 双击本文件即可启动图形界面（无需打开终端敲命令）
cd "$(dirname "$0")"
nohup python3 range_gui.py >/dev/null 2>&1 &
disown
exit 0
