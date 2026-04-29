from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]


def resolve_project_root(script_dir: Path) -> Path:
    if script_dir.name == "tools" and script_dir.parent.name == ".trade-tracker":
        return script_dir.parent.parent
    if script_dir.name == "tools":
        return script_dir.parent
    return script_dir


PROJECT_ROOT = resolve_project_root(SCRIPT_DIR)
APP_DIR = PROJECT_ROOT / ".trade-tracker"
CORE_PATH = SCRIPT_DIR / "export_trade_tracker_core.pyc"
NAME_CACHE_PATH = APP_DIR / "security_name_cache.json"
HISTORY_DIR = APP_DIR / "history"
FUTU_HOST = os.environ.get("FUTU_OPEND_HOST", "127.0.0.1")
FUTU_PORT = int(os.environ.get("FUTU_OPEND_PORT", "11111"))

_PROGRESS_ENABLED = os.environ.get("TRADE_TRACKER_PROGRESS") == "1"
_LAST_PROGRESS_PERCENT = 0.0


def emit_progress(step: str, detail: str = "", percent: float | int | None = None, **extra) -> None:
    global _LAST_PROGRESS_PERCENT
    if not _PROGRESS_ENABLED:
        return
    payload = {"step": step, "detail": detail}
    if percent is not None:
        next_percent = max(float(percent), _LAST_PROGRESS_PERCENT)
        _LAST_PROGRESS_PERCENT = next_percent
        payload["percent"] = next_percent
    payload.update(extra)
    print("::trade-progress::" + json.dumps(payload, ensure_ascii=False), flush=True)


def load_core_module():
    if not CORE_PATH.exists():
        raise FileNotFoundError(f"Missing compiled dashboard core: {CORE_PATH}")
    loader = importlib.machinery.SourcelessFileLoader("trade_tracker_core", str(CORE_PATH))
    spec = importlib.util.spec_from_loader("trade_tracker_core", loader)
    if spec is None:
        raise RuntimeError("Could not create import spec for dashboard core.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    if hasattr(module, "SECURITY_NAME_CACHE_PATH"):
        module.SECURITY_NAME_CACHE_PATH = NAME_CACHE_PATH
    return module
