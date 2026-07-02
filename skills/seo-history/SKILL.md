---
name: seo-history
description: >
  Log a manual or automated SEO intervention (a fix, a change, a completed
  action) as a structured entry in the seo-history data repo, linked back to
  the audit finding that motivated it. Use when user says "log intervention",
  "record this fix", "log-intervention", "mark as fixed", "register this
  change", "track this intervention", or wants to record that a specific
  finding from a prior audit was acted on.
user-invocable: true
argument-hint: "log-intervention <domain> \"<description>\" [--finding <ref>] [--no-link] [--status planned|completed|verified] [--category <category>]"
license: MIT
metadata:
  author: AgriciDaniel
  version: "2.2.0"
  category: seo
---

# SEO History: Intervention Logging (story B4, seo-S-42)

Records that a specific SEO fix/change happened, and -- unless explicitly
opted out -- links it to the audit **finding** that motivated it. This is
the write path for the `intervention` entry type in the `seo-history` data
repo (`Lookin-AI/seo-history`), via `scripts/history_write.py` (story B0,
the same script `/seo audit` and `/seo content-brief` use).

Unlike `audit` and `content` entries (auto-persisted after `/seo audit`,
`/seo page`, `/seo technical`, `/seo content`, `/seo schema`, `/seo geo`,
`/seo sxo`, and `/seo content-brief` produce their reports -- see
`skills/seo/SKILL.md` "History Persistence"), `log-intervention` is a
**manual, explicit write command**. Nothing else auto-triggers it.

---

## Commands

| Command | Purpose |
|---------|---------|
| `/seo log-intervention <domain> "<description>" [--finding <ref>] [--no-link] [--status ...] [--category ...]` | Record an intervention, linked to the audit finding that motivated it (unless `--no-link`) |

---

## Command: `log-intervention`

**Arguments:**

| Arg | Required | Notes |
|-----|----------|-------|
| `<domain>` | Yes | Bare domain (e.g. `example.com`), so the entry is written under `sites/<domain>/interventions/`. |
| `"<description>"` | Yes | Short human description of the intervention; quoted if it contains spaces. Drives the filename slug and the schema's `description` field. |
| `--finding <audit-file>#<finding-id>` | Conditional | The specific finding this intervention addresses, e.g. `2026-07-01-audit.json#3` or a short finding description string. Required unless `--no-link` is passed -- see "Linkage enforcement" below. |
| `--no-link` | Conditional | Explicit opt-out: this intervention is not tied to a specific audit finding. Required if `--finding` is omitted. |
| `--status planned\|completed\|verified` | No | Defaults to `completed` -- see "Default status" below. |
| `--category <one of the 7 SEO categories>` | No | `Technical SEO`, `Content Quality`, `On-Page SEO`, `Schema / Structured Data`, `Performance (CWV)`, `AI Search Readiness`, or `Images`. Omit if the intervention doesn't map cleanly to one. |

### Linkage enforcement (skill-layer business rule -- hard precondition)

The whole point of B4 is connecting interventions back to the finding that
justified them, so a finding link is **mandatory unless explicitly waived**:

- If the user's invocation includes `--finding <ref>` -> proceed, `finding_ref`
  is set on the payload.
- If the user's invocation includes `--no-link` -> proceed, `finding_ref` is
  omitted from the payload entirely (not written as `null` or `""` --
  omitted, since the schema field is optional).
- If **neither** is present -> **do NOT write anything**. Do not call
  `history_write.py`, do not guess a finding, do not silently fall back to
  `--no-link`. Ask the user: "Serve un riferimento alla finding che ha
  motivato questo intervento (`--finding <audit-file>#<finding-id>`), oppure
  conferma esplicitamente `--no-link` se questo intervento non deriva da una
  finding specifica di un audit."

This is enforced BEFORE calling `scripts/history_write.py` -- the script
itself does not know about `--finding`/`--no-link` (they are
`log-intervention`-specific CLI surface, not part of the generic payload
contract). For testability, the precondition itself is also expressed as a
small importable stdlib function, `check_intervention_linkage(finding_ref,
no_link)`, in `scripts/history_write.py` (raises `PayloadError` when neither
is present) -- call it (or replicate its exact logic) before assembling the
payload.

Note this is a *linkage* precondition, not a schema requirement:
`finding_ref` remains OPTIONAL in `seo-history/schema/intervention.schema.json`
itself (`additionalProperties: false`, but `finding_ref` is listed and not
`required`) -- the mandatory-unless-opted-out rule lives here, one layer up,
per the epic's plan.

### Default status: `completed`

`log-intervention` defaults `status` to `"completed"` because the command's
natural use is "I just did X, log it" (past tense: "record this fix",
"mark as fixed"). Pass `--status planned` explicitly to log work that is
scheduled but not yet done, or `--status verified` once a completed
intervention's effect has been separately confirmed (e.g. via a follow-up
`/seo drift compare` or `/seo audit`).

### Steps

1. Parse `<domain>` and `<description>` (both required -- if either is
   missing, ask the user for it; do not guess a domain or invent a
   description).
2. **Linkage enforcement** (see above) -- hard precondition before any
   write. Stop here with a question if neither `--finding` nor `--no-link`
   is present.
3. Resolve `--status` (default `completed`) and, if given, validate
   `--category` is one of the 7 canonical names (case-sensitive match);
   if it isn't, ask the user to pick one from the list or omit it.
4. Compute the slug via the canonical helper (do not hand-derive it):
   ```
   python3 scripts/history_write.py --slugify "<description>"
   ```
5. If `--finding` was given, derive `audit_id` when the reference follows
   the `<audit-file>#<finding-id>` pattern: take the basename of the part
   before `#`, strip its extension (e.g. `2026-07-01-audit.json#3` ->
   `audit_id: "2026-07-01-audit"`). If `--finding` is a freeform string
   with no recognizable file component (e.g. a short finding description),
   omit `audit_id` and keep `finding_ref` as-is.
6. Build ONE JSON payload object (write it to a tmp file):
   - `site`: `<domain>`
   - `date`: today, `YYYY-MM-DD`
   - `slug`: the schema's own required `slug` field -- reuse the output of
     step 4 (same slugify rule `history_write.py` will independently apply
     to `description` for the filename; using the identical value keeps the
     JSON's `slug` field and the filename consistent)
   - `description`: `<description>` verbatim
   - `status`: from step 3
   - `type`: `"manual"`
   - `category` (optional): from step 3, if provided
   - `finding_ref` (omitted entirely when `--no-link`): the `--finding` value
   - `audit_id` (optional): from step 5, if derivable
   - `performed_by` (optional): the user's identity if known from context
     (e.g. git config, session context) -- omit rather than guess
   - `markdown_report`: a short human-readable markdown report -- what was
     done, which finding it addresses (or that it's intentionally
     unlinked), when, and by whom. Template:
     ```markdown
     # Intervento: <description>

     **Sito:** <domain>
     **Data:** <date>
     **Stato:** <status>
     **Finding collegata:** <finding_ref, oppure "Nessuna (--no-link)">
     **Categoria:** <category, se presente>

     ## Cosa e' stato fatto

     <1-3 frasi che descrivono l'intervento>
     ```
7. Invoke the single write path (BLOCKING GATE on the write itself, but the
   linkage check in step 2 already happened before this):
   ```
   python scripts/history_write.py --type intervention --domain <domain> --payload <tmpfile> --json
   ```

**Output:**
- Exit `0` -> tell the user `✓ Intervento registrato in seo-history`, and
  show the written `.md`/`.json` paths from the JSON output.
- Non-zero (`1` or `2`) -> the write did NOT happen (fail-closed: schema
  violation, secret detected, or clone/auth problem -- nothing is
  committed). Show `⚠️ Intervento NON registrato: <reason from stderr>`.
  This must never be silently swallowed -- always surface the reason.

`seo-history` is auto-cloned on first use (a sibling directory of this fork
by default). Override the location with the `SEO_HISTORY_PATH` env var.

---

## Cross-Skill Integration

| Situation | Recommendation |
|-----------|-----------------|
| User just ran `/seo audit` and wants to track a fix for one of its findings | Reference the audit's own file as `--finding <date>-audit.json#<n>` (the finding's position/id within `top_findings`, or a short quote of it). |
| User wants to verify a previously logged intervention actually worked | Run `/seo drift compare <url>` or a fresh `/seo audit`, then re-log with `--status verified` and the same `--finding` (or a fresh one) if the effect needs its own record. |
| An intervention doesn't trace back to any specific audit finding (e.g. a proactive change) | Use `--no-link` explicitly -- do not fabricate a `--finding` value. |

---

## Error Handling

| Scenario | Action |
|----------|--------|
| Neither `--finding` nor `--no-link` given | Do not write. Ask the user for a finding reference or an explicit `--no-link`. |
| `<domain>` or `<description>` missing | Ask the user to supply it. Do not guess. |
| `--category` not one of the 7 canonical names | Ask the user to pick one from the list, or omit `--category`. |
| `history_write.py` exits non-zero | Show `⚠️ Intervento NON registrato: <reason from stderr>`. Never silently drop the failure. |
| `git`/`gh`/`gh auth` missing or unauthenticated | Surface the setup instructions from the error message verbatim (same fail-closed gate as B0/B1/B2). |
| seo-history clone missing/unreachable | Same as above -- `history_clone.py`'s preflight hard-fails with setup instructions; surface them. |
