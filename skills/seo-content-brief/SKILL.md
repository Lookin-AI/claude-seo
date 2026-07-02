---
name: seo-content-brief
description: >
  Generate competitive SEO content briefs with per-section word counts,
  competitor scoring, keyword density guidance, and page-type templates.
  Supports both new page briefs and improve-existing-page briefs.
  Use when user says "content brief", "write a brief", "content outline",
  "blog brief", "service page brief", "brief for", "writing brief",
  "content plan", or "outline for".
user-invocable: true
argument-hint: "[url-or-keyword] [page-type]"
license: MIT
metadata:
  author: puneetindersingh
  original_author: puneetindersingh
  version: "1.0.0"
  category: seo
---

# SEO Content Brief Generator

Generate research-backed content briefs that help writers produce pages capable of outranking current top results. Briefs include competitor analysis with gap scoring, per-section word count breakdowns, keyword placement rules, and page-type-specific templates.

## Process

### 1. Determine Brief Mode

**Improve mode** (existing page URL provided):
- Fetch the existing page content and structure
- Identify what is already strong (keep it)
- Identify missing, thin, or outdated sections
- Distinguish "keep/strengthen" vs "add new" sections in the outline
- Do not recommend a full rewrite when targeted improvements will win

**New page mode** (keyword or topic provided, no existing page):
- Use the target site's homepage or sitemap for business context only
- Build the brief from scratch for a new page
- Focus on competitive gaps the new page can fill

### 2. Fetch Context

- Fetch the target URL or homepage to understand the business
- Fetch the sitemap to discover all existing pages, categories, and services
- This context is critical for the Website Relevance Rule (see below)

### 3. Analyse SERPs

- Identify the top 5 ranking pages for the target keyword
- Filter out non-competitors (Wikipedia, Reddit, Pinterest, Amazon, YouTube, government sites, SEO tool pages, job boards, directories, news aggregators, social platforms). See `references/excluded-domains.md` for the full list.
- Score each real competitor: Depth (1-10), Formatting (1-10), SEO (1-10), UX (1-10)
- Identify three gap types:
  - **Topic gaps:** subtopics competitors miss entirely
  - **Depth gaps:** topics covered but shallow
  - **Quality gaps:** outdated info, no expert perspective, poor formatting
- Calculate gap priority: `Impact x Competitive Advantage / Effort`

### 4. Classify Search Intent

- **Informational:** user wants to learn (guides, how-tos, definitions)
- **Commercial:** user is researching before buying (comparisons, reviews, "best X")
- **Transactional:** user is ready to act (buy, book, enquire, sign up)
- **Navigational:** user is looking for a specific site or page

Identify what SERP format Google rewards for this query: long-form guide, listicle, comparison table, landing page, FAQ, video, local pack.

### 5. Build the Brief

Apply the page-type template from `references/page-type-templates.md`, then customise based on competitor gaps and search intent.

## Critical Rules

### Website Relevance Rule

Every heading, subtopic, keyword, and FAQ you suggest MUST be something the target website can credibly write about based on its actual services or products.

- Read the site's homepage and sitemap to understand what it does
- Do not borrow competitor structure if those sections cover things this site does not offer
- Before each suggestion, ask: "Can this website actually deliver on this content?" If no, remove it.

### Site Structure Coverage Rule

When briefing a hub, overview, category, or "types of" page:
- The outline MUST reference every relevant product category, service, or sub-page that exists on the site
- Do not invent categories that don't exist, do not leave out categories that do exist
- Each category should appear as its own section with an internal link suggestion
- This ensures the page acts as a proper hub linking to all child pages

For non-hub pages (single service page, blog post), use site structure to suggest relevant internal links but do not force every category into the outline.

### Output Language Rules

- Never mention researcher names, framework names, or tool names in the output (no "Ben Goodey method", "Frase.io formula", "Princeton GEO", "Clearscope", "Backlinko")
- These are internal thinking tools only. The output must read as plain, professional advice.
- Write for a business owner or content writer, not an SEO academic

## Keyword Density and Placement

Read `references/keyword-density.md` for the full rules. Summary:

**Primary keyword density:** 0.5% to 2.0% of total word count.
- Above 2% requires review. Above 3% risks keyword stuffing penalties.
- First 1-2 mentions carry the most SEO weight. Diminishing returns after.
- For a 1,000-word article at 1-2%: roughly 10-20 total appearances including headings, body, and alt text.

**Primary keyword MUST appear in:**
1. Title tag (near the front)
2. H1 tag (near the front)
3. URL slug
4. Meta description
5. First paragraph / first 100 words
6. At least one image alt text

**Primary keyword does NOT need to appear in:**
- Every H2 or H3 (subtopics carry context naturally if H1 covers it)
- Every paragraph or section

**Secondary keywords:**
- 5-8 closely related supporting terms distributed through body content
- 10-15 broader semantic terms covering related concepts
- Use in H2-H6 subheadings where natural
- Synonyms improve readability and do NOT count toward keyword density

**Per-section keyword guidance:** For each section in the outline, specify:
- Which keyword (primary or secondary) belongs in the heading
- Whether the body should include the primary keyword or a variation
- Example: "Use secondary keyword 'structural drafting services' in H2. Body: mention primary keyword once."

**Distribution:** Spread the primary keyword evenly. Do not front-load or cluster in one section.

## Meta Tag Rules

**Title tag:**
- 50-60 characters (never under 50, never over 60)
- Primary keyword first, brand name last
- Separate brand with a pipe or dash (match the site's existing pattern)
- Lead with outcomes, numbers, or specifics when possible

**Meta description:**
- 130-150 characters (never under 130, never over 150)
- Active voice, expand on the title with USPs and specifics
- End with a call to action
- No brand name at the end (it's already in the title)
- No quotes (Google truncates at quotes)

## Information Gain (non-negotiable)

Every brief must specify EXACTLY what new value this content adds that no current ranking page provides. Must be specific:
- Proprietary data or original research
- Case studies with real outcomes
- Expert quotes or first-hand experience
- Original synthesis or unique framework
- NOT "more detail" or "better formatting"

## E-E-A-T Requirements

List the exact trust signals this content needs:
- Author credentials and bio relevant to the topic
- Expert quotes or citations from authoritative sources
- Cited studies, data, or statistics with dates
- Last updated date
- Especially critical for YMYL topics (health, finance, legal, safety)

## Internal Linking

- Suggest 3-5 specific internal link opportunities with anchor text
- Specify whether the page is a hub (links out to cluster pages) or spoke (links to pillar page)
- Use the site structure from the sitemap to find real link targets

## Output Format

Always output in this exact structure:

```
## Content Brief: [Primary Keyword]

### Search Intent
[Intent type, SERP format rewarded, target audience and knowledge level. 3-4 lines.]

### Competitor Analysis
| # | URL | Key H2 Sections | Est. Words | Score | Main Gap |
|---|-----|-----------------|------------|-------|----------|
| 1 | ... | ...             | ...        | X/40  | ...      |

### Content Gaps and Opportunities
[Bullet list: topic gaps, depth gaps, quality gaps with specifics]

### Winning Outline

**H1:** [H1 with primary keyword]
**URL Slug:** /[slug]
**Target Word Count:** ~[X] words (competitor avg: ~[X] words)

[Full H2/H3 outline with:
- Word count per section
- Content format notes (bullet list, table, definition box, etc.)
- Featured Snippet targets marked with "FS target"
- Per-section keyword guidance]

### Recommended Meta Tags

**Title**
[title, 60 chars max]

**Meta Description**
[description, 150 chars max]

### Unique Angle and Information Gain
[Specific paragraph: what exact new value this piece adds]

### E-E-A-T Requirements
[Bullet list of exact trust signals needed]

### Internal Linking Opportunities
[3-5 suggestions with anchor text and target URL]
```

## Outline-Only Mode

When the user asks for "just an outline" or "content outline" instead of a full brief, skip the Competitor Analysis table, Content Gaps section, Information Gain section, and E-E-A-T section. Output only:

```
## Content Outline: [Primary Keyword]

**H1:** [H1 with primary keyword]
**URL Slug:** /[slug]
**Target Word Count:** ~[X] words (competitor avg: ~[X] words)

[Full H2/H3 outline with word counts, format notes, FS targets, keyword guidance, and a 1-2 sentence writing note per section]
```

## History Persistence (story B2, seo-S-40)

After delivering the brief (full mode or outline-only mode), persist a
`content` entry to the `seo-history` data repo via `scripts/history_write.py`
(the same script `/seo audit` uses, story B0). This is a **BLOCKING GATE,
non-fatal to output**: a persistence failure must never swallow, delay, or
block the brief you just produced.

### Why this matters: the cross-fork addressing key

This entry is how `claude-blog` (story B3 -- a different repo that cannot
read this skill or import this script) will later find this exact brief
when the article gets published, to transition it from `state: "brief"` to
`state: "pubblicato"`. B3 finds it by globbing
`sites/<domain>/content/*.json` and matching on the `slug` field -- it
cannot reconstruct the filename, because the filename embeds today's date
and B3 won't know it. So the `slug` you write here MUST be reproducible by
B3 from the title/topic alone, using the identical deterministic rule.

**The full contract (addressing key + slug rule + rationale for where it
lives) is documented in `seo-history/docs/addressing-key.md`** -- the data
repo both `claude-seo` and `claude-blog` already read and write, chosen
specifically so the rule lives in exactly one place instead of being copied
into two forks' skill prose and drifting. Do not restate or reinvent the
rule here; that file is canonical.

### Computing the slug

Do NOT hand-derive the slug from prose rules. Call the canonical helper:

```
python3 scripts/history_write.py --slugify "<the exact title/H1 you used>"
```

This prints the slug and exits 0. Use the H1 / primary-keyword-based title
you put in the brief's `## Content Brief: [Primary Keyword]` (or `##
Content Outline: [Primary Keyword]`) heading as the input text, so the slug
is derivable later from the published article's own title.

### Building the payload

Assemble ONE JSON object (write it to a tmp file):
- `site`: the bare domain of the site this brief is for -- the domain of
  the target URL (improve mode) or the homepage/domain fetched for context
  (new-page mode); strip scheme/path and a leading `www.`. Must equal the
  `--domain` value passed to the CLI.
- `date`: today, `YYYY-MM-DD`
- `slug`: the output of `--slugify` above (already normalized -- do not
  re-slugify or edit it)
- `content_type`: `"brief"`
- `state`: `"brief"`
- `title`: the same title/H1 text you passed to `--slugify`
- `target_keyword` (optional): the primary keyword, if distinct from the title
- `audit_id` (optional): only if this brief was explicitly requested as a
  follow-up to a specific prior `/seo audit` run and you have its
  `audit_id` -- omit otherwise, never invent one
- `markdown_report`: the full brief or outline exactly as delivered to the
  user, as one string (the `## Content Brief: ...` or `## Content Outline:
  ...` block, verbatim)

Do not set `published_url` or `word_count` -- those belong to the
`pubblicato` transition B3 performs later, not to a brief.

### Invoking history_write.py (BLOCKING GATE)

```
python3 scripts/history_write.py --type content --domain <domain> --payload <tmpfile> --json
```

- Exit `0` -> tell the user `✓ Brief storicizzato`.
- Non-zero (`1` or `2`) -> the write did NOT happen (fail-closed: schema
  violation, secret detected, or clone/auth problem -- nothing is
  committed). Show `⚠️ Brief NON persistito: <reason from stderr>` -- but
  STILL deliver the full brief/outline produced above, unchanged.

## DataForSEO Integration (Optional)

If DataForSEO MCP tools are available, use `serp_google_organic_live_advanced` for real SERP data and competitor analysis, `kw_data_google_ads_search_volume` for keyword volume, `dataforseo_labs_bulk_keyword_difficulty` for difficulty scores, `dataforseo_labs_search_intent` for intent classification, and `on_page_content_parsing_live` for competitor content extraction.

## Ahrefs Integration (Optional)

If Ahrefs MCP tools are available, use `keywords-explorer-overview` for keyword volume and difficulty, `serp-overview` for SERP analysis, `site-explorer-organic-keywords` for existing keyword rankings, and `site-explorer-top-pages` for competitor page performance.

## Error Handling

| Scenario | Action |
|----------|--------|
| Target URL unreachable | Report the error. Do not guess page content. Ask the user to verify the URL. |
| No competitors found after filtering | Broaden the search to include partial-match competitors. Note the thin competitive landscape in the brief. |
| Sitemap not found | Proceed without site structure context. Note that internal linking suggestions may be incomplete. |
| Page type not specified | Auto-detect from the keyword intent and SERP format. State the detected type in the brief. |
| Target word count not specified | Use competitor average as the baseline. Note this in the outline. |
