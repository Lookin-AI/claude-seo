---
name: seo-runbooks
description: "Run the full in-session SEO runbook (audit swarm + keyword pull + competitor pull) across every site tracked in the SEO data repo, once per site, saving results per-site. Defaults-first weekly war-room run: no flags required. Use when user says runbooks, run the runbook, weekly SEO run, war room, batch audit all sites, or /seo runbooks."
user-invocable: true
argument-hint: "[domain]"
license: MIT
metadata:
  author: Lookin-AI
  version: "2.2.0"
  category: seo
---

# SEO Runbooks: Multi-Site In-Session Batch

**Invocation:** `/seo runbooks [<domain>]`

Runs the SAME in-session subagent swarm `/seo audit` uses, once per site
listed in the SEO data repo, then enriches each site with a keyword pull and
a competitor pull, and persists everything per-site. This is the sensible
weekly run: **defaults-first, no required flags ever**. It runs entirely
inside the current Claude Code session (interactive subagents) -- it is NOT a
headless `claude -p` orchestrator and must never shell out to one.

The optional `<domain>` argument filters the run to a single site. With no
argument, ALL tracked sites are processed -- that is the default.

---

## Command

| Command | What it does |
|---------|-------------|
| `/seo runbooks` | Process EVERY site in `sites.yaml` (default weekly war-room run) |
| `/seo runbooks <domain>` | Process only `<domain>` (must be present in `sites.yaml`) |

There are no other flags. Do not invent any.

---

## Step 1 -- Resolve the SEO data repo and site list

Resolve the data-repo path `P` with this precedence (stop at the first hit):

1. `$SEO_HISTORY_PATH` env var, if set and non-empty.
2. The `path` configured in `~/.config/claude-seo/history.json`, if that file
   exists and declares one.
3. Default: `/Users/massimoferri/Documents/coding/seo-data`.

Read `P/sites.yaml`. Parse the `sites:` list, supporting BOTH item forms:

- mapping form: `- domain: example.com` (plus optional `business_type`,
  `gsc_property` hints -- carry them through to the audit if present)
- bare scalar form: `- example.com`

Collect the domain of every item. If `<domain>` was passed, filter to just
that one site; if it is not in `sites.yaml`, tell the user and stop (do not
audit an untracked domain). If `sites.yaml` is missing or has zero sites,
report that clearly and stop.

---

## Step 2 -- Per-site loop (the runbook)

For EACH selected site, in `sites.yaml` order, run the three data sources
below **in-session**. Treat every site and every source independently: wrap
each in its own error boundary (see "Robustness"). Use today's date as
`<date>` = `YYYY-MM-DD` for all output filenames.

### 2a. Full audit (the swarm)

Run the SAME machinery as `/seo audit` for `https://<domain>`: load and
execute `skills/seo-audit/SKILL.md` end to end -- detect business type, crawl,
delegate to the parallel specialist subagents (8 always + conditional ones),
aggregate the SEO Health Score (0-100), and produce the
`{domain}-audit/audit-data.json` envelope. This is real in-session subagent
delegation, identical to a normal `/seo audit`; do not reimplement or shortcut
it.

Then persist the audit to history, exactly as the `/seo audit` "History
Persistence" flow does (see `skills/seo/SKILL.md` -> "History Persistence").
Build ONE JSON payload from the audit envelope (write it to a tmp file):

- `audit_id`: `<date>-<domain>-<short-time-or-hash>` (unique per run)
- `site`: the bare `<domain>` (must equal `--domain`)
- `date`: `<date>`
- `health_score`: the 0-100 weighted aggregate
- `categories`: exactly the 7 canonical categories with their weights
  (`Technical SEO`=22, `Content Quality`=23, `On-Page SEO`=20,
  `Schema / Structured Data`=10, `Performance (CWV)`=10,
  `AI Search Readiness`=10, `Images`=5), weights summing to 100
- `issue_counts`: `{critical, high, medium, low}`
- `data_sources` (optional): omit unless a paid source (Semrush / DataForSEO)
  was actually used this run
- `markdown_report`: the full human-readable audit report as one string

Then call the single write path, pinning it to the SAME repo `P` so the audit
lands next to `sites.yaml`:

```
python scripts/history_write.py --type audit --domain <domain> --payload <tmpfile> --history-path P --json
```

Exit `0` -> audit stored. Non-zero (`1`/`2`) -> the write did NOT happen
(fail-closed); record the stderr reason for the summary and keep going. Never
let a persistence failure abort the site or the run.

### 2b. Keyword pull

Pull the site's ranking / opportunity keywords using whichever live source is
available in-session (prefer Semrush, fall back to DataForSEO; skip cleanly if
neither is present):

- **Semrush** (`mcp__semrush__*` OR `mcp__claude_ai_Semrush__*`): run the
  `organic_research` -> `domain_organic` report (organic keywords the domain
  ranks for) via `discovery -> get_report_schema -> execute_report`, as
  `skills/seo-semrush/SKILL.md` describes. Default `database` to the site's
  market (`it` for `.it`/Italian sites, else `us`).
- **DataForSEO** (`lookin-dataforseo`, i.e.
  `mcp__claude_ai_MCP_Lookin_Server__lookin-dataforseo`, or a locally
  installed DataForSEO MCP tool): use the ranked-keywords / keyword-ideas path
  from `skills/seo-dataforseo/SKILL.md` (`/seo dataforseo ranked <domain>`).

Write the result to `P/sites/<domain>/keywords/<date>-keywords.json` (create
the `keywords/` folder if missing; do NOT touch the sibling `keywords/universe/`
subtree, which is owned by a separate pipeline). Shape:

```json
{
  "schema_version": "1.0",
  "site": "<domain>",
  "date": "<date>",
  "source": "semrush|dataforseo",
  "keyword_count": 0,
  "keywords": []
}
```

### 2c. Competitor pull

Pull the site's organic competitors using the same source preference:

- **Semrush**: the Competitor / Keyword Gap toolkit -- top organic competitor
  domains by keyword overlap (`/seo semrush competitors <domain>` pattern).
- **DataForSEO**: the competitors endpoint (`/seo dataforseo competitors
  <domain>` pattern).

Write the result to `P/sites/<domain>/competitors/<date>-competitors.json`
(create the `competitors/` folder if missing). Shape:

```json
{
  "schema_version": "1.0",
  "site": "<domain>",
  "date": "<date>",
  "source": "semrush|dataforseo",
  "competitor_count": 0,
  "competitors": []
}
```

---

## Robustness (never abort the whole run)

- One site fails -> log a warning, record it, move to the next site.
- One source (audit / keywords / competitors) fails for a site -> log a
  warning, record it, still run the other two sources for that site.
- A history write fails -> record the reason, keep the audit output, continue.
- A missing MCP source (no Semrush and no DataForSEO) is NOT an error: mark
  that source `skipped (no live data source)` and continue.

Nothing here is fatal to the batch. The run always reaches Step 3.

---

## Step 3 -- War-room summary

After the loop, print ONE concise table the user can scan at a glance -- a
mini war-room status. One row per site:

| Site | Health | Keywords | Competitors | Saved | Errors |
|------|--------|----------|-------------|-------|--------|
| example.com | 78 | 830 | 6 | audit+kw+comp | - |
| other.it | -- | -- | 4 | comp only | audit: crawl timeout; kw: no source |

Columns: domain; health score (or `--` if the audit failed); # keywords
pulled; # competitors pulled; what was saved (audit / kw / comp); any
per-source errors. Close with a one-line tally: N sites processed, M fully
successful, K with at least one warning.

---

## Error Handling

| Scenario | Action |
|----------|--------|
| `sites.yaml` missing or empty at `P` | Report the resolved path `P` and that no sites were found. Stop. |
| `<domain>` arg not in `sites.yaml` | Tell the user it is untracked; do not audit it. Stop. |
| One site's audit fails | Warn, record, continue with the next site. |
| One source fails for a site | Warn, record, run the remaining sources for that site. |
| No Semrush and no DataForSEO in-session | Mark keyword/competitor pulls `skipped`; still run and persist audits. |
| `history_write.py` exits non-zero | Record `<reason from stderr>` in the summary; keep the audit output; continue. |
