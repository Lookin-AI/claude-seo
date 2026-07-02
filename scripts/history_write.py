#!/usr/bin/env python3
"""
history_write.py -- the single write path from claude-seo skills into the
seo-history data repo (Lookin-AI/seo-history).

Story B0 (seo-S-38, epic seo-E-4), the foundation of Part B. Stories B1
(audit), B2 (content), and B4 (intervention) call this script (or import
its `write_entry` function) instead of writing to seo-history directly.

Usage:
    python scripts/history_write.py --type {audit|content|intervention} \\
        --domain <domain> --payload <path-to-json> \\
        [--history-path <dir>] [--no-push] [--json]

Payload contract (single source of truth -- Invariante 2)
-----------------------------------------------------------
The payload is ONE JSON file containing every structured field required by
seo-history's schema/<type>.schema.json for that entry type, PLUS a single
extra string field: `markdown_report` (the human-readable report the
calling skill produced). This script splits it:
    - `markdown_report` -> written verbatim as the paired .md file.
    - everything else   -> written as the .json file (after this script
      sets/overwrites `report_paths.markdown` to the paired .md's filename
      and strips `markdown_report` out). The resulting .json MUST validate
      against seo-history's schema/<type>.schema.json.
Required payload fields beyond the schema's own `required` list:
    - `date` (YYYY-MM-DD) is required for ALL three types (also required by
      each schema) and drives the entry filename.
    - `slug` is required for --type content (drives the filename).
    - `description` is required for --type intervention (slugified into the
      filename; this is separate from the schema's own required `slug`
      field, which is written through unchanged into the .json).
    - if payload["site"] is present it must equal --domain (hard-fail on
      mismatch, to catch a payload accidentally built for the wrong site).

Entry filenames / locations inside the seo-history clone:
    - audit        -> sites/<domain>/audits/<date>-audit.md (+ .json)
    - content       -> sites/<domain>/content/<date>-brief-<slug>.md (+ .json)
    - intervention  -> sites/<domain>/interventions/<date>-<slug(description)>.md (+ .json)

Pipeline (fail-closed at every step -- a failure at any step means NOTHING
is committed or pushed):
    1. ensure-history-clone preflight (scripts/history_clone.py): resolve
       the clone path (--history-path > $SEO_HISTORY_PATH > ~/.config/
       claude-seo/history.json > sibling default) and guarantee a usable
       clone exists there.
    2. Render the .md/.json pair into a tempdir, then copy into place at
       the target paths inside the clone.
    3. Validate: `python <clone>/scripts/validate_entry.py <entry.json>`.
       Non-zero -> exit 1, nothing committed. This is the fail-closed
       schema + secret/PII gate (validate_entry.py, story A2).
    4. Timeline (audit only): `python <clone>/scripts/append_timeline.py
       <domain>`. Non-zero -> exit 1, nothing committed.
    5. git add (only the specific files written) + commit (Italian
       message) inside the clone -- always via `git -C <clone>`, so the
       claude-seo fork's own working tree is never touched (worktree
       isolation). Push to origin main with a pull --rebase + retry loop
       (up to 3 attempts) unless --no-push (commit locally only; used by
       tests -- NEVER pushes to the real seo-history during tests).
    6. Exit 0 on success. --json emits:
       {status, type, domain, md_path, json_path, committed, pushed}.

Exit codes:
    0  success
    1  fail-closed gate failure (schema/secret validation, timeline
       regeneration, or a git commit/push failure) -- nothing committed
    2  environment/usage error (bad CLI args, bad payload, ensure-clone
       preflight failure)

Stdlib-only at runtime (argparse, json, re, shutil, subprocess, sys,
tempfile, pathlib) plus the sibling module scripts/history_clone.py, which
is itself stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Optional

# Sibling-module import, same pattern as scripts/drift_baseline.py /
# seo-history's scripts/append_timeline.py importing validate_entry.py --
# not a third-party dependency.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from history_clone import HistoryCloneError, ensure_history_clone  # noqa: E402

ENTRY_TYPES = ("audit", "content", "intervention")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_TYPE_TO_SUBDIR = {
    "audit": "audits",
    "content": "content",
    "intervention": "interventions",
}

_TYPE_TO_COMMIT_LABEL = {
    "audit": "audit",
    "content": "content",
    "intervention": "intervento",
}


# ---------------------------------------------------------------------------
# slug helper
# ---------------------------------------------------------------------------
#
# CANONICAL RULE (do not fork/reimplement from prose elsewhere): this is the
# one deterministic slug function claude-seo uses for every entry type, and
# it is also the addressing-key contract for content briefs (story B2,
# seo-S-40): a brief is later found by claude-blog (story B3, a *different*
# repo that cannot import this module) via the pair (domain, slug), where
# slug = slugify(title). B3 must reimplement this exact algorithm --
# normalize Unicode to strip accents/diacritics BEFORE casing/collapsing, so
# "Café" and "cafe" produce the same slug. See
# seo-history/docs/addressing-key.md (the shared data repo both forks read)
# for the full contract; this docstring + function body is the reference
# implementation it points back to.


def slugify(text: str, max_len: int = 60) -> str:
    """Deterministic slug: Unicode-normalize (strip accents/diacritics),
    lowercase, collapse any run of non-alphanumeric characters to a single
    hyphen, strip leading/trailing hyphens, cap at max_len (default 60,
    trimmed back to a hyphen boundary). Always returns a non-empty string.

    Pure stdlib (re + unicodedata), no I/O -- safe to call standalone via
    `python3 scripts/history_write.py --slugify "<text>"`.
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    if not text:
        text = "untitled"
    text = text[:max_len].rstrip("-")
    return text or "untitled"


# ---------------------------------------------------------------------------
# Payload -> (base filename, subdir) + validated required fields
# ---------------------------------------------------------------------------


class PayloadError(ValueError):
    """A malformed/incomplete payload -- a usage error (exit 2), distinct
    from a schema/secret validation failure (exit 1)."""


def compute_target(entry_type: str, domain: str, payload: dict) -> tuple[str, str]:
    """Return (base_filename_without_extension, subdir) for this entry.
    Raises PayloadError if a required driving field is missing."""
    date = payload.get("date")
    if not isinstance(date, str) or not _DATE_RE.match(date):
        raise PayloadError("payload.date is required and must be YYYY-MM-DD")

    site = payload.get("site")
    if isinstance(site, str) and site.strip().lower() != domain:
        raise PayloadError(
            f"payload.site ({site!r}) does not match --domain ({domain!r})"
        )

    if entry_type == "audit":
        return f"{date}-audit", _TYPE_TO_SUBDIR[entry_type]

    if entry_type == "content":
        slug = payload.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            raise PayloadError("payload.slug is required for --type content")
        return f"{date}-brief-{slugify(slug)}", _TYPE_TO_SUBDIR[entry_type]

    if entry_type == "intervention":
        description = payload.get("description")
        if not isinstance(description, str) or not description.strip():
            raise PayloadError(
                "payload.description is required for --type intervention"
            )
        return f"{date}-{slugify(description)}", _TYPE_TO_SUBDIR[entry_type]

    raise PayloadError(f"unknown entry type: {entry_type!r}")


def split_payload(payload: dict, md_filename: str) -> tuple[str, dict]:
    """Split the single-source payload into (markdown_text, json_data).

    `markdown_report` is stripped out of json_data; json_data's
    report_paths.markdown is set/overwritten to md_filename (a bare
    filename -- the .md always lives alongside its .json).
    """
    markdown_report = payload.get("markdown_report")
    if not isinstance(markdown_report, str) or not markdown_report.strip():
        raise PayloadError(
            "payload.markdown_report is required and must be a non-empty string"
        )

    json_data = {k: v for k, v in payload.items() if k != "markdown_report"}
    report_paths = dict(json_data.get("report_paths") or {})
    report_paths["markdown"] = md_filename
    json_data["report_paths"] = report_paths

    return markdown_report, json_data


# ---------------------------------------------------------------------------
# Render + place (tempdir first, then copy into the clone's working tree)
# ---------------------------------------------------------------------------


def render_and_place(
    markdown_report: str, json_data: dict, target_dir: Path, base: str
) -> tuple[Path, Path]:
    """Render the .md/.json pair into a tempdir, then copy both into
    target_dir. Returns (md_path, json_path). Raises on any I/O error --
    the caller must not treat a partial write as success."""
    md_filename = f"{base}.md"
    json_filename = f"{base}.json"
    json_text = json.dumps(json_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    with tempfile.TemporaryDirectory(prefix="history-write-") as tmpdir_name:
        tmpdir = Path(tmpdir_name)
        tmp_md = tmpdir / md_filename
        tmp_json = tmpdir / json_filename
        tmp_md.write_text(markdown_report, encoding="utf-8")
        tmp_json.write_text(json_text, encoding="utf-8")

        target_dir.mkdir(parents=True, exist_ok=True)
        md_path = target_dir / md_filename
        json_path = target_dir / json_filename
        shutil.copy2(tmp_md, md_path)
        shutil.copy2(tmp_json, json_path)

    return md_path, json_path


# ---------------------------------------------------------------------------
# Validate / timeline subprocesses (fail-closed gates)
# ---------------------------------------------------------------------------


def run_validate_entry(clone_path: Path, json_path: Path) -> tuple[bool, str]:
    validate_script = clone_path / "scripts" / "validate_entry.py"
    proc = subprocess.run(
        [sys.executable, str(validate_script), str(json_path)],
        cwd=str(clone_path),
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output


def run_append_timeline(clone_path: Path, domain: str) -> tuple[bool, str]:
    timeline_script = clone_path / "scripts" / "append_timeline.py"
    proc = subprocess.run(
        [sys.executable, str(timeline_script), domain],
        cwd=str(clone_path),
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output


# ---------------------------------------------------------------------------
# git (always -C <clone> -- worktree isolation from the claude-seo fork)
# ---------------------------------------------------------------------------


def git_add(clone_path: Path, rel_paths: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        ["git", "-C", str(clone_path), "add", "--", *rel_paths],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def git_commit(clone_path: Path, message: str) -> tuple[bool, bool, str]:
    """Returns (ok, committed, output). ok is False only on a real
    failure; a 'nothing to commit' outcome is ok=True, committed=False."""
    proc = subprocess.run(
        ["git", "-C", str(clone_path), "commit", "-m", message],
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        return True, True, output
    if "nothing to commit" in output.lower():
        return True, False, output
    return False, False, output


def push_with_retry(clone_path: Path, attempts: int = 3) -> tuple[bool, str]:
    """pull --rebase + push loop, surviving concurrent pushes from the
    other fork working the same repo."""
    last_err = ""
    for _ in range(attempts):
        pull = subprocess.run(
            ["git", "-C", str(clone_path), "pull", "--rebase", "origin", "main"],
            capture_output=True,
            text=True,
        )
        if pull.returncode != 0:
            last_err = (pull.stdout or "") + (pull.stderr or "")
            continue
        push = subprocess.run(
            ["git", "-C", str(clone_path), "push", "origin", "HEAD:main"],
            capture_output=True,
            text=True,
        )
        if push.returncode == 0:
            return True, ""
        last_err = (push.stdout or "") + (push.stderr or "")
    return False, last_err


def build_commit_message(entry_type: str, domain: str, date: str, base: str) -> str:
    label = _TYPE_TO_COMMIT_LABEL[entry_type]
    return f"{label}: aggiungi entry {date} per {domain} ({base})"


# ---------------------------------------------------------------------------
# End-to-end write (importable by tests / by B1/B2/B4 skills directly)
# ---------------------------------------------------------------------------


class HistoryWriteError(RuntimeError):
    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def write_entry(
    entry_type: str,
    domain: str,
    payload: dict,
    history_path_arg: Optional[str] = None,
    no_push: bool = False,
) -> dict:
    """Run the full B0 pipeline. Returns the result dict on success; raises
    HistoryWriteError (with .exit_code) on any fail-closed step."""
    domain = domain.strip().lower()

    try:
        base, subdir = compute_target(entry_type, domain, payload)
    except PayloadError as exc:
        raise HistoryWriteError(str(exc), exit_code=2) from exc

    date = payload["date"]

    try:
        clone_path = ensure_history_clone(history_path_arg)
    except HistoryCloneError as exc:
        raise HistoryWriteError(str(exc), exit_code=exc.exit_code) from exc

    md_filename = f"{base}.md"
    try:
        markdown_report, json_data = split_payload(payload, md_filename)
    except PayloadError as exc:
        raise HistoryWriteError(str(exc), exit_code=2) from exc

    target_dir = clone_path / "sites" / domain / subdir
    md_path, json_path = render_and_place(markdown_report, json_data, target_dir, base)

    ok, output = run_validate_entry(clone_path, json_path)
    if not ok:
        raise HistoryWriteError(
            f"validate_entry.py FAILED -- nothing committed:\n{output}", exit_code=1
        )

    if entry_type == "audit":
        ok, output = run_append_timeline(clone_path, domain)
        if not ok:
            raise HistoryWriteError(
                f"append_timeline.py FAILED -- nothing committed:\n{output}", exit_code=1
            )

    add_files = [
        str(md_path.relative_to(clone_path)),
        str(json_path.relative_to(clone_path)),
    ]
    if entry_type == "audit":
        timeline_path = clone_path / "sites" / domain / "timeline.csv"
        if timeline_path.is_file():
            add_files.append(str(timeline_path.relative_to(clone_path)))

    ok, output = git_add(clone_path, add_files)
    if not ok:
        raise HistoryWriteError(f"git add failed:\n{output}", exit_code=1)

    commit_message = build_commit_message(entry_type, domain, date, base)
    ok, committed, output = git_commit(clone_path, commit_message)
    if not ok:
        raise HistoryWriteError(f"git commit failed:\n{output}", exit_code=1)

    pushed = False
    if committed and not no_push:
        pushed, push_err = push_with_retry(clone_path)
        if not pushed:
            raise HistoryWriteError(
                f"push to origin main failed after retries:\n{push_err}", exit_code=1
            )

    return {
        "status": "ok",
        "type": entry_type,
        "domain": domain,
        "md_path": str(md_path),
        "json_path": str(json_path),
        "committed": committed,
        "pushed": pushed,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Write one audit/content/intervention entry into the seo-history "
            "data repo (stdlib-only; the single write path for B1/B2/B4)."
        )
    )
    parser.add_argument(
        "--slugify",
        metavar="TEXT",
        default=None,
        help=(
            "Print the deterministic slug for TEXT and exit 0 -- no other "
            "flags required. This is the canonical addressing-key rule "
            "(see seo-history/docs/addressing-key.md); skills call this "
            "instead of computing a slug from prose rules."
        ),
    )
    parser.add_argument("--type", choices=ENTRY_TYPES, default=None)
    parser.add_argument("--domain", default=None, help="Bare domain, e.g. example.com")
    parser.add_argument(
        "--payload", type=Path, default=None, help="Path to the payload JSON file"
    )
    parser.add_argument(
        "--history-path",
        default=None,
        dest="history_path",
        help="Override the seo-history clone path (see history_clone.py precedence)",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Commit locally only; do not push to origin main (used by tests)",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.slugify is not None:
        print(slugify(args.slugify))
        return 0

    missing = [
        name
        for name, value in (("--type", args.type), ("--domain", args.domain), ("--payload", args.payload))
        if value is None
    ]
    if missing:
        print(
            f"error: {', '.join(missing)} required (unless --slugify is used)",
            file=sys.stderr,
        )
        return 2

    if not args.payload.is_file():
        print(f"error: payload file not found: {args.payload}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(args.payload.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read/parse payload JSON {args.payload}: {exc}", file=sys.stderr)
        return 2

    if not isinstance(payload, dict):
        print("error: payload JSON must be an object at the top level", file=sys.stderr)
        return 2

    try:
        result = write_entry(
            args.type,
            args.domain,
            payload,
            history_path_arg=args.history_path,
            no_push=args.no_push,
        )
    except HistoryWriteError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"history_write: type={result['type']} domain={result['domain']} "
            f"committed={result['committed']} pushed={result['pushed']}"
        )
        print(f"  md:   {result['md_path']}")
        print(f"  json: {result['json_path']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
