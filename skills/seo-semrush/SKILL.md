---
name: seo-semrush
description: >
  Semrush domain analytics, keyword research, backlink/Authority Score, and
  competitor/keyword-gap analysis via the Semrush MCP server. Domain overview
  (authority score, traffic estimate, keyword counts), organic and paid
  keyword rankings, keyword volume/difficulty/CPC research, backlink profile
  and Authority Score, and multi-domain keyword gap analysis (2-5 domains).
  Requires the Semrush MCP server connected in-session (no local API key).
  Use when user says "semrush", "authority score", "domain overview",
  "keyword gap", "organic keywords", "keyword difficulty", "semrush
  backlinks", or "domain vs domain".
user-invocable: true
argument-hint: "[command] [domain or keyword]"
license: MIT
compatibility: "Requires Semrush MCP connected in-session"
metadata:
  author: Lookin-AI
  version: "2.2.0"
  category: seo
---

# Semrush: Domain Analytics, Keywords, Backlinks (Extension-Grade Core Skill)

Live Semrush data via the Semrush MCP server's `mcp__semrush__*` /
`mcp__claude_ai_Semrush__*` tools. Covers domain analytics, keyword research,
backlink/Authority Score, and competitor/keyword-gap analysis. Position
Tracking and Site Audit report families are **out of scope** for this skill
(deferred to a future story) — do not route to `tracking_research` or
`siteaudit_research`.

## Prerequisites / Source Detection

This skill does **not** use a gateway and does **not** read any local secret.
Semrush authentication lives entirely inside the Semrush MCP server; this
skill only calls the MCP tools that server exposes.

**Before every command**, probe for tool presence on **both** namespaces:

- `mcp__semrush__*` (direct MCP install), OR
- `mcp__claude_ai_Semrush__*` (Claude.ai connector install)

If any Semrush discovery tool (e.g. `overview_research`, `organic_research`,
`keyword_research`, `backlink_research`, `get_report_schema`,
`execute_report`) is present under **either** namespace, treat Semrush as
available. If neither namespace exposes a Semrush tool, **skip silently** —
do not error, do not prompt to install anything, just omit Semrush from the
output. Never call `mcp__claude_ai_MCP_Lookin_Server__*` or any `lookin-*`
tool for Semrush data; that gateway is out of scope for this skill entirely.

## The Semrush Flow (read this before writing any command handler)

Every Semrush report follows the same 3-step flow. There is no flat
per-tool call like DataForSEO's individual endpoints — Semrush is
report-oriented:

1. **Discovery** — call the relevant toolkit discovery tool
   (`overview_research`, `organic_research`, `keyword_research`, or
   `backlink_research`). Each takes no arguments and returns the list of
   `report` names available in that toolkit, with per-line/per-request
   pricing in Semrush API units.
2. **`get_report_schema(report=<name>)`** — returns the exact parameters
   for that report (required vs optional, allowed values, defaults). Do
   **not** guess parameter names or values from this document — schemas can
   change. **Always re-verify params via `get_report_schema` immediately
   before calling `execute_report`**, even if you called it earlier in the
   same session.
3. **`execute_report(report=<name>, params={...})`** — the metered call
   that actually fetches data. This is the only step that costs money; run
   the Cost guardrails workflow (below) around this step, not around
   discovery or schema calls.

`discovery → get_report_schema → execute_report` is the whole pattern for
every command family below.

## Quick Reference

| Command | Report family | What it does |
|---------|---------------|--------------|
| `/seo semrush overview <domain>` | Domain Analytics | Authority score, keyword counts, traffic estimate (current snapshot + historical trend) |
| `/seo semrush organic <domain>` | Domain Analytics | Organic keyword rankings for a domain |
| `/seo semrush paid <domain>` | Domain Analytics | Paid/PPC keyword rankings for a domain |
| `/seo semrush compare <domain1> <domain2>` | Domain Analytics | Domain-vs-domain: two `domain_rank` snapshots diffed client-side |
| `/seo semrush keywords <keyword>` | Keyword Research | Search volume, CPC, competition, keyword difficulty for one or more keywords |
| `/seo semrush serp <keyword>` | Keyword Research | Who ranks for a keyword (SERP composition) and available SERP features |
| `/seo semrush backlinks <domain>` | Backlink / Authority Score | Backlink overview, referring domains, anchor text, Authority Score |
| `/seo semrush gap <domain1> <domain2> [domain3...]` | Competitor / Keyword Gap | Keyword gap analysis across 2-5 domains |
| `/seo semrush competitors <domain>` | Competitor / Keyword Gap | Top organic competitor domains by keyword overlap |

---

## Domain Analytics (organic/paid keywords, traffic, domain-vs-domain)

### `/seo semrush overview <domain>`

1. **Discovery**: `overview_research()` -> reports include `domain_rank`
   (current snapshot: organic/paid keyword counts, traffic estimate,
   authority score; 10 units/line) and `domain_rank_history` (monthly
   trend; 10 units/line).
2. **Schema**: `get_report_schema(report="domain_rank")` -> required
   `domain`, required `database` (2-letter market code, default to `us`
   unless the user specifies a market).
3. **Execute**: `execute_report(report="domain_rank", params={domain, database})`.

### `/seo semrush organic <domain>` / `/seo semrush paid <domain>`

1. **Discovery**: `organic_research()` -> `domain_organic` (organic
   keywords a domain ranks for, 10 units/line) for the `organic` command;
   `domain_adwords` (paid keywords, 20 units/line) for the `paid` command.
2. **Schema**: `get_report_schema(report="domain_organic")` (or
   `domain_adwords`) -> required `domain`, required `database`. Optional
   `display_limit` (recommend 30-50 unless the user asks for more),
   `display_sort`, `display_filter`.
3. **Execute**: `execute_report(...)`.

### `/seo semrush compare <domain1> <domain2>`

There is no single "domain vs domain" report in the Semrush toolkits
probed here — build it client-side: run `domain_rank` for each domain
(same `database`) and diff the two result rows (authority score, organic
traffic estimate, organic/paid keyword counts). Note this explicitly in
the report so the user understands it is two calls, not one.

---

## Keyword Research (volume, KD, intent, SERP features)

### `/seo semrush keywords <keyword>`

1. **Discovery**: `keyword_research()` -> `phrase_this` (single keyword:
   volume, CPC, competition, trend, 10 units/line), `phrase_these` (batch,
   semicolon-separated, 10 units/line), `phrase_kdi` (keyword difficulty
   index, 50 units/line), `phrase_related` (semantically related terms, 40
   units/line), `phrase_questions` (question-format keywords, 40
   units/line).
2. **Schema**: `get_report_schema(report="phrase_this")` -> required
   `phrase`, required `database`.
3. **Execute**: `execute_report(...)`.

**Intent note**: Semrush's `keyword_research` toolkit has **no dedicated
intent-classification report** — do not claim one. Infer intent
heuristically: question-format keywords (`phrase_questions`) skew
informational; high-CPC/competition keywords (`phrase_this` /
`phrase_adwords`) skew commercial/transactional. Report intent as an
inference with a confidence caveat, not as a Semrush-native field.

### `/seo semrush serp <keyword>`

1. **Discovery**: `keyword_research()` -> `phrase_organic` (who ranks for
   a keyword: domains, positions, traffic share, URL; 10 units/line).
2. **Schema**: `get_report_schema(report="phrase_organic")` -> required
   `phrase`, required `database`.
3. **Execute**: `execute_report(...)`. SERP feature presence, where
   returned, comes from the report's own columns — re-verify which
   columns are available via the schema call rather than assuming a fixed
   set.

---

## Backlink / Authority Score

### `/seo semrush backlinks <domain>`

1. **Discovery**: `backlink_research()` -> `backlinks_overview` (total
   links, referring domains, Authority Score, monthly changes; 40
   units/request — start here), `backlinks_refdomains` (40 units/line),
   `backlinks_anchors` (anchor text distribution, 40 units/line),
   `backlinks_ascore_profile` (Authority Score distribution, 100
   units/request).
2. **Schema**: `get_report_schema(report="backlinks_overview")` ->
   required `target`, required `target_type` (one of `root_domain`,
   `domain`, `url`).
3. **Execute**: `execute_report(...)`.

**Single-call-per-audit note**: during `/seo audit`, backlink data via
Semrush is **owned by `seo-backlinks`** (multi-source confidence-weighted
merge — a later story wires Semrush in as one of its sources). The
`seo-semrush` agent covers overview / keyword / competitor-gap only during
audits; it does **not** independently call `backlinks_overview` inside an
audit run, to avoid double-billing the same domain's backlink profile
through two code paths. Outside of `/seo audit` (a direct `/seo semrush
backlinks <domain>` invocation), this restriction does not apply.

---

## Competitor / Keyword Gap

### `/seo semrush gap <domain1> <domain2> [domain3...]`

1. **Discovery**: `organic_research()` -> `domain_domains` (keyword gap
   between 2-5 domains, 80 units/line).
2. **Schema**: `get_report_schema(report="domain_domains")` -> required
   `database`, required `domains` (URL-encoded `<sign>|<type>|<domain>`
   segments joined by `|`; e.g. `*|or|<domain1>|*|or|<domain2>` for shared
   keywords, `*|or|<domain1>|-|or|<domain2>` for keywords unique to
   domain1). **Always re-verify this encoding via `get_report_schema`
   before building the string** — it is easy to get the sign/type order
   wrong.
3. **Execute**: `execute_report(...)`.

### `/seo semrush competitors <domain>`

1. **Discovery**: `organic_research()` -> `domain_organic_organic` (top
   organic competitors by keyword overlap, 40 units/line).
2. **Schema**: `get_report_schema(report="domain_organic_organic")` ->
   required `domain`, required `database`.
3. **Execute**: `execute_report(...)`.

---

## Cost guardrails

Semrush `execute_report` calls are metered in Semrush API units and billed
against the account connected to the MCP server. Treat every
`execute_report` call the same way `seo-dataforseo` and `seo-ahrefs` treat
their metered calls:

**Before every `execute_report` call:**
```
python3 scripts/dataforseo_costs.py check semrush_execute_report --count N
```
Use `--count` for the number of result lines/rows you expect (most Semrush
reports bill per-line; a few bill per-request — see the per-report pricing
noted in each Discovery step above). For backlink-profile pulls, use
`semrush_backlink_research` instead:
```
python3 scripts/dataforseo_costs.py check semrush_backlink_research --count N
```

- `"status": "approved"` -> proceed with `execute_report`
- `"status": "needs_approval"` -> show the cost estimate and ask the user
  to confirm before calling `execute_report`
- `"status": "blocked"` -> do not call `execute_report`; tell the user the
  daily budget would be exceeded

**After every `execute_report` call completes**, log it:
```
python3 scripts/dataforseo_costs.py log semrush_execute_report <actual_cost>
```
(or `semrush_backlink_research` for backlink-profile pulls)

Discovery calls (`overview_research`, `organic_research`,
`keyword_research`, `backlink_research`) and `get_report_schema` are free —
do not run cost checks around them.

**Semrush is opt-in per audit**: during `/seo audit`, ask for one upfront
confirmation ("Include live Semrush data in this audit? It will call the
metered Semrush API.") rather than confirming per-command inside the audit
run.

## Source labeling

Every metric pulled from Semrush must be labeled in output as:

```
Semrush (live, confidence X.XX)
```

Use the confidence value defined by the skill/agent that is merging
Semrush into a multi-source report (e.g. `seo-backlinks`). If no merge
context applies (a direct `/seo semrush ...` call), label as `Semrush
(live)` without a confidence suffix.

## Error Handling

| Scenario | Action |
|----------|--------|
| `get_report_schema` fails or returns no parameters | Report that the schema fetch failed for that report name; do not guess parameters or call `execute_report` blind. Suggest re-running the discovery tool in case the report name is stale. |
| `execute_report` returns an empty result set | Report "no data found for `<domain/keyword>` in `<database>`" rather than treating it as an error. Suggest checking the domain spelling or trying a different `database` market code. |
| Invalid domain (malformed input, not a resolvable domain shape) | Report the validation error and ask the user to confirm the domain before retrying. Do not silently strip/rewrite the input. |
| Quota / rate limit exceeded (Semrush MCP server error) | Report the limit hit, do not retry automatically, and suggest waiting or checking the account's remaining API units. |
| Semrush MCP tools absent from both namespaces | Skip Semrush silently per Source Detection above — do not error, do not block the rest of the audit. |

## Cross-Skill Integration

- **seo-backlinks**: owns the multi-source confidence-weighted merge;
  Semrush's `backlinks_overview` / Authority Score is a candidate input
  source for a later story, not wired in by this skill.
- **seo-audit**: may spawn the `seo-semrush` agent (opt-in, see Cost
  guardrails) for domain overview / keyword / competitor-gap context;
  backlink data during audits stays with `seo-backlinks` per the
  single-call-per-audit note above.

## Not Covered (deferred)

Position Tracking (`tracking_research`) and Site Audit
(`siteaudit_research`) toolkits are **out of scope** for this skill. Do not
document, route to, or call those discovery tools from `seo-semrush`.
