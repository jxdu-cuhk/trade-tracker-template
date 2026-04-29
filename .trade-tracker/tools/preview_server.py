#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def resolve_project_root() -> Path:
    env_root = os.environ.get("TRADE_TRACKER_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    script_path = Path(__file__).resolve()
    if script_path.parent.name == "tools" and script_path.parent.parent.name == ".trade-tracker":
        return script_path.parent.parent.parent
    return script_path.parents[1]


PROJECT_ROOT = resolve_project_root()
APP_DIR = PROJECT_ROOT / ".trade-tracker"
EXPORT_SCRIPT = APP_DIR / "tools" / "export_trade_tracker_html.py"
WORKBOOK_PATH = PROJECT_ROOT / "Trade Tracker.xlsx"
PYTHON_BIN = os.environ.get("TRADE_TRACKER_PYTHON", sys.executable)
HOST = os.environ.get("TRADE_PREVIEW_HOST", "127.0.0.1")
PORT = int(os.environ.get("TRADE_PREVIEW_PORT", "8765"))
PREVIEW_URL = f"http://{HOST}:{PORT}/preview/index.html"
PROGRESS_PREFIX = "::trade-progress::"
REFRESH_LOCK = threading.Lock()


def write_sse(wfile, event: str, payload: dict) -> None:
    raw = json.dumps(payload, ensure_ascii=False)
    wfile.write(f"event: {event}\n".encode("utf-8"))
    for line in raw.splitlines() or [""]:
        wfile.write(f"data: {line}\n".encode("utf-8"))
    wfile.write(b"\n")
    wfile.flush()


class PreviewRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def log_message(self, format, *args):  # noqa: A002 - stdlib method name
        print(f"[preview] {self.address_string()} - {format % args}", flush=True)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_response(302)
            self.send_header("Location", "/preview/index.html")
            self.end_headers()
            return
        if parsed.path == "/api/ping":
            self.send_json({"ok": True, "preview": PREVIEW_URL})
            return
        if parsed.path == "/api/refresh":
            self.handle_refresh()
            return
        return super().do_GET()

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def start_event_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def handle_refresh(self) -> None:
        self.start_event_stream()
        if not REFRESH_LOCK.acquire(blocking=False):
            write_sse(
                self.wfile,
                "error",
                {
                    "step": "已有刷新在进行",
                    "detail": "请等当前刷新完成后再点一次。",
                    "percent": 0,
                },
            )
            self.close_connection = True
            return

        process = None
        try:
            write_sse(self.wfile, "progress", {"step": "检查文件", "detail": "确认工作簿和生成脚本存在。", "percent": 1})
            if not WORKBOOK_PATH.exists():
                write_sse(self.wfile, "error", {"step": "找不到工作簿", "detail": str(WORKBOOK_PATH), "percent": 1})
                return
            if not EXPORT_SCRIPT.exists():
                write_sse(self.wfile, "error", {"step": "找不到生成脚本", "detail": str(EXPORT_SCRIPT), "percent": 1})
                return

            env = os.environ.copy()
            env["TRADE_TRACKER_PROGRESS"] = "1"
            env["PYTHONUNBUFFERED"] = "1"
            env["NO_OPEN"] = "1"
            cmd = [
                PYTHON_BIN,
                str(EXPORT_SCRIPT),
                str(WORKBOOK_PATH),
                "-o",
                str(APP_DIR / "preview"),
            ]
            write_sse(self.wfile, "progress", {"step": "启动生成器", "detail": "正在拉起 Python 刷新流程。", "percent": 2})
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.rstrip("\n")
                if not line:
                    continue
                if line.startswith(PROGRESS_PREFIX):
                    try:
                        payload = json.loads(line[len(PROGRESS_PREFIX) :])
                    except json.JSONDecodeError:
                        payload = {"step": "解析进度", "detail": line, "percent": 0}
                    write_sse(self.wfile, "progress", payload)
                else:
                    write_sse(self.wfile, "log", {"line": line})

            return_code = process.wait()
            if return_code != 0:
                write_sse(
                    self.wfile,
                    "error",
                    {
                        "step": "生成失败",
                        "detail": f"生成器退出码：{return_code}。命令窗口里会保留详细输出。",
                        "percent": 0,
                    },
                )
                return

            write_sse(
                self.wfile,
                "done",
                {
                    "step": "完成",
                    "detail": "看板已刷新，页面马上重新载入。",
                    "percent": 100,
                    "reload": f"/preview/index.html?ts={int(time.time())}",
                },
            )
        except BrokenPipeError:
            if process and process.poll() is None:
                process.terminate()
        except Exception as error:
            try:
                write_sse(self.wfile, "error", {"step": "刷新异常", "detail": str(error), "percent": 0})
            except BrokenPipeError:
                pass
        finally:
            REFRESH_LOCK.release()
            self.close_connection = True


def existing_server_is_healthy() -> bool:
    try:
        with urlopen(f"http://{HOST}:{PORT}/api/ping?ts={int(time.time())}", timeout=0.5) as response:
            return response.status == 200
    except (OSError, URLError, ValueError):
        return False


def main() -> int:
    try:
        server = ThreadingHTTPServer((HOST, PORT), PreviewRequestHandler)
    except OSError as error:
        if existing_server_is_healthy():
            print(f"本地预览服务已经在运行：{PREVIEW_URL}", flush=True)
            if os.environ.get("NO_OPEN") != "1":
                webbrowser.open(PREVIEW_URL)
            return 0
        print(f"无法启动本地预览服务：{error}", flush=True)
        return 1

    print(f"本地预览服务已启动：{PREVIEW_URL}", flush=True)
    print("保持这个窗口打开，网页里的刷新按钮才能运行。", flush=True)
    if os.environ.get("NO_OPEN") != "1":
        webbrowser.open(PREVIEW_URL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止本地预览服务。", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
