#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import shutil


ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
STATIC = ROOT / "static"
PICKS = ROOT / "data" / "picks"


def copy_tree(source: pathlib.Path, target: pathlib.Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def main() -> None:
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir(exist_ok=True)
    shutil.copy2(STATIC / "index.html", PUBLIC / "index.html")
    copy_tree(STATIC, PUBLIC / "static")

    public_picks = PUBLIC / "data" / "picks"
    public_picks.mkdir(parents=True, exist_ok=True)
    for stale in public_picks.glob("*.json"):
        stale.unlink()

    files = []
    for path in sorted(PICKS.glob("*.json")):
        shutil.copy2(path, public_picks / path.name)
        if path.name != "latest.json":
            files.append(path.name)

    manifest = {"files": files}
    (public_picks / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
