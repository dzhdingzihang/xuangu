#!/usr/bin/env python3
"""Launch the local gateway with its bearer token read from macOS Keychain."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys


KEYCHAIN_SERVICE = "com.alixjd.xuangu.quote-gateway"
KEYCHAIN_ACCOUNT = "xuangu"
GATEWAY = pathlib.Path(__file__).with_name("realtime_gateway.py")


def main() -> None:
    result = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if result.returncode or len(token) < 24:
        raise SystemExit("quote gateway token is unavailable in macOS Keychain")
    environment = os.environ.copy()
    environment["QUOTE_GATEWAY_TOKEN"] = token
    environment.setdefault("PYTHONUNBUFFERED", "1")
    os.execve(
        sys.executable,
        [sys.executable, str(GATEWAY), "--host", "127.0.0.1", "--port", "8789"],
        environment,
    )


if __name__ == "__main__":
    main()
