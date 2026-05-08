# Research Feed — Krishnagopal Halder

A self-updating **research-interest feed**. Pulls the latest publications from
the **Web of Science API** every Monday via **GitHub Actions** and serves them
as a static site through **GitHub Pages**.

This site is **not** an author page — it does not list Krishnagopal's own
papers. It surfaces new work in his configured **research topics**,
**keywords**, and **journals of interest**, so he can stay on top of the
field.

The site supports both **dark and light themes**, with a toggle in the header.

```
/
├── query_config.yml           ← ✏️  EDIT THIS to change your search interests
├── .github/workflows/
│   └── update-publications.yml   ← Fetch papers, then deploy Pages
├── scripts/fetch_publications.py
├── data/publications.json     ← Auto-generated, committed by Actions
├── index.html  style.css  app.js
```

## Setup

1. Fork / clone this repository.
2. **Edit `query_config.yml`** to set your topic terms, keywords and journals
   of interest. This is the only file you ever need to edit to change what
   gets fetched.
3. Obtain a Web of Science API key from <https://developer.clarivate.com/>.
4. Add it as a GitHub secret: **Settings → Secrets and variables → Actions →
   New repository secret**
   - Name: `WOS_API_KEY`
   - Value: your API key
5. **Enable GitHub Pages with GitHub Actions as the source:**
   **Settings → Pages → Build and deployment → Source → GitHub Actions.**
   (The "Deploy from branch" mode is no longer used — the workflow now
   deploys directly so the fetch always runs *before* the docs are built.)
6. Run the workflow manually once: **Actions → Update publications and
   deploy → Run workflow**.
7. Your site is live at `https://{your-github-username}.github.io/{repo-name}/`
   and refreshes every Monday at 06:00 UTC.

## How the workflow works

A single workflow (`update-publications.yml`) does both fetch *and* deploy in
order, so the published site is guaranteed to use fresh data:

1. **Fetch** (only on cron + manual triggers) — runs
   `scripts/fetch_publications.py`, which queries Web of Science for every
   topic term, keyword, journal and extra query in `query_config.yml` and
   writes `data/publications.json`.
2. **Commit** the refreshed JSON back to `main` (skipped when nothing changed).
3. **Stage** a clean `_site/` directory containing only the static files
   (`index.html`, `style.css`, `app.js`, `data/`).
4. **Deploy** that directory to GitHub Pages via `actions/deploy-pages@v4`.

Push-triggered runs (e.g. when you tweak the CSS) skip the fetch step and
deploy immediately with the last-committed publications.

## What gets fetched

For every query, up to `fetch.results_per_query` (default **50**) most-recent
matching papers are pulled from WoS. Four query kinds are merged and
deduplicated into one feed:

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

Papers can **only** come from journals listed in `journals_of_interest`. A
post-fetch case-insensitive guard drops anything WoS returns whose source
title isn't on the allow-list.

## Embedded query log

The output JSON includes a top-level `queries` block with the **full WoS query
string** (including the AND-joined `SO=(...)` and `PY=(...)` clauses) for
every query that was run, along with hit counts. Copy any of these into
another tool to reuse the search.

## Changing your search interests

Edit **`query_config.yml`** — no Python or workflow changes needed. Commit
and push (which triggers the deploy job), or trigger the workflow manually
for an immediate fetch + deploy.

The config covers:

- `site.title` / `site.subtitle` — header text shown on the site
- `topic_query.terms` — `TS=` topic terms (broad themes)
- `topic_query.year_from` / `year_to` — optional year-range filter
  (use `CURRENT_YEAR` for today's year)
- `keywords` — `TS=` queries for specific keywords/tags
- `journals_of_interest` — strict allow-list of source journals; also drives
  the per-journal fetch and the journal-dropdown / publisher-tab UI
- `extra_queries` — any additional standalone WoS queries
- `fetch.results_per_query` — how many papers each query pulls (default 50)

## Running locally

```bash
pip install requests pyyaml
echo 'WOS_API_KEY=your_key_here' > .env  # auto-loaded by the script
python scripts/fetch_publications.py
# Then open index.html via any static server, e.g.:
python -m http.server 8000
```

## Tech

- **Fetch:** Python 3.11 · `requests` · `pyyaml`
- **Site:** Pure static HTML / CSS / JS — no build step, no framework
- **Themes:** Dark / light, persisted via `localStorage`, respects
  `prefers-color-scheme`
- **Hosting:** GitHub Pages, deployed via GitHub Actions
- **Automation:** GitHub Actions (weekly cron + manual trigger + push deploy)

## Data source

Publication metadata sourced from the
[Web of Science Starter API](https://developer.clarivate.com/apis/wos-starter)
(Clarivate). Subject to Clarivate's terms.
