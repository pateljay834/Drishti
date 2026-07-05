"""
DRISHTI — News module v4
Loads all feed configuration from static/data/news_sources.json.
Supports national (by category) and per-state feeds.
Add/edit/remove feeds by editing the JSON — no Python changes needed.
"""

import os, json, re, html, logging, hashlib, time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import requests, feedparser, difflib
from modules import cache

logger      = logging.getLogger("drishti")
TIMEOUT     = 10
SOURCES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static", "data", "news_sources.json"
)

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Connection":      "keep-alive",
}

ALL_CATEGORIES = [
    "national","business","markets","politics","technology",
    "sports","health","science","defence","environment",
    "entertainment","international","policy","regional",
]

# ── Source registry ────────────────────────────────────────────────
_sources_cache: dict | None = None
_sources_mtime: float       = 0.0

def load_sources(force: bool = False) -> dict:
    """Load news_sources.json, re-reading if file changed on disk."""
    global _sources_cache, _sources_mtime
    try:
        mtime = os.path.getmtime(SOURCES_FILE)
    except Exception:
        mtime = 0.0

    if _sources_cache is None or force or mtime != _sources_mtime:
        try:
            with open(SOURCES_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            _sources_cache = raw
            _sources_mtime = mtime
            n = len(raw.get("national", []))
            s = sum(len(v) for v in raw.get("states", {}).values())
            logger.info(f"[news] Sources loaded: {n} national, {s} state feeds")
        except Exception as e:
            logger.error(f"[news] Failed to load news_sources.json: {e}")
            _sources_cache = {"national": [], "states": {}}
    return _sources_cache


def get_national_sources(enabled_only: bool = True) -> list:
    d = load_sources()
    feeds = d.get("national", [])
    return [f for f in feeds if (not enabled_only or f.get("enabled", True))]


def get_state_sources(state_id: str, enabled_only: bool = True) -> list:
    d = load_sources()
    feeds = d.get("states", {}).get(state_id, [])
    return [f for f in feeds if (not enabled_only or f.get("enabled", True))]


def get_all_state_sources(enabled_only: bool = True) -> dict:
    d = load_sources()
    result = {}
    for sid, feeds in d.get("states", {}).items():
        filtered = [f for f in feeds if (not enabled_only or f.get("enabled", True))]
        if filtered:
            result[sid] = filtered
    return result


def save_sources(data: dict) -> bool:
    """Write updated sources back to JSON file."""
    global _sources_cache, _sources_mtime
    try:
        with open(SOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _sources_cache = data
        _sources_mtime = os.path.getmtime(SOURCES_FILE)
        logger.info("[news] news_sources.json saved")
        return True
    except Exception as e:
        logger.error(f"[news] Save error: {e}")
        return False


# ── Feed fetching ──────────────────────────────────────────────────
def _clean(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _esc(text: str) -> str:
    return html.escape(_clean(text), quote=True)


def _parse_date(entry) -> tuple:
    """Return (display_str, unix_timestamp) for sorting."""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                ts = time.mktime(parsed)
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                return _fmt_relative(dt), ts
            except Exception:
                pass
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                dt  = parsedate_to_datetime(raw)
                ts  = dt.timestamp()
                return _fmt_relative(dt), ts
            except Exception:
                pass
    return "Recently", time.time()


def _fmt_relative(dt: datetime) -> str:
    """Human-friendly 'X hours ago'."""
    try:
        now   = datetime.now(tz=timezone.utc)
        delta = now - dt.astimezone(timezone.utc)
        secs  = int(delta.total_seconds())
        if secs < 0:
            return "Just now"
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs//60}m ago"
        if secs < 86400:
            return f"{secs//3600}h ago"
        if secs < 604800:
            return f"{secs//86400}d ago"
        return dt.strftime("%d %b %Y")
    except Exception:
        return "Recently"


def _is_breaking(title: str) -> bool:
    kws = ["breaking", "just in", "alert", "urgent", "flash", "live:"]
    return any(kw in title.lower() for kw in kws)


def _article_id(title: str, link: str) -> str:
    return hashlib.md5((title[:80] + link[:60]).encode()).hexdigest()[:12]


def _fetch_feed(source: dict) -> list:
    """Download one RSS feed and return parsed article list."""
    items = []
    try:
        resp = requests.get(source["url"], timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if not feed.entries:
            logger.warning(f"[news] No entries: {source['id']}")
            return []
        for entry in feed.entries[:20]:
            title   = _esc(entry.get("title") or "")
            link    = entry.get("link") or "#"
            summary = _esc(entry.get("summary") or entry.get("description") or "")[:400]
            pub_str, pub_ts = _parse_date(entry)
            if not title:
                continue
            items.append({
                "id":          _article_id(title, link),
                "title":       title,
                "link":        link,
                "summary":     summary,
                "pub_display": pub_str,
                "pub_ts":      pub_ts,
                "source_id":   source["id"],
                "source_name": source["name"],
                "source_icon": source.get("icon", source["name"][:3].upper()),
                "category":    source.get("category","national"),
                "language":    source.get("language","en"),
                "is_breaking": _is_breaking(title),
                "priority":    source.get("priority", 50),
            })
        logger.info(f"[news] OK {source['id']}: {len(items)} articles")
    except requests.exceptions.Timeout:
        logger.error(f"[news] Timeout: {source['id']}")
        _record_health(source["id"], "timeout")
    except requests.exceptions.HTTPError as e:
        logger.error(f"[news] HTTP {e.response.status_code}: {source['id']}")
        _record_health(source["id"], f"http_{e.response.status_code}")
    except Exception as e:
        logger.error(f"[news] Error {source['id']}: {e}")
        _record_health(source["id"], "error")
    return items


# ── Feed health tracking ──────────────────────────────────────────
_health: dict = {}

def _record_health(source_id: str, status: str):
    import pytz
    ts = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %H:%M IST")
    prev = _health.get(source_id, {})
    _health[source_id] = {
        "status":        status,
        "last_error":    ts,
        "fail_count":    prev.get("fail_count", 0) + 1,
        "last_success":  prev.get("last_success", "Never"),
    }

def _record_success(source_id: str):
    import pytz
    ts = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %H:%M IST")
    prev = _health.get(source_id, {})
    _health[source_id] = {
        "status":       "ok",
        "last_success": ts,
        "fail_count":   0,
        "last_error":   prev.get("last_error", "Never"),
    }

def get_feed_health() -> dict:
    return dict(_health)


# ── Deduplication ─────────────────────────────────────────────────
def _deduplicate(articles: list, threshold: float = 0.72) -> list:
    seen, out = [], []
    for a in articles:
        t = a["title"].lower()
        if not any(difflib.SequenceMatcher(None, t, s).ratio() > threshold for s in seen):
            out.append(a)
            seen.append(t)
    return out


def _sort_articles(articles: list) -> list:
    """Sort by timestamp desc, breaking news first."""
    breaking = [a for a in articles if a["is_breaking"]]
    normal   = [a for a in articles if not a["is_breaking"]]
    normal.sort(key=lambda x: x.get("pub_ts", 0), reverse=True)
    breaking.sort(key=lambda x: x.get("pub_ts", 0), reverse=True)
    return breaking + normal


# ── Trending keywords ──────────────────────────────────────────────
STOP_WORDS = {
    "the","a","an","in","of","to","for","and","or","is","are","was","were",
    "with","at","by","from","on","has","have","will","be","been","his","her",
    "their","this","that","it","as","he","she","but","not","after","after",
    "india","says","over","amid","new","get","two","per","cent","rs","crore",
    "year","years","day","days","how","why","who","what","when","where","us",
    "pm","cm","amid","also","more","than","them","into","its","amid","amid",
}

def extract_trending(articles: list, top_n: int = 15) -> list:
    from collections import Counter
    words = []
    for a in articles[:100]:
        for w in re.findall(r"\b[A-Za-z]{4,}\b", a["title"]):
            w = w.lower()
            if w not in STOP_WORDS:
                words.append(w.title())
    counter = Counter(words)
    return [{"word": w, "count": c} for w, c in counter.most_common(top_n)]


# ── National news API ──────────────────────────────────────────────
def fetch_national_news(ttl: int = 15) -> list:
    cached = cache.get("national_news", ttl_minutes=ttl)
    if cached:
        return cached
    sources  = get_national_sources()
    articles = []
    for src in sorted(sources, key=lambda x: x.get("priority", 50), reverse=True):
        fetched = _fetch_feed(src)
        if fetched:
            _record_success(src["id"])
            articles.extend(fetched)
    articles = _deduplicate(articles)
    articles = _sort_articles(articles)
    cache.set("national_news", articles)
    logger.info(f"[news] National: {len(articles)} unique articles")
    return articles


def fetch_news_by_category(category: str, ttl: int = 15) -> list:
    all_articles = fetch_national_news(ttl=ttl)
    if category == "all" or not category:
        return all_articles
    return [a for a in all_articles if a.get("category") == category]


def get_top_headlines(n: int = 10, ttl: int = 15) -> list:
    return fetch_national_news(ttl=ttl)[:n]


# ── State news API ─────────────────────────────────────────────────
def fetch_state_news(state_id: str, ttl: int = 20) -> list:
    """Fetch state-specific feeds + national articles mentioning the state."""
    cache_key = f"state_news_{state_id}"
    cached    = cache.get(cache_key, ttl_minutes=ttl)
    if cached:
        return cached

    # 1. State-specific RSS feeds
    local_sources = get_state_sources(state_id)
    local_articles = []
    for src in local_sources:
        fetched = _fetch_feed(src)
        if fetched:
            _record_success(src["id"])
            local_articles.extend(fetched)

    # 2. National news tagged with this state's keywords
    tagged = fetch_news_for_state(state_id, ttl=ttl)

    # Merge — local feeds first, then tagged national
    combined = local_articles + [a for a in tagged if a["id"] not in {x["id"] for x in local_articles}]
    combined = _deduplicate(combined)
    combined = _sort_articles(combined)

    cache.set(cache_key, combined)
    logger.info(f"[news] State {state_id}: {len(local_articles)} local + {len(tagged)} national tagged")
    return combined


STATE_KEYWORDS = {
    "maharashtra":     ["maharashtra","mumbai","pune","nagpur","nashik","thane","aurangabad"],
    "delhi":           ["delhi","new delhi","ncr","dwarka","rohini","connaught"],
    "karnataka":       ["karnataka","bengaluru","bangalore","mysuru","mysore","mangaluru","hubli"],
    "gujarat":         ["gujarat","ahmedabad","surat","vadodara","rajkot","gandhinagar","jamnagar"],
    "tamil_nadu":      ["tamil nadu","chennai","coimbatore","madurai","trichy","tirunelveli","salem"],
    "telangana":       ["telangana","hyderabad","secunderabad","warangal","karimnagar"],
    "uttar_pradesh":   ["uttar pradesh","lucknow","kanpur","agra","varanasi","prayagraj","noida","ghaziabad","meerut"],
    "west_bengal":     ["west bengal","kolkata","calcutta","howrah","siliguri","durgapur","asansol"],
    "rajasthan":       ["rajasthan","jaipur","jodhpur","udaipur","kota","ajmer","bikaner","alwar"],
    "andhra_pradesh":  ["andhra pradesh","amaravati","visakhapatnam","vijayawada","guntur","tirupati","kakinada"],
    "kerala":          ["kerala","thiruvananthapuram","kochi","kozhikode","thrissur","kollam","palakkad"],
    "madhya_pradesh":  ["madhya pradesh","bhopal","indore","jabalpur","gwalior","ujjain","sagar"],
    "punjab":          ["punjab","ludhiana","amritsar","jalandhar","patiala","mohali","bathinda"],
    "haryana":         ["haryana","gurugram","gurgaon","faridabad","panipat","ambala","rohtak","karnal"],
    "odisha":          ["odisha","bhubaneswar","cuttack","rourkela","brahmapur","sambalpur","puri"],
    "bihar":           ["bihar","patna","gaya","muzaffarpur","bhagalpur","darbhanga","purnia","nalanda"],
    "jharkhand":       ["jharkhand","ranchi","jamshedpur","dhanbad","bokaro","hazaribagh","giridih"],
    "assam":           ["assam","guwahati","dispur","dibrugarh","tezpur","jorhat","silchar","nagaon"],
    "chhattisgarh":    ["chhattisgarh","raipur","bhilai","bilaspur","korba","durg","rajnandgaon"],
    "uttarakhand":     ["uttarakhand","dehradun","haridwar","roorkee","rishikesh","nainital","haldwani"],
    "himachal_pradesh":["himachal pradesh","shimla","manali","dharamsala","solan","baddi","mandi"],
    "goa":             ["goa","panaji","margao","vasco","mapusa","ponda","calangute"],
    "jammu_kashmir":   ["jammu","kashmir","srinagar","anantnag","baramulla","sopore","j&k","jk"],
    "ladakh":          ["ladakh","leh","kargil","pangong","nubra"],
    "sikkim":          ["sikkim","gangtok","namchi","gyalshing","mangan"],
    "arunachal_pradesh":["arunachal pradesh","itanagar","tawang","ziro","naharlagun","pasighat"],
    "nagaland":        ["nagaland","kohima","dimapur","mokokchung","wokha","zunheboto"],
    "meghalaya":       ["meghalaya","shillong","tura","nongpoh","jowai","cherrapunji","mawsynram"],
    "manipur":         ["manipur","imphal","thoubal","bishnupur","churachandpur","ukhrul"],
    "mizoram":         ["mizoram","aizawl","lunglei","champhai","serchhip"],
    "tripura":         ["tripura","agartala","dharmanagar","udaipur","kailashahar"],
    "chandigarh":      ["chandigarh"],
    "puducherry":      ["puducherry","pondicherry","karaikal","mahe","yanam"],
    "andaman_nicobar": ["andaman","nicobar","port blair"],
    "lakshadweep":     ["lakshadweep","kavaratti","agatti"],
    "dadra_nagar_haveli":["silvassa","daman","diu","dadra","nagar haveli"],
}

def fetch_news_for_state(state_id: str, ttl: int = 15) -> list:
    """National articles tagged to a specific state via keyword matching."""
    try:
        kws      = STATE_KEYWORDS.get(state_id, [])
        articles = fetch_national_news(ttl=ttl)
        return [a for a in articles
                if any(kw in (a["title"] + " " + a.get("summary","")).lower() for kw in kws)]
    except Exception as e:
        logger.error(f"[news] State tag error ({state_id}): {e}")
        return []


# ── Feed management ────────────────────────────────────────────────
def test_feed_url(url: str) -> dict:
    """Test if an RSS URL is fetchable and returns articles."""
    try:
        resp = requests.get(url, timeout=8, headers=HEADERS, allow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        count = len(feed.entries)
        sample = feed.entries[0].get("title","") if count else ""
        return {"ok": True, "article_count": count, "sample_title": _clean(sample)[:100],
                "feed_title": _clean(feed.feed.get("title","Unknown Feed"))}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def add_source(source_data: dict, scope: str = "national", state_id: str = "") -> bool:
    """Add a new feed to national or state sources."""
    d = load_sources()
    src = {
        "id":          source_data.get("id","").strip() or f"custom_{int(time.time())}",
        "name":        source_data.get("name","Custom Feed").strip(),
        "url":         source_data.get("url","").strip(),
        "category":    source_data.get("category","national"),
        "language":    source_data.get("language","en"),
        "enabled":     source_data.get("enabled", True),
        "priority":    int(source_data.get("priority", 60)),
        "icon":        source_data.get("icon","").strip()[:5] or source_data["name"][:3].upper(),
        "description": source_data.get("description",""),
    }
    if scope == "state" and state_id:
        d.setdefault("states", {}).setdefault(state_id, []).append(src)
    else:
        d.setdefault("national", []).append(src)
    cache.clear("national_news")
    if state_id:
        cache.clear(f"state_news_{state_id}")
    return save_sources(d)


def toggle_source(source_id: str, enabled: bool) -> bool:
    """Enable or disable a feed by ID."""
    d = load_sources()
    changed = False
    for src in d.get("national", []):
        if src["id"] == source_id:
            src["enabled"] = enabled
            changed = True
    for feeds in d.get("states", {}).values():
        for src in feeds:
            if src["id"] == source_id:
                src["enabled"] = enabled
                changed = True
    if changed:
        cache.clear("national_news")
        return save_sources(d)
    return False


def delete_source(source_id: str) -> bool:
    """Remove a feed by ID."""
    d = load_sources()
    original_n = len(d.get("national", []))
    d["national"] = [s for s in d.get("national", []) if s["id"] != source_id]
    for sid in d.get("states", {}):
        d["states"][sid] = [s for s in d["states"][sid] if s["id"] != source_id]
    if len(d.get("national", [])) != original_n or True:
        cache.clear("national_news")
        return save_sources(d)
    return False


# ── Unified fetch (used by scheduler) ─────────────────────────────
def fetch_news(enabled_sources: dict = None, ttl: int = 15) -> list:
    """Backward-compatible wrapper returning national news."""
    return fetch_national_news(ttl=ttl)
