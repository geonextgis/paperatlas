"""
fetch_publications.py
Reads query_config.yml, fetches publications from Web of Science Starter API,
and writes data/publications.json.

Sources merged into the feed:
  1. Topic query (TS=...)        — research interests
  2. Per-journal queries (SO=..) — latest N papers from each journal_of_interest
  3. extra_queries               — any custom queries from the config
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


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_topic_query(cfg: dict) -> str:
    terms = cfg["topic_query"]["terms"]
    clauses = []
    for t in terms:
        if any(op in t for op in [" AND ", " OR ", " NOT ", "="]):
            clauses.append(f"({t})")
        else:
            if t.startswith('"') and t.endswith('"'):
                clauses.append(t)
            else:
                clauses.append(f'"{t}"')
    ts_inner = " OR ".join(clauses)
    query = f"TS=({ts_inner})"

    year_from = cfg["topic_query"].get("year_from")
    year_to = cfg["topic_query"].get("year_to")
    now_year = datetime.datetime.utcnow().year
    if year_to == "CURRENT_YEAR":
        year_to = now_year
    if year_from and year_to:
        query += f" AND PY=({year_from}-{year_to})"
    elif year_from:
        query += f" AND PY=({year_from}-{now_year})"
    return query


def fetch_wos(query: str, headers: dict, cfg: dict, max_results: int = 200) -> list:
    retries = cfg["fetch"].get("retry_attempts", 3)
    backoff = cfg["fetch"].get("retry_backoff_seconds", 5)
    rps_delay = 1.0 / cfg["fetch"].get("requests_per_second", 2)

    results, page = [], 1
    while len(results) < max_results:
        limit = min(50, max_results - len(results))
        params = {"q": query, "limit": limit, "page": page, "sortField": "PY+D"}

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
                    print(f"ERROR fetching '{query}' page {page}: {e}", file=sys.stderr)
                    raise
                time.sleep(backoff)

        data = resp.json()
        hits = data.get("hits", [])
        total = data.get("metadata", {}).get("total", 0)
        results.extend(hits)
        if len(results) >= total or not hits:
            break
        page += 1
        time.sleep(max(rps_delay, 0.5))
    return results


def parse_record(hit: dict) -> dict:
    names = hit.get("names", {})
    authors = []
    for a in names.get("authors", []) or []:
        last = a.get("lastName") or ""
        first = a.get("firstName") or ""
        display = a.get("displayName") or (f"{last}, {first}".strip(", "))
        authors.append(display)

    source = hit.get("source", {}) or {}
    pages = source.get("pages") or {}
    if isinstance(pages, dict):
        page_range = pages.get("range", "")
    else:
        page_range = str(pages)

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
    if isinstance(keywords_obj, dict):
        keywords = keywords_obj.get("authorKeywords") or []
    else:
        keywords = []

    metrics = hit.get("metrics") or {}
    citations = metrics.get("timesCited", 0) if isinstance(metrics, dict) else 0

    oa = hit.get("openAccess") or {}
    if isinstance(oa, dict):
        is_oa = bool(oa.get("isOa", False) or oa.get("oases"))
    else:
        is_oa = False

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
    }


def merge_unique(target_list: list, seen: set, hits: list, source_label: str):
    added = 0
    for hit in hits:
        rec = parse_record(hit)
        rec["sources"] = [source_label]
        key = rec["doi"] or rec["uid"]
        if not key:
            continue
        if key in seen:
            for existing in target_list:
                if (existing["doi"] or existing["uid"]) == key:
                    if source_label not in existing["sources"]:
                        existing["sources"].append(source_label)
                    break
        else:
            seen.add(key)
            target_list.append(rec)
            added += 1
    return added


def main():
    cfg = load_config(CONFIG_PATH)

    api_key = os.environ.get("WOS_API_KEY")
    if not api_key:
        print("ERROR: WOS_API_KEY environment variable is not set.", file=sys.stderr)
        raise SystemExit(1)
    headers = {"X-ApiKey": api_key, "Accept": "application/json"}

    topic_max = cfg["topic_query"].get("max_results", 200)
    journal_max = cfg["fetch"].get("journal_max_results", 25) or 0
    journals = cfg.get("journals_of_interest") or []
    topic_query = build_topic_query(cfg)

    print(f"Config loaded from {CONFIG_PATH}")
    print(f"Topic query : {topic_query}")
    print(f"Journals    : {len(journals)} configured, "
          f"fetching {journal_max} latest each")

    seen, pubs = set(), []

    print("\nFetching topic-interest publications...")
    topic_hits = fetch_wos(topic_query, headers, cfg, max_results=topic_max)
    added = merge_unique(pubs, seen, topic_hits, "topic")
    print(f"  → {len(topic_hits)} hits ({added} new)")

    if journal_max > 0 and journals:
        for j in journals:
            j_query = f'SO=("{j}")'
            print(f"Fetching latest from journal: {j}")
            try:
                hits = fetch_wos(j_query, headers, cfg, max_results=journal_max)
            except requests.RequestException as e:
                print(f"  ! Skipping journal '{j}': {e}", file=sys.stderr)
                continue
            added = merge_unique(pubs, seen, hits, "journal")
            print(f"  → {len(hits)} hits ({added} new)")

    for eq in cfg.get("extra_queries") or []:
        label = eq.get("label", "(unnamed)")
        print(f"Fetching extra query: {label}")
        hits = fetch_wos(
            eq["query"], headers, cfg, max_results=eq.get("max_results", 50)
        )
        added = merge_unique(pubs, seen, hits, f"extra:{label}")
        print(f"  → {len(hits)} hits ({added} new)")

    if not pubs:
        print(
            "ERROR: No publications fetched. Aborting to protect existing data.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    pubs.sort(
        key=lambda p: int(p["year"]) if str(p["year"]).isdigit() else 0,
        reverse=True,
    )

    output = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "total": len(pubs),
        "site": cfg.get("site", {}),
        "journals_of_interest": journals,
        "publications": pubs,
    }

    os.makedirs("data", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(pubs)} publications to {OUT_PATH}")


if __name__ == "__main__":
    main()
