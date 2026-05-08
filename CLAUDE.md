# CLAUDE.md — Personal Research-Interest Feed

## Project Overview

Build a **research-interest feed** for **Krishnagopal Halder**, a researcher at
ZALF (Leibniz Centre for Agricultural Landscape Research). The site automatically
fetches the latest publications weekly from the **Web of Science (WoS) API** that
match (a) configured **topic terms** and (b) configured **journals of interest**,
structures them beautifully, and is deployed via **GitHub Pages**. The entire
pipeline runs on **GitHub Actions** on a weekly schedule with zero manual
intervention.

> The site is **not** an author self-publication page. It does **not** fetch
> Krishnagopal's own papers. It is a curated feed of new work in his research
> areas and his journals of interest.

The site supports both **dark and light themes**, with a toggle in the header
that persists choice via `localStorage` and respects the user's
`prefers-color-scheme` on first visit.

---

## Research Profile & Interests → `query_config.yml`

**Do not hard-code queries in the Python script.** All search configuration lives
in a single standalone file: **`query_config.yml`**. This is the only file a user
needs to edit to change what publications are fetched.

### `query_config.yml` — full specification & default content

```yaml
# ============================================================
# query_config.yml
# Edit this file to customise which publications are fetched.
# No Python or workflow files need to be changed.
#
# This site is a research-interest feed: it pulls the latest
# publications matching your topic terms and your journals of
# interest. It does NOT fetch your own author publications.
# ============================================================

# ── Site identity (used only for page title / header text) ──
site:
  title: "Krishnagopal Halder — Research Feed"
  subtitle: "Latest in crop modelling, nitrogen dynamics, and agricultural AI"

# ── Topic interest search ────────────────────────────────────
# Publications matching your research interests.
# Uses WoS TS= (Topic: title + abstract + keywords) field.
# Each item in `terms` becomes one clause joined by OR inside TS=().
# Use WoS wildcard syntax: * for suffix (e.g. "model*" matches modeling, models).
topic_query:
  terms:
    - "crop model*"
    - "nitrogen dynamic*"
    - "agricultural landscape"
    - "crop yield forecast*"
    - '"deep learning" AND "agriculture"'
    - "SIMPLACE"
    - '"planetary boundaries" AND "nitrogen"'
    - '"climate change" AND "crop*" AND "SSP"'
  year_from: null            # e.g. 2020
  year_to: null              # e.g. CURRENT_YEAR
  max_results: 200

# ── Journals of interest ────────────────────────────────────
# Two roles:
#   1. Populate the "Filter by Journal" dropdown on the website.
#   2. Drive a per-journal fetch — the script pulls the latest N papers from
#      each of these journals (controlled by `fetch.journal_max_results`).
# Use exact journal names as they appear in Web of Science (SO= field).
# Leave empty ([]) to skip journal-based fetching and let the dropdown
# auto-populate from whatever journals are returned by the topic query.
journals_of_interest:
  - "Agricultural and Forest Meteorology"
  - "Field Crops Research"
  - "European Journal of Agronomy"
  - "Agricultural Systems"
  - "Global Change Biology"
  - "Nature Food"
  - "Environmental Research Letters"
  - "Computers and Electronics in Agriculture"
  - "Remote Sensing of Environment"
  - "Science of the Total Environment"

# ── Additional named queries (optional) ─────────────────────
extra_queries: []
# Example:
# extra_queries:
#   - label: "ZALF group output"
#     query: 'OG=("Leibniz Centre for Agricultural Landscape Research")'
#     max_results: 100

# ── Fetch settings ───────────────────────────────────────────
fetch:
  requests_per_second: 2
  retry_attempts: 3
  retry_backoff_seconds: 5
  # Latest papers to pull from each journal in `journals_of_interest`.
  # Set to 0 (or null) to skip per-journal fetching.
  journal_max_results: 25
```

### How the Python script reads this config

```python
import yaml, datetime

with open("query_config.yml", "r") as f:
    cfg = yaml.safe_load(f)

def build_topic_query(cfg):
    terms = cfg["topic_query"]["terms"]
    clauses = []
    for t in terms:
        if any(op in t for op in [" AND ", " OR ", " NOT ", "="]):
            clauses.append(f"({t})")        # already has operators
        else:
            clauses.append(f'"{t}"' if not t.startswith('"') else t)
    query = f"TS=({' OR '.join(clauses)})"
    yf = cfg["topic_query"].get("year_from")
    yt = cfg["topic_query"].get("year_to")
    if yt == "CURRENT_YEAR":
        yt = datetime.datetime.utcnow().year
    if yf and yt:
        query += f" AND PY=({yf}-{yt})"
    elif yf:
        query += f" AND PY=({yf}-{datetime.datetime.utcnow().year})"
    return query
```

Install `pyyaml` alongside `requests` in the workflow and locally.

---

## Repository Structure

```
/
├── CLAUDE.md                  ← This file
├── query_config.yml           ← ✏️  EDIT THIS to change your search interests
├── .github/
│   └── workflows/
│       └── update-publications.yml   ← Weekly GitHub Actions workflow
├── scripts/
│   └── fetch_publications.py         ← WoS API fetch + JSON generation
├── data/
│   └── publications.json             ← Auto-generated, committed by Actions
├── index.html                        ← Main website (static, reads publications.json)
├── style.css                         ← Styles (dark + light themes)
├── app.js                            ← Site logic
└── README.md
```

> **To change your search interests**, only edit `query_config.yml` — no Python
> or workflow files need to be touched. The fetch script reads this file at
> runtime.

---

## 1. GitHub Actions Workflow (`.github/workflows/update-publications.yml`)

```yaml
name: Weekly Publications Update

on:
  schedule:
    - cron: "0 6 * * 1"   # Every Monday at 06:00 UTC
  workflow_dispatch:       # Allow manual trigger

permissions:
  contents: write          # Allow the workflow to commit updated JSON

jobs:
  update-publications:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install requests pyyaml
      - name: Fetch publications from Web of Science
        env:
          WOS_API_KEY: ${{ secrets.WOS_API_KEY }}
        run: python scripts/fetch_publications.py
      - name: Commit updated publications
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/publications.json
          git diff --cached --quiet || git commit -m "chore: update publications $(date -u +%Y-%m-%d)"
          git push
```

**Secret required:** Add `WOS_API_KEY` to your GitHub repository
→ Settings → Secrets → Actions.

---

## 2. Python Fetch Script (`scripts/fetch_publications.py`)

Implement this script with the following logic. **Queries must be loaded from
`query_config.yml` at the repo root — never hardcoded.**

### Sources merged into the feed

1. **Topic query** — `TS=(... OR ...)` built from `topic_query.terms`.
2. **Per-journal queries** — for each entry in `journals_of_interest`, run
   `SO=("<journal name>")` and pull the latest `fetch.journal_max_results`
   papers (skip when that value is 0/null).
3. **Extra queries** — anything in `extra_queries`.

Records are tagged with their `sources` (a list of strings: `"topic"`,
`"journal"`, `"extra:<label>"`). When the same DOI/UID is returned by multiple
sources, the entry is kept once and the additional source labels are merged
onto it. There is **no `is_author_pub` field** — the feed has no concept of
"my publications".

### API details

- **Base URL:** `https://api.clarivate.com/apis/wos-starter/v1`
- **Auth header:** `X-ApiKey: {WOS_API_KEY}`
- **Endpoint:** `GET /documents` with `q`, `limit=50`, `page`, `sortField=PY+D`.

### Output schema (`data/publications.json`)

```jsonc
{
  "updated_at": "2026-05-08T06:00:00Z",
  "total": 220,
  "site": {
    "title": "Krishnagopal Halder — Research Feed",
    "subtitle": "Latest in crop modelling, nitrogen dynamics, and agricultural AI"
  },
  "journals_of_interest": ["Agricultural and Forest Meteorology", "..."],
  "publications": [
    {
      "uid": "WOS:000...",
      "title": "...",
      "authors": ["Last, First", "..."],
      "journal": "Agricultural Systems",
      "year": "2026",
      "volume": "212",
      "issue": "3",
      "pages": "104310",
      "doi": "10.1016/...",
      "abstract": "...",
      "keywords": ["crop model", "nitrogen"],
      "citations": 4,
      "open_access": true,
      "sources": ["topic", "journal"]
    }
  ]
}
```

If zero publications are fetched, the script must exit non-zero so the Actions
run fails visibly and `publications.json` is never overwritten with empty data.

---

## 3. Website (`index.html` + `style.css` + `app.js`)

### Design Direction

**Editorial / scientific journal aesthetic** — refined, data-rich,
authoritative. Think Nature or Annual Reviews meets a modern research page.

- **Dark palette:** Deep navy (`#0a1628`) bg, warm off-white (`#f5f0e8`) text,
  ZALF green (`#4a7c59`) and amber (`#d4a843`) accents.
- **Light palette:** Warm cream (`#faf7f0`) bg, deep navy text, deeper
  green/amber for contrast (WCAG AA).
- **Theme toggle:** A button in the header switches between themes. Choice is
  stored in `localStorage` (key `paperatlas-theme`). On first visit, the site
  honours the user's `prefers-color-scheme`. An inline pre-paint script applies
  the saved theme before first render to avoid a light/dark flash.
- **Typography:** Google Fonts — **Playfair Display** (headings), **Source
  Serif 4** (body), **JetBrains Mono** (metadata: year/DOI/citations).
- **Layout:** Full-bleed hero header, sticky filter/search bar, then a 1/2/3-
  column responsive card grid.
- **Cards:** title, authors, journal (italic), year, citation badge,
  Open-Access badge, "Journal feed" badge if the paper came from the per-journal
  fetch, DOI link, expandable abstract, keyword tags.
- **Animations:** subtle fade-in stagger on card load; smooth filter
  transitions. Honours `prefers-reduced-motion`.

### Functional Requirements

```javascript
// 1. On page load, fetch ./data/publications.json
// 2. Render all publications as cards
// 3. Search bar: title/author/keyword/journal/year (live, debounced 300ms)
// 4. Filter pills: All | Open Access  (no "My Publications" pill)
// 5. Journal dropdown: populated from journals_of_interest; if empty, auto-
//    populated from unique journal names in the data
// 6. Year pills: injected dynamically; "All Years" + each year
// 7. Sort dropdown: Newest First | Most Cited | Alphabetical
// 8. Each card: expandable abstract
// 9. DOI badge: links to https://doi.org/{doi} in new tab
// 10. Citation badge styled with color scale (gray=0, green>10, gold>50)
// 11. Show "Last updated: {date}" from publications.json
// 12. Show total count: "Showing X of Y publications"
// 13. All active filters compose with AND logic
// 14. Theme toggle button; persisted across sessions
```

### HTML Skeleton

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Krishnagopal Halder — Research Feed</title>
    <script>
      // Pre-paint theme application — read localStorage / prefers-color-scheme
      // and set document.documentElement.dataset.theme before first paint.
    </script>
    <link rel="stylesheet" href="style.css" />
    <link href="https://fonts.googleapis.com/..." rel="stylesheet" />
  </head>
  <body>
    <header class="site-header">
      <div class="header-inner">
        <div class="researcher-identity">
          <p class="researcher-eyebrow">Research Feed</p>
          <h1 class="researcher-name" id="siteTitle">Krishnagopal Halder</h1>
          <p class="researcher-affiliation" id="siteSubtitle">…</p>
        </div>
        <div class="header-meta">
          <button id="themeToggle" class="theme-toggle" type="button"
                  aria-label="Toggle light / dark theme">
            <span class="theme-icon" aria-hidden="true"></span>
            <span class="theme-label">Theme</span>
          </button>
          <span class="last-updated" id="lastUpdated">Loading…</span>
          <span class="pub-count" id="pubCount"></span>
        </div>
      </div>
    </header>

    <div class="controls-bar">
      <input type="search" id="searchInput" class="search-input"
             placeholder="Search publications, authors, keywords…" />
      <div class="filter-row">
        <div class="filter-pills">
          <button class="pill active" data-filter="all">All</button>
          <button class="pill" data-filter="oa">Open Access</button>
        </div>
        <select id="journalSelect" class="journal-select">
          <option value="">All Journals</option>
        </select>
        <select id="sortSelect" class="sort-select">
          <option value="year">Newest First</option>
          <option value="cited">Most Cited</option>
          <option value="alpha">A → Z</option>
        </select>
      </div>
    </div>

    <div class="year-filter" id="yearFilter"></div>
    <main class="publications-grid" id="pubGrid">
      <div class="loading-state">Fetching publications…</div>
    </main>

    <footer class="site-footer">…</footer>
    <script src="app.js"></script>
  </body>
</html>
```

### CSS theming

```css
:root,
:root[data-theme="dark"]  { --bg:#0a1628; --text:#f5f0e8; /* … */ }
:root[data-theme="light"] { --bg:#faf7f0; --text:#1a2a40; /* … */ }
```

All colours referenced in component rules use CSS custom properties (e.g.
`--bg`, `--bg-soft`, `--bg-line`, `--text`, `--text-dim`, `--text-mute`,
`--accent`, `--accent-hi`, `--warm`, `--warm-hi`, `--error`). Switching
themes is a one-attribute swap.

### JS behaviour (`app.js`)

- Apply persisted theme on init; toggle on button click; persist to
  `localStorage`.
- Fetch `./data/publications.json`; render cards.
- Show a "Journal feed" badge on cards whose `sources` array includes
  `"journal"`.
- Populate the journal dropdown from `data.journals_of_interest`; fall back to
  unique journal names if that list is empty.
- All active filters (type pill + journal + year + search) compose with AND.
- Filtering and sorting operate on the in-memory array (no re-fetch).
- Search input is debounced 300 ms.
- Per-card abstract toggle.

---

## 4. Deployment (GitHub Pages)

1. **Settings → Pages → Source → Deploy from branch → `main` → `/ (root)`**
2. Site lives at `https://{user}.github.io/{repo}/`
3. Every Monday the workflow updates `data/publications.json` and commits it,
   triggering a Pages rebuild.

---

## 5. First-Time Setup Instructions

Add to `README.md`:

```markdown
## Setup

1. Fork / clone this repository
2. **Edit `query_config.yml`** to set your topic terms and journals of interest
3. Get a Web of Science API key: https://developer.clarivate.com/
4. Add it as a GitHub secret: Settings → Secrets → Actions
   - Name: `WOS_API_KEY`
5. Enable GitHub Pages: Settings → Pages → main → /(root)
6. Run the workflow once: Actions → Weekly Publications Update → Run workflow
7. Site is live and refreshes every Monday.
```

---

## 6. Quality & Robustness Requirements

- **Error handling:** On WoS API errors, log and exit code 1. Never overwrite
  `publications.json` with empty / broken data.
- **Resilience:** If a single per-journal fetch fails, log the error and skip
  that journal — don't abort the whole run.
- **Rate limiting:** Respect Clarivate's rate limits; ≥ 0.5 s between pages.
- **Fallback:** If `publications.json` fails to load in the browser, show a
  friendly error message with a link to the GitHub repo.
- **Accessibility:** Keyboard-navigable controls; ARIA labels on cards and
  filters; theme toggle is a real `<button>`. WCAG AA contrast in both themes.
  Honour `prefers-reduced-motion`.
- **Performance:** Lazy-load abstracts (collapsed by default). Keep the page
  fast even with hundreds of publications.

---

## 7. Optional Enhancements (implement if time allows)

- [ ] **Citation graph:** sparkline showing citation trend per paper
- [ ] **Topic clustering:** auto-tag cards with topic badges (Crop Model /
      Nitrogen / Deep Learning / Climate)
- [ ] **BibTeX export:** copy BibTeX citation per card
- [ ] **RSS feed:** auto-generate `feed.xml` from the JSON
- [ ] **Source filter pills:** Topic feed | Journal feed | Extra queries

---

## Notes for Claude

- Always read this entire file before writing any code.
- Implement **all four components** in one pass: `query_config.yml`, the Python
  script, the GitHub Actions YAML, and the full website (HTML + CSS + JS).
- **`query_config.yml` is the single source of truth for all queries** — the
  Python script must load it with `yaml.safe_load`. Never hardcode query
  strings in Python.
- The site is a **research-interest feed**, not an author page. Do not add
  author self-search or "My Publications" UI.
- The website must be **self-contained static HTML** — no build step, no
  Node.js, no React. Pure HTML/CSS/JS that reads a local JSON file.
- Theming is via CSS custom properties + `[data-theme="light"|"dark"]` on
  `<html>`. An inline pre-paint script must apply the saved theme before first
  render to avoid flash.
- CSS goes in `style.css`; JS goes in `app.js`. No inline styles or scripts
  beyond the pre-paint theme bootstrap.
- Test the Python script locally:
  `pip install requests pyyaml && WOS_API_KEY=xxx python scripts/fetch_publications.py`
- Commit order matters: always commit `data/publications.json` before the site
  tries to read it.
