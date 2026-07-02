#!/usr/bin/env python3
"""
history_clone.py -- ensure-history-clone preflight for scripts/history_write.py.

Story B0 (seo-S-38, epic seo-E-4), Part B foundation. This module resolves
where the seo-history data repo (Lookin-AI/seo-history) lives on disk and
guarantees a usable clone exists there before history_write.py writes
anything -- fail-closed, never a silent "proceed as though it worked".

Clone path resolution precedence (highest to lowest):
    1. `cli_path` argument (history_write.py's --history-path flag)
    2. $SEO_HISTORY_PATH environment variable
    3. ~/.config/claude-seo/history.json  {"path": "..."}
    4. default: a `seo-history` directory that is a SIBLING of this fork's
       parent directory -- i.e. if this fork (claude-seo) lives at
       /a/b/claude-seo, the default is /a/b/seo-history.

Hard preconditions, each a DISTINCT hard-fail with a clear message and a
non-zero exit code (mirrors scripts/sync-upstream.sh's idiom: `command -v
git`, `command -v gh`, `gh auth status`, never a silent fallback):
    1. git must be on PATH
    2. gh (GitHub CLI) must be on PATH
    3. gh must be authenticated (`gh auth status`)
    4. the parent directory of the resolved clone path must exist and be
       writable

Clone reuse vs. fresh clone:
    - If the resolved path exists AND looks like a git clone with an
      'origin' remote pointing at seo-history -> reused as-is.
    - If the resolved path exists but does NOT look like such a clone ->
      hard-fail (never silently reuse/overwrite an unrelated directory).
    - If the resolved path does not exist -> `gh repo clone
      Lookin-AI/seo-history <path>`. If that clone fails for ANY reason
      (network, permissions, gh error, ...) this hard-fails with setup
      instructions; it NEVER proceeds as though the clone had succeeded
      (this is the silent-failure risk the council flagged).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

SEO_HISTORY_REPO_SLUG = "Lookin-AI/seo-history"
ENV_VAR = "SEO_HISTORY_PATH"
CONFIG_PATH = Path(os.path.expanduser("~/.config/claude-seo/history.json"))


class HistoryCloneError(RuntimeError):
    """A hard-fail during the ensure-history-clone preflight.

    `exit_code` is the process exit code the CLI should propagate (always
    non-zero -- this class exists specifically to make hard-fails
    distinguishable from each other in tests and from schema/secret
    fail-closed errors raised elsewhere in history_write.py).
    """

    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def default_history_path() -> Path:
    """`seo-history`, a sibling of this fork's parent directory."""
    fork_root = Path(__file__).resolve().parent.parent  # scripts/.. -> fork root
    return fork_root.parent / "seo-history"


def _read_config_path() -> Optional[Path]:
    if not CONFIG_PATH.is_file():
        return None
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = data.get("path") if isinstance(data, dict) else None
    if not value or not isinstance(value, str):
        return None
    return Path(value).expanduser()


def resolve_history_path(cli_path: Optional[str] = None) -> Path:
    """Resolve the seo-history clone path per the precedence documented in
    the module docstring. Never touches the filesystem beyond reading the
    optional config file."""
    if cli_path:
        return Path(cli_path).expanduser().resolve()

    env_value = os.environ.get(ENV_VAR)
    if env_value:
        return Path(env_value).expanduser().resolve()

    config_value = _read_config_path()
    if config_value is not None:
        return config_value.resolve()

    return default_history_path().resolve()


# ---------------------------------------------------------------------------
# Hard preconditions
# ---------------------------------------------------------------------------


def check_git_present() -> None:
    if shutil.which("git") is None:
        raise HistoryCloneError(
            "git non trovato sul PATH: installa git per continuare.", exit_code=2
        )


def check_gh_present() -> None:
    if shutil.which("gh") is None:
        raise HistoryCloneError(
            "gh (GitHub CLI) non trovato sul PATH: installa gh "
            "(https://cli.github.com) per continuare.",
            exit_code=2,
        )


def check_gh_authenticated() -> None:
    try:
        proc = subprocess.run(
            ["gh", "auth", "status"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HistoryCloneError(
            f"impossibile eseguire 'gh auth status': {exc}", exit_code=2
        ) from exc
    if proc.returncode != 0:
        raise HistoryCloneError(
            "gh non autenticato. Esegui 'gh auth login' per continuare.", exit_code=2
        )


def check_parent_writable(path: Path) -> None:
    parent = path.parent
    if not parent.exists():
        raise HistoryCloneError(
            f"la directory padre {parent} non esiste: creala prima di continuare.",
            exit_code=2,
        )
    if not os.access(parent, os.W_OK):
        raise HistoryCloneError(
            f"la directory padre {parent} non è scrivibile.", exit_code=2
        )


# ---------------------------------------------------------------------------
# Clone detection / creation
# ---------------------------------------------------------------------------


def _remote_looks_like_seo_history(path: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        return False
    return "seo-history" in proc.stdout.strip().lower()


def looks_like_seo_history_clone(path: Path) -> bool:
    """True if `path` is a directory containing a .git dir whose 'origin'
    remote URL mentions seo-history."""
    return path.is_dir() and (path / ".git").exists() and _remote_looks_like_seo_history(path)


def clone_seo_history(path: Path) -> None:
    """`gh repo clone Lookin-AI/seo-history <path>`. Hard-fails on any
    problem; NEVER proceeds as though a failed clone had succeeded."""
    try:
        proc = subprocess.run(
            ["gh", "repo", "clone", SEO_HISTORY_REPO_SLUG, str(path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HistoryCloneError(
            f"clone di {SEO_HISTORY_REPO_SLUG} in {path} fallito: {exc}", exit_code=2
        ) from exc
    if proc.returncode != 0 or not looks_like_seo_history_clone(path):
        raise HistoryCloneError(
            f"clone di {SEO_HISTORY_REPO_SLUG} in {path} fallito.\n"
            f"stdout: {proc.stdout.strip()}\nstderr: {proc.stderr.strip()}\n"
            "Verifica i permessi su Lookin-AI/seo-history e riprova manualmente con:\n"
            f"  gh repo clone {SEO_HISTORY_REPO_SLUG} {path}",
            exit_code=2,
        )


def ensure_history_clone(cli_path: Optional[str] = None) -> Path:
    """Full B0 preflight: enforce hard preconditions, resolve the clone
    path, and guarantee a usable seo-history clone exists there -- or raise
    HistoryCloneError. Never returns a path that does not actually look
    like a valid clone.
    """
    check_git_present()
    check_gh_present()
    check_gh_authenticated()

    path = resolve_history_path(cli_path)
    check_parent_writable(path)

    if path.exists():
        if looks_like_seo_history_clone(path):
            return path
        raise HistoryCloneError(
            f"{path} esiste già ma non sembra un clone git di {SEO_HISTORY_REPO_SLUG} "
            "(manca .git oppure il remote 'origin' non corrisponde). Rimuovilo o punta "
            "altrove con --history-path / $SEO_HISTORY_PATH.",
            exit_code=2,
        )

    clone_seo_history(path)
    return path


def main(argv: Optional[list[str]] = None) -> int:
    """Standalone CLI: resolve + ensure the clone, print its path. Mainly
    useful for manual debugging; history_write.py imports the functions
    above directly."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Ensure a local seo-history clone exists and is usable."
    )
    parser.add_argument("--history-path", default=None, dest="history_path")
    args = parser.parse_args(argv)

    try:
        path = ensure_history_clone(args.history_path)
    except HistoryCloneError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code

    print(str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
