"""
No-regression guard for skills/seo-backlinks/SKILL.md's confidence-weighted
source encodings.

Background: S-C wired Semrush in as a fifth confidence-weighted backlink
source (0.90), inserted between DataForSEO (1.0) and Moz (0.85) in every
place source precedence is encoded (Source Detection, the per-factor
Backlink Health Score table, the Output Format source column, and the
Fallback cascade). This test guards two things at once:

1. The four pre-existing confidence values (Moz 0.85, Bing 0.70,
   Common Crawl 0.50, DataForSEO 1.0) remain byte-identical -- a typo or
   accidental overwrite while adding Semrush must fail this test.
2. Semrush at confidence 0.90 is now present, targeted at the specific
   table/section contexts where source precedence is encoded (not a bare
   "Semrush" and "0.90" appearing anywhere in the file, which would be too
   permissive and could pass even if the actual scoring table were wrong).

Tests run via `pytest tests/` and are wired into `.github/workflows/ci.yml`.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = REPO_ROOT / "skills" / "seo-backlinks" / "SKILL.md"


def _text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _section(text: str, start_marker: str, end_marker: str) -> str:
    """Return the slice of text between two markers (start inclusive)."""
    start_idx = text.index(start_marker)
    end_idx = text.index(end_marker, start_idx)
    return text[start_idx:end_idx]


def test_skill_md_exists():
    assert SKILL_MD.is_file(), f"Expected {SKILL_MD} to exist"


# ---------------------------------------------------------------------------
# 1. Backlink Health Score table: per-factor confidence rows.
# ---------------------------------------------------------------------------

def test_health_score_table_existing_confidence_values_unchanged():
    """The four pre-existing confidence values must appear verbatim, in the
    Backlink Health Score table context, unchanged by the Semrush addition.
    """
    table = _section(_text(), "## Backlink Health Score", "## Output Format")

    # DataForSEO 1.0 -- appears in every factor row.
    assert "DataForSEO > Semrush > Moz > CC in-degree | 1.0 / 0.90 / 0.85 / 0.50" in table
    # Moz 0.85 -- domain quality distribution row (Moz DA distribution).
    assert "DataForSEO > Semrush Authority Score > Moz DA distribution | 1.0 / 0.90 / 0.85" in table
    # Bing 0.70 -- anchor text naturalness row.
    assert "DataForSEO > Semrush > Moz > Bing anchors | 1.0 / 0.90 / 0.85 / 0.70" in table
    # Common Crawl (CC) 0.50 -- referring domain count row (same row as DataForSEO check above,
    # asserted again explicitly against the "CC" label + "0.50" value pairing).
    assert "CC in-degree | 1.0 / 0.90 / 0.85 / 0.50" in table
    # Follow/nofollow + Geographic relevance rows are untouched by the Semrush addition
    # (Semrush has no documented follow/nofollow or country-level backlink data in scope).
    assert "| Follow/nofollow ratio | 5% | DataForSEO > Bing details | 1.0 / 0.70 |" in table
    assert "| Geographic relevance | 10% | DataForSEO > Bing country | 1.0 / 0.70 |" in table


def test_health_score_table_semrush_added_at_correct_confidence():
    """Semrush must now be present in the Backlink Health Score table at
    confidence 0.90, ordered between DataForSEO (1.0) and Moz (0.85)."""
    table = _section(_text(), "## Backlink Health Score", "## Output Format")

    assert "Semrush" in table
    assert "0.90" in table
    # Ordering: DataForSEO 1.0 > Semrush 0.90 > Moz 0.85 > Bing 0.70 > Common Crawl 0.50.
    assert "DataForSEO > Semrush > Moz > CC in-degree | 1.0 / 0.90 / 0.85 / 0.50" in table
    assert "DataForSEO > Semrush Authority Score > Moz DA distribution | 1.0 / 0.90 / 0.85" in table
    assert "DataForSEO > Semrush > Moz > Bing anchors | 1.0 / 0.90 / 0.85 / 0.70" in table


# ---------------------------------------------------------------------------
# 2. Fallback cascade: numbered precedence list.
# ---------------------------------------------------------------------------

def test_fallback_cascade_existing_confidence_values_unchanged():
    cascade = _section(_text(), "**Fallback cascade:**", "## Pre-Delivery Review")

    assert "DataForSEO available? → Use as primary (confidence: 1.0)" in cascade
    assert "Moz configured? → Use for DA/PA/spam/anchors (confidence: 0.85)" in cascade
    assert "Bing configured? → Use for links/competitor comparison (confidence: 0.70)" in cascade
    assert "Common Crawl for domain-level metrics (confidence: 0.50)" in cascade


def test_fallback_cascade_semrush_added_at_correct_confidence():
    cascade = _section(_text(), "**Fallback cascade:**", "## Pre-Delivery Review")

    assert "Semrush available" in cascade
    assert "confidence: 0.90" in cascade
    # Semrush must sit between DataForSEO and Moz in the cascade order.
    dfs_idx = cascade.index("DataForSEO available?")
    semrush_idx = cascade.index("Semrush available")
    moz_idx = cascade.index("Moz configured?")
    bing_idx = cascade.index("Bing configured?")
    assert dfs_idx < semrush_idx < moz_idx < bing_idx


# ---------------------------------------------------------------------------
# 3. Source Detection: dual-namespace MCP tool-probe idiom present.
# ---------------------------------------------------------------------------

def test_source_detection_uses_dual_namespace_semrush_probe():
    detection = _section(_text(), "## Source Detection", "## Quick Reference")

    assert "mcp__semrush__*" in detection
    assert "mcp__claude_ai_Semrush__*" in detection
    assert "Semrush" in detection


# ---------------------------------------------------------------------------
# 4. Error Handling table: graceful-skip row for Semrush.
# ---------------------------------------------------------------------------

def test_error_handling_has_semrush_skip_row():
    error_table = _section(_text(), "## Error Handling", "**Fallback cascade:**")

    assert "Semrush not available" in error_table
    assert "no blocking error" in error_table


# ---------------------------------------------------------------------------
# 5. Total factor count is unchanged (Semrush is a new source, not an 8th factor).
# ---------------------------------------------------------------------------

def test_seven_factors_unchanged():
    table = _section(_text(), "## Backlink Health Score", "## Output Format")
    factor_rows = [
        line for line in table.splitlines()
        if line.strip().startswith("|") and "Weight" not in line and "---" not in line
    ]
    assert len(factor_rows) == 7, (
        f"Expected 7 scoring factor rows (Semrush is a new source, not an 8th factor), "
        f"found {len(factor_rows)}"
    )
    assert "X/7 factors scored" in table
