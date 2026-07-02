"""
Data-contract test for story B1 (seo-S-39, epic seo-E-4): does the payload
shape that skills/seo/SKILL.md's "History Persistence" section instructs the
model to build actually satisfy scripts/history_write.py (story B0) end to
end -- schema validation, secret gate, timeline row, paired .md/.json?

This is deliberately NOT a test of history_write.py itself (that's B0's
test_history_write.py); it is a test of the *shape* the /seo audit skill
produces: 7 canonical categories summing to weight 100, issue_counts, a
markdown_report string, and (to prove the degrade-without-paid-data path)
NO data_sources field at all.

Hermetic: no real network access, no push to the real Lookin-AI/seo-history.
Mirrors test_history_write.py's fake-history-repo fixture (git init'd
locally under tmp_path, seeded with the real seo-history clone's
scripts/schema so validate_entry.py / append_timeline.py run for real).
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
    """A local git repo, seeded with the real validate_entry.py /
    append_timeline.py / schema/*.schema.json, with a fake 'origin' remote
    that is never dialed in this test (--no-push everywhere)."""
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


def build_skill_shaped_audit_payload(domain: str, date: str) -> dict:
    """Exactly the payload shape skills/seo/SKILL.md's "History Persistence"
    -> "Building the payload" section instructs the model to assemble for a
    scored /seo audit run:

        - audit_id: unique per run
        - site: bare domain, equal to --domain
        - date: YYYY-MM-DD
        - health_score: weighted aggregate of the 7 categories
        - categories: exactly the 7 canonical categories, weights summing
          to 100 (Technical SEO=22, Content Quality=23, On-Page SEO=20,
          Schema / Structured Data=10, Performance (CWV)=10,
          AI Search Readiness=10, Images=5)
        - issue_counts: {critical, high, medium, low}
        - markdown_report: the full human-readable report as one string

    NO `data_sources` field -- this is the "no Semrush/DataForSEO used this
    run" degrade path the SKILL.md instructions call out explicitly
    ("omit entirely when no ... paid source was used").
    """
    categories = [
        {"name": "Technical SEO", "weight": 22, "score": 84},
        {"name": "Content Quality", "weight": 23, "score": 71},
        {"name": "On-Page SEO", "weight": 20, "score": 88},
        {"name": "Schema / Structured Data", "weight": 10, "score": 65},
        {"name": "Performance (CWV)", "weight": 10, "score": 77},
        {"name": "AI Search Readiness", "weight": 10, "score": 55},
        {"name": "Images", "weight": 5, "score": 92},
    ]
    assert sum(c["weight"] for c in categories) == 100

    health_score = round(sum(c["weight"] * c["score"] for c in categories) / 100, 1)

    markdown_report = (
        f"# SEO Audit -- {domain}\n\n"
        f"**Date:** {date}\n"
        f"**Health Score:** {health_score}/100\n\n"
        "## Category Scores\n\n"
        + "\n".join(f"- {c['name']}: {c['score']}/100 (weight {c['weight']}%)" for c in categories)
        + "\n\n## Top Findings\n\n"
        "- Missing hreflang on 3 locale pages\n"
        "- LCP above threshold on the homepage\n\n"
        "## Quick Wins\n\n"
        "- Add missing alt text on product images\n"
    )

    return {
        "audit_id": f"{date}-{domain.replace('.', '-')}-b1contract",
        "site": domain,
        "date": date,
        "health_score": health_score,
        "categories": categories,
        "issue_counts": {"critical": 1, "high": 3, "medium": 6, "low": 4},
        "top_findings": [
            "Missing hreflang on 3 locale pages",
            "LCP above threshold on the homepage",
        ],
        "quick_wins": [
            "Add missing alt text on product images",
        ],
        "markdown_report": markdown_report,
        # no "data_sources" key at all -- proves the degrade-without-paid-source path.
    }


def test_skill_shaped_audit_payload_round_trips_through_history_write(tmp_path):
    """The exact payload shape SKILL.md instructs the model to build must
    satisfy history_write.py's full pipeline end to end: schema validation,
    secret gate, timeline append, paired .md/.json written, local commit
    (--no-push, so the real seo-history is never touched)."""
    domain = "example-test.com"
    date = "2026-07-02"

    repo = make_fake_history_repo(tmp_path)
    payload = build_skill_shaped_audit_payload(domain, date)
    assert "data_sources" not in payload, "this payload proves the no-paid-source degrade path"

    payload_path = tmp_path / "audit-payload.json"
    payload_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "history_write.py"),
            "--type", "audit",
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
    assert result["type"] == "audit"
    assert result["domain"] == domain
    assert result["committed"] is True
    assert result["pushed"] is False

    # paired .md + .json were produced at the expected location
    md_path = Path(result["md_path"])
    json_path = Path(result["json_path"])
    assert md_path.is_file(), "markdown_report must be written verbatim as the paired .md"
    assert json_path.is_file()
    assert md_path.parent == repo / "sites" / domain / "audits"
    assert md_path.name == f"{date}-audit.md"
    assert json_path.name == f"{date}-audit.json"

    written_json = json.loads(json_path.read_text(encoding="utf-8"))
    assert "markdown_report" not in written_json, "markdown_report must be stripped from the .json"
    assert written_json["report_paths"]["markdown"] == f"{date}-audit.md"
    assert written_json["audit_id"] == payload["audit_id"]
    assert written_json["health_score"] == payload["health_score"]
    assert "data_sources" not in written_json, "degrade path: schema must accept a missing data_sources"

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

    # append_timeline.py ran and produced a timeline row for this audit_id
    timeline_path = repo / "sites" / domain / "timeline.csv"
    assert timeline_path.is_file()
    timeline_text = timeline_path.read_text(encoding="utf-8")
    assert payload["audit_id"] in timeline_text

    # local commit made, nothing left dirty (worktree of the fake repo, not
    # the claude-seo fork -- --no-push everywhere, never touches real seo-history)
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    assert status.strip() == ""


def test_skill_shaped_payload_categories_match_canonical_weights():
    """Sanity check on the fixture itself: the 7 categories + weights this
    test builds are exactly the canonical set SKILL.md's Scoring
    Methodology and seo-history's audit.schema.json both require."""
    payload = build_skill_shaped_audit_payload("example-test.com", "2026-07-02")
    weights_by_name = {c["name"]: c["weight"] for c in payload["categories"]}
    assert weights_by_name == {
        "Technical SEO": 22,
        "Content Quality": 23,
        "On-Page SEO": 20,
        "Schema / Structured Data": 10,
        "Performance (CWV)": 10,
        "AI Search Readiness": 10,
        "Images": 5,
    }
    assert sum(weights_by_name.values()) == 100
    assert 0 <= payload["health_score"] <= 100
