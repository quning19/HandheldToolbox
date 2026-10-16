"""Device discovery independent of converters and Qt."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import shlex
import shutil
import subprocess
import sys
from retrolibx.errors import ValidationError
from .adb import AdbReader

def find_adb() -> Path:
    found = shutil.which("adb")
    if found:
        return Path(found)
    candidates = [
        Path(os.environ.get("ANDROID_HOME", ".")) / "platform-tools/adb.exe",
        Path(os.environ.get("ANDROID_SDK_ROOT", ".")) / "platform-tools/adb.exe",
        Path(os.environ.get("LOCALAPPDATA", ".")) / "Android/Sdk/platform-tools/adb.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValidationError("未找到 ADB。请安装 Android platform-tools 并加入 PATH。")


@dataclass(frozen=True)
class Device:
    adb: Path
    serial: str
    label: str
    esde_root: str
    roots: tuple[tuple[str, int, str], ...]


def mumu_endpoints() -> list[str]:
    """Ask the running MuMu installation for its active local ADB ports."""
    if sys.platform != "win32":
        return []
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = (
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
        "Get-Process -Name MuMuNxMain -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_.Path }; exit 0"
    )
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, check=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        managers = {
            Path(line.strip()).with_name("MuMuManager.exe")
            for line in result.stdout.decode("utf-8-sig").splitlines() if line.strip()
        }
        endpoints = set()
        for manager in sorted(managers):
            if not manager.is_file():
                continue
            result = subprocess.run(
                [str(manager), "info", "--vmindex", "all"],
                capture_output=True, check=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            instances = json.loads(result.stdout.decode("utf-8-sig"))
            if not isinstance(instances, dict):
                raise ValueError("MuMu 实例信息格式无效")
            for instance in instances.values():
                if not isinstance(instance, dict):
                    continue
                if instance.get("is_process_started") is not True or instance.get("is_android_started") is not True:
                    continue
                host, port = instance.get("adb_host_ip"), instance.get("adb_port")
                if isinstance(host, str) and host in {"127.0.0.1", "localhost"} and type(port) is int and 1 <= port <= 65535:
                    endpoints.add(f"127.0.0.1:{port}")
        return sorted(endpoints)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValidationError(f"无法读取 MuMu 连接信息，请确认模拟器已启动：{exc}") from exc


def adb_device_rows(adb: Path) -> list[list[str]]:
    result = subprocess.run([str(adb), "devices", "-l"], capture_output=True, check=True, timeout=20,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return [parts for line in result.stdout.decode("utf-8").splitlines()
            if len(parts := line.split()) > 1 and parts[1] in {"device", "offline", "unauthorized"}]


def discover_device() -> Device:
    adb = find_adb()
    rows = adb_device_rows(adb)
    connection_errors = []
    if not any(parts[1] in {"device", "unauthorized"} for parts in rows):
        endpoints = mumu_endpoints()
        for endpoint in endpoints:
            try:
                result = subprocess.run(
                    [str(adb), "connect", endpoint], capture_output=True, check=True, timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                message = result.stdout.decode("utf-8", errors="replace").strip()
                if "connected to" not in message:
                    connection_errors.append(message or endpoint)
            except (OSError, subprocess.SubprocessError) as exc:
                connection_errors.append(f"{endpoint}: {exc}")
        if endpoints:
            rows = adb_device_rows(adb)
    authorized = [parts for parts in rows if parts[1] == "device"]
    if not authorized:
        if any(parts[1] == "unauthorized" for parts in rows):
            raise ValidationError("设备尚未授权，请在设备上允许 USB 调试后刷新。")
        detail = "；".join(connection_errors)
        raise ValidationError("未找到在线设备。请连接掌机或等待 MuMu 安卓系统启动后刷新。"
                              + (f" MuMu 连接失败：{detail}" if detail else ""))
    if len(authorized) > 1:
        raise ValidationError("多台设备在线，请先断开其他设备后刷新：" + "、".join(parts[0] for parts in authorized))
    parts = authorized[0]
    serial = parts[0]
    label = next((part[6:] for part in parts[2:] if part.startswith("model:")), serial)
    reader = AdbReader(adb, serial)
    # Root discovery counts immediate child directories only.
    script = """for base in /storage/emulated/0 /storage/*; do
case "$base" in /storage/emulated|/storage/self) continue;; esac
[ -d "$base" ] || continue
for dir in "$base"/*; do
[ -d "$dir" ] || continue
name=$(basename "$dir")
case "$name" in [Rr][Oo][Mm]|[Rr][Oo][Mm][Ss])
count=0
for child in "$dir"/*; do [ ! -d "$child" ] || count=$((count+1)); done
printf '%s\\0%s\\0' "$dir" "$count";; esac
done
done"""
    fields = reader.read(script).decode("utf-8").split("\0")
    roots = {}
    for index in range(0, len(fields) - 1, 2):
        path, count = fields[index:index + 2]
        roots[path] = (path, int(count), "内置存储" if path.startswith("/storage/emulated/0/") else "SD 卡")
    candidates = reader.read("""for dir in /storage/emulated/0/*; do
[ -d "$dir" ] || continue
name=$(basename "$dir")
case "$name" in [Ee][Ss]-[Dd][Ee]) printf '%s\\0' "$dir";; esac
done""").decode("utf-8").strip("\0").split("\0")
    candidates = [path for path in candidates if path]
    if len(candidates) > 1:
        raise ValidationError("内置存储发现多个 ES-DE 目录，请保留唯一工作目录后刷新设备。")
    return Device(adb, serial, label, candidates[0] if candidates else "/storage/emulated/0/ES-DE", tuple(roots.values()))


