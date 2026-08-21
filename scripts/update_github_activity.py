#!/usr/bin/env python3
"""Update GitHub repository activity ages in README tables."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


REPO_RE = re.compile(r"https://github\.com/([^/\s)]+)/([^/\s)#]+)")


def repository_from_row(row: str) -> str | None:
    match = REPO_RE.search(row)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2).removesuffix('.git')}"


def activity_text(committed_at: str, now: datetime) -> str:
    committed = datetime.fromisoformat(committed_at.replace("Z", "+00:00"))
    days = max(0, (now.date() - committed.date()).days)
    if days == 0:
        return "今天"
    if days < 7:
        return f"{days} 天前"
    if days < 30:
        return f"{days // 7} 周前"
    if days < 365:
        return f"{days // 30} 个月前"
    return f"{days // 365} 年前"


def fetch_last_commit_at(repository: str, token: str | None) -> str:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/commits?per_page=1",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "limbus-resource-index",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)[0]["commit"]["committer"]["date"]


def update_readme(text: str, activity: dict[str, str]) -> str:
    lines = text.splitlines()
    recent_column: int | None = None

    for index, line in enumerate(lines):
        if not line.startswith("|"):
            recent_column = None
            continue

        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if "最近更新" in cells:
            recent_column = cells.index("最近更新")
            continue
        if recent_column is None or all(set(cell) <= {"-", ":"} for cell in cells):
            continue

        repository = repository_from_row(line)
        if repository and repository in activity:
            cells[recent_column] = activity[repository]
            lines[index] = "| " + " | ".join(cells) + " |"

    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + suffix


def self_test() -> None:
    now = datetime(2026, 8, 21, tzinfo=timezone.utc)
    assert repository_from_row("| [x](https://github.com/a/b) | — |") == "a/b"
    assert activity_text("2026-08-21T01:00:00Z", now) == "今天"
    assert activity_text("2026-08-18T01:00:00Z", now) == "3 天前"
    assert activity_text("2026-08-07T01:00:00Z", now) == "2 周前"
    assert activity_text("2026-06-21T01:00:00Z", now) == "2 个月前"
    assert activity_text("2025-08-21T01:00:00Z", now) == "1 年前"
    source = "| 项目 | 最近更新 | Confirm |\n| --- | --- | --- |\n| [x](https://github.com/a/b) | — | — |\n"
    expected = "| 项目 | 最近更新 | Confirm |\n| --- | --- | --- |\n| [x](https://github.com/a/b) | 1 天前 | — |\n"
    assert update_readme(source, {"a/b": "1 天前"}) == expected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    text = args.readme.read_text(encoding="utf-8")
    repositories = sorted(
        {
            repository
            for line in text.splitlines()
            if line.startswith("|") and (repository := repository_from_row(line))
        }
    )
    now = datetime.now(timezone.utc)
    token = os.environ.get("GITHUB_TOKEN")
    activity: dict[str, str] = {}

    for repository in repositories:
        try:
            activity[repository] = activity_text(fetch_last_commit_at(repository, token), now)
        except urllib.error.HTTPError as error:
            if error.code in {404, 409}:
                activity[repository] = "不可访问" if error.code == 404 else "无提交"
                continue
            raise

    updated = update_readme(text, activity)
    if updated != text:
        args.readme.write_text(updated, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
