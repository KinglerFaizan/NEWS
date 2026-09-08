"""
news_providers.py
-----------------
Multi-source news ingestion layer for the Audit Intelligence briefing.

Tiering
    PRIMARY   NewsAPI.org + APITube.io   run together on every refresh
    RESERVE   NewsData.io                stays idle, spending none of its quota,
                                         until BOTH primaries are exhausted

Providers
    1. NewsAPI.org   -> https://newsapi.org/v2/everything
    2. APITube.io    -> https://api.apitube.io/v1/news/everything
    3. NewsData.io   -> https://newsdata.io/api/1/news

Every provider is optional. Supply one key, two, or all three — whatever is
present is used, and a missing/failed provider never breaks the others.

Normalized record schema (dict):
    title, description, content, url, image_url, source, published_at,
    author, providers (list of provider ids that returned this story)
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import requests


# =========================================================
# 1. PROVIDER REGISTRY
# =========================================================

PROVIDERS = {
    "newsapi": {
        "label": "NewsAPI.org",
        "endpoint": "https://newsapi.org/v2/everything",
        "signup": "https://newsapi.org/register",
        # Full boolean syntax supported; long queries are fine.
        "max_query_len": 500,
        "page_size": 100,
        "max_pages": 2,
        "tier": 1,          # primary — always runs
    },
    "apitube": {
        "label": "APITube.io",
        "endpoint": "https://api.apitube.io/v1/news/everything",
        "signup": "https://apitube.io/",
        # Boolean search is supported; keep variants moderate in length.
        "max_query_len": 300,
        # Free plan caps per_page at 10 — asking for more returns ER0171.
        # Raise to 50 (Starter) or 250 (Basic+) on a paid key.
        "page_size": 10,
        # Free plan allows only 10 requests/minute, so keep the request
        # count low rather than paginating.
        "max_pages": 1,
        "tier": 1,          # primary — always runs
    },
    "newsdata": {
        "label": "NewsData.io",
        "endpoint": "https://newsdata.io/api/1/news",
        "signup": "https://newsdata.io/register",
        # NewsData caps q at 100 chars on the free plan, and paginates with an
        # opaque cursor rather than page numbers — so only one page is fetched.
        "max_query_len": 100,
        "page_size": 50,
        "max_pages": 1,
        "tier": 2,          # reserve — only used when tier 1 is exhausted
    },
}

DEFAULT_TIMEOUT = 25

# Primary providers run together on every refresh. The reserve provider stays
# completely idle — burning none of its quota — until BOTH primaries are
# rate-limited or otherwise unusable, at which point it takes over.
PRIMARY_PROVIDERS = [p for p, c in PROVIDERS.items() if c["tier"] == 1]
RESERVE_PROVIDERS = [p for p, c in PROVIDERS.items() if c["tier"] == 2]


class QuotaExhausted(RuntimeError):
    """Raised when a provider refuses a request because its limit is spent."""


# Signals that a provider is out of quota rather than merely erroring.
_QUOTA_MARKERS = (
    "ratelimited", "rate limit", "rate-limit", "too many requests",
    "quota", "exhausted", "limit reached", "limit exceeded",
    "maximum requests", "daily limit", "upgrade", "requests per day",
    "you have made too many", "apikeyexhausted", "429",
)


def _is_quota_error(message: str, status_code=None) -> bool:
    if status_code in (429, 402):
        return True
    m = (message or "").lower()
    return any(marker in m for marker in _QUOTA_MARKERS)


# =========================================================
# 2. QUERY SETS
#    Each provider gets phrasing tuned to its own syntax limits.
#    More variants = more distinct articles reaching the dedup stage.
# =========================================================

QUERIES_NEWSAPI = {
    "Transformation": [
        '("bank" OR "banking") AND ("audit" OR "internal controls" OR "risk" OR "governance") AND ("digital transformation" OR "core banking" OR "automation" OR "artificial intelligence" OR "cloud")',
        '("bank" OR "banking") AND ("core banking" OR "digital banking" OR "cloud migration" OR "operating model" OR "modernisation")',
        '("bank" OR "lender") AND ("artificial intelligence" OR "generative AI" OR "machine learning") AND ("risk" OR "controls" OR "governance")',
    ],
    "Regulation": [
        '("bank" OR "banking") AND ("compliance" OR "internal controls" OR "audit") AND ("regulation" OR "regulatory" OR "supervision" OR "RBI" OR "Basel" OR "AML" OR "KYC" OR "enforcement")',
        '("Reserve Bank of India" OR "RBI" OR "central bank") AND ("circular" OR "guidelines" OR "penalty" OR "supervisory action" OR "master direction")',
        '("bank" OR "banking") AND ("anti-money laundering" OR "AML" OR "KYC" OR "sanctions" OR "financial crime" OR "fraud" OR "fined")',
        '("bank" OR "financial institution") AND ("Basel" OR "prudential" OR "capital adequacy" OR "stress test" OR "supervisory review")',
    ],
    "People": [
        '("bank" OR "banking") AND ("audit" OR "risk" OR "governance") AND ("appointed" OR "CEO" OR "CFO" OR "CRO" OR "chief audit" OR "audit committee" OR "board")',
        '("bank" OR "banking group") AND ("chief audit executive" OR "head of internal audit" OR "chief risk officer" OR "chief compliance officer")',
        '("bank" OR "lender") AND ("resigns" OR "steps down" OR "succession" OR "board appointment" OR "reshuffle")',
    ],
    "Global Banks": [
        '("audit" OR "internal controls" OR "risk" OR "regulatory") AND ("HSBC" OR "JPMorgan" OR "Citigroup" OR "Barclays" OR "Deutsche Bank" OR "UBS" OR "BNP Paribas" OR "Standard Chartered")',
        '("Bank of America" OR "Goldman Sachs" OR "Morgan Stanley" OR "Wells Fargo" OR "ICBC" OR "MUFG" OR "Mizuho") AND ("audit" OR "risk" OR "compliance" OR "regulator" OR "fine")',
        '("HSBC" OR "Standard Chartered" OR "Citi" OR "Barclays" OR "UBS") AND ("investigation" OR "probe" OR "penalty" OR "settlement" OR "internal review")',
    ],
}

# APITube searches the headline via the `title` filter and supports boolean
# operators. Kept to 8 variants total so a free key (10 requests/minute)
# never trips its rate limit in a single refresh.
QUERIES_APITUBE = {
    "Transformation": [
        'bank AND ("digital transformation" OR "core banking" OR automation)',
        'banking AND ("artificial intelligence" OR cloud OR modernisation)',
    ],
    "Regulation": [
        'bank AND (regulation OR regulatory OR compliance OR supervision)',
        '(RBI OR "central bank") AND (penalty OR guidelines OR circular)',
        'bank AND ("money laundering" OR AML OR KYC OR sanctions OR fraud)',
    ],
    "People": [
        'bank AND ("chief risk officer" OR "chief audit" OR "audit committee")',
    ],
    "Global Banks": [
        '(HSBC OR JPMorgan OR Citigroup OR Barclays) AND (audit OR risk OR fine)',
        '(UBS OR "Deutsche Bank" OR "Goldman Sachs" OR "Standard Chartered")',
    ],
}

QUERIES_NEWSDATA = {
    "Transformation": [
        'bank AND ("digital transformation" OR "core banking")',
        'banking AND ("artificial intelligence" OR cloud)',
    ],
    "Regulation": [
        'bank AND (regulation OR compliance OR supervision)',
        'RBI AND (penalty OR guidelines OR circular)',
        'bank AND ("money laundering" OR AML OR KYC OR fraud)',
    ],
    "People": [
        'bank AND ("chief risk officer" OR "audit committee")',
        'bank AND (appointed OR resigns OR board)',
    ],
    "Global Banks": [
        'HSBC OR JPMorgan OR Citigroup OR Barclays',
        'UBS OR "Deutsche Bank" OR "Goldman Sachs"',
    ],
}

PROVIDER_QUERIES = {
    "newsapi": QUERIES_NEWSAPI,
    "apitube": QUERIES_APITUBE,
    "newsdata": QUERIES_NEWSDATA,
}

CATEGORY_NAMES = list(QUERIES_NEWSAPI.keys())


# =========================================================
# 3. PER-PROVIDER FETCH ADAPTERS
#    Each returns: (list_of_normalized_records, total_reported)
# =========================================================

def _blank_to_none(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def fetch_newsapi(query, api_key, from_date, page, cfg):
    params = {
        "q": query[: cfg["max_query_len"]],
        "from": from_date,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": cfg["page_size"],
        "page": page,
        "apiKey": api_key,
    }
    resp = requests.get(cfg["endpoint"], params=params, timeout=DEFAULT_TIMEOUT)
    try:
        payload = resp.json()
    except ValueError:
        payload = {}

    if payload.get("status") != "ok":
        msg = payload.get("message") or f"HTTP {resp.status_code}"
        code = payload.get("code", "")
        if _is_quota_error(f"{code} {msg}", resp.status_code):
            raise QuotaExhausted(msg)
        raise RuntimeError(msg)

    rows = []
    for a in payload.get("articles", []):
        rows.append({
            "title": _blank_to_none(a.get("title")),
            "description": _blank_to_none(a.get("description")) or "",
            "content": _blank_to_none(a.get("content")) or "",
            "url": _blank_to_none(a.get("url")) or "",
            "image_url": _blank_to_none(a.get("urlToImage")) or "",
            "source": _blank_to_none((a.get("source") or {}).get("name")) or "Unknown",
            "published_at": _blank_to_none(a.get("publishedAt")) or "",
            "author": _blank_to_none(a.get("author")) or "",
        })
    return rows, payload.get("totalResults", 0)


def fetch_apitube(query, api_key, from_date, page, cfg):
    """
    APITube /v1/news/everything.

    Docs: https://docs.apitube.io/platform/news-api/everything
    Auth is sent as the X-API-Key header (preferred over the api_key query
    parameter, which would expose the key in URLs and logs).

    Two failure modes are deliberately distinguished:
      * HTTP 429              -> per-minute rate limit. Costs no credit, so it
                                 is retried briefly rather than treated as fatal.
      * HTTP 402 / ER0176     -> the plan's credit quota is spent -> QuotaExhausted,
                                 which is what triggers failover to the reserve.
    """
    params = {
        "title": query[: cfg["max_query_len"]],
        "language.code": "en",
        "published_at.start": from_date,
        "sort.by": "published_at",
        "sort.order": "desc",
        "per_page": cfg["page_size"],
        "page": page,
    }
    headers = {"X-API-Key": api_key}

    payload = {}
    resp = None

    # One short retry: a 429 here is a speed cap, not an exhausted plan.
    for attempt in range(2):
        resp = requests.get(
            cfg["endpoint"], params=params, headers=headers, timeout=DEFAULT_TIMEOUT
        )
        if resp.status_code == 429 and attempt == 0:
            time.sleep(2.5)
            continue
        break

    try:
        payload = resp.json()
    except ValueError:
        payload = {}

    if resp.status_code == 429:
        raise RuntimeError("rate limited (10 req/min on the free plan) — retry shortly")

    if payload.get("status") != "ok":
        # Errors arrive as {"status":"error","code":"ER0176","message":"..."}
        code = str(payload.get("code") or "")
        msg = payload.get("message") or f"HTTP {resp.status_code}"

        # ER0176 = no points left; ER0201/0202/0230 = auth problems
        if resp.status_code == 402 or "ER0176" in code:
            raise QuotaExhausted(msg)
        if _is_quota_error(f"{code} {msg}", resp.status_code):
            raise QuotaExhausted(msg)
        raise RuntimeError(f"{code} {msg}".strip())

    rows = []
    for a in payload.get("results", []) or []:
        source = a.get("source") or {}
        author = a.get("author") or {}

        # Free plans truncate the body and tag it "[Upgrade subscription plan]";
        # that marker is stripped so it never pollutes relevance scoring.
        body = _blank_to_none(a.get("body")) or ""
        for marker in ("[Upgrade subscription plan]",
                       "[Test mode — use a live key for full content]"):
            body = body.replace(marker, "")

        rows.append({
            "title": _blank_to_none(a.get("title")),
            "description": _blank_to_none(a.get("description")) or "",
            "content": body.strip(),
            "url": _blank_to_none(a.get("href")) or "",
            "image_url": _blank_to_none(a.get("image")) or "",
            "source": (
                _blank_to_none(source.get("domain"))
                or _blank_to_none(source.get("name"))
                or "Unknown"
            ),
            "published_at": _blank_to_none(a.get("published_at")) or "",
            "author": _blank_to_none(author.get("name")) or "",
        })

    return rows, payload.get("limit", len(rows))


def fetch_newsdata(query, api_key, from_date, page, cfg):
    # NewsData paginates with an opaque cursor, not an integer page number,
    # so only page 1 is requested here; breadth comes from query variants.
    if page > 1:
        return [], 0

    params = {
        "apikey": api_key,
        "q": query[: cfg["max_query_len"]],
        "language": "en",
        "category": "business,technology,politics,world",
    }
    resp = requests.get(cfg["endpoint"], params=params, timeout=DEFAULT_TIMEOUT)
    try:
        payload = resp.json()
    except ValueError:
        payload = {}

    if payload.get("status") != "success":
        res = payload.get("results")
        msg = res.get("message") if isinstance(res, dict) else payload.get("message")
        code = res.get("code", "") if isinstance(res, dict) else ""
        msg = msg or f"HTTP {resp.status_code}"
        if _is_quota_error(f"{code} {msg}", resp.status_code):
            raise QuotaExhausted(msg)
        raise RuntimeError(msg)

    rows = []
    for a in payload.get("results", []) or []:
        img = _blank_to_none(a.get("image_url")) or ""
        creator = a.get("creator")
        author = ", ".join(creator) if isinstance(creator, list) else (creator or "")

        # NewsData returns "YYYY-MM-DD HH:MM:SS" in UTC
        pub = _blank_to_none(a.get("pubDate")) or ""
        if pub and "T" not in pub:
            pub = pub.replace(" ", "T") + "Z"

        rows.append({
            "title": _blank_to_none(a.get("title")),
            "description": _blank_to_none(a.get("description")) or "",
            "content": _blank_to_none(a.get("content")) or "",
            "url": _blank_to_none(a.get("link")) or "",
            "image_url": img,
            "source": _blank_to_none(a.get("source_id")) or "Unknown",
            "published_at": pub,
            "author": author,
        })
    return rows, payload.get("totalResults", 0)


FETCHERS = {
    "newsapi": fetch_newsapi,
    "apitube": fetch_apitube,
    "newsdata": fetch_newsdata,
}


# =========================================================
# 4. DEDUPLICATION
#    Three passes, cheapest first:
#      a) canonical URL match   (same link, different tracking params)
#      b) exact normalized title
#      c) fuzzy token-overlap   (same story, reworded headline)
# =========================================================

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "cmpid", "icid")

_TITLE_NOISE = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

# Dropped when comparing headlines — they carry no distinguishing signal
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "at",
    "by", "from", "as", "is", "are", "was", "were", "be", "been", "it", "its",
    "that", "this", "these", "those", "after", "over", "amid", "says", "say",
    "new", "news", "report", "reports", "update", "updates", "live",
}


def canonical_url(url: str) -> str:
    """Strip scheme, www, tracking params, AMP suffixes and trailing slashes."""
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
    except Exception:
        return url.strip().lower()

    netloc = (p.netloc or "").lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if netloc.startswith("amp."):
        netloc = netloc[4:]

    path = (p.path or "").rstrip("/")
    for suffix in ("/amp", ".amp", "/amp.html"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]

    keep = [
        (k, v) for k, v in parse_qsl(p.query or "")
        if not any(k.lower().startswith(t) for t in TRACKING_PREFIXES)
    ]
    query = urlencode(sorted(keep))

    return urlunparse(("", netloc, path, "", query, "")).lstrip("/").lower()


def normalize_title(title: str) -> str:
    """Lowercase, drop publisher suffix (' - Reuters') and punctuation."""
    if not title:
        return ""
    t = title.lower().strip()
    # Publishers commonly append " - Outlet" or " | Outlet"
    for sep in (" - ", " | ", " — ", " – "):
        if sep in t:
            head, _, tail = t.rpartition(sep)
            # only strip if the tail looks like an outlet name
            if head and len(tail.split()) <= 5:
                t = head
    t = _TITLE_NOISE.sub(" ", t)
    return _WS.sub(" ", t).strip()


def title_tokens(title: str) -> frozenset:
    return frozenset(
        w for w in normalize_title(title).split()
        if w not in STOPWORDS and len(w) > 2
    )


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


def overlap_coef(a: frozenset, b: frozenset) -> float:
    """Containment: tolerant of one headline being much longer than the other."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def similarity(rec_a: dict, rec_b: dict) -> float:
    """
    Blended headline similarity in [0,1].

    Jaccard alone is too harsh when outlets reword ("fines" vs "penalised")
    or when one headline is much longer, so the strongest of three signals
    is used: set overlap, containment, and character-level sequence ratio.
    """
    ta, tb = rec_a["_tokens"], rec_b["_tokens"]
    if not ta or not tb:
        return 0.0

    j = jaccard(ta, tb)
    o = overlap_coef(ta, tb)
    r = SequenceMatcher(None, rec_a["_norm"], rec_b["_norm"]).ratio()

    # Containment is slightly discounted — on its own it over-merges
    # short headlines that happen to share a couple of entity words.
    return max(j, 0.92 * o, r)


def _richness(rec: dict) -> tuple:
    """Prefer the copy with an image, a longer description, and more providers."""
    return (
        1 if rec.get("image_url") else 0,
        len(rec.get("description") or ""),
        len(rec.get("content") or ""),
        len(rec.get("providers") or ()),
    )


def merge_records(keep: dict, other: dict) -> dict:
    """Fold `other` into `keep`, taking the better value for each field."""
    keep["providers"] = set(keep.get("providers", set())) | set(other.get("providers", set()))

    if not keep.get("image_url") and other.get("image_url"):
        keep["image_url"] = other["image_url"]
    if len(other.get("description") or "") > len(keep.get("description") or ""):
        keep["description"] = other["description"]
    if len(other.get("content") or "") > len(keep.get("content") or ""):
        keep["content"] = other["content"]
    if not keep.get("author") and other.get("author"):
        keep["author"] = other["author"]
    if not keep.get("published_at") and other.get("published_at"):
        keep["published_at"] = other["published_at"]

    return keep


def deduplicate(records: list, fuzzy_threshold: float = 0.72) -> tuple:
    """
    Collapse duplicates across providers.
    Returns (unique_records, stats_dict).
    """
    stats = {"by_url": 0, "by_title": 0, "by_fuzzy": 0}

    # Richest copies first so the survivor of each clash is the best one
    ordered = sorted(records, key=_richness, reverse=True)

    by_url = {}
    by_title = {}
    survivors = []

    for rec in ordered:
        if not rec.get("title"):
            continue
        if rec["title"].strip().lower().startswith("[removed]"):
            continue

        cu = canonical_url(rec.get("url", ""))
        nt = normalize_title(rec["title"])

        if cu and cu in by_url:
            merge_records(by_url[cu], rec)
            stats["by_url"] += 1
            continue

        if nt and nt in by_title:
            merge_records(by_title[nt], rec)
            stats["by_title"] += 1
            continue

        rec["providers"] = set(rec.get("providers", set()))
        rec["_tokens"] = title_tokens(rec["title"])
        rec["_norm"] = nt

        survivors.append(rec)
        if cu:
            by_url[cu] = rec
        if nt:
            by_title[nt] = rec

    # Fuzzy pass — same story, differently worded headline.
    # Bucketed by shared token so this stays near-linear instead of O(n^2).
    final = []
    buckets = {}

    for rec in survivors:
        toks = rec["_tokens"]
        candidate_ids = set()
        for tok in toks:
            candidate_ids.update(buckets.get(tok, ()))

        matched = None
        best = 0.0
        for idx in candidate_ids:
            score = similarity(rec, final[idx])
            if score >= fuzzy_threshold and score > best:
                best, matched = score, idx

        if matched is not None:
            merge_records(final[matched], rec)
            stats["by_fuzzy"] += 1
            continue

        final.append(rec)
        new_idx = len(final) - 1
        for tok in toks:
            buckets.setdefault(tok, []).append(new_idx)

    for rec in final:
        rec.pop("_tokens", None)
        rec.pop("_norm", None)
        rec["providers"] = sorted(rec.get("providers", set()))

    return final, stats


# =========================================================
# 5. ORCHESTRATION — tiered failover
# =========================================================

def build_jobs(api_keys: dict, provider_ids, categories=None):
    """Expand the given providers x category x query variant x page."""
    jobs = []
    for pid in provider_ids:
        cfg = PROVIDERS[pid]
        key = (api_keys.get(pid) or "").strip()
        if not key:
            continue

        qset = PROVIDER_QUERIES[pid]
        for category, queries in qset.items():
            if categories and category not in categories:
                continue
            for query in queries:
                for page in range(1, cfg["max_pages"] + 1):
                    jobs.append((pid, category, query, page, key, cfg))
    return jobs


def _run_tier(provider_ids, api_keys, from_date, categories, max_workers,
              per_provider, errors):
    """
    Execute one tier of providers in parallel.

    Returns (records, exhausted_set). A provider lands in `exhausted` when
    every one of its requests failed AND at least one failure was a quota
    refusal — i.e. the key is genuinely spent, not just erroring sporadically.
    """
    jobs = build_jobs(api_keys, provider_ids, categories)
    if not jobs:
        return [], set()

    raw = []
    quota_hits = {pid: 0 for pid in provider_ids}
    failures = {pid: 0 for pid in provider_ids}
    attempts = {pid: 0 for pid in provider_ids}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {}
        for pid, category, query, page, key, cfg in jobs:
            fut = ex.submit(FETCHERS[pid], query, key, from_date, page, cfg)
            futures[fut] = (pid, category, page)

        for fut in as_completed(futures):
            pid, category, page = futures[fut]
            attempts[pid] += 1
            per_provider[pid]["requests"] += 1

            try:
                rows, _total = fut.result()
                per_provider[pid]["articles"] += len(rows)
                for r in rows:
                    r["category_hint"] = category
                    r["providers"] = {pid}
                    raw.append(r)

            except QuotaExhausted as exc:
                quota_hits[pid] += 1
                failures[pid] += 1
                per_provider[pid]["quota_hits"] += 1
                if quota_hits[pid] == 1:      # report once, not 26 times
                    errors.append(
                        f"{PROVIDERS[pid]['label']}: quota reached — {exc}"
                    )

            except Exception as exc:
                msg = str(exc)
                failures[pid] += 1
                # Page-2 refusals on free tiers are a plan limit, not an outage
                if page > 1 and any(w in msg.lower() for w in
                                    ("upgrade", "developer", "limit", "paid", "plan")):
                    quota_hits[pid] += 1
                    continue
                per_provider[pid]["errors"] += 1
                errors.append(f"{PROVIDERS[pid]['label']} · {category} (p{page}): {msg}")

    exhausted = {
        pid for pid in provider_ids
        if attempts.get(pid, 0) > 0
        and failures[pid] == attempts[pid]
        and quota_hits[pid] > 0
    }
    return raw, exhausted


def fetch_all(api_keys: dict, lookback_days: int = 7, categories=None,
              fuzzy_threshold: float = 0.72, max_workers: int = 12):
    """
    Tiered ingestion.

      Tier 1 (NewsAPI.org + APITube.io) runs on every refresh, together.
      Tier 2 (NewsData.io) stays idle and spends none of its quota until
      BOTH tier-1 providers are exhausted, then transparently takes over.

    Returns (records, errors, stats).
    """
    from_date = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%d")

    per_provider = {
        pid: {"requests": 0, "articles": 0, "errors": 0, "quota_hits": 0, "used": False}
        for pid in PROVIDERS
    }
    errors = []

    primary = [p for p in PRIMARY_PROVIDERS if (api_keys.get(p) or "").strip()]
    reserve = [p for p in RESERVE_PROVIDERS if (api_keys.get(p) or "").strip()]

    if not primary and not reserve:
        return [], ["No API keys supplied — add at least one provider key."], {
            "per_provider": per_provider, "raw": 0, "unique": 0,
            "dedup": {"by_url": 0, "by_title": 0, "by_fuzzy": 0},
            "failover": False, "active": [], "exhausted": [],
        }

    raw = []
    exhausted = set()

    # ---- Tier 1: the two primaries, in parallel ----
    if primary:
        for pid in primary:
            per_provider[pid]["used"] = True
        raw, exhausted = _run_tier(
            primary, api_keys, from_date, categories, max_workers,
            per_provider, errors,
        )

    # ---- Tier 2: reserve engages only if every primary is spent ----
    failover = False
    primaries_down = bool(primary) and exhausted >= set(primary)

    if reserve and (primaries_down or not primary):
        failover = True
        for pid in reserve:
            per_provider[pid]["used"] = True

        reserve_raw, reserve_exhausted = _run_tier(
            reserve, api_keys, from_date, categories, max_workers,
            per_provider, errors,
        )
        raw.extend(reserve_raw)
        exhausted |= reserve_exhausted

        if primaries_down:
            errors.append(
                "Primary providers exhausted — switched to "
                + ", ".join(PROVIDERS[p]["label"] for p in reserve)
            )

    unique, dedup_stats = deduplicate(raw, fuzzy_threshold=fuzzy_threshold)

    stats = {
        "per_provider": per_provider,
        "raw": len(raw),
        "unique": len(unique),
        "dedup": dedup_stats,
        "failover": failover,
        "active": [p for p in PROVIDERS if per_provider[p]["used"]],
        "exhausted": sorted(exhausted),
    }
    return unique, errors, stats
