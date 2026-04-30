#!/usr/bin/env python3

from __future__ import annotations

import os
import plistlib
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


LABEL = "com.leek-ledger.preview"
HOST = "127.0.0.1"
PORT = "8765"
def resolve_project_root() -> Path:
    script_path = Path(__file__).resolve()
    if script_path.parent.name == "tools" and script_path.parent.parent.name == ".trade-tracker":
        return script_path.parent.parent.parent
    return script_path.parents[1]


PROJECT_ROOT = resolve_project_root()
APP_DIR = PROJECT_ROOT / ".trade-tracker"
TOOLS_DIR = APP_DIR / "tools"
SERVER_SCRIPT = TOOLS_DIR / "preview_server.py"
RUNTIME_DIR = Path.home() / "Library" / "Application Support" / "TradeTracker"
RUNTIME_SERVER_SCRIPT = RUNTIME_DIR / "preview_server.py"
RUNTIME_VENV = RUNTIME_DIR / ".venv"
RUNTIME_PYTHON = RUNTIME_VENV / "bin" / "python"
LOG_DIR = Path.home() / "Library" / "Logs" / "TradeTracker"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = LAUNCH_AGENTS_DIR / f"{LABEL}.plist"
PING_URL = f"http://{HOST}:{PORT}/api/ping"
RUNTIME_PACKAGES = [
    "openpyxl==3.1.5",
    "pandas==3.0.2",
    "futu_api==10.4.6408",
]


def base_python() -> Path:
    return Path(shutil.which("python3") or sys.executable)


def run(command: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, text=True, capture_output=True)


def ping_preview_service(timeout: float = 0.5) -> bool:
    try:
        with urlopen(f"{PING_URL}?ts={int(time.time() * 1000)}", timeout=timeout) as response:
            return response.status == 200
    except (OSError, URLError, ValueError):
        return False


def pids_on_preview_port() -> list[int]:
    result = run(["lsof", "-ti", f"tcp:{PORT}"])
    pids = []
    for item in result.stdout.split():
        try:
            pids.append(int(item))
        except ValueError:
            pass
    return pids


def stop_existing_preview_service() -> None:
    if not ping_preview_service():
        return
    for pid in pids_on_preview_port():
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + 3
    while time.time() < deadline:
        if not ping_preview_service(timeout=0.2):
            return
        time.sleep(0.15)


def runtime_python_has_dependencies() -> bool:
    if not RUNTIME_PYTHON.exists():
        return False
    result = run(
        [
            str(RUNTIME_PYTHON),
            "-c",
            "import openpyxl, pandas, futu; print('ok')",
        ]
    )
    return result.returncode == 0


def ensure_runtime() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SERVER_SCRIPT, RUNTIME_SERVER_SCRIPT)
    if not RUNTIME_PYTHON.exists():
        run([str(base_python()), "-m", "venv", str(RUNTIME_VENV)], check=True)
    if not runtime_python_has_dependencies():
        run(
            [
                str(RUNTIME_PYTHON),
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
            ],
            check=True,
        )
        run(
            [
                str(RUNTIME_PYTHON),
                "-m",
                "pip",
                "install",
                *RUNTIME_PACKAGES,
            ],
            check=True,
        )


def write_launch_agent() -> None:
    ensure_runtime()
    LOG_DIR.mkdir(exist_ok=True)
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [str(RUNTIME_PYTHON), str(RUNTIME_SERVER_SCRIPT)],
        "EnvironmentVariables": {
            "NO_OPEN": "1",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "TRADE_TRACKER_PROJECT_ROOT": str(PROJECT_ROOT),
            "TRADE_TRACKER_PYTHON": str(RUNTIME_PYTHON),
        },
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "StandardOutPath": str(LOG_DIR / "preview_service.out.log"),
        "StandardErrorPath": str(LOG_DIR / "preview_service.err.log"),
    }
    with PLIST_PATH.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)


def install_launch_agent() -> None:
    uid = os.getuid()
    domain = f"gui/{uid}"
    service_target = f"{domain}/{LABEL}"
    run(["launchctl", "bootout", service_target])
    run(["launchctl", "bootout", domain, str(PLIST_PATH)])
    stop_existing_preview_service()
    run(["launchctl", "bootstrap", domain, str(PLIST_PATH)], check=True)
    run(["launchctl", "enable", service_target])
    run(["launchctl", "kickstart", "-k", service_target])


def wait_until_ready() -> bool:
    deadline = time.time() + 6
    while time.time() < deadline:
        if ping_preview_service(timeout=0.4):
            return True
        time.sleep(0.25)
    return False


def main() -> int:
    if not SERVER_SCRIPT.exists():
        print(f"找不到预览服务脚本：{SERVER_SCRIPT}")
        return 1
    try:
        write_launch_agent()
        install_launch_agent()
    except subprocess.CalledProcessError as error:
        print("注册本地刷新服务失败。")
        print(error.stderr.strip() or error.stdout.strip() or str(error))
        return error.returncode or 1

    if wait_until_ready():
        print(f"本地刷新服务已常驻：{PING_URL}")
        print(f"现在可以直接打开韭菜账本：{PROJECT_ROOT / 'Trade Tracker.html'}")
        return 0

    print("服务已经注册，但暂时没有通过健康检查。")
    print(f"可以查看日志：{LOG_DIR / 'preview_service.err.log'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
