"""Guard rails for the Semrush COST_TABLE additions in dataforseo_costs.py.

Semrush is a Pattern-A integration: it is called only via its own MCP
tools (mcp__semrush__* / mcp__claude_ai_Semrush__*), never through a
gateway, and never with a local API key. The cost-tracker module is
shared/generic across vendors (see seo-ahrefs's Cost guardrails section),
so Semrush's metered `execute_report` / `backlink_research` calls get
their own COST_TABLE keys rather than a new script.

This test asserts:
1. The new Semrush keys exist with a positive placeholder cost.
2. A handful of pre-existing DataForSEO keys are still present with their
   original values unchanged (typo/overwrite guard -- the contract for
   this change is additive-only, appended at the end of COST_TABLE).
"""

from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import dataforseo_costs  # noqa: E402


def test_semrush_keys_present_with_positive_cost():
    for key in ("semrush_execute_report", "semrush_backlink_research"):
        assert key in dataforseo_costs.COST_TABLE, (
            f"Expected '{key}' in COST_TABLE for the Semrush integration."
        )
        cost = dataforseo_costs.COST_TABLE[key]
        assert isinstance(cost, (int, float)), f"{key} cost must be numeric"
        assert cost > 0, f"{key} cost must be a positive placeholder"


def test_existing_dataforseo_keys_unchanged():
    """Typo guard: adding Semrush keys must not rename/edit existing rows."""
    expected_unchanged = {
        "serp_organic_live_advanced": 0.002,
        "kw_data_google_ads_search_volume": 0.05,
        "backlinks_summary": 0.02,
        "on_page_lighthouse": 0.02,
        "domain_analytics_whois_overview": 0.005,
        "ai_optimization_chat_gpt_scraper": 0.05,
        "merchant_google_products_search": 0.02,
    }
    for key, expected_cost in expected_unchanged.items():
        assert key in dataforseo_costs.COST_TABLE, (
            f"Pre-existing DataForSEO key '{key}' is missing from COST_TABLE."
        )
        assert dataforseo_costs.COST_TABLE[key] == expected_cost, (
            f"Pre-existing DataForSEO key '{key}' changed value: "
            f"expected {expected_cost}, got {dataforseo_costs.COST_TABLE[key]}."
        )


def test_semrush_keys_do_not_collide_with_dataforseo_namespace():
    """Semrush keys are additive and distinctly named -- no accidental overwrite."""
    dataforseo_prefixes = (
        "serp_", "kw_data_", "dataforseo_labs_", "on_page_", "backlinks_",
        "domain_analytics_", "content_analysis_", "business_data_",
        "ai_optimization_", "ai_opt_", "merchant_",
    )
    for key in ("semrush_execute_report", "semrush_backlink_research"):
        assert key.startswith("semrush_"), f"{key} must use the semrush_ prefix"
        assert not key.startswith(dataforseo_prefixes), (
            f"{key} unexpectedly collides with a DataForSEO key prefix"
        )
