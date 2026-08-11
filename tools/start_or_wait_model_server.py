#!/usr/bin/env python3
"""Use a ready local model server or start the configured batch exactly once."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def endpoint_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(response.status) < 300
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def llama_server_process_exists() -> bool:
    if os.name != "nt":
        return False
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq llama-server.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode == 0 and '"llama-server.exe"' in result.stdout.casefold()


def wait_ready(url: str, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if endpoint_ready(url):
            return True
        time.sleep(2.0)
    return endpoint_ready(url)


def start_detached(batch: Path, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = f'call "{batch}"'
    with log_path.open("a", encoding="utf-8") as output:
        process = subprocess.Popen(
            [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command],
            cwd=batch.parent,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    return int(process.pid)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starter", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8080/v1/models")
    parser.add_argument("--wait-seconds", type=float, default=180.0)
    parser.add_argument(
        "--log",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "runtime" / "model_server.log",
    )
    args = parser.parse_args()

    if endpoint_ready(args.url):
        print("Model server is already ready.")
        return 0
    if not args.starter.is_file():
        print(f"ERROR: Model starter not found: {args.starter}", file=sys.stderr)
        return 1

    if llama_server_process_exists():
        print("A llama-server process is already starting; waiting without spawning another.")
    else:
        pid = start_detached(args.starter.resolve(), args.log.resolve())
        print(f"Started model server wrapper PID {pid}; log: {args.log.resolve()}")

    if wait_ready(args.url, args.wait_seconds):
        print("Model server is ready.")
        return 0
    print(
        f"ERROR: Model server did not become ready within {args.wait_seconds:g} seconds. "
        f"See {args.log.resolve()}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
