#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公网结果筛选回归测试。"""

import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scanner_app.core import scanner_core


def _port(**overrides):
    value = {
        "state": "open",
        "port": 8000,
        "is_http": True,
        "scheme": "http",
        "status": 200,
        "title": "VLUN 靶场",
    }
    value.update(overrides)
    return value


def _target(ip, ping_alive, ports):
    return {
        "ip": ip,
        "ping": {"alive": ping_alive, "latency_ms": 1.0},
        "ports": {str(port["port"]): port for port in ports},
        "open_count": len(ports),
    }


class PublicFilterTests(unittest.TestCase):
    def test_only_http_with_title_is_a_qualified_port(self):
        self.assertTrue(scanner_core.is_qualified_port(_port()))
        self.assertFalse(scanner_core.is_qualified_port(_port(is_http=False)))
        self.assertFalse(scanner_core.is_qualified_port(_port(title="")))
        self.assertFalse(scanner_core.is_qualified_port(_port(state="closed")))

    def test_ping_failure_skips_port_probe(self):
        events = []
        with TemporaryDirectory() as temp:
            with patch.object(
                scanner_core,
                "ping_host",
                return_value={"alive": False, "latency_ms": None},
            ), patch.object(scanner_core, "scan_port") as scan_port:
                result = scanner_core.scan_target(
                    "203.0.113.10",
                    range(8000, 8002),
                    1,
                    2,
                    Path(temp),
                    events.append,
                    threading.Event(),
                )

        scan_port.assert_not_called()
        self.assertEqual(result["ports"], {})
        self.assertEqual(events[-1]["qualified_count"], 0)

    def test_run_scan_returns_only_qualified_targets(self):
        events = []
        scanned = [
            _target("203.0.113.10", False, [_port()]),
            _target("203.0.113.11", True, [_port(title="")]),
            _target("203.0.113.12", True, [_port()]),
        ]
        with TemporaryDirectory() as temp:
            with patch.object(scanner_core, "scan_target", side_effect=scanned), \
                    patch.object(scanner_core, "write_reports") as write_reports:
                result = scanner_core.run_scan(
                    [target["ip"] for target in scanned],
                    ports=[8000],
                    output=temp,
                    screenshots=False,
                    on_event=events.append,
                )

        self.assertEqual([item["ip"] for item in result], ["203.0.113.12"])
        write_reports.assert_called_once()
        finished = next(event for event in events if event["type"] == "scan_done")
        self.assertEqual(finished["qualified_target_total"], 1)
        self.assertEqual(finished["qualified_site_total"], 1)
        self.assertTrue(finished["report_available"])


if __name__ == "__main__":
    unittest.main()
