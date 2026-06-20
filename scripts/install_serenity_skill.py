#!/usr/bin/env python3
"""Install a local Serenity skill for Agents/Codex workflows.

Usage:
  python3 scripts/install_serenity_skill.py
  python3 scripts/install_serenity_skill.py --source /path/to/serenity-skill

If --source contains SKILL.md plus optional LICENSE/references/assets/scripts/
examples/agents, those files are copied into ~/.agents/skills/serenity-skill.
Without --source, the script builds a minimal skill from the local UZI-Skill
Serenity research notes already present in this workspace.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFAULT_TARGET = Path.home() / ".agents" / "skills" / "serenity-skill"
UZI_DOSSIER = WORKSPACE / "UZI-Skill" / "docs" / "serenity-research-dossier.md"
UZI_BOTTLENECK = WORKSPACE / "UZI-Skill" / "skills" / "deep-analysis" / "references" / "fin-methods" / "serenity-bottleneck.md"
COPY_NAMES = ("SKILL.md", "LICENSE", "references", "assets", "scripts", "examples", "agents")


def copy_tree(source: Path, target: Path) -> list[str]:
    copied: list[str] = []
    target.mkdir(parents=True, exist_ok=True)
    for name in COPY_NAMES:
        src = source / name
        if not src.exists():
            continue
        dst = target / name
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        copied.append(name)
    if "SKILL.md" not in copied:
        raise FileNotFoundError(f"{source} 缺少 SKILL.md，无法安装 Serenity skill")
    return copied


def write_minimal_skill(target: Path) -> list[str]:
    references = target / "references"
    target.mkdir(parents=True, exist_ok=True)
    references.mkdir(parents=True, exist_ok=True)

    skill_md = """# Serenity Skill

Use this skill when analyzing stocks through Serenity's bottleneck investing lens.

Core workflow:
1. Confirm whether demand is real and maps to a specific AI workload or supply-chain bill of materials.
2. Map the demand to financial statement lines such as revenue, gross margin, backlog, capex, or cash flow.
3. Find misclassified small or mid-cap suppliers that sit upstream of visible AI winners.
4. Verify mispricing through customer validation, supply tightness, capacity, certifications, and sell-side relabeling.
5. Build a falsifiable validation chain with green/yellow/red checkpoints.
6. Score certainty, clarity, purity, elasticity, and timeframe before considering position sizing.

Hard rules:
- Do not treat Serenity social attention as a buy signal by itself.
- Penalize already-repriced, high-dilution, low-liquidity, single-customer, or technically broken names.
- Prefer missed upstream bottlenecks over crowded downstream AI leaders.
- Always state what evidence would invalidate the thesis.
"""
    (target / "SKILL.md").write_text(skill_md, encoding="utf-8")

    copied = ["SKILL.md", "references"]
    if UZI_DOSSIER.exists():
        shutil.copy2(UZI_DOSSIER, references / "serenity-research-dossier.md")
    if UZI_BOTTLENECK.exists():
        shutil.copy2(UZI_BOTTLENECK, references / "serenity-bottleneck.md")
    return copied


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, help="Directory containing Serenity SKILL.md and optional assets")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()

    if args.source:
        copied = copy_tree(args.source.expanduser().resolve(), args.target.expanduser())
        mode = "copied"
    else:
        copied = write_minimal_skill(args.target.expanduser())
        mode = "generated"

    print(f"Installed Serenity skill ({mode}) at {args.target.expanduser()}")
    print("Copied:", ", ".join(copied))


if __name__ == "__main__":
    main()
