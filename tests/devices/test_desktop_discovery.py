"""MuMu auto-connect cases; no actual process, ADB or window operations."""

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from frontend_devices.discovery import discover_device, mumu_endpoints
from retrolibx.errors import ValidationError


class MuMuDiscoveryTests(TestCase):
    def test_manager_returns_only_started_local_instances_and_deduplicates_ports(self):
        active = dict(is_process_started=True, is_android_started=True,
                      adb_host_ip="127.0.0.1", adb_port=17001)
        instances = {
            "0": active, "1": active,
            "2": dict(active, is_android_started=False),
            "3": dict(active, is_process_started=False),
            "4": dict(active, adb_host_ip="192.168.1.2"),
            "5": dict(active, adb_port=0), "6": dict(active, adb_port=True),
            "7": dict(active, adb_host_ip=[]),
        }
        results = [SimpleNamespace(stdout="D:/模拟器/nx_main/MuMuNxMain.exe\n".encode()),
                   SimpleNamespace(stdout=json.dumps(instances).encode())]
        with patch("frontend_devices.discovery.sys.platform", "win32"), \
             patch.object(Path, "is_file", return_value=True), \
             patch("frontend_devices.discovery.subprocess.run", side_effect=results) as run:
            self.assertEqual(mumu_endpoints(), ["127.0.0.1:17001"])
        self.assertEqual(run.call_args.args[0][1:], ["info", "--vmindex", "all"])
        self.assertEqual(run.call_args.args[0][0], str(Path("D:/模拟器/nx_main/MuMuManager.exe")))

    def test_no_running_mumu_does_not_query_or_start_a_manager(self):
        with patch("frontend_devices.discovery.sys.platform", "win32"), \
             patch("frontend_devices.discovery.subprocess.run", return_value=SimpleNamespace(stdout=b"")) as run:
            self.assertEqual(mumu_endpoints(), [])
        self.assertEqual(run.call_count, 1)

    def test_other_os_does_not_run_windows_commands(self):
        with patch("frontend_devices.discovery.sys.platform", "linux"), \
             patch("frontend_devices.discovery.subprocess.run") as run:
            self.assertEqual(mumu_endpoints(), [])
        run.assert_not_called()

    def test_malformed_manager_info_reports_actionable_error(self):
        with patch("frontend_devices.discovery.sys.platform", "win32"), \
             patch.object(Path, "is_file", return_value=True), \
             patch("frontend_devices.discovery.subprocess.run", side_effect=[
                 SimpleNamespace(stdout=b"D:/MuMu/MuMuNxMain.exe\n"), SimpleNamespace(stdout=b"bad-json")]):
            with self.assertRaisesRegex(ValidationError, "MuMu 连接信息"):
                mumu_endpoints()

    def test_empty_device_list_connects_reported_endpoint_and_reads_device(self):
        endpoint = "127.0.0.1:17001"
        with patch("frontend_devices.discovery.find_adb", return_value=Path("adb.exe")), \
             patch("frontend_devices.discovery.adb_device_rows", side_effect=[[], [[endpoint, "device", "model:MuMu"]]]) as rows, \
             patch("frontend_devices.discovery.mumu_endpoints", return_value=[endpoint]), \
             patch("frontend_devices.discovery.subprocess.run", return_value=SimpleNamespace(stdout=b"connected to 127.0.0.1:17001")) as run, \
             patch("frontend_devices.discovery.AdbReader") as reader:
            reader.return_value.read.side_effect = [b"/storage/emulated/0/ROMs\0" + b"3\0", b""]
            device = discover_device()
        self.assertEqual(device.serial, endpoint)
        self.assertEqual(device.roots[0][1], 3)
        self.assertEqual(rows.call_count, 2)
        self.assertEqual(run.call_args.args[0], [str(Path("adb.exe")), "connect", endpoint])

    def test_online_device_is_used_without_connecting_any_emulator(self):
        with patch("frontend_devices.discovery.find_adb", return_value=Path("adb.exe")), \
             patch("frontend_devices.discovery.adb_device_rows", return_value=[["usb-device", "device"]]), \
             patch("frontend_devices.discovery.mumu_endpoints") as endpoints, \
             patch("frontend_devices.discovery.AdbReader") as reader:
            reader.return_value.read.side_effect = [b"", b""]
            self.assertEqual(discover_device().serial, "usb-device")
        endpoints.assert_not_called()

    def test_unauthorized_usb_requires_authorization_without_switching_to_mumu(self):
        with patch("frontend_devices.discovery.find_adb", return_value=Path("adb.exe")), \
             patch("frontend_devices.discovery.adb_device_rows", return_value=[["usb", "unauthorized"]]), \
             patch("frontend_devices.discovery.mumu_endpoints") as endpoints:
            with self.assertRaisesRegex(ValidationError, "允许 USB 调试"):
                discover_device()
        endpoints.assert_not_called()

    def test_multiple_devices_report_serials_without_selecting_one(self):
        with patch("frontend_devices.discovery.find_adb", return_value=Path("adb.exe")), \
             patch("frontend_devices.discovery.adb_device_rows", return_value=[["usb-a", "device"], ["usb-b", "device"]]), \
             patch("frontend_devices.discovery.mumu_endpoints") as endpoints, \
             patch("frontend_devices.discovery.AdbReader") as reader:
            with self.assertRaisesRegex(ValidationError, "usb-a、usb-b"):
                discover_device()
        endpoints.assert_not_called()
        reader.assert_not_called()

    def test_offline_endpoint_timeout_reports_failure_without_reading_storage(self):
        with patch("frontend_devices.discovery.find_adb", return_value=Path("adb.exe")), \
             patch("frontend_devices.discovery.adb_device_rows", return_value=[["old", "offline"]]), \
             patch("frontend_devices.discovery.mumu_endpoints", return_value=["127.0.0.1:17001"]), \
             patch("frontend_devices.discovery.subprocess.run", side_effect=subprocess.TimeoutExpired("adb", 5)), \
             patch("frontend_devices.discovery.AdbReader") as reader:
            with self.assertRaisesRegex(ValidationError, "MuMu 连接失败"):
                discover_device()
        reader.assert_not_called()

    def test_multiple_active_instances_are_connected_then_reported_as_ambiguous(self):
        endpoints = ["127.0.0.1:17001", "127.0.0.1:17002"]
        with patch("frontend_devices.discovery.find_adb", return_value=Path("adb.exe")), \
             patch("frontend_devices.discovery.adb_device_rows", side_effect=[[], [[value, "device"] for value in endpoints]]), \
             patch("frontend_devices.discovery.mumu_endpoints", return_value=endpoints), \
             patch("frontend_devices.discovery.subprocess.run", return_value=SimpleNamespace(stdout=b"connected to localhost")) as run, \
             patch("frontend_devices.discovery.AdbReader") as reader:
            with self.assertRaisesRegex(ValidationError, "多台设备在线"):
                discover_device()
        self.assertEqual(run.call_count, 2)
        reader.assert_not_called()
