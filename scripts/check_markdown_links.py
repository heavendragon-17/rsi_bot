"""Validate local links in the repository's tracked Markdown files.

External URLs are intentionally not fetched. The check is deterministic,
works offline, and catches missing or incorrectly cased repository paths.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

INLINE_LINK_RE = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)\r\n]+)\)")
REFERENCE_LINK_RE = re.compile(r"^[ \t]*\[[^\]]+\]:[ \t]*(?P<target><[^>]+>|\S+)", re.MULTILINE)
INLINE_CODE_RE = re.compile(r"(?<!`)`[^`\r\n]*`(?!`)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
MARKDOWN_PATTERNS = ("*.md", "*.mdx")


@dataclass(frozen=True)
class BrokenLink:
    """A local Markdown link that cannot be resolved safely."""

    source: Path
    line: int
    target: str
    reason: str


def _tracked_markdown_files(root: Path) -> list[Path]:
    command = [
        "git",
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        *MARKDOWN_PATTERNS,
    ]
    result = subprocess.run(
        command,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    # ``--cached`` also reports tracked files deleted in the worktree. Ignore
    # those paths so archive moves can be validated before they are staged.
    return [candidate for name in result.stdout.split("\0") if name and (candidate := root / name).is_file()]


def _expand_paths(root: Path, paths: list[str]) -> list[Path]:
    files: set[Path] = set()
    for raw_path in paths:
        path = (root / raw_path).resolve()
        if path.is_dir():
            for pattern in MARKDOWN_PATTERNS:
                files.update(candidate for candidate in path.rglob(pattern) if candidate.is_file())
        elif path.is_file():
            files.add(path)
        else:
            raise FileNotFoundError(raw_path)
    return sorted(files)


def _without_code(text: str) -> str:
    """Blank fenced and inline code while preserving source line numbers."""

    output: list[str] = []
    active_fence: str | None = None
    for line in text.splitlines(keepends=True):
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            if active_fence is None:
                active_fence = marker
            elif marker == active_fence:
                active_fence = None
            output.append("\n" if line.endswith("\n") else "")
            continue
        if active_fence is not None:
            output.append("\n" if line.endswith("\n") else "")
            continue
        output.append(INLINE_CODE_RE.sub("", line))
    return "".join(output)


def _link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<"):
        closing = target.find(">")
        return target[1:closing] if closing != -1 else target
    return target.split(maxsplit=1)[0]


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _has_exact_case(root: Path, candidate: Path) -> bool:
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return False

    current = root
    for part in relative.parts:
        try:
            child_names = {child.name for child in current.iterdir()}
        except OSError:
            return False
        if part not in child_names:
            return False
        current /= part
    return True


def _resolve_local_target(root: Path, source: Path, target: str) -> tuple[Path | None, str | None]:
    if not target or target.startswith("#") or target.startswith("//"):
        return None, None

    parsed = urlsplit(target)
    if parsed.scheme:
        return None, None

    decoded_path = unquote(parsed.path)
    if not decoded_path:
        return None, None

    if decoded_path.startswith("/"):
        candidate = (root / decoded_path.lstrip("/")).resolve()
    else:
        candidate = (source.parent / decoded_path).resolve()

    try:
        candidate.relative_to(root)
    except ValueError:
        return candidate, "target escapes the repository"

    if not candidate.exists():
        return candidate, "target does not exist"
    if not _has_exact_case(root, candidate):
        return candidate, "target casing does not match the filesystem"
    return candidate, None


def check_files(root: Path, files: list[Path]) -> list[BrokenLink]:
    """Return all invalid local links found in *files*."""

    failures: list[BrokenLink] = []
    for source in files:
        original = source.read_text(encoding="utf-8")
        text = _without_code(original)
        matches = [*INLINE_LINK_RE.finditer(text), *REFERENCE_LINK_RE.finditer(text)]
        for match in sorted(matches, key=lambda item: item.start()):
            target = _link_target(match.group("target"))
            _, reason = _resolve_local_target(root, source, target)
            if reason is not None:
                failures.append(
                    BrokenLink(
                        source=source.relative_to(root),
                        line=_line_number(text, match.start()),
                        target=target,
                        reason=reason,
                    )
                )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Optional Markdown files or directories")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    try:
        files = _expand_paths(root, args.paths) if args.paths else _tracked_markdown_files(root)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"documentation check could not start: {exc}", file=sys.stderr)
        return 2

    failures = check_files(root, files)
    for failure in failures:
        print(
            f"{failure.source.as_posix()}:{failure.line}: {failure.reason}: {failure.target}",
            file=sys.stderr,
        )

    if failures:
        print(f"Documentation links failed: {len(failures)} problem(s).", file=sys.stderr)
        return 1

    print(f"Documentation links passed: {len(files)} Markdown file(s) checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
