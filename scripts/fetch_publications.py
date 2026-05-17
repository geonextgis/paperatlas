"""
fetch_publications.py
Reads query_config.yml, fetches matching papers from the Web of Science Starter
API and (optionally) the arXiv Atom API, then writes data/publications.json.

Behaviour
---------
* Each WoS query (topic term, keyword, journal, extra) fetches up to
  `fetch.results_per_query` (default 50) most recent matching papers, paginated
  in 50-record pages.
* Topic, keyword and extra queries are strictly scoped to `journals_of_interest`
  via an `AND SO=(...)` clause; a post-fetch case-insensitive guard drops any
  WoS record whose source title isn't on that allow-list.
* arXiv preprints are fetched independently. They bypass the journal allow-list
  (preprints aren't journals) but still dedupe against WoS by DOI when the
  preprint has been formally published.
* Records are deduplicated by DOI/UID. The merged record carries `sources`
  (e.g. ["topic", "keyword", "arxiv"]) and `matched_queries`.
* The publisher mapping is loaded from publishers_config.yml and embedded into
  publications.json under `publishers` so the front-end can render tabs without
  hardcoding the mapping in JS.
* The WoS API key is read from `WOS_API_KEY` (env or .env); arXiv needs no key.
"""

import datetime
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

import requests
import yaml

CONFIG_PATH = "query_config.yml"
PUBLISHERS_CONFIG_PATH = "publishers_config.yml"
OUT_PATH = "data/publications.json"

WOS_BASE_URL = "https://api.clarivate.com/apis/wos-starter/v1"
WOS_PAGE_LIMIT = 50  # WoS Starter API maximum per page.

ARXIV_BASE_URL = "http://export.arxiv.org/api/query"
ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}
ARXIV_PAGE_LIMIT = 100      # arXiv max per request
ARXIV_REQUEST_GAP = 3.0     # arXiv rate-limit politeness, seconds
# arXiv API guidelines ask clients to identify themselves with a descriptive
# User-Agent including a contact URL or email. This avoids tighter throttling
# applied to the default `python-requests/...` UA.
ARXIV_USER_AGENT = (
    "paperatlas/1.0 "
    "(+https://github.com/geonextgis/paperatlas; "
    "mailto:geonextgis@gmail.com)"
)

DEFAULT_RESULTS_PER_QUERY = 50


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader — does not overwrite existing environment values."""
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), val)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_previous_keys(path: str) -> set | None:
    """Return the set of (uid OR doi) strings from the previous publications.json,
    used to flag freshly added records with `is_new: true`. Returns None when no
    prior file exists (first run) so the script can avoid marking *every* record
    as new on the very first build."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"WARNING: could not read {path} for diff ({e}); "
              "treating this run as a first build.", file=sys.stderr)
        return None
    keys = set()
    for p in prev.get("publications", []) or []:
        uid = (p.get("uid") or "").strip()
        doi = (p.get("doi") or "").strip().lower()
        if uid:
            keys.add(uid)
        if doi:
            keys.add(doi)
    return keys


def load_publishers(path: str) -> dict | None:
    """Load publishers_config.yml; validate every regex compiles. Returns a
    dict {"groups": [...], "overrides": {...}} ready to embed in JSON, or
    None if the file is missing (the front-end then falls back to its
    bundled default mapping)."""
    if not os.path.isfile(path):
        print(f"WARNING: {path} missing — front-end will use bundled defaults.")
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    groups_in = data.get("publishers") or []
    groups = []
    for g in groups_in:
        label = (g.get("label") or "").strip()
        patterns = g.get("patterns") or []
        if not label or not patterns:
            continue
        for p in patterns:
            try:
                re.compile(p, re.IGNORECASE)
            except re.error as e:
                raise SystemExit(
                    f"ERROR: invalid regex in {path} "
                    f"(publisher '{label}'): {p!r} → {e}"
                )
        groups.append({"label": label, "patterns": list(patterns)})
    overrides = data.get("overrides") or {}
    if not isinstance(overrides, dict):
        overrides = {}
    print(f"Publishers loaded from {path}: {len(groups)} group(s), "
          f"{len(overrides)} override(s)")
    return {"groups": groups, "overrides": dict(overrides)}


def quote_term(term: str) -> str:
    """Wrap one TS term safely; preserves user-supplied AND/OR/NOT/field tags."""
    if any(op in term for op in [" AND ", " OR ", " NOT ", "="]):
        return f"({term})"
    if term.startswith('"') and term.endswith('"'):
        return term
    return f'"{term}"'


def journal_clause(journals: list) -> str:
    """Build `SO=("J1" OR "J2" ...)` from a list of journal names."""
    if not journals:
        return ""
    parts = [f'"{j}"' for j in journals]
    return f"SO=({' OR '.join(parts)})"


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def resolve_year_range(cfg: dict) -> tuple:
    """Read topic_query.year_from / year_to (with CURRENT_YEAR support) and
    return (yf, yt) as ints (or None for unset). The same range is honoured
    by WoS topic/keyword/extra queries via apply_year() and by the arXiv
    post-filter in parse_arxiv_record()."""
    tq = cfg.get("topic_query") or {}
    yf = tq.get("year_from")
    yt = tq.get("year_to")
    if yt == "CURRENT_YEAR":
        yt = utc_now().year
    if yf == "CURRENT_YEAR":
        yf = utc_now().year
    try:
        yf = int(yf) if yf is not None else None
    except (TypeError, ValueError):
        yf = None
    try:
        yt = int(yt) if yt is not None else None
    except (TypeError, ValueError):
        yt = None
    return yf, yt


def apply_year(query: str, cfg: dict) -> str:
    yf, yt = resolve_year_range(cfg)
    now_year = utc_now().year
    if yf and yt:
        return f"{query} AND PY=({yf}-{yt})"
    if yf:
        return f"{query} AND PY=({yf}-{now_year})"
    return query


# ─────────────────────────── WoS fetch ────────────────────────────

def fetch_wos_query(query: str, headers: dict, cfg: dict, max_results: int) -> list:
    """Fetch up to `max_results` papers from WoS, paginated in 50-record pages."""
    if max_results <= 0:
        return []
    retries = cfg["fetch"].get("retry_attempts", 3)
    backoff = cfg["fetch"].get("retry_backoff_seconds", 5)
    rps_delay = 1.0 / max(float(cfg["fetch"].get("requests_per_second", 2)), 0.1)

    out, page = [], 1
    while len(out) < max_results:
        page_size = min(WOS_PAGE_LIMIT, max_results - len(out))
        params = {"q": query, "limit": page_size, "page": page, "sortField": "PY+D"}
        resp = None
        for attempt in range(retries):
            try:
                resp = requests.get(
                    f"{WOS_BASE_URL}/documents",
                    headers=headers,
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                break
            except requests.RequestException as e:
                if attempt == retries - 1:
                    print(f"  ! Request failed: {e}", file=sys.stderr)
                    return out
                time.sleep(backoff)
        if resp is None:
            return out
        data = resp.json()
        hits = data.get("hits", []) or []
        out.extend(hits)
        total = (data.get("metadata") or {}).get("total", 0)
        if not hits or len(out) >= total:
            break
        page += 1
        time.sleep(max(rps_delay, 0.5))
    return out[:max_results]


def parse_citations(hit: dict) -> int:
    """WoS Starter returns `citations: [{db, count}, ...]`. Prefer the WoS DB
    count; fall back to the max count across all reported databases."""
    cits = hit.get("citations") or []
    if not isinstance(cits, list) or not cits:
        return 0
    wos = next(
        (c for c in cits if isinstance(c, dict) and str(c.get("db", "")).upper() == "WOS"),
        None,
    )
    if wos and isinstance(wos.get("count"), (int, float)):
        return int(wos["count"])
    counts = [int(c.get("count", 0) or 0) for c in cits if isinstance(c, dict)]
    return max(counts) if counts else 0


def parse_wos_record(hit: dict) -> dict:
    names = hit.get("names", {}) or {}
    authors = []
    for a in names.get("authors", []) or []:
        last = a.get("lastName") or ""
        first = a.get("firstName") or ""
        display = a.get("displayName") or (f"{last}, {first}".strip(", "))
        authors.append(display)

    source = hit.get("source", {}) or {}
    pages = source.get("pages") or {}
    page_range = pages.get("range", "") if isinstance(pages, dict) else str(pages)
    if not page_range:
        art = source.get("articleNumber") or ""
        if art:
            page_range = f"Art. {art}"

    identifiers = hit.get("identifiers") or []
    doi = ""
    if isinstance(identifiers, list):
        for i in identifiers:
            if isinstance(i, dict) and i.get("type") == "doi":
                doi = i.get("value", "")
                break
    elif isinstance(identifiers, dict):
        doi = identifiers.get("doi", "") or ""

    keywords_obj = hit.get("keywords") or {}
    keywords = (
        keywords_obj.get("authorKeywords") or []
        if isinstance(keywords_obj, dict)
        else []
    )

    citations = parse_citations(hit)

    oa = hit.get("openAccess") or {}
    is_oa = bool(oa.get("isOa", False) or oa.get("oases")) if isinstance(oa, dict) else False

    return {
        "uid": hit.get("uid", ""),
        "title": (hit.get("title") or "No title").strip(),
        "authors": authors,
        "journal": source.get("sourceTitle", "") or "",
        "year": source.get("publishYear", "") or "",
        "volume": source.get("volume", "") or "",
        "issue": source.get("issue", "") or "",
        "pages": page_range,
        "doi": doi,
        "abstract": hit.get("abstract", "") or "",
        "keywords": keywords,
        "citations": citations,
        "open_access": is_oa,
        "sources": [],
        "matched_queries": [],
    }


# ─────────────────────────── arXiv fetch ──────────────────────────

def build_arxiv_query(raw: str, categories: list) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if categories:
        cats = [c for c in categories if c]
        if cats:
            cat_clause = " OR ".join(f"cat:{c}" for c in cats)
            return f"({raw}) AND ({cat_clause})"
    return raw


def fetch_arxiv_query(query: str, max_results: int, retries: int, backoff: int) -> list:
    """Fetch one arXiv search; return list of parsed entry dicts. arXiv caps a
    single response at 100; for our typical 25-per-query usage no pagination is
    needed."""
    if not query or max_results <= 0:
        return []
    params = {
        "search_query": query,
        "start": 0,
        "max_results": min(max_results, ARXIV_PAGE_LIMIT),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    resp = None
    headers = {"User-Agent": ARXIV_USER_AGENT, "Accept": "application/atom+xml"}
    for attempt in range(retries):
        try:
            resp = requests.get(
                ARXIV_BASE_URL, params=params, headers=headers, timeout=30
            )
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt == retries - 1:
                print(f"  ! arXiv request failed: {e}", file=sys.stderr)
                return []
            time.sleep(backoff)
    if resp is None:
        return []
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"  ! arXiv XML parse failed: {e}", file=sys.stderr)
        return []
    return root.findall("atom:entry", ARXIV_NS)


def parse_arxiv_record(entry, max_age_days, year_from=None, year_to=None):
    def text_of(tag: str) -> str:
        el = entry.find(tag, ARXIV_NS)
        return (el.text or "").strip() if el is not None and el.text else ""

    arxiv_url = text_of("atom:id")  # e.g. http://arxiv.org/abs/2401.12345v2
    arxiv_id_full = arxiv_url.rsplit("/", 1)[-1]
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id_full) or arxiv_id_full
    if not arxiv_id:
        return None

    title = " ".join(text_of("atom:title").split())
    # Abstracts are intentionally not stored for arXiv records — they bloat
    # publications.json significantly and the card already links straight to
    # the preprint via DOI.
    published = text_of("atom:published")  # e.g. 2024-01-22T18:30:00Z
    year = published[:4] if len(published) >= 4 and published[:4].isdigit() else ""

    # Honour the same year range (topic_query.year_from / year_to) that
    # constrains WoS topic/keyword/extra queries, so arXiv preprints stay in
    # the same time window as the journal feed.
    if year:
        try:
            y = int(year)
            if year_from is not None and y < int(year_from):
                return None
            if year_to is not None and y > int(year_to):
                return None
        except (TypeError, ValueError):
            pass

    if max_age_days is not None and published:
        try:
            pub_dt = datetime.datetime.fromisoformat(published.replace("Z", "+00:00"))
            age_days = (utc_now() - pub_dt).days
            if age_days > int(max_age_days):
                return None
        except ValueError:
            pass  # if the date is unparseable, keep the record

    authors = []
    for a in entry.findall("atom:author", ARXIV_NS):
        name_el = a.find("atom:name", ARXIV_NS)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    cats = [c.attrib.get("term", "") for c in entry.findall("atom:category", ARXIV_NS)]
    cats = [c for c in cats if c]
    primary = entry.find("arxiv:primary_category", ARXIV_NS)
    if primary is not None:
        primary_term = primary.attrib.get("term", "")
        if primary_term and primary_term not in cats:
            cats.insert(0, primary_term)

    journal_doi = ""
    doi_el = entry.find("arxiv:doi", ARXIV_NS)
    if doi_el is not None and doi_el.text:
        journal_doi = doi_el.text.strip()

    # If the preprint has been formally published, use its DOI so the record
    # dedupes against any matching WoS hit. Otherwise fall back to the
    # arXiv-assigned DOI (10.48550/arXiv.<id>) so the card still opens via
    # doi.org.
    doi = journal_doi or f"10.48550/arXiv.{arxiv_id}"

    return {
        "uid": f"arxiv:{arxiv_id}",
        "title": title or "No title",
        "authors": authors,
        "journal": "arXiv",
        "year": year,
        "volume": "",
        "issue": "",
        "pages": f"arXiv:{arxiv_id}",
        "doi": doi,
        "abstract": "",
        "keywords": cats,
        "citations": 0,
        "open_access": True,
        "sources": [],
        "matched_queries": [],
    }


# ────────────────────────── merging ──────────────────────────

def merge_records(
    pubs: list, by_key: dict, records: list, source_label: str, query_label: str
) -> int:
    """Merge a list of already-parsed records into the working set. Returns the
    number of brand-new records added (the rest get their labels merged onto
    the existing entry)."""
    added = 0
    for rec in records:
        if rec is None:
            continue
        key = rec["doi"] or rec["uid"]
        if not key:
            continue
        if key in by_key:
            existing = by_key[key]
            if source_label not in existing["sources"]:
                existing["sources"].append(source_label)
            if query_label not in existing["matched_queries"]:
                existing["matched_queries"].append(query_label)
        else:
            rec["sources"].append(source_label)
            rec["matched_queries"].append(query_label)
            by_key[key] = rec
            pubs.append(rec)
            added += 1
    return added


def run_wos_query_set(
    label_kind: str,
    items: list,
    build_query,
    pubs: list,
    by_key: dict,
    headers: dict,
    cfg: dict,
    per_query: int,
    queries_log: dict,
):
    """Run one set of WoS queries (topic/keyword/journal/extra) and merge
    results. Each executed query is appended to `queries_log[label_kind]`."""
    if not items:
        return
    print(f"\n── {label_kind.capitalize()} queries (WoS) ──")
    bucket = queries_log.setdefault(label_kind, [])
    for item in items:
        q = build_query(item)
        if not q:
            continue
        label = item if isinstance(item, str) else item.get("label", "(unnamed)")
        print(f"  · {label}")
        hits = fetch_wos_query(q, headers, cfg, per_query)
        records = [parse_wos_record(h) for h in hits]
        added = merge_records(
            pubs, by_key, records, label_kind, f"{label_kind}:{label}"
        )
        bucket.append({
            "label": label,
            "query": q,
            "hits": len(hits),
            "new": added,
        })
        print(f"    → {len(hits)} hits ({added} new)")


def run_arxiv_queries(
    arxiv_cfg: dict,
    pubs: list,
    by_key: dict,
    queries_log: dict,
    cfg: dict,
):
    if not arxiv_cfg or not arxiv_cfg.get("enabled"):
        return
    queries = arxiv_cfg.get("queries") or []
    if not queries:
        return
    cats = arxiv_cfg.get("categories") or []
    per_query = int(arxiv_cfg.get("results_per_query", 25) or 25)
    max_age = arxiv_cfg.get("max_age_days")
    fetch_cfg = cfg.get("fetch", {}) or {}
    retries = int(fetch_cfg.get("retry_attempts", 3))
    backoff = int(fetch_cfg.get("retry_backoff_seconds", 5))
    yf, yt = resolve_year_range(cfg)

    print("\n── arXiv queries ──")
    if yf or yt:
        print(f"  (year filter: {yf or '…'} – {yt or '…'})")
    bucket = queries_log.setdefault("arxiv", [])
    for i, eq in enumerate(queries):
        if not isinstance(eq, dict):
            continue
        label = (eq.get("label") or "(unnamed)").strip() or "(unnamed)"
        raw = (eq.get("query") or "").strip()
        if not raw:
            continue
        q = build_arxiv_query(raw, cats)
        print(f"  · {label}")
        try:
            entries = fetch_arxiv_query(q, per_query, retries, backoff)
            records = [parse_arxiv_record(e, max_age, yf, yt) for e in entries]
        except Exception as e:
            print(f"    ! Skipping arXiv query '{label}': {e}", file=sys.stderr)
            entries, records = [], []
        kept = [r for r in records if r is not None]
        added = merge_records(pubs, by_key, kept, "arxiv", f"arxiv:{label}")
        bucket.append({
            "label": label,
            "query": q,
            "hits": len(kept),
            "new": added,
        })
        print(f"    → {len(entries)} fetched, {len(kept)} kept ({added} new)")
        if i < len(queries) - 1:
            time.sleep(ARXIV_REQUEST_GAP)


# ────────────────────────────── main ──────────────────────────────

def main():
    load_dotenv()
    cfg = load_config(CONFIG_PATH)
    publishers = load_publishers(PUBLISHERS_CONFIG_PATH)
    previous_keys = load_previous_keys(OUT_PATH)

    journals = cfg.get("journals_of_interest") or []
    so_clause = journal_clause(journals)
    per_query = int(cfg.get("fetch", {}).get("results_per_query", DEFAULT_RESULTS_PER_QUERY))
    if per_query <= 0:
        per_query = DEFAULT_RESULTS_PER_QUERY

    topic_terms = (cfg.get("topic_query") or {}).get("terms") or []
    keywords = cfg.get("keywords") or []
    extras = cfg.get("extra_queries") or []
    arxiv_cfg = cfg.get("arxiv") or {}
    arxiv_enabled = bool(arxiv_cfg.get("enabled"))

    needs_wos = bool(topic_terms or keywords or extras or journals)
    api_key = os.environ.get("WOS_API_KEY")
    if needs_wos and not api_key:
        print(
            "ERROR: WOS_API_KEY is not set. Add it to .env or the workflow secrets.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    headers = {"X-ApiKey": api_key, "Accept": "application/json"} if api_key else {}

    if (topic_terms or keywords or extras) and not so_clause:
        print(
            "ERROR: journals_of_interest is empty. Topic/keyword/extra queries "
            "require at least one journal so results can be scoped. "
            "Edit query_config.yml.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(f"Config loaded from {CONFIG_PATH}")
    print(f"Journals of interest: {len(journals)}")
    print(f"Results per query   : {per_query}")
    print(f"arXiv enabled       : {arxiv_enabled}")

    pubs, by_key = [], {}
    queries_log = {"topic": [], "keyword": [], "journal": [], "extra": [], "arxiv": []}

    # ── Topic queries (broad themes, TS=) ──
    run_wos_query_set(
        "topic",
        topic_terms,
        lambda t: apply_year(f"TS=({quote_term(t)}) AND {so_clause}", cfg),
        pubs, by_key, headers, cfg, per_query, queries_log,
    )

    # ── Keyword queries (specific terms, also TS=) ──
    run_wos_query_set(
        "keyword",
        keywords,
        lambda k: apply_year(f"TS=({quote_term(k)}) AND {so_clause}", cfg),
        pubs, by_key, headers, cfg, per_query, queries_log,
    )

    # ── Per-journal queries (absolute latest from each journal) ──
    run_wos_query_set(
        "journal",
        journals,
        lambda j: f'SO=("{j}")',
        pubs, by_key, headers, cfg, per_query, queries_log,
    )

    # ── Extra queries (free-form, scoped to journals_of_interest) ──
    if extras:
        print("\n── Extra queries (WoS) ──")
        bucket = queries_log.setdefault("extra", [])
        for eq in extras:
            label = eq.get("label", "(unnamed)")
            raw = (eq.get("query") or "").strip()
            if not raw:
                continue
            q = f"({raw}) AND {so_clause}" if so_clause else raw
            print(f"  · {label}")
            hits = fetch_wos_query(q, headers, cfg, per_query)
            records = [parse_wos_record(h) for h in hits]
            added = merge_records(
                pubs, by_key, records, f"extra:{label}", f"extra:{label}"
            )
            bucket.append({
                "label": label,
                "query": q,
                "hits": len(hits),
                "new": added,
            })
            print(f"    → {len(hits)} hits ({added} new)")

    # ── arXiv queries (preprints, no journal scope) ──
    run_arxiv_queries(arxiv_cfg, pubs, by_key, queries_log, cfg)

    if not pubs:
        print(
            "\nERROR: No publications matched any query. "
            "Aborting to protect existing data.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Belt-and-braces: drop anything outside the journal allow-list, but
    # exempt arXiv records (preprints aren't journals).
    if journals:
        allowed = {j.casefold().strip() for j in journals}
        before = len(pubs)
        pubs = [
            p for p in pubs
            if "arxiv" in (p.get("sources") or [])
            or (p.get("journal") or "").casefold().strip() in allowed
        ]
        dropped = before - len(pubs)
        if dropped:
            print(f"\nPost-filter dropped {dropped} record(s) outside journals_of_interest.")
        by_key = {(p["doi"] or p["uid"]): p for p in pubs}

    if not pubs:
        print(
            "\nERROR: All matches were filtered out as out-of-scope. "
            "Check journal-name spellings in query_config.yml.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Flag papers that weren't in the previous publications.json. Skipped on
    # the first run (previous_keys is None) so we don't mark the whole archive
    # as new.
    if previous_keys is not None:
        new_count = 0
        for p in pubs:
            uid = (p.get("uid") or "").strip()
            doi = (p.get("doi") or "").strip().lower()
            if (uid and uid in previous_keys) or (doi and doi in previous_keys):
                continue
            p["is_new"] = True
            new_count += 1
        print(f"\n{new_count} new publication(s) since previous run.")

    pubs.sort(
        key=lambda p: (
            int(p["year"]) if str(p["year"]).isdigit() else 0,
            int(p.get("citations") or 0),
        ),
        reverse=True,
    )

    output = {
        "updated_at": utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "total": len(pubs),
        "site": cfg.get("site", {}),
        "journals_of_interest": journals,
        "publishers": publishers,
        "queries": queries_log,
        "publications": pubs,
    }

    os.makedirs("data", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(pubs)} publications to {OUT_PATH}")


if __name__ == "__main__":
    main()