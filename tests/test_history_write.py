"""
Tests for scripts/history_write.py + scripts/history_clone.py (story B0,
seo-S-38, epic seo-E-4).

Hermetic: NO real network access, NO push to the real Lookin-AI/seo-history.
Every git operation in these tests targets a TEMP fake history repo created
under tmp_path (git init'd locally, with a fake 'origin' remote URL that is
never actually dialed because every test that reaches the commit stage
passes --no-push / no_push=True).

The fake history repo is seeded by copying scripts/ and schema/ from the
real seo-history clone that lives as a sibling of this fork (../seo-history)
so validate_entry.py / append_timeline.py are exercised for real. If that
sibling checkout isn't present (e.g. a CI runner without it), the tests
that need it are skipped rather than failing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import history_clone  # noqa: E402
import history_write  # noqa: E402

# Sibling of the claude-seo fork, matching history_clone.default_history_path()'s
# own resolution logic (fork_root.parent / "seo-history").
REAL_SEO_HISTORY_ROOT = REPO_ROOT.parent / "seo-history"

CANONICAL_CATEGORIES = [
    {"name": "Technical SEO", "weight": 22, "score": 80},
    {"name": "Content Quality", "weight": 23, "score": 75},
    {"name": "On-Page SEO", "weight": 20, "score": 85},
    {"name": "Schema / Structured Data", "weight": 10, "score": 90},
    {"name": "Performance (CWV)", "weight": 10, "score": 70},
    {"name": "AI Search Readiness", "weight": 10, "score": 60},
    {"name": "Images", "weight": 5, "score": 95},
]


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
    that is never dialed in these tests (--no-push everywhere)."""
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


def make_audit_payload(domain: str = "example.com", date: str = "2026-07-02") -> dict:
    return {
        "audit_id": f"audit-{date}-{domain.replace('.', '-')}-001",
        "site": domain,
        "date": date,
        "health_score": 79.5,
        "categories": [dict(c) for c in CANONICAL_CATEGORIES],
        "issue_counts": {"critical": 0, "high": 2, "medium": 5, "low": 3},
        "markdown_report": f"# Audit report for {domain}\n\nHealth score: 79.5/100.\n",
    }


# ---------------------------------------------------------------------------
# Path resolution precedence
# ---------------------------------------------------------------------------


def test_resolve_history_path_cli_arg_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("SEO_HISTORY_PATH", str(tmp_path / "from-env"))
    monkeypatch.setattr(history_clone, "CONFIG_PATH", tmp_path / "no-such-config.json")

    result = history_clone.resolve_history_path(cli_path=str(tmp_path / "from-cli"))
    assert result == (tmp_path / "from-cli").resolve()


def test_resolve_history_path_env_wins_over_config(tmp_path, monkeypatch):
    config_path = tmp_path / "history.json"
    config_path.write_text(json.dumps({"path": str(tmp_path / "from-config")}))
    monkeypatch.setattr(history_clone, "CONFIG_PATH", config_path)
    monkeypatch.setenv("SEO_HISTORY_PATH", str(tmp_path / "from-env"))

    result = history_clone.resolve_history_path(cli_path=None)
    assert result == (tmp_path / "from-env").resolve()


def test_resolve_history_path_config_wins_over_default(tmp_path, monkeypatch):
    config_path = tmp_path / "history.json"
    config_path.write_text(json.dumps({"path": str(tmp_path / "from-config")}))
    monkeypatch.setattr(history_clone, "CONFIG_PATH", config_path)
    monkeypatch.delenv("SEO_HISTORY_PATH", raising=False)

    result = history_clone.resolve_history_path(cli_path=None)
    assert result == (tmp_path / "from-config").resolve()


def test_resolve_history_path_default_is_sibling_of_fork(tmp_path, monkeypatch):
    monkeypatch.setattr(history_clone, "CONFIG_PATH", tmp_path / "no-such-config.json")
    monkeypatch.delenv("SEO_HISTORY_PATH", raising=False)

    result = history_clone.resolve_history_path(cli_path=None)
    assert result == history_clone.default_history_path().resolve()
    assert result.name == "seo-history"
    assert result.parent == REPO_ROOT.parent


# ---------------------------------------------------------------------------
# ensure-history-clone hard-fail preconditions (PATH manipulation)
# ---------------------------------------------------------------------------


def _stub_gh_ok(monkeypatch) -> None:
    """Stub out the gh-present / gh-authenticated preflight checks so the
    rest of the pipeline can be exercised without depending on gh actually
    being installed/authenticated on the test runner, and WITHOUT `gh auth
    status` making a real network call (hermeticity)."""
    monkeypatch.setattr(history_clone, "check_gh_present", lambda: None)
    monkeypatch.setattr(history_clone, "check_gh_authenticated", lambda: None)


def _shim_bin_dir(tmp_path: Path, include_gh: bool, gh_auth_ok: bool = True) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    real_git = shutil.which("git")
    assert real_git, "git must be present on the test runner's real PATH"
    os.symlink(real_git, bin_dir / "git")

    if include_gh:
        gh_path = bin_dir / "gh"
        exit_code = 0 if gh_auth_ok else 1
        gh_path.write_text(f"#!/bin/sh\nexit {exit_code}\n")
        gh_path.chmod(0o755)

    return bin_dir


def test_missing_gh_hard_fails_distinctly(tmp_path, monkeypatch):
    bin_dir = _shim_bin_dir(tmp_path, include_gh=False)
    monkeypatch.setenv("PATH", str(bin_dir))

    with pytest.raises(history_clone.HistoryCloneError) as exc_info:
        history_clone.ensure_history_clone(cli_path=str(tmp_path / "clone-target"))

    assert exc_info.value.exit_code == 2
    assert "gh" in str(exc_info.value).lower()


def test_gh_not_authenticated_hard_fails_distinctly(tmp_path, monkeypatch):
    bin_dir = _shim_bin_dir(tmp_path, include_gh=True, gh_auth_ok=False)
    monkeypatch.setenv("PATH", str(bin_dir))

    with pytest.raises(history_clone.HistoryCloneError) as exc_info:
        history_clone.ensure_history_clone(cli_path=str(tmp_path / "clone-target"))

    assert exc_info.value.exit_code == 2
    assert "autenticat" in str(exc_info.value).lower()


def test_missing_git_hard_fails_distinctly(tmp_path, monkeypatch):
    bin_dir = tmp_path / "empty-bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))

    with pytest.raises(history_clone.HistoryCloneError) as exc_info:
        history_clone.ensure_history_clone(cli_path=str(tmp_path / "clone-target"))

    assert exc_info.value.exit_code == 2
    assert "git" in str(exc_info.value).lower()


def test_ensure_history_clone_reuses_existing_valid_clone(tmp_path, monkeypatch):
    _stub_gh_ok(monkeypatch)

    repo = make_fake_history_repo(tmp_path)
    resolved = history_clone.ensure_history_clone(cli_path=str(repo))
    assert resolved == repo


def test_ensure_history_clone_refuses_non_git_directory(tmp_path, monkeypatch):
    _stub_gh_ok(monkeypatch)

    not_a_clone = tmp_path / "not-a-clone"
    not_a_clone.mkdir()
    (not_a_clone / "some_file.txt").write_text("hello")

    with pytest.raises(history_clone.HistoryCloneError) as exc_info:
        history_clone.ensure_history_clone(cli_path=str(not_a_clone))
    assert exc_info.value.exit_code == 2


# ---------------------------------------------------------------------------
# Happy path: valid audit payload -> paired .md/.json, validated, timeline
# row, local commit (--no-push), exit 0
# ---------------------------------------------------------------------------


def test_write_entry_audit_happy_path(tmp_path, monkeypatch):
    _stub_gh_ok(monkeypatch)
    repo = make_fake_history_repo(tmp_path)
    payload = make_audit_payload()

    before_log = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"], capture_output=True, text=True
    ).stdout

    result = history_write.write_entry(
        "audit", "example.com", payload, history_path_arg=str(repo), no_push=True
    )

    assert result["status"] == "ok"
    assert result["type"] == "audit"
    assert result["domain"] == "example.com"
    assert result["committed"] is True
    assert result["pushed"] is False

    md_path = Path(result["md_path"])
    json_path = Path(result["json_path"])
    assert md_path.is_file()
    assert json_path.is_file()
    assert md_path.name == "2026-07-02-audit.md"
    assert json_path.name == "2026-07-02-audit.json"

    json_data = json.loads(json_path.read_text())
    assert "markdown_report" not in json_data
    assert json_data["report_paths"]["markdown"] == "2026-07-02-audit.md"
    assert json_data["audit_id"] == payload["audit_id"]

    # validate_entry.py must accept the written pair
    validate_proc = subprocess.run(
        [sys.executable, str(repo / "scripts" / "validate_entry.py"), str(json_path)],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert validate_proc.returncode == 0, validate_proc.stdout + validate_proc.stderr

    # timeline.csv got a row
    timeline_path = repo / "sites" / "example.com" / "timeline.csv"
    assert timeline_path.is_file()
    timeline_text = timeline_path.read_text()
    assert payload["audit_id"] in timeline_text

    # a local commit was made (no push -- --no-push / no_push=True)
    after_log = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"], capture_output=True, text=True
    ).stdout
    assert after_log != before_log
    last_commit_msg = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--pretty=%s"], capture_output=True, text=True
    ).stdout
    assert "audit" in last_commit_msg
    assert "example.com" in last_commit_msg

    # working tree is clean post-commit (files were git-added + committed)
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    assert status.strip() == ""


def test_write_entry_intervention_happy_path(tmp_path, monkeypatch):
    _stub_gh_ok(monkeypatch)
    repo = make_fake_history_repo(tmp_path)
    payload = {
        "site": "example.com",
        "date": "2026-07-02",
        "slug": "fix-canonical-tags",
        "description": "Fix duplicate canonical tags on product pages!",
        "status": "completed",
        "markdown_report": "# Intervention\n\nFixed duplicate canonical tags.\n",
    }

    result = history_write.write_entry(
        "intervention", "example.com", payload, history_path_arg=str(repo), no_push=True
    )

    assert result["status"] == "ok"
    assert result["committed"] is True
    md_path = Path(result["md_path"])
    assert md_path.name == "2026-07-02-fix-duplicate-canonical-tags-on-product-pages.md"


# ---------------------------------------------------------------------------
# Fail-closed: nothing committed on schema violation or secret leak
# ---------------------------------------------------------------------------


def test_write_entry_fails_closed_on_weight_sum_mismatch(tmp_path, monkeypatch):
    _stub_gh_ok(monkeypatch)
    repo = make_fake_history_repo(tmp_path)
    payload = make_audit_payload()
    # Corrupt one category weight so the canonical weights no longer sum to 100.
    payload["categories"][0]["weight"] = 21  # was 22 -> sum is now 99

    before_log = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"], capture_output=True, text=True
    ).stdout

    with pytest.raises(history_write.HistoryWriteError) as exc_info:
        history_write.write_entry(
            "audit", "example.com", payload, history_path_arg=str(repo), no_push=True
        )
    assert exc_info.value.exit_code == 1
    assert "validate_entry" in str(exc_info.value).lower() or "weight" in str(exc_info.value).lower()

    after_log = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"], capture_output=True, text=True
    ).stdout
    assert after_log == before_log, "nothing should have been committed on a fail-closed gate failure"


def test_write_entry_fails_closed_on_secret_in_markdown(tmp_path, monkeypatch):
    _stub_gh_ok(monkeypatch)
    repo = make_fake_history_repo(tmp_path)
    payload = make_audit_payload()
    fake_google_api_key = "AIza" + "x" * 35
    payload["markdown_report"] += f"\n\nDebug: used key {fake_google_api_key} for testing.\n"

    before_log = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"], capture_output=True, text=True
    ).stdout

    with pytest.raises(history_write.HistoryWriteError) as exc_info:
        history_write.write_entry(
            "audit", "example.com", payload, history_path_arg=str(repo), no_push=True
        )
    assert exc_info.value.exit_code == 1

    after_log = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"], capture_output=True, text=True
    ).stdout
    assert after_log == before_log, "nothing should have been committed when a secret is detected"


def test_write_entry_fails_closed_on_missing_markdown_report(tmp_path, monkeypatch):
    _stub_gh_ok(monkeypatch)
    repo = make_fake_history_repo(tmp_path)
    payload = make_audit_payload()
    del payload["markdown_report"]

    with pytest.raises(history_write.HistoryWriteError) as exc_info:
        history_write.write_entry(
            "audit", "example.com", payload, history_path_arg=str(repo), no_push=True
        )
    assert exc_info.value.exit_code == 2
    assert "markdown_report" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Worktree isolation: only the history clone is touched, never the fork
# ---------------------------------------------------------------------------


def test_write_entry_never_touches_fork_worktree(tmp_path, monkeypatch):
    _stub_gh_ok(monkeypatch)
    repo = make_fake_history_repo(tmp_path)
    payload = make_audit_payload(domain="isolation-test.example", date="2026-07-02")

    git_calls: list[list[str]] = []
    real_run = subprocess.run

    def spy_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0] == "git":
            git_calls.append(cmd)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(history_write.subprocess, "run", spy_run)

    fork_snapshot_before = {
        p: p.stat().st_mtime
        for p in REPO_ROOT.rglob("*")
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts
    }

    result = history_write.write_entry(
        "audit",
        "isolation-test.example",
        payload,
        history_path_arg=str(repo),
        no_push=True,
    )
    assert result["status"] == "ok"

    fork_snapshot_after = {
        p: p.stat().st_mtime
        for p in REPO_ROOT.rglob("*")
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts
    }
    assert fork_snapshot_before == fork_snapshot_after, (
        "history_write.write_entry must never modify files inside the claude-seo fork"
    )

    # every git invocation must be scoped with -C <clone>, never bare / never
    # pointed at the fork's own working tree
    assert git_calls, "expected at least one git subprocess call"
    for cmd in git_calls:
        assert cmd[1] == "-C", f"git call not scoped with -C: {cmd}"
        assert cmd[2] == str(repo), f"git call scoped to unexpected path: {cmd}"
        assert str(REPO_ROOT) not in cmd, f"git call touched the fork worktree: {cmd}"


# ---------------------------------------------------------------------------
# CLI smoke test (subprocess, --json, --no-push)
# ---------------------------------------------------------------------------


def test_cli_end_to_end_json_output(tmp_path):
    repo = make_fake_history_repo(tmp_path)
    payload = make_audit_payload(domain="cli-test.example")
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload))

    # Runs as a real subprocess, so monkeypatch can't reach it: shim a PATH
    # with a real `git` and a `gh` stub that always exits 0 (so `gh auth
    # status` never makes a real network call) to keep this hermetic.
    bin_dir = _shim_bin_dir(tmp_path, include_gh=True, gh_auth_ok=True)
    child_env = dict(os.environ)
    child_env["PATH"] = str(bin_dir)

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "history_write.py"),
            "--type", "audit",
            "--domain", "cli-test.example",
            "--payload", str(payload_path),
            "--history-path", str(repo),
            "--no-push",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=child_env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    output = json.loads(proc.stdout)
    assert output["status"] == "ok"
    assert output["committed"] is True
    assert output["pushed"] is False
