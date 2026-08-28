from pathlib import Path

from scripts.check_markdown_links import check_files


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_accepts_existing_relative_root_and_external_links(tmp_path):
    guide = _write(tmp_path / "docs" / "guide.md", "# Guide\n")
    index = _write(
        tmp_path / "README.md",
        "[guide](docs/guide.md) [root](/docs/guide.md) [section](docs/guide.md#guide) [web](https://example.com)\n",
    )

    assert check_files(tmp_path, [index, guide]) == []


def test_reports_missing_target_with_source_line(tmp_path):
    source = _write(tmp_path / "docs" / "guide.md", "# Guide\n\n[missing](nope.md)\n")

    failures = check_files(tmp_path, [source])

    assert len(failures) == 1
    assert failures[0].source == Path("docs/guide.md")
    assert failures[0].line == 3
    assert failures[0].target == "nope.md"
    assert failures[0].reason == "target does not exist"


def test_ignores_links_inside_inline_and_fenced_code(tmp_path):
    source = _write(
        tmp_path / "guide.md",
        "`[inline](missing.md)`\n\n```markdown\n[fenced](missing.md)\n```\n",
    )

    assert check_files(tmp_path, [source]) == []


def test_checks_reference_link_definitions(tmp_path):
    source = _write(
        tmp_path / "guide.md",
        "Read [the guide][guide].\n\n[guide]: missing.md\n",
    )

    failures = check_files(tmp_path, [source])

    assert len(failures) == 1
    assert failures[0].line == 3
    assert failures[0].target == "missing.md"


def test_rejects_links_that_escape_repository(tmp_path):
    source = _write(tmp_path / "docs" / "guide.md", "[outside](../../outside.md)\n")

    failures = check_files(tmp_path, [source])

    assert len(failures) == 1
    assert failures[0].reason == "target escapes the repository"
