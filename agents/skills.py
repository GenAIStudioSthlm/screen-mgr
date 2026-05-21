"""Markdown-with-frontmatter skill loader.

Each skill is a .md file like:

    ---
    name: presentation-mode
    description: Dim Studio room lights to a warm, focused presentation level
    when_to_use: User asks for "presentation mode" / "demo lights" / similar
    ---

    Step-by-step instructions for the agent...

Format intentionally matches Claude Code's skill convention so the same
authoring habits transfer. No YAML dep — frontmatter is parsed line-by-line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    when_to_use: str
    body: str
    path: Path


def load_skills(skills_dir: Path) -> list[Skill]:
    """Load every *.md in `skills_dir`, sorted by filename. Skips files
    without valid frontmatter (prints a warning so authors notice)."""
    out: list[Skill] = []
    if not skills_dir.is_dir():
        return out
    for md in sorted(skills_dir.glob("*.md")):
        try:
            out.append(_parse(md))
        except ValueError as e:
            print(f"[skills] skipping {md.name}: {e}")
    return out


def _parse(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("missing --- frontmatter block")

    fm = _parse_frontmatter(m.group(1))
    body = m.group(2).strip()

    name = fm.get("name") or path.stem
    return Skill(
        name=name,
        description=fm.get("description", ""),
        when_to_use=fm.get("when_to_use", ""),
        body=body,
        path=path,
    )


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Minimal key: value parser. Values are stripped; quotes left as-is."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def render_skills_block(skills: Iterable[Skill]) -> str:
    """Render a skills section for the system prompt. The when-to-use
    hint is what the model uses to decide which skill applies; the body
    is the actual instruction set the model follows once it picks one."""
    lines: list[str] = []
    for s in skills:
        lines.append(f"### Skill: {s.name}")
        if s.when_to_use:
            lines.append(f"_When to use:_ {s.when_to_use}")
        lines.append("")
        lines.append(s.body)
        lines.append("")
    return "\n".join(lines).strip()
