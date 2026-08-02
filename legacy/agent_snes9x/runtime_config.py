import copy
import json
import logging
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "runtime_config.json"

DEFAULT_RUNTIME_CONFIG = {
    "emulator": {
        "window_title": "Snes9x",
    },
    "helper": {
        "relative_executable_path": "emulator/csharp_helper/bin/Release/net8.0/win-x64/Lufia2AutoTracker.Helper.exe",
        "startup_delay_seconds": 2,
    },
    "llm": {
        "api_url": "http://localhost:5001/api/v1/generate",
        "request_timeout_seconds": 60,
    },
}


def _merge_dicts(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_dicts(base[key], value)
        else:
            base[key] = value


@lru_cache(maxsize=1)
def get_runtime_config():
    config = copy.deepcopy(DEFAULT_RUNTIME_CONFIG)

    if not CONFIG_PATH.exists():
        return config

    try:
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.warning("Failed to load runtime_config.json: %s", exc)
        return config

    if not isinstance(loaded, dict):
        logging.warning("runtime_config.json must contain a JSON object at the top level.")
        return config

    _merge_dicts(config, loaded)
    return config


def get_emulator_window_title():
    return str(get_runtime_config()["emulator"]["window_title"])


def get_helper_executable_path(project_root=None):
    root = Path(project_root) if project_root else PROJECT_ROOT
    relative_path = Path(get_runtime_config()["helper"]["relative_executable_path"])
    return root / relative_path


def get_helper_startup_delay():
    return int(get_runtime_config()["helper"]["startup_delay_seconds"])


def get_llm_api_url():
    return str(get_runtime_config()["llm"]["api_url"])


def get_llm_request_timeout():
    return int(get_runtime_config()["llm"]["request_timeout_seconds"])
