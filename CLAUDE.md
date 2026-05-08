# CLAUDE.md — Personal Research-Interest Feed

## Project Overview

Build a **research-interest feed** for **Krishnagopal Halder**, a researcher at
ZALF (Leibniz Centre for Agricultural Landscape Research). The site automatically
fetches publications weekly from the **Web of Science (WoS) API** that match
(a) configured **topic terms** and (b) configured **journals of interest**,
structures them beautifully, and is deployed via **GitHub Pages**. The entire
pipeline runs on **GitHub Actions** on a weekly schedule with zero manual
intervention.

> The site is **not** an author self-publication page. It does **not** fetch
> Krishnagopal's own papers. It is a curated feed of new work in his research
> areas and his journals of interest.

### Fetch semantics — "up to N latest papers per query"

- For **every query** (each topic term, each entry in `keywords`, each
  journal in `journals_of_interest`, each entry in `extra_queries`), the
  script fetches up to `fetch.results_per_query` papers (default **50**),
  paginated in 50-record WoS pages and sorted by `PY+D` (publication year
  descending). The site is designed to comfortably display 50+ papers; with
  several queries the deduplicated total is typically in the hundreds.
- **Topic, keyword and extra queries** are **strictly scoped** to
  `journals_of_interest` via an `AND SO=(...)` clause. Papers can only come
  from journals listed there. A belt-and-braces post-filter discards anything
  WoS returns whose source title isn't on the allow-list (case-insensitive).
- **Per-journal queries** (one per entry in `journals_of_interest`) ensure
  the latest papers from each watched journal are present even if no topic
  or keyword query matched them.
- If a query returns no match, that query simply contributes no result —
  this is expected and never an error.
- The WoS API key is read from the `WOS_API_KEY` environment variable. The
  script auto-loads `.env` from the repo root for local runs (`.env` is
  gitignored). In GitHub Actions the secret is injected as an env var.

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
# Broad themes. Each term becomes its own query:
#   TS=("term") AND SO=(<journals_of_interest>)
# Up to fetch.results_per_query papers are returned per query.
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

# ── Keyword search ───────────────────────────────────────────
# Specific tags or phrases. Each entry becomes its own TS=(...) query, identical
# in mechanics to topic terms but tagged `source: "keyword"` so the feed and
# the website can distinguish broad themes from specific keywords.
keywords:
  - "remote sensing"
  - "deep learning"
  - "machine learning"
  - "satellite imagery"
  - "GeoAI"
  - "convolutional neural network*"
  - "Sentinel-2"
  - "land use"
  - "precision agriculture"

# ── Journals of interest (the strict allow-list) ────────────
# Used to:
#   1. Scope every topic and extra query via SO=(<journals_of_interest>).
#   2. Drive a per-journal fetch — the latest paper from each is included.
#   3. Populate the "Filter by Journal" dropdown on the website.
# A post-fetch guard drops any record whose source title isn't on this list.
# Use exact journal names as they appear in Web of Science (SO= field).
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
# Each entry: { label: str, query: str }. The script combines the query with
# the journals_of_interest SO=(...) clause via AND, and keeps the latest match.
extra_queries: []
# Example:
# extra_queries:
#   - label: "ZALF group output"
#     query: 'OG=("Leibniz Centre for Agricultural Landscape Research")'

# ── Fetch settings ───────────────────────────────────────────
fetch:
  # Up to this many most recent papers are pulled per query. WoS pages of 50
  # are fetched and concatenated. Default 50 keeps the feed >=50 papers wide.
  results_per_query: 50
  requests_per_second: 2
  retry_attempts: 3
  retry_backoff_seconds: 5
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

For every query the script asks WoS for up to **`fetch.results_per_query`**
papers (default 50), sorted `PY+D`, paginated 50 at a time:

1. **Topic queries** — for each term `t` in `topic_query.terms`, run
   `TS=("t") AND SO=(<journals_of_interest>)` (plus the optional
   `AND PY=...` year clause).
2. **Keyword queries** — for each entry `k` in `keywords`, run
   `TS=("k") AND SO=(<journals_of_interest>)` (with the same year clause).
3. **Per-journal queries** — for each entry `j` in `journals_of_interest`,
   run `SO=("j")` (no year filter — absolute latest).
4. **Extra queries** — for each entry in `extra_queries`, AND its query with
   the `SO=(<journals_of_interest>)` clause.

Records are tagged with their `sources` (a list of strings:
`"topic"`, `"keyword"`, `"journal"`, `"extra:<label>"`) and a
`matched_queries` list of the specific query labels that returned that paper
(e.g. `"topic:crop model*"`, `"keyword:Sentinel-2"`). When the same DOI/UID
is returned by multiple queries, the entry is stored once and the additional
labels are merged onto it. There is **no `is_author_pub` field** — the feed
has no concept of "my publications".

### Embedded query log

Every executed WoS query is recorded under the top-level `queries` key in
`data/publications.json`, bucketed by kind (`topic` / `keyword` / `journal`
/ `extra`). Each entry contains:

- `label` — the user-facing identifier (e.g. `"crop model*"`, `"NATURE FOOD"`).
- `wos_query` — the **full** WoS query string sent to the API, including the
  AND-joined `SO=(...)` journal scope and any `PY=(...)` year clause. This
  is the value to copy and paste into another tool.
- `hits` — number of papers WoS returned for that query.
- `new` — how many of those were newly added to the feed (the rest were
  duplicates already brought in by earlier queries).

This gives a complete, machine-readable audit of what was asked and what
came back.

### Strict journal scoping

After fetching, the script discards any record whose `source.sourceTitle`
isn't in `journals_of_interest` (case-insensitive comparison). This is a
defence-in-depth safeguard against fuzzy WoS `SO=` matches. If
`journals_of_interest` is empty while `topic_query.terms` is set, the script
aborts with a clear error.

### API key handling

The script reads `WOS_API_KEY` from the environment. For local runs it also
auto-loads variables from a `.env` file at the repo root (`.env` is in
`.gitignore`):

```python
def load_dotenv(path=".env"):
    if not os.path.isfile(path): return
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
```

The key is **never** hardcoded. In GitHub Actions, `WOS_API_KEY` is provided
as a repository secret.

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
  "queries": {
    "topic":   [{"label": "crop model*",     "wos_query": "TS=(\"crop model*\") AND SO=(\"...\") AND PY=(2020-2026)", "hits": 50, "new": 50}],
    "keyword": [{"label": "Sentinel-2",      "wos_query": "TS=(\"Sentinel-2\") AND SO=(\"...\") AND PY=(2020-2026)", "hits": 50, "new": 27}],
    "journal": [{"label": "NATURE FOOD",     "wos_query": "SO=(\"NATURE FOOD\")",                                   "hits": 50, "new": 36}],
    "extra":   [{"label": "ZALF group",      "wos_query": "(OG=(\"...\")) AND SO=(\"...\")",                         "hits":  3, "new":  3}]
  },
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
      "sources": ["topic", "keyword", "journal"],
      "matched_queries": [
        "topic:crop model*",
        "keyword:Sentinel-2",
        "journal:Agricultural Systems"
      ]
    }
  ]
}
```

If zero publications are fetched, the script must exit non-zero so the Actions
run fails visibly and `publications.json` is never overwritten with empty data.

---

## 3. Website (`index.html` + `style.css` + `app.js`)

### Design Direction — clean modern editorial

Solid surfaces, crisp 1px borders, generous whitespace. No glass blur, no
gradient blobs. Inspired by Linear / Stripe / GitHub feeds applied to a
scientific paper context.

- **Background:** Solid `var(--bg)`. A single 3px gradient strip
  (green → amber → green) runs across the very top of the header as the
  only chromatic flourish.
- **Surfaces:** Cards, search input, dropdowns, theme toggle and footer
  all sit on `var(--surface)` with a 1px `var(--border)`. Hover bumps the
  border to `var(--border-hi)` and adds a soft drop shadow; on clickable
  cards the hover border is the accent green and the title shifts colour.
- **Dark palette:** `#0d1322` bg, `#131a2d` surface, warm off-white text
  (`#e8e3d8`), brighter ZALF green (`#6db685`) and amber (`#e2b758`) for
  AA contrast on dark.
- **Light palette:** `#f7f4ec` warm cream bg, white surfaces, deep navy
  (`#1a2440`) text, deeper green (`#2d5440`) and amber (`#a06f0e`).
- **Typography:** **Inter** for UI (headers, controls, body of cards),
  **Playfair Display** for the researcher name and paper titles only,
  **Source Serif 4** for italic affiliations / author lists / abstracts,
  **JetBrains Mono** for metadata (year, DOI, citations, counts). Inter
  was added in this redesign to give the chrome a more modern feel; the
  serif fonts remain for editorial weight on titles and abstracts.
- **Theme toggle:** small icon button (34×34) in the header meta row.
  Choice is stored in `localStorage` (key `paperatlas-theme`); first
  visit honours `prefers-color-scheme`. An inline pre-paint script
  applies the saved theme before first render to avoid a flash.
- **Layout:** Hero header → sticky toolbar (search row → dropdowns +
  result counter row → publisher tabs row → year-chip row) → 1/2/3-column
  responsive card grid → footer.
- **Filter bar:**
  - **Search** — single full-width input with an inline magnifier icon
    and an accent focus ring.
  - **Dropdowns** — Journal and Sort, each rendered as a labelled chip
    (`Journal`/`Sort` mono caps inside, native `<select>` to the right).
  - **Publisher tabs** — a real tab strip with an underline indicator on
    the active tab. Each tab carries a count badge. **Only publishers
    with at least one paper in the data are rendered** (empty groups are
    omitted entirely).
  - **Year chips** — small mono pills with `Year` label prefix; "All"
    plus each year present in the data.
  - **No "Open Access" pill** — removed in this iteration.
- **Cards:** Solid surface, 1px border, soft shadow; hover lifts 2px and
  brightens the border (accent on clickable cards). Header line carries
  year (chip), publisher badge, "Journal feed" badge, and a citation
  badge **only when count > 0** (no "0 cites" noise). Title links to DOI
  on hover via colour shift. Authors in italic Source Serif. Journal name
  in italic accent. Keyword tags in mono with accent-tinted backgrounds.
  Expandable abstract with mono toggle. **The whole card is clickable**
  (role="link", tabIndex=0) and opens `https://doi.org/{doi}` in a new
  tab; clicks on inner buttons or links do not trigger navigation.
- **Animations:** subtle fade-in stagger on card load; smooth hover lift;
  smooth focus-ring transitions. Honours `prefers-reduced-motion`.

### Functional Requirements

```javascript
// 1. On page load, fetch ./data/publications.json
// 2. Render all publications as cards
// 3. Search bar: title/author/keyword/journal/year (live, debounced 300ms)
// 4. (Removed) — no Open Access filter pill, no type filter
// 5. Journal dropdown: populated from journals_of_interest; if empty, auto-
//    populated from unique journal names in the data
// 6. Publisher tabs: only publishers with at least one paper in the data are
//    rendered. Order = canonical PUBLISHER_GROUPS order, with "Other" last
//    if present. Active tab gets an underline indicator and accent-tinted
//    count badge. Mapping (journal → publisher) lives in PUBLISHER_GROUPS
//    in app.js; new journals are auto-classified from regexes.
// 7. Year chips: injected dynamically; "Year" label prefix, "All" + each year.
// 8. Sort dropdown: Newest First | Most Cited | Alphabetical
// 9. Each card: expandable abstract; publisher badge in header.
//    The entire card is clickable (role="link", keyboard-accessible) and
//    opens https://doi.org/{doi} in a new tab. Inner buttons/anchors
//    (abstract toggle, DOI link) don't trigger navigation.
// 10. DOI badge: links to https://doi.org/{doi} in new tab
// 11. Citation badge: only rendered when count > 0; colour scale
//     (low/mid/hi) based on thresholds (>10, >50).
// 12. Header shows "Updated · {date}" and "{N} papers" total count.
// 13. Toolbar shows live "Showing X of Y" via #resultCount.
// 14. All active filters compose with AND logic
// 15. Theme toggle button; persisted across sessions
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
- Show a publisher badge (Nature, Elsevier, …) on each card based on the
  journal→publisher mapping (`publisherFor(journal)` in `app.js`).
- Populate the journal dropdown from `data.journals_of_interest`; fall back
  to unique journal names if that list is empty.
- Populate the **Publisher tab strip** dynamically: only render tabs whose
  count is > 0 in the current data. Active tab gets an underline indicator.
- Bind a **whole-card click** handler that opens `https://doi.org/{doi}` in
  a new tab; suppresses navigation when the click originated from a `button`
  or `a` inside the card. Cards with no DOI are not clickable.
- All active filters (journal + publisher + year + search) compose with AND.
- Filtering and sorting operate on the in-memory array (no re-fetch).
- Search input is debounced 300 ms.
- Per-card abstract toggle.

### Citation parsing

WoS Starter returns `hit.citations` as a list of `{db, count}` objects (often
just one, with `db: "WOS"`). The script's `parse_citations()` prefers the
WoS DB count and falls back to the maximum across all reported databases.
The earlier `metrics.timesCited` path was a dead-end — `metrics` is `null`
in this endpoint's responses and produced 0-citation values for every paper.

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
