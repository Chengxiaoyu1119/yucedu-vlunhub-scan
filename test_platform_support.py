#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""平台适配层回归测试，不依赖桌面 GUI 或真实网络。"""

import os
import subprocess
import unittest

from platform_support import (
    PROJECT_ROOT,
    parse_arp_output,
    parse_ping_output,
    ping_command,
    resolve_output_dir,
    hidden_subprocess_kwargs,
)


class PlatformSupportTests(unittest.TestCase):
    def test_windows_ping_output(self):
        parsed = parse_ping_output("Reply from 127.0.0.1: bytes=32 time<1ms TTL=128")
        self.assertEqual(parsed["ttl"], 128)
        self.assertEqual(parsed["latency_ms"], 1.0)

    def test_macos_ping_output(self):
        parsed = parse_ping_output("64 bytes from 127.0.0.1: time=0.123 ms ttl=64")
        self.assertEqual(parsed["ttl"], 64)
        self.assertEqual(parsed["latency_ms"], 0.123)

    def test_arp_formats(self):
        output = """
        ? (192.168.3.10) at aa:bb:cc:dd:ee:ff on en0
        192.168.3.11    11-22-33-44-55-66    dynamic
        """
        self.assertEqual(
            parse_arp_output(output),
            {
                "192.168.3.10": "aa:bb:cc:dd:ee:ff",
                "192.168.3.11": "11:22:33:44:55:66",
            },
        )

    def test_paths_are_project_based_by_default(self):
        self.assertEqual(resolve_output_dir().parent, PROJECT_ROOT / "scan_results")
        self.assertEqual(resolve_output_dir(kind="internal").parent, PROJECT_ROOT / "scan_results")

    def test_current_platform_ping_command(self):
        command = ping_command("127.0.0.1", 0.5)
        self.assertEqual(command[-1], "127.0.0.1")
        if os.name == "nt":
            self.assertEqual(command[:2], ["ping", "-n"])
        else:
            self.assertIn("-c", command)

    def test_windows_subprocess_window_policy(self):
        options = hidden_subprocess_kwargs()
        if os.name == "nt":
            self.assertEqual(options["creationflags"], subprocess.CREATE_NO_WINDOW)
        else:
            self.assertEqual(options, {})


if __name__ == "__main__":
    unittest.main()
