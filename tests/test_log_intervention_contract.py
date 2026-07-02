"""
Data-contract test for story B4 (seo-S-42, epic seo-E-4): the `/seo
log-intervention` command (skills/seo-history/SKILL.md).

Two things are tested:

1. The linkage-enforcement precondition
   (`history_write.check_intervention_linkage`) -- a small, importable,
   stdlib-only helper factored out of SKILL.md prose specifically so the
   "mandatory finding link unless --no-link" business rule is unit-testable
   (per the story instructions), even though the rest of log-intervention's
   argument parsing / payload assembly is pure SKILL.md prose the model
   follows (same pattern as B1/B2 -- no dedicated script for those).

2. The payload SHAPE the skill instructs the model to build actually
   satisfies scripts/history_write.py (story B0) end to end -- schema
   validation, secret gate, paired .md/.json -- for BOTH the linked
   (--finding) and unlinked (--no-link) cases. finding_ref is OPTIONAL at
   the schema level (seo-history/schema/intervention.schema.json); the
   mandatory-unless-opted-out rule is enforced above, at the skill layer,
   not by the schema.

Hermetic: no real network access, no push to the real Lookin-AI/seo-history.
Mirrors test_history_write.py / test_history_persist_contract.py's
fake-history-repo fixture (git init'd locally under tmp_path, seeded with
the real seo-history clone's scripts/schema -- which now includes the
finding_ref field added alongside this story -- so validate_entry.py runs
for real).
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
    """A local git repo, seeded with the real validate_entry.py /
    schema/*.schema.json (including this story's finding_ref addition),
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


def build_intervention_payload(
    domain: str,
    date: str,
    description: str,
    *,
    finding_ref: str | None,
    audit_id: str | None = None,
    status: str = "completed",
    category: str | None = None,
) -> dict:
    """Exactly the payload shape skills/seo-history/SKILL.md's
    `log-intervention` "Building the payload" step instructs the model to
    assemble."""
    slug_proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "history_write.py"), "--slugify", description],
        capture_output=True,
        text=True,
    )
    assert slug_proc.returncode == 0, slug_proc.stderr
    slug = slug_proc.stdout.strip()

    payload = {
        "site": domain,
        "date": date,
        "slug": slug,
        "description": description,
        "status": status,
        "type": "manual",
        "markdown_report": (
            f"# Intervento: {description}\n\n"
            f"**Sito:** {domain}\n"
            f"**Data:** {date}\n"
            f"**Stato:** {status}\n"
            f"**Finding collegata:** {finding_ref or 'Nessuna (--no-link)'}\n"
        ),
    }
    if category is not None:
        payload["category"] = category
    if finding_ref is not None:
        payload["finding_ref"] = finding_ref
    if audit_id is not None:
        payload["audit_id"] = audit_id
    return payload


def _write_and_run(tmp_path: Path, repo: Path, domain: str, payload: dict, name: str) -> subprocess.CompletedProcess:
    payload_path = tmp_path / name
    payload_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "history_write.py"),
            "--type", "intervention",
            "--domain", domain,
            "--payload", str(payload_path),
            "--history-path", str(repo),
            "--no-push",
            "--json",
        ],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# 1. Linkage-enforcement precondition (unit-testable, per the story)
# ---------------------------------------------------------------------------


def test_linkage_refused_when_neither_finding_nor_no_link() -> None:
    with pytest.raises(history_write.PayloadError):
        history_write.check_intervention_linkage(None, False)


def test_linkage_refused_when_finding_is_blank_string() -> None:
    with pytest.raises(history_write.PayloadError):
        history_write.check_intervention_linkage("   ", False)


def test_linkage_ok_with_finding_ref() -> None:
    history_write.check_intervention_linkage("2026-07-01-audit.json#3", False)  # no raise


def test_linkage_ok_with_explicit_no_link() -> None:
    history_write.check_intervention_linkage(None, True)  # no raise


# ---------------------------------------------------------------------------
# 2. Payload shape round-trips through history_write.py -- WITH finding_ref
# ---------------------------------------------------------------------------


def test_intervention_with_finding_ref_round_trips_through_history_write(tmp_path):
    domain = "example-test.com"
    date = "2026-07-02"
    description = "Corretti i tag canonical duplicati su 14 pagine prodotto"

    history_write.check_intervention_linkage("2026-07-01-audit.json#3", False)  # precondition passes

    repo = make_fake_history_repo(tmp_path)
    payload = build_intervention_payload(
        domain,
        date,
        description,
        finding_ref="2026-07-01-audit.json#3",
        audit_id="2026-07-01-audit",
        status="completed",
        category="Technical SEO",
    )

    proc = _write_and_run(tmp_path, repo, domain, payload, "intervention-linked.json")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    result = json.loads(proc.stdout)
    assert result["status"] == "ok"
    assert result["type"] == "intervention"
    assert result["domain"] == domain
    assert result["committed"] is True
    assert result["pushed"] is False

    md_path = Path(result["md_path"])
    json_path = Path(result["json_path"])
    assert md_path.is_file()
    assert json_path.is_file()
    assert md_path.parent == repo / "sites" / domain / "interventions"

    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert "markdown_report" not in written
    assert written["finding_ref"] == "2026-07-01-audit.json#3"
    assert written["audit_id"] == "2026-07-01-audit"
    assert written["status"] == "completed"
    assert written["category"] == "Technical SEO"
    assert written["report_paths"]["markdown"] == md_path.name

    validate_proc = subprocess.run(
        [sys.executable, str(repo / "scripts" / "validate_entry.py"), str(json_path)],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert validate_proc.returncode == 0, validate_proc.stdout + validate_proc.stderr


# ---------------------------------------------------------------------------
# 3. Payload shape round-trips through history_write.py -- WITHOUT
#    finding_ref (the --no-link case): still valid, finding_ref optional
#    at the schema level.
# ---------------------------------------------------------------------------


def test_intervention_without_finding_ref_no_link_case_still_valid(tmp_path):
    domain = "example-test.com"
    date = "2026-07-02"
    description = "Aggiornata la homepage con nuovo hero banner"

    history_write.check_intervention_linkage(None, True)  # --no-link precondition passes

    repo = make_fake_history_repo(tmp_path)
    payload = build_intervention_payload(
        domain,
        date,
        description,
        finding_ref=None,
        status="completed",
    )
    assert "finding_ref" not in payload, "the --no-link case must omit finding_ref entirely"

    proc = _write_and_run(tmp_path, repo, domain, payload, "intervention-unlinked.json")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    result = json.loads(proc.stdout)
    assert result["status"] == "ok"
    assert result["committed"] is True

    json_path = Path(result["json_path"])
    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert "finding_ref" not in written
    assert written["status"] == "completed"

    validate_proc = subprocess.run(
        [sys.executable, str(repo / "scripts" / "validate_entry.py"), str(json_path)],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert validate_proc.returncode == 0, validate_proc.stdout + validate_proc.stderr


def test_default_status_used_when_caller_omits_it():
    payload = build_intervention_payload(
        "example-test.com",
        "2026-07-02",
        "Un intervento senza stato esplicito",
        finding_ref="2026-07-01-audit.json#1",
    )
    # SKILL.md documents "completed" as the default; this helper mirrors
    # that default when the caller doesn't override `status`.
    assert payload["status"] == "completed"
