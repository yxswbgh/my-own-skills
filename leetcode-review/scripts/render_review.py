#!/usr/bin/env python3
"""Render a validated daily review file from a selection plan and code starters."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

STUDIED_CHAPTERS = ("数组", "链表", "栈", "二叉树", "回溯算法")
FIXED_HEADER = """from typing import Optional,List
from collections import deque

class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right
"""
MARKDOWN_FENCE_RE = re.compile(
    r"\A\s*```(?:python|py)?\s*\n(.*?)\n```\s*\Z",
    re.DOTALL | re.IGNORECASE,
)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def clean_starter(raw: str, number: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    fence_match = MARKDOWN_FENCE_RE.fullmatch(text)
    if fence_match:
        text = fence_match.group(1).strip()

    text = text.replace(FIXED_HEADER.strip(), "").strip()
    if "```" in text:
        raise ValueError(
            f"Starter for {number} still contains a Markdown code fence"
        )
    if re.search(r"(?m)^\s*class\s+Solution\s*(?:\([^)]*\))?\s*:\s*$", text) is None:
        raise ValueError(
            f"Starter for {number} must contain a 'class Solution:' declaration"
        )

    solution_match = re.search(
        r"(?m)^\s*class\s+Solution\s*(?:\([^)]*\))?\s*:\s*$",
        text,
    )
    assert solution_match is not None
    remainder = text[solution_match.end() :]
    if re.search(r"(?m)^\s+def\s+\w+\s*\(", remainder) is None:
        raise ValueError(
            f"Starter for {number} must contain an indented Solution method"
        )
    return text


def starter_from_payload(payload: dict[str, Any], number: str, slug: str) -> str:
    starters = payload.get("starters", payload)
    if not isinstance(starters, dict):
        raise ValueError("Starter JSON must be an object keyed by question number")

    aliases = (number, slug, f"number:{number}", f"slug:{slug}")
    for alias in aliases:
        if alias and alias in starters:
            value = starters[alias]
            if isinstance(value, str):
                return value
            if isinstance(value, dict) and isinstance(value.get("starter_code"), str):
                return value["starter_code"]
            raise ValueError(
                f"Starter value for {alias!r} must be a string or "
                "{'starter_code': string}"
            )
    raise ValueError(f"Missing starter code for question {number} ({slug})")


def validate_plan(plan: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    if plan.get("status") != "ready":
        raise ValueError("Selection plan is not ready")
    date_text = str(plan.get("date", ""))
    try:
        review_date = date.fromisoformat(date_text)
    except ValueError as exc:
        raise ValueError("Selection plan has an invalid date") from exc

    selected = plan.get("selected")
    if not isinstance(selected, list):
        raise ValueError("Selection plan must contain a 'selected' array")
    if len(selected) != len(STUDIED_CHAPTERS):
        raise ValueError("Selection plan must contain exactly five selected problems")

    normalized: list[dict[str, str]] = []
    seen_chapters: set[str] = set()
    seen_identities: set[str] = set()
    for index, item in enumerate(selected):
        if not isinstance(item, dict):
            raise ValueError(f"selected[{index}] must be an object")
        chapter = str(item.get("chapter", "")).strip()
        number = str(item.get("number", "")).strip()
        title = str(item.get("title", "")).strip()
        slug = str(item.get("slug", "")).strip()
        if chapter not in STUDIED_CHAPTERS:
            raise ValueError(f"Unstudied or unknown chapter in plan: {chapter!r}")
        if chapter in seen_chapters:
            raise ValueError(f"Duplicate chapter in plan: {chapter}")
        if not number or not title:
            raise ValueError(f"selected[{index}] needs number and title")
        if "\n" in number or "\r" in number:
            raise ValueError(f"Question number must be one line: {number!r}")
        if "\n" in title or "\r" in title:
            raise ValueError(f"Question title must be one line: {title!r}")

        identity = re.sub(r"\s+", " ", number).strip().casefold()
        if identity in seen_identities:
            raise ValueError(f"Duplicate selected question: {number}")
        seen_chapters.add(chapter)
        seen_identities.add(identity)
        normalized.append(
            {
                "chapter": chapter,
                "number": number,
                "title": title,
                "slug": slug,
            }
        )

    if seen_chapters != set(STUDIED_CHAPTERS):
        missing = sorted(set(STUDIED_CHAPTERS) - seen_chapters)
        raise ValueError(f"Selection plan is missing chapters: {', '.join(missing)}")

    return review_date.isoformat(), normalized


def render(plan: dict[str, Any], starters: dict[str, Any]) -> tuple[str, str]:
    date_text, selected = validate_plan(plan)
    blocks: list[str] = []
    for item in selected:
        starter = clean_starter(
            starter_from_payload(starters, item["number"], item["slug"]),
            item["number"],
        )
        blocks.append(f"# {item['number']}. {item['title']}\n{starter}")

    content = FIXED_HEADER.rstrip() + "\n\n\n" + "\n\n\n".join(blocks) + "\n"
    return date_text, content


def write_atomic(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render review_YYYY-MM-DD.py from a ready selection plan."
    )
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--starters", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing review file only after explicit user approval",
    )
    return parser


def configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main() -> int:
    configure_utf8_output()
    args = build_parser().parse_args()
    try:
        plan = load_json(args.plan.expanduser().resolve())
        starters = load_json(args.starters.expanduser().resolve())
        if not isinstance(plan, dict) or not isinstance(starters, dict):
            raise ValueError("Plan and starter JSON roots must be objects")

        date_text, content = render(plan, starters)
        output_dir = args.output_dir.expanduser().resolve()
        if not output_dir.exists() or not output_dir.is_dir():
            raise ValueError(f"Output directory does not exist: {output_dir}")

        output_path = output_dir / f"review_{date_text}.py"
        if output_path.exists() and not args.overwrite:
            raise ValueError(
                f"Review file already exists: {output_path}. "
                "Inspect it before requesting replacement."
            )
        write_atomic(output_path, content)
        print(output_path)
        return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
