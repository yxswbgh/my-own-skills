#!/usr/bin/env python3
"""Select one unique reviewed problem per studied chapter with date cooldown."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

STUDIED_CHAPTERS = ("数组", "链表", "栈", "二叉树", "回溯算法")
UNSTUDIED_CHAPTERS = ("图论搜索", "动态规划")
REVIEW_FILE_RE = re.compile(r"^review_(\d{4}-\d{2}-\d{2})\.py$")
HEADING_RE = re.compile(r"^#\s+(.+?)(?:\.|、)\s+.+$")


@dataclass(frozen=True)
class Candidate:
    chapter: str
    number: str
    title: str
    slug: str
    url: str

    @property
    def identity(self) -> str:
        """Use the front-end question number, which is stable in review headings."""
        return normalize_identity(self.number)

    def as_dict(self) -> dict[str, str]:
        return {
            "chapter": self.chapter,
            "number": self.number,
            "title": self.title,
            "slug": self.slug,
            "url": self.url,
            "identity": self.identity,
        }


def normalize_identity(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date '{value}'; expected YYYY-MM-DD") from exc


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"Candidate file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def parse_candidate(raw: Any, index: int) -> Candidate:
    if not isinstance(raw, dict):
        raise ValueError(f"candidates[{index}] must be an object")

    chapter = str(raw.get("chapter", "")).strip()
    number = str(raw.get("number", "")).strip()
    title = str(raw.get("title", "")).strip()
    slug = str(raw.get("slug", "")).strip().strip("/")
    url = str(raw.get("url", "")).strip()

    if not chapter:
        raise ValueError(f"candidates[{index}].chapter is required")
    if not number:
        raise ValueError(f"candidates[{index}].number is required")
    if not title:
        raise ValueError(f"candidates[{index}].title is required")
    if not slug and not url:
        raise ValueError(f"candidates[{index}] needs slug or url")
    if not title.isprintable() or "\n" in title or "\r" in title:
        raise ValueError(f"candidates[{index}].title must be one printable line")
    if not number.isprintable() or "\n" in number or "\r" in number:
        raise ValueError(f"candidates[{index}].number must be one printable line")

    if not slug and url:
        match = re.search(r"/problems/([^/?#]+)/?", url)
        if match:
            slug = match.group(1)
    if not url:
        url = f"https://leetcode.cn/problems/{slug}/"
    if not url.endswith("/"):
        url += "/"
    if not re.match(r"^https://leetcode\.cn/problems/[^/?#]+/", url):
        raise ValueError(
            f"candidates[{index}].url must be a leetcode.cn problem URL: {url}"
        )

    return Candidate(
        chapter=chapter,
        number=number,
        title=title,
        slug=slug,
        url=url,
    )


def load_candidates(path: Path) -> tuple[list[Candidate], list[str]]:
    payload = load_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise ValueError("Candidate JSON must contain a 'candidates' array")

    warnings: list[str] = []
    deduped: dict[str, Candidate] = {}
    for index, raw in enumerate(payload["candidates"]):
        candidate = parse_candidate(raw, index)
        if candidate.chapter in UNSTUDIED_CHAPTERS:
            warnings.append(
                f"Ignored {candidate.number} {candidate.title}: "
                f"chapter '{candidate.chapter}' is not studied"
            )
            continue
        if candidate.chapter not in STUDIED_CHAPTERS:
            warnings.append(
                f"Ignored {candidate.number} {candidate.title}: "
                f"unknown chapter '{candidate.chapter}'"
            )
            continue

        previous = deduped.get(candidate.identity)
        if previous and previous.chapter != candidate.chapter:
            warnings.append(
                f"Ignored duplicate {candidate.number} {candidate.title} from "
                f"'{candidate.chapter}'; it was already classified as "
                f"'{previous.chapter}'"
            )
            continue
        deduped.setdefault(candidate.identity, candidate)

    return list(deduped.values()), warnings


def collect_recent_identities(
    output_dir: Path,
    review_date: date,
    cooldown_days: int,
) -> tuple[set[str], list[dict[str, Any]], list[str]]:
    blocked: set[str] = set()
    evidence: list[dict[str, Any]] = []
    warnings: list[str] = []

    for path in sorted(output_dir.glob("review_*.py")):
        filename_match = REVIEW_FILE_RE.fullmatch(path.name)
        if not filename_match:
            continue
        try:
            old_date = parse_date(filename_match.group(1))
        except ValueError:
            warnings.append(f"Ignored review file with invalid date: {path}")
            continue

        age = (review_date - old_date).days
        if age < 0:
            warnings.append(f"Ignored future-dated review file: {path}")
            continue
        if age >= cooldown_days:
            continue

        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as exc:
            warnings.append(f"Could not read {path}: {exc}")
            continue

        for line in lines:
            match = HEADING_RE.match(line.strip())
            if not match:
                continue
            identity = normalize_identity(match.group(1))
            blocked.add(identity)
            evidence.append(
                {
                    "identity": identity,
                    "date": old_date.isoformat(),
                    "file": path.name,
                }
            )

    return blocked, evidence, warnings


def random_matching(
    candidates_by_chapter: dict[str, list[Candidate]],
    blocked: set[str],
    rng: random.Random,
) -> dict[str, Candidate] | None:
    available: dict[str, list[Candidate]] = {}
    for chapter in STUDIED_CHAPTERS:
        options = [
            candidate
            for candidate in candidates_by_chapter.get(chapter, [])
            if candidate.identity not in blocked
        ]
        rng.shuffle(options)
        available[chapter] = options

    def search(
        remaining: tuple[str, ...],
        used: frozenset[str],
    ) -> dict[str, Candidate] | None:
        if not remaining:
            return {}

        ranked = sorted(
            remaining,
            key=lambda chapter: sum(
                1
                for candidate in available[chapter]
                if candidate.identity not in used
            ),
        )
        chapter = ranked[0]
        options = [
            candidate
            for candidate in available[chapter]
            if candidate.identity not in used
        ]
        next_remaining = tuple(item for item in remaining if item != chapter)

        for candidate in options:
            result = search(
                next_remaining,
                used | frozenset((candidate.identity,)),
            )
            if result is not None:
                result[chapter] = candidate
                return result
        return None

    return search(STUDIED_CHAPTERS, frozenset())


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def select_reviews(
    candidates_path: Path,
    output_dir: Path,
    review_date: date,
    plan_path: Path,
    cooldown_days: int,
    seed: int | None,
) -> int:
    if cooldown_days < 0:
        raise ValueError("--cooldown-days cannot be negative")
    if not output_dir.exists() or not output_dir.is_dir():
        raise ValueError(f"Output directory does not exist: {output_dir}")

    output_file = output_dir / f"review_{review_date.isoformat()}.py"
    if output_file.exists():
        raise ValueError(
            f"Review file already exists: {output_file}. "
            "Inspect it before requesting replacement."
        )

    candidates, candidate_warnings = load_candidates(candidates_path)
    blocked, evidence, history_warnings = collect_recent_identities(
        output_dir,
        review_date,
        cooldown_days,
    )

    by_chapter: dict[str, list[Candidate]] = {chapter: [] for chapter in STUDIED_CHAPTERS}
    for candidate in candidates:
        by_chapter[candidate.chapter].append(candidate)

    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    matching = random_matching(by_chapter, blocked, rng)
    warnings = candidate_warnings + history_warnings

    selected: list[dict[str, str]] = []
    unavailable: list[str] = []
    if matching is None:
        for chapter in STUDIED_CHAPTERS:
            eligible = [
                candidate
                for candidate in by_chapter[chapter]
                if candidate.identity not in blocked
            ]
            if not eligible:
                unavailable.append(chapter)
        status = "incomplete"
        if not unavailable:
            warnings.append(
                "Candidates exist for every chapter, but no unique assignment exists; "
                "add more distinct solved problems"
            )
    else:
        selected = [matching[chapter].as_dict() for chapter in STUDIED_CHAPTERS]
        status = "ready"

    payload = {
        "schema_version": 1,
        "status": status,
        "date": review_date.isoformat(),
        "output_file": output_file.name,
        "cooldown_days": cooldown_days,
        "selected": selected,
        "unavailable_chapters": unavailable,
        "recent_review_evidence": evidence,
        "warnings": warnings,
    }
    write_json_atomic(plan_path, payload)

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if status != "ready":
        missing = ", ".join(unavailable) if unavailable else "unique assignment"
        print(f"No complete selection is available: {missing}", file=sys.stderr)
        print(f"Selection plan written to {plan_path}", file=sys.stderr)
        return 2

    print(f"Selection plan: {plan_path}")
    for item in selected:
        print(f"{item['chapter']}: {item['number']}. {item['title']} - {item['url']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pick one unique, non-recent problem for each studied chapter."
    )
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--date", required=True, help="Review date in YYYY-MM-DD form")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--cooldown-days", type=int, default=7)
    parser.add_argument(
        "--seed",
        type=int,
        help="Optional deterministic seed for testing only",
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
        review_date = parse_date(args.date)
        output_dir = args.output_dir.expanduser().resolve()
        plan_path = (
            args.plan.expanduser().resolve()
            if args.plan
            else output_dir / f"review_{review_date.isoformat()}.plan.json"
        )
        return select_reviews(
            candidates_path=args.candidates.expanduser().resolve(),
            output_dir=output_dir,
            review_date=review_date,
            plan_path=plan_path,
            cooldown_days=args.cooldown_days,
            seed=args.seed,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
