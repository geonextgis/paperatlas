# Research Feed — Krishnagopal Halder

A self-updating **research-interest feed**. Pulls the latest publications from
the **Web of Science API** every Monday via **GitHub Actions** and serves them
as a static site through **GitHub Pages**.

This site is **not** an author page — it does not list Krishnagopal's own
papers. It surfaces new work in his configured **research topics** and
**journals of interest**, so he can stay on top of the field.

The site supports both **dark and light themes**, with a toggle in the header.

```
/
├── query_config.yml           ← ✏️  EDIT THIS to change your search interests
├── .github/workflows/         ← Weekly fetch workflow
├── scripts/fetch_publications.py
├── data/publications.json     ← Auto-generated, committed by Actions
├── index.html  style.css  app.js
```

## Setup

1. Fork / clone this repository.
2. **Edit `query_config.yml`** to set your topic terms and journals of
   interest. This is the only file you ever need to edit to change what gets
   fetched.
3. Obtain a Web of Science API key from <https://developer.clarivate.com/>.
4. Add it as a GitHub secret: **Settings → Secrets and variables → Actions →
   New repository secret**
   - Name: `WOS_API_KEY`
   - Value: your API key
5. Enable GitHub Pages: **Settings → Pages → Source → Deploy from branch →
   `main` → `/ (root)`**.
6. Run the workflow manually once: **Actions → Weekly Publications Update →
   Run workflow**.
7. Your site is live at `https://{your-github-username}.github.io/{repo-name}/`
   and refreshes every Monday at 06:00 UTC.

## What gets fetched

Three sources are merged into one deduplicated feed:

1. **Topic query** — `TS=("crop model*" OR "nitrogen dynamic*" OR …)` built
   from `topic_query.terms`.
2. **Per-journal queries** — for each entry in `journals_of_interest`, the
   latest *N* papers (default 25, configurable via
   `fetch.journal_max_results`).
3. **Extra queries** — anything you list in `extra_queries`.

Set `fetch.journal_max_results: 0` if you want the journal list to be a
filter only and skip per-journal fetching.

## Changing your search interests

Just edit **`query_config.yml`** — no Python or workflow changes needed.
Commit and push, then trigger the workflow manually to refresh immediately.

The config covers:

- `site.title` / `site.subtitle` — header text shown on the site
- `topic_query.terms` — `TS=` topic terms (joined with `OR`)
- `topic_query.year_from` / `year_to` — optional year-range filter
  (use `CURRENT_YEAR` to mean today)
- `journals_of_interest` — drives both the journal dropdown and per-journal
  fetching
- `fetch.journal_max_results` — papers per journal (0 to disable)
- `extra_queries` — any additional standalone WoS queries

## Running locally

```bash
pip install requests pyyaml
WOS_API_KEY=your_key_here python scripts/fetch_publications.py
# Then open index.html via any static server, e.g.:
python -m http.server 8000
```

## Tech

- **Fetch:** Python 3.11 · `requests` · `pyyaml`
- **Site:** Pure static HTML / CSS / JS — no build step, no framework
- **Themes:** Dark / light, persisted via `localStorage`, respects
  `prefers-color-scheme`
- **Hosting:** GitHub Pages
- **Automation:** GitHub Actions (weekly cron + manual trigger)

## Data source

Publication metadata sourced from the
[Web of Science Starter API](https://developer.clarivate.com/apis/wos-starter)
(Clarivate). Subject to Clarivate's terms.
