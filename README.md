# Research Feed — Krishnagopal Halder

A self-updating **research-interest feed**. Pulls the latest publications from
the **Web of Science API** and the **arXiv API** every Monday via **GitHub
Actions** and serves them as a static site through **GitHub Pages**.

This site is **not** an author page — it does not list Krishnagopal's own
papers. It surfaces new work in his configured **research topics**,
**keywords**, **journals of interest**, and **arXiv preprint queries**, so he
can stay on top of the field.

The site supports both **dark and light themes**, with a toggle in the header.

```
/
├── query_config.yml            ← ✏️  EDIT to change your search interests
├── publishers_config.yml       ← ✏️  EDIT to fix journal → publisher mapping
├── .github/workflows/
│   └── update-publications.yml    ← Fetch papers, then deploy Pages
├── scripts/fetch_publications.py
├── data/publications.json      ← Auto-generated, committed by Actions
├── index.html  style.css  app.js
```

## Setup

1. Fork / clone this repository.
2. **Edit `query_config.yml`** to set your topic terms, keywords, journals of
   interest, and arXiv queries. This is the only file you need to edit to
   change *what* gets fetched.
3. (Optional) **Edit `publishers_config.yml`** to fix or extend the journal →
   publisher mapping that drives the publisher tabs on the site.
4. Obtain a Web of Science API key from <https://developer.clarivate.com/>
   (arXiv needs no key).
5. Add the WoS key as a GitHub secret: **Settings → Secrets and variables →
   Actions → New repository secret**
   - Name: `WOS_API_KEY`
   - Value: your API key
6. **Enable GitHub Pages with GitHub Actions as the source:**
   **Settings → Pages → Build and deployment → Source → GitHub Actions.**
   (The "Deploy from branch" mode is no longer used — the workflow now
   deploys directly so the fetch always runs *before* the docs are built.)
7. Run the workflow manually once: **Actions → Update publications and
   deploy → Run workflow**.
8. Your site is live at `https://{your-github-username}.github.io/{repo-name}/`
   and refreshes every Monday at 06:00 UTC.

## How the workflow works

A single workflow (`update-publications.yml`) does both fetch *and* deploy in
order, so the published site is guaranteed to use fresh data:

1. **Fetch** (only on cron + manual triggers) — runs
   `scripts/fetch_publications.py`, which queries Web of Science for every
   topic term, keyword, journal and extra query, and arXiv for every preprint
   query in `query_config.yml`, then writes `data/publications.json`.
2. **Commit** the refreshed JSON back to `main` (skipped when nothing changed).
3. **Stage** a clean `_site/` directory containing only the static files
   (`index.html`, `style.css`, `app.js`, `data/`).
4. **Deploy** that directory to GitHub Pages via `actions/deploy-pages@v4`.

Push-triggered runs (e.g. when you tweak the CSS) skip the fetch step and
deploy immediately with the last-committed publications.

GitHub may auto-disable the cron after 60 days of repository inactivity. The
workflow's own JSON commit normally keeps the repo "active" — but if WoS and
arXiv return identical results for two months, no commit is created and the
schedule eventually pauses. Re-enable it from the Actions tab or trigger
once manually.

## What gets fetched

For every WoS query, up to `fetch.results_per_query` (default **50**)
most-recent matching papers are pulled. For every arXiv query, up to
`arxiv.results_per_query` (default **25**). All sources are merged and
deduplicated by DOI / UID into one feed.

**Web of Science queries** — four kinds, all paginated in 50-record pages:

1. **Topic queries** — `TS=("term") AND SO=(<journals_of_interest>)` for each
   term in `topic_query.terms`. Year-restricted via `topic_query.year_from`
   / `year_to`.
2. **Keyword queries** — same shape, run from `keywords`. Tagged
   `source: "keyword"` to distinguish from broad topic terms.
3. **Per-journal queries** — `SO=("journal")` for each entry in
   `journals_of_interest`. Returns the absolute latest from each, ignoring
   the year clause.
4. **Extra queries** — anything in `extra_queries`, AND-combined with the
   journals_of_interest scope.

WoS papers can **only** come from journals listed in `journals_of_interest`.
A post-fetch case-insensitive guard drops anything WoS returns whose source
title isn't on the allow-list.

**arXiv preprint queries** — one kind:

5. Each entry in `arxiv.queries` is sent to the arXiv API as
   `(<your query>) AND (cat:c1 OR cat:c2 ...)` when `arxiv.categories` is
   set. Records:
   - bypass the `journals_of_interest` allow-list (preprints aren't journals);
   - honour the same `topic_query.year_from` / `year_to` range *plus* an
     additional rolling `arxiv.max_age_days` window — both filters apply;
   - dedupe against WoS via DOI when the preprint has been formally
     published. Otherwise the record carries the arXiv-assigned DOI
     (`10.48550/arXiv.<id>`) so the card still resolves via doi.org;
   - show up under the dedicated **arXiv** publisher tab on the site;
   - omit abstracts to keep `data/publications.json` small.

The arXiv client sends a descriptive `User-Agent` (`paperatlas/1.0 …`) and
sleeps 3 s between calls per arXiv's rate-limit guidance. Occasional `429
Too Many Requests` errors are logged and that single query simply
contributes zero papers for the run; the next run retries.

## Embedded query log

The output JSON includes a top-level `queries` block with the **full query
string** (including the AND-joined `SO=(...)` / `PY=(...)` clauses for WoS,
or the `cat:(...)` clause for arXiv) for every query that was run, along
with `hits` and dedup-aware `new` counts. Copy any of these into another
tool to reuse the search. Buckets: `topic`, `keyword`, `journal`, `extra`,
`arxiv`.

## Publisher mapping

The journal → publisher mapping that drives the publisher tabs lives in
**`publishers_config.yml`**:

- `publishers:` is an ordered list of `{label, patterns}` entries; patterns
  are case-insensitive regular expressions matched against the journal name.
  The first hit wins; anything unmatched falls into `Other`.
- `overrides:` is a map of `"Exact Journal Name": "Publisher"` (case-
  insensitive) that beats `patterns`.
- Tab order on the site = the order declared in this file (with `Other`
  appended last when present, and tabs only rendered if at least one paper
  matches).

The Python script validates every regex compiles and embeds the mapping into
`data/publications.json` under `publishers`. The site reads it from there;
a bundled `DEFAULT_PUBLISHER_GROUPS` in `app.js` is used only as a fallback
when the field is missing (e.g. before the script has been re-run locally).

## Changing your search interests

Edit **`query_config.yml`** — no Python or workflow changes needed. Commit
and push (which triggers the deploy job), or trigger the workflow manually
for an immediate fetch + deploy.

The config covers:

- `site.title` / `site.subtitle` — header text shown on the site
- `topic_query.terms` — `TS=` topic terms (broad themes)
- `topic_query.year_from` / `year_to` — year-range filter shared by WoS
  topic/keyword/extra queries **and** arXiv preprints
  (use `CURRENT_YEAR` for today's year)
- `keywords` — `TS=` queries for specific keywords/tags
- `journals_of_interest` — strict allow-list of source journals; also drives
  the per-journal fetch and the journal-dropdown / publisher-tab UI
- `extra_queries` — any additional standalone WoS queries
- `fetch.results_per_query` — how many papers each WoS query pulls (default 50)
- `arxiv.enabled` — toggle the arXiv source on/off
- `arxiv.queries` — list of `{label, query}` arXiv search strings
- `arxiv.categories` — optional AND-restriction to specific arXiv categories
- `arxiv.results_per_query` — how many preprints each arXiv query pulls
- `arxiv.max_age_days` — rolling-window age cap on preprints
  (`null` to disable)

### Reducing the feed size

The biggest knobs (multiplied across all queries) are `fetch.results_per_query`
and `arxiv.results_per_query`. Trim the lists in `topic_query.terms`,
`keywords`, `journals_of_interest`, and `arxiv.queries` for further
reductions. Tightening `topic_query.year_from`/`year_to` shrinks both
sources at once.

## Running locally

```bash
pip install requests pyyaml
echo 'WOS_API_KEY=your_key_here' > .env  # auto-loaded by the script
python scripts/fetch_publications.py
# Then open index.html via any static server, e.g.:
python -m http.server 8000
```

arXiv works without any key. The `WOS_API_KEY` is only required when topic /
keyword / journal / extra queries are configured (the typical case).

## Tech

- **Fetch:** Python 3.11 · `requests` · `pyyaml` · stdlib `xml.etree`
- **Site:** Pure static HTML / CSS / JS — no build step, no framework
- **Themes:** Dark / light, persisted via `localStorage`, respects
  `prefers-color-scheme`
- **Hosting:** GitHub Pages, deployed via GitHub Actions
- **Automation:** GitHub Actions (weekly cron + manual trigger + push deploy)

## Data sources

- Publication metadata from the
  [Web of Science Starter API](https://developer.clarivate.com/apis/wos-starter)
  (Clarivate). Subject to Clarivate's terms.
- Preprint metadata from the
  [arXiv API](https://info.arxiv.org/help/api/index.html). Used in line with
  arXiv's terms; the client identifies itself via a descriptive
  `User-Agent`.
