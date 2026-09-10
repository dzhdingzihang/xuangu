#!/usr/bin/env python3
"""Install an explicitly supplied repository-scoped dispatch secret safely.

No local credential discovery is performed. Absence is an optional, reported
gap; the existing GitHub scheduler and any existing Worker secret are retained.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping


def configure(environ: Mapping[str, str] | None = None, *, runner=subprocess.run) -> dict:
    values = dict(os.environ if environ is None else environ)
    token = values.get("XUANGU_WORKFLOW_DISPATCH_TOKEN", "").strip()
    if not token:
        return {"configured": False, "reason": "REPOSITORY_SCOPED_SECRET_NOT_CONFIGURED"}
    if not token.startswith("github_pat_") or any(char.isspace() for char in token):
        raise ValueError("scheduler requires a repository-scoped fine-grained GitHub token")
    child_env = {key: value for key, value in values.items() if key != "XUANGU_WORKFLOW_DISPATCH_TOKEN"}
    try:
        completed = runner(
            ["npx", "--no-install", "wrangler", "secret", "put",
             "GITHUB_WORKFLOW_DISPATCH_TOKEN", "--name", "xuangu"],
            input=token + "\n", text=True, capture_output=True, timeout=60,
            env=child_env, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("scheduler secret provisioning failed or timed out; provider output withheld") from None
    if completed.returncode != 0:
        raise RuntimeError("scheduler secret provisioning failed; provider output withheld")
    return {"configured": True, "reason": "EXPLICIT_REPOSITORY_SECRET_INSTALLED"}


if __name__ == "__main__":
    print(json.dumps(configure(), sort_keys=True))
