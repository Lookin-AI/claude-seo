"""
Data-contract test for story B2 (seo-S-40, epic seo-E-4): does the payload
shape that skills/seo-content-brief/SKILL.md's "History Persistence"
section instructs the model to build actually satisfy
scripts/history_write.py (story B0) end to end -- schema validation, secret
gate, paired .md/.json, state="brief", no published_url?

This is deliberately NOT a test of history_write.py itself (that's B0's
test_history_write.py); it is a test of the *shape* the `/seo
content-brief` skill produces for a content entry, plus a standalone unit
test of the shared `slugify()` addressing-key helper (scripts/
history_write.py) against a handful of tricky titles -- spaces,
punctuation, accents, casing -- since story B3 (claude-blog, a different
repo) must reproduce identical slugs from titles alone to find this brief
later. See seo-history/docs/addressing-key.md for the full cross-fork
contract this test exercises.

Hermetic: no real network access, no push to the real Lookin-AI/seo-history.
Mirrors test_history_write.py / test_history_persist_contract.py's
fake-history-repo fixture (git init'd locally under tmp_path, seeded with
the real seo-history clone's scripts/schema so validate_entry.py runs for
real).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import history_write  # noqa: E402

# Sibling of the claude-seo fork, matching history_clone.default_history_path()'s
# own resolution logic (fork_root.parent / "seo-history").
REAL_SEO_HISTORY_ROOT = REPO_ROOT.parent / "seo-history"


def _require_real_seo_history() -> None:
    if not (REAL_SEO_HISTORY_ROOT / "scripts" / "validate_entry.py").is_file():
        pytest.skip(
            f"real seo-history checkout not found at {REAL_SEO_HISTORY_ROOT}; "
            "skipping tests that need its scripts/schema"
        )


def _run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"command {cmd} failed in {cwd}:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


def make_fake_history_repo(tmp_path: Path) -> Path:
    """A local git repo, seeded with the real validate_entry.py / schema/,
    with a fake 'origin' remote that is never dialed in this test
    (--no-push everywhere)."""
    _require_real_seo_history()

    repo = tmp_path / "seo-history"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "test@example.invalid"], repo)
    _run(["git", "config", "user.name", "Test Runner"], repo)
    _run(
        ["git", "remote", "add", "origin", "https://github.com/Lookin-AI/seo-history.git"],
        repo,
    )

    shutil.copytree(
        REAL_SEO_HISTORY_ROOT / "scripts",
        repo / "scripts",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copytree(
        REAL_SEO_HISTORY_ROOT / "schema",
        repo / "schema",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (repo / "sites").mkdir()
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n")

    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-q", "-m", "seed fake seo-history repo for tests"], repo)
    return repo


def build_skill_shaped_brief_payload(domain: str, date: str, title: str) -> dict:
    """Exactly the payload shape skills/seo-content-brief/SKILL.md's
    "History Persistence" -> "Building the payload" section instructs the
    model to assemble after delivering a brief:

        - site: bare domain, equal to --domain
        - date: YYYY-MM-DD
        - slug: history_write.slugify(title) -- the canonical addressing
          key helper, exactly as the skill instructs the model to call it
          via `--slugify` on the CLI
        - content_type: "brief"
        - state: "brief"
        - title
        - target_keyword (optional)
        - markdown_report: the brief text as one string

    No published_url, no word_count -- those belong to the B3 "pubblicato"
    transition, not a brief.
    """
    slug = history_write.slugify(title)
    markdown_report = (
        f"## Content Brief: {title}\n\n"
        "### Search Intent\nInformational, long-form guide.\n\n"
        "### Winning Outline\n\n"
        f"**H1:** {title}\n"
        f"**URL Slug:** /{slug}\n"
        "**Target Word Count:** ~1800 words\n"
    )

    return {
        "site": domain,
        "date": date,
        "slug": slug,
        "content_type": "brief",
        "state": "brief",
        "title": title,
        "target_keyword": title.lower(),
        "markdown_report": markdown_report,
    }


def test_skill_shaped_brief_payload_round_trips_through_history_write(tmp_path):
    """The exact payload shape SKILL.md instructs the model to build for a
    content brief must satisfy history_write.py's full pipeline end to end:
    schema validation, secret gate, paired .md/.json written, state=brief,
    no published_url, local commit (--no-push, so the real seo-history is
    never touched)."""
    domain = "example-brief-test.com"
    date = "2026-07-02"
    title = "How to Fix 404 Errors: A Complete Guide"

    repo = make_fake_history_repo(tmp_path)
    payload = build_skill_shaped_brief_payload(domain, date, title)
    assert payload["state"] == "brief"
    assert "published_url" not in payload
    assert "word_count" not in payload

    payload_path = tmp_path / "brief-payload.json"
    payload_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "history_write.py"),
            "--type", "content",
            "--domain", domain,
            "--payload", str(payload_path),
            "--history-path", str(repo),
            "--no-push",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    result = json.loads(proc.stdout)
    assert result["status"] == "ok"
    assert result["type"] == "content"
    assert result["domain"] == domain
    assert result["committed"] is True
    assert result["pushed"] is False

    md_path = Path(result["md_path"])
    json_path = Path(result["json_path"])
    assert md_path.is_file()
    assert json_path.is_file()
    assert md_path.parent == repo / "sites" / domain / "content"
    expected_slug = history_write.slugify(title)
    assert md_path.name == f"{date}-brief-{expected_slug}.md"
    assert json_path.name == f"{date}-brief-{expected_slug}.json"

    written_json = json.loads(json_path.read_text(encoding="utf-8"))
    assert "markdown_report" not in written_json
    assert written_json["report_paths"]["markdown"] == f"{date}-brief-{expected_slug}.md"
    assert written_json["state"] == "brief"
    assert written_json["content_type"] == "brief"
    assert written_json["slug"] == expected_slug
    assert "published_url" not in written_json, "a brief must never carry published_url"

    written_md = md_path.read_text(encoding="utf-8")
    assert payload["markdown_report"] == written_md

    # validate_entry.py (schema + fail-closed secret gate) must accept it
    validate_proc = subprocess.run(
        [sys.executable, str(repo / "scripts" / "validate_entry.py"), str(json_path)],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert validate_proc.returncode == 0, validate_proc.stdout + validate_proc.stderr

    # local commit made, nothing left dirty
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    assert status.strip() == ""


def test_addressing_key_lookup_by_slug_finds_the_brief(tmp_path):
    """Simulates the B3 (claude-blog) lookup path documented in
    seo-history/docs/addressing-key.md: glob sites/<domain>/content/*.json
    and match on the `slug` field re-derived independently from the title
    -- NOT by reconstructing the filename (B3 doesn't know the date)."""
    domain = "example-brief-test.com"
    date = "2026-07-02"
    title = "How to Fix 404 Errors: A Complete Guide"

    repo = make_fake_history_repo(tmp_path)
    payload = build_skill_shaped_brief_payload(domain, date, title)
    payload_path = tmp_path / "brief-payload.json"
    payload_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "history_write.py"),
            "--type", "content",
            "--domain", domain,
            "--payload", str(payload_path),
            "--history-path", str(repo),
            "--no-push",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    # B3 knows only the published title, NOT the date the brief was created.
    b3_recomputed_slug = history_write.slugify(title)

    content_dir = repo / "sites" / domain / "content"
    matches = []
    for json_file in content_dir.glob("*.json"):
        entry = json.loads(json_file.read_text(encoding="utf-8"))
        if entry.get("slug") == b3_recomputed_slug and entry.get("state") == "brief":
            matches.append(entry)

    assert len(matches) == 1, "B3 must find exactly this one brief via (domain, slug)"
    assert matches[0]["title"] == title


# ---------------------------------------------------------------------------
# slugify() unit tests -- the cross-fork addressing-key helper itself.
# B3 (claude-blog) must reproduce these exact outputs independently
# (mirrored implementation, see seo-history/docs/addressing-key.md).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,expected",
    [
        ("  Café Résumé!!  ", "cafe-resume"),
        ("How to Fix 404 Errors (2026 Guide)", "how-to-fix-404-errors-2026-guide"),
        (
            "SEO for Small Business — A Complete Guide",
            "seo-for-small-business-a-complete-guide",
        ),
        ("Título con Ñ y acentos", "titulo-con-n-y-acentos"),
        ("UPPERCASE Title With MiXeD Case", "uppercase-title-with-mixed-case"),
        ("multiple   spaces\tand\ntabs", "multiple-spaces-and-tabs"),
        ("Punctuation: commas, semicolons; colons!", "punctuation-commas-semicolons-colons"),
        ("---leading-and-trailing-hyphens---", "leading-and-trailing-hyphens"),
        ("", "untitled"),
        ("!!!???", "untitled"),
    ],
)
def test_slugify_tricky_titles(title, expected):
    assert history_write.slugify(title) == expected


def test_slugify_is_idempotent():
    """Re-slugifying an already-slugified string must be a no-op -- this is
    what history_write.py's compute_target() relies on when it calls
    slugify(payload['slug']) a second time to build the filename."""
    title = "Café Résumé: A Complete Guide (2026)!!"
    once = history_write.slugify(title)
    twice = history_write.slugify(once)
    assert once == twice


def test_slugify_deterministic_across_calls():
    title = "How to Fix 404 Errors: A Complete Guide"
    assert history_write.slugify(title) == history_write.slugify(title)


def test_slugify_cli_matches_function(tmp_path):
    """The `--slugify` CLI mode the skill is instructed to shell out to
    must match the importable function exactly."""
    title = "Café Résumé: A Complete Guide (2026)!!"
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "history_write.py"), "--slugify", title],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip() == history_write.slugify(title)
