#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内网穿透靶场 CLI 入口（核心逻辑在 internal_scanner.py，与 GUI 共用）

用法：
  python3 range_internal.py                          # 默认扫 192.168.3.0/24 与 192.168.4.0/24
  python3 range_internal.py --cidrs 192.168.3.0/24   # 自定义网段
  python3 range_internal.py --ports 22,445,3389      # 自定义探测端口
"""

import argparse
import re

import internal_scanner
from platform_support import configure_console


def parse_args():
    p = argparse.ArgumentParser(description="内网穿透靶场存活与系统发现（无凭据）")
    p.add_argument("--cidrs", default=",".join(internal_scanner.DEFAULT_CIDRS),
                   help="目标网段 CIDR，逗号分隔（默认：192.168.3.0/24,192.168.4.0/24）")
    p.add_argument("--ports", default=",".join(map(str, internal_scanner.DEFAULT_PORTS)),
                   help="探测端口，逗号分隔（默认：22,80,443,135,139,445,3389,8080）")
    p.add_argument("--timeout", type=float, default=1.0, help="单次探测超时秒数（默认 1）")
    p.add_argument("--threads", type=int, default=200, help="并发线程数（默认 200）")
    p.add_argument("--output", default="", help="结果输出目录（默认 scan_results/internal_<时间戳>）")
    args = p.parse_args()
    try:
        args.port_list = sorted({int(x) for x in re.split(r"[,，\s]+", args.ports) if x.strip()})
    except ValueError:
        p.error("--ports 应为逗号分隔的数字")
    args.cidr_list = [c.strip() for c in args.cidrs.split(",") if c.strip()]
    if not args.cidr_list:
        p.error("--cidrs 不能为空")
    return args


def print_event(evt):
    t = evt["type"]
    if t == "scan_start":
        print(f"内网扫描启动：网段 {', '.join(evt['cidrs'])}（共 {evt['total_hosts']} 个 IP），"
              f"探测端口 {', '.join(map(str, evt['ports']))}")
    elif t == "progress":
        label = "ICMP 存活探测" if evt["phase"] == "ping" else "端口与系统探测"
        if evt["done"] % 64 == 0 or evt["done"] == evt["total"]:
            print(f"  [{label}] {evt['done']}/{evt['total']}")
    elif t == "host_found":
        ports = f" · 端口 {','.join(map(str, evt['open_ports']))}" if evt["open_ports"] else ""
        print(f"  [+] {evt['ip']:<16} 存活（{evt['via'].upper()}" +
              (f"，TTL={evt['ttl']}" if evt.get("ttl") is not None else "") +
              f"）→ {evt['os_guess']}{ports}")
        for r in evt["reasons"]:
            print(f"        - {r}")
    elif t == "mac_resolved":
        if evt["macs"]:
            print("\n  ARP MAC 地址表：")
            for ip, mac in evt["macs"].items():
                print(f"    {ip:<16} {mac}")
    elif t == "scan_done":
        c = evt.get("counts") or {}
        if evt["cancelled"]:
            print("\n扫描已取消")
        else:
            print(f"\n========== 内网扫描汇总 ==========")
            print(f"存活主机 {c.get('存活主机', 0)} 台："
                  f"Linux {c.get('Linux', 0)} · Windows {c.get('Windows', 0)} · "
                  f"未知 {c.get('未知', 0)}（共扫描 {c.get('总 IP 数', 0)} 个 IP）")
        print(f"分类报告已保存：{evt['results_dir']}（report.html / report.md / report.csv）")
    elif t == "error":
        print(f"  [错误] {evt['message']}")


def main():
    configure_console()
    args = parse_args()
    internal_scanner.run_internal_scan(
        cidrs=args.cidr_list,
        ports=args.port_list,
        timeout=args.timeout,
        threads=args.threads,
        output=args.output,
        on_event=print_event,
    )


if __name__ == "__main__":
    main()
