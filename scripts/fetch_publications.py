"""
fetch_publications.py
Reads query_config.yml, fetches matching papers from the Web of Science Starter
API, and writes data/publications.json.

Behaviour
---------
* Each query (topic term, keyword, journal, extra) fetches up to
  `fetch.results_per_query` (default 50) most recent matching papers — not just
  one. Pages of 50 are requested until the limit is reached or WoS runs out.
* Topic, keyword and extra queries are strictly scoped to `journals_of_interest`
  via an `AND SO=(...)` clause; a post-fetch case-insensitive guard drops any
  record whose source title isn't on that allow-list.
* Records are deduplicated by DOI/UID. The merged record carries `sources`
  (e.g. ["topic", "keyword"]) and `matched_queries` (e.g. ["topic:crop model*"]).
* The API key is read from the `WOS_API_KEY` environment variable; for local
  runs the script auto-loads `.env` from the repo root.
"""

import datetime
import json
import os
import sys
import time

import requests
import yaml

CONFIG_PATH = "query_config.yml"
OUT_PATH = "data/publications.json"
BASE_URL = "https://api.clarivate.com/apis/wos-starter/v1"
DEFAULT_RESULTS_PER_QUERY = 50
WOS_PAGE_LIMIT = 50  # WoS Starter API maximum per page.


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


def apply_year(query: str, cfg: dict) -> str:
    yf = (cfg.get("topic_query") or {}).get("year_from")
    yt = (cfg.get("topic_query") or {}).get("year_to")
    now_year = utc_now().year
    if yt == "CURRENT_YEAR":
        yt = now_year
    if yf and yt:
        return f"{query} AND PY=({yf}-{yt})"
    if yf:
        return f"{query} AND PY=({yf}-{now_year})"
    return query


def fetch_query(query: str, headers: dict, cfg: dict, max_results: int) -> list:
    """Fetch up to `max_results` papers, paginated in 50-record pages."""
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
                    f"{BASE_URL}/documents",
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


def parse_record(hit: dict) -> dict:
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


def merge_hits(
    pubs: list, by_key: dict, hits: list, source_label: str, query_label: str
) -> int:
    """Add new hits or merge labels onto existing records. Returns # added."""
    added = 0
    for hit in hits:
        rec = parse_record(hit)
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


def run_query_set(
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
    """Run one set of queries (topic/keyword/journal/extra) and merge results.
    Each executed query is appended to `queries_log[label_kind]` with the
    full WoS query string, hit count, and how many new (deduped) papers it
    contributed."""
    if not items:
        return
    print(f"\n── {label_kind.capitalize()} queries ──")
    bucket = queries_log.setdefault(label_kind, [])
    for item in items:
        q = build_query(item)
        if not q:
            continue
        label = item if isinstance(item, str) else item.get("label", "(unnamed)")
        print(f"  · {label}")
        hits = fetch_query(q, headers, cfg, per_query)
        added = merge_hits(
            pubs, by_key, hits, label_kind, f"{label_kind}:{label}"
        )
        bucket.append({
            "label": label,
            "wos_query": q,
            "hits": len(hits),
            "new": added,
        })
        print(f"    → {len(hits)} hits ({added} new)")


def main():
    load_dotenv()
    cfg = load_config(CONFIG_PATH)

    api_key = os.environ.get("WOS_API_KEY")
    if not api_key:
        print(
            "ERROR: WOS_API_KEY is not set. Add it to .env or the workflow secrets.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    headers = {"X-ApiKey": api_key, "Accept": "application/json"}

    journals = cfg.get("journals_of_interest") or []
    so_clause = journal_clause(journals)
    per_query = int(cfg.get("fetch", {}).get("results_per_query", DEFAULT_RESULTS_PER_QUERY))
    if per_query <= 0:
        per_query = DEFAULT_RESULTS_PER_QUERY

    topic_terms = (cfg.get("topic_query") or {}).get("terms") or []
    keywords = cfg.get("keywords") or []
    extras = cfg.get("extra_queries") or []

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

    pubs, by_key = [], {}
    queries_log = {"topic": [], "keyword": [], "journal": [], "extra": []}

    # ── Topic queries (broad themes, TS=) ──
    run_query_set(
        "topic",
        topic_terms,
        lambda t: apply_year(f"TS=({quote_term(t)}) AND {so_clause}", cfg),
        pubs, by_key, headers, cfg, per_query, queries_log,
    )

    # ── Keyword queries (specific terms, also TS= for breadth) ──
    run_query_set(
        "keyword",
        keywords,
        lambda k: apply_year(f"TS=({quote_term(k)}) AND {so_clause}", cfg),
        pubs, by_key, headers, cfg, per_query, queries_log,
    )

    # ── Per-journal queries (absolute latest from each journal) ──
    run_query_set(
        "journal",
        journals,
        lambda j: f'SO=("{j}")',
        pubs, by_key, headers, cfg, per_query, queries_log,
    )

    # ── Extra queries (free-form, scoped to journals_of_interest) ──
    if extras:
        print("\n── Extra queries ──")
        bucket = queries_log.setdefault("extra", [])
        for eq in extras:
            label = eq.get("label", "(unnamed)")
            raw = (eq.get("query") or "").strip()
            if not raw:
                continue
            q = f"({raw}) AND {so_clause}" if so_clause else raw
            print(f"  · {label}")
            hits = fetch_query(q, headers, cfg, per_query)
            added = merge_hits(
                pubs, by_key, hits, f"extra:{label}", f"extra:{label}"
            )
            bucket.append({
                "label": label,
                "wos_query": q,
                "hits": len(hits),
                "new": added,
            })
            print(f"    → {len(hits)} hits ({added} new)")

    if not pubs:
        print(
            "\nERROR: No publications matched any query. "
            "Aborting to protect existing data.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Belt-and-braces: drop anything outside the journal allow-list.
    if journals:
        allowed = {j.casefold().strip() for j in journals}
        before = len(pubs)
        pubs = [p for p in pubs if (p.get("journal") or "").casefold().strip() in allowed]
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
        "queries": queries_log,
        "publications": pubs,
    }

    os.makedirs("data", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(pubs)} publications to {OUT_PATH}")


if __name__ == "__main__":
    main()
