"""
DRISHTI — India Intelligence Platform v5
News-first architecture. Only genuinely live data is presented as live:
  - Markets & Currency: yfinance (real-time-ish, ~15min delayed)
  - News: 103 RSS feeds, national + state-specific, 12 languages
Economy and Mutual Funds pages removed — they relied on static/hardcoded
figures dressed up as live data, which was misleading.
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from werkzeug.security import check_password_hash
import config as cfg
from modules import markets, news, states, cache, scheduler
from datetime import datetime
from functools import wraps
import pytz, json, logging, secrets, os

IST = pytz.timezone("Asia/Kolkata")
app = Flask(__name__)
app.config["SECRET_KEY"]            = secrets.token_hex(32)
app.config["SESSION_COOKIE_SECURE"]  = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("drishti.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("drishti")


# ── Helpers ───────────────────────────────────────────────────────
def ist_now(): return datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")
def api_ok(data): return jsonify({"status": "ok", "data": data, "ts": ist_now()})
def api_err(msg, code=400):
    logger.error(f"API {code}: {msg}")
    return jsonify({"status": "error", "message": str(msg), "ts": ist_now()}), code

def _csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]

def _valid_state(s):  return bool(s) and s in states.STATES
def _valid_symbol(s): return bool(s) and len(s) <= 20 and all(c.isalnum() or c in "^.=/-" for c in s)

VALID_PERIODS   = {"1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","max"}
VALID_INTERVALS = {"1m","5m","15m","30m","60m","1d","1wk","1mo"}

def admin_required(f):
    @wraps(f)
    def dec(*a, **kw):
        conf = cfg.load_config()
        h    = conf.get("admin_password_hash")
        if not h: return f(*a, **kw)
        auth = request.headers.get("Authorization","")
        if auth.startswith("Bearer ") and check_password_hash(h, auth[7:]):
            return f(*a, **kw)
        return api_err("Unauthorized", 401)
    return dec


# ── Page routes ───────────────────────────────────────────────────
@app.route("/")
def dashboard():
    return render_template("dashboard.html", config=cfg.load_config(),
                           page="dashboard", ts=ist_now(), csrf_token=_csrf())

@app.route("/markets")
def markets_page():
    return render_template("markets.html", config=cfg.load_config(),
                           page="markets", ts=ist_now(), csrf_token=_csrf())

@app.route("/currency")
def currency_page():
    return render_template("currency.html", config=cfg.load_config(),
                           page="currency", ts=ist_now(), csrf_token=_csrf())

@app.route("/states")
def states_page():
    return render_template("states.html", config=cfg.load_config(), page="states",
                           region=request.args.get("region","").strip().lower(),
                           ts=ist_now(), csrf_token=_csrf())

@app.route("/state/<state_id>")
def state_detail(state_id):
    sid = state_id.strip().lower()
    if not _valid_state(sid): return redirect(url_for("states_page"))
    return render_template("state_detail.html", config=cfg.load_config(),
                           page="states", state=states.get_state(sid),
                           ts=ist_now(), csrf_token=_csrf())

@app.route("/news")
def news_page():
    return render_template("news.html", config=cfg.load_config(), page="news",
                           ts=ist_now(), csrf_token=_csrf())

@app.route("/news/feeds")
def feed_manager():
    all_states = [(s["id"], s["name"]) for s in states.get_state_summary()]
    all_states.sort(key=lambda x: x[1])
    return render_template("feed_manager.html", config=cfg.load_config(),
                           page="news", states_list=all_states,
                           ts=ist_now(), csrf_token=_csrf())

@app.route("/settings")
def settings_page():
    return render_template("settings.html", config=cfg.load_config(),
                           page="settings", ts=ist_now(), csrf_token=_csrf())


# ── Health ────────────────────────────────────────────────────────
@app.route("/api/health")
def api_health():
    return api_ok({"status": "healthy", "version": "5.0",
                   "scheduler": scheduler.get_status()})


# ── Dashboard — fast, zero blocking calls ─────────────────────────
@app.route("/api/dashboard")
def api_dashboard():
    """
    Returns quickly from cache. Markets and news are pre-warmed by the
    scheduler at startup, so this should never block on an external API.
    """
    try:
        summary    = markets.fetch_all_indices(ttl=5)
        headlines  = news.get_top_headlines(n=12)
        state_list = states.get_state_summary()

        def _pick(sym): return next((x for x in summary if x["symbol"] == sym), {})

        return api_ok({
            "ticker": {
                "sensex": _pick("^BSESN"), "nifty":  _pick("^NSEI"),
                "usdinr": _pick("USDINR=X"),"gold":  _pick("GC=F"),
                "crude":  _pick("CL=F"),
            },
            "indices":   summary,
            "headlines": headlines,
            "states":    state_list,
        })
    except Exception as e:
        logger.exception("Dashboard error")
        return api_err(str(e), 500)


# ── Markets ───────────────────────────────────────────────────────
@app.route("/api/markets")
def api_markets():
    try:
        force = request.args.get("force") == "1"
        if force:
            cache.clear("indices")
            cache.clear("top_stocks")
        return api_ok({"indices": markets.fetch_all_indices(ttl=0 if force else 5),
                       "stocks":  markets.fetch_top_stocks(ttl=0 if force else 10)})
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/markets/history/<path:symbol>")
def api_market_history(symbol):
    try:
        symbol   = symbol.strip().upper()
        period   = request.args.get("period",   "1mo").strip().lower()
        interval = request.args.get("interval", "1d").strip().lower()
        if not _valid_symbol(symbol):       return api_err("Invalid symbol", 400)
        if period   not in VALID_PERIODS:   return api_err("Invalid period", 400)
        if interval not in VALID_INTERVALS: return api_err("Invalid interval", 400)
        return api_ok(markets.fetch_history(symbol, period=period, interval=interval))
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/markets/extended")
def api_markets_extended():
    try:
        return api_ok(markets.fetch_extended_data())
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/currency")
def api_currency():
    try:
        force = request.args.get("force") == "1"
        if force:
            cache.clear("currency_rates")
        return api_ok({"rates": markets.fetch_currency_rates(ttl=0 if force else 5)})
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/currency/history/<path:symbol>")
def api_currency_history(symbol):
    try:
        symbol = symbol.strip().upper()
        period = request.args.get("period","1mo").strip().lower()
        if not _valid_symbol(symbol):   return api_err("Invalid symbol", 400)
        if period not in VALID_PERIODS: return api_err("Invalid period", 400)
        return api_ok(markets.fetch_history(symbol, period=period, interval="1d"))
    except Exception as e:
        return api_err(str(e), 500)


# ── News: National ────────────────────────────────────────────────
@app.route("/api/news")
def api_news():
    try:
        force    = request.args.get("force") == "1"
        category = request.args.get("category","").strip().lower()
        language = request.args.get("language","").strip().lower()
        source   = request.args.get("source","").strip().lower()

        if force:
            cache.clear("national_news")

        articles = news.fetch_national_news(ttl=0 if force else 15)
        if category and category != "all":
            articles = [a for a in articles if a.get("category") == category]
        if language:
            articles = [a for a in articles if a.get("language") == language]
        if source:
            articles = [a for a in articles if a.get("source_id") == source]

        trending = news.extract_trending(articles)
        health   = news.get_feed_health()
        sources  = [{"id":s["id"],"name":s["name"],"icon":s.get("icon","?"),
                     "category":s.get("category",""),"enabled":s.get("enabled",True)}
                    for s in news.get_national_sources()]

        return api_ok({
            "articles": articles, "total": len(articles),
            "trending": trending, "health": health, "sources": sources,
        })
    except Exception as e:
        logger.exception("National news error")
        return api_err(str(e), 500)


# ── News: State ───────────────────────────────────────────────────
@app.route("/api/news/state/<state_id>")
def api_news_state(state_id):
    try:
        state_id = state_id.strip().lower()
        if not _valid_state(state_id): return api_err("Unknown state", 400)
        force = request.args.get("force") == "1"
        if force: cache.clear(f"state_news_{state_id}")

        local_srcs = news.get_state_sources(state_id)
        articles   = news.fetch_state_news(state_id, ttl=0 if force else 20)
        local_ids  = {s["id"] for s in local_srcs}
        for a in articles:
            a["is_local"] = a.get("source_id","") in local_ids

        return api_ok({
            "articles": articles, "total": len(articles),
            "local_count": sum(1 for a in articles if a.get("is_local")),
            "national_count": sum(1 for a in articles if not a.get("is_local")),
            "local_sources": [{"id":s["id"],"name":s["name"],"icon":s.get("icon","?"),
                               "language":s.get("language","en")} for s in local_srcs],
        })
    except Exception as e:
        logger.exception(f"State news error: {state_id}")
        return api_err(str(e), 500)


# ── News: Feed Sources CRUD ───────────────────────────────────────
@app.route("/api/news/sources")
def api_news_sources():
    try:
        d           = news.load_sources()
        national    = d.get("national", [])
        state_feeds = []
        for sid, feeds in d.get("states", {}).items():
            for f in feeds:
                state_feeds.append({**f, "scope": "state", "state_id": sid})
        all_feeds = [{**f, "scope": "national"} for f in national] + state_feeds
        return api_ok({"all": all_feeds, "national": national,
                       "states": d.get("states", {}), "total": len(all_feeds)})
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/news/sources", methods=["POST"])
@admin_required
def api_news_sources_add():
    try:
        payload = request.get_json(force=True) or {}
        url  = payload.get("url","").strip()
        name = payload.get("name","").strip()
        if not url or not name: return api_err("url and name are required", 400)
        scope    = payload.get("scope","national")
        state_id = payload.get("state_id","").strip().lower()
        if scope == "state" and state_id and not _valid_state(state_id):
            return api_err(f"Unknown state: {state_id}", 400)
        ok = news.add_source(payload, scope=scope, state_id=state_id)
        if ok:
            cache.clear("national_news")
            return api_ok({"message": f"Feed '{name}' added"})
        return api_err("Failed to save sources file", 500)
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/news/sources/<source_id>/toggle", methods=["POST"])
@admin_required
def api_news_toggle(source_id):
    try:
        payload = request.get_json(force=True) or {}
        enabled = bool(payload.get("enabled", True))
        ok = news.toggle_source(source_id, enabled)
        if ok:
            cache.clear("national_news")
            return api_ok({"message": f"Feed {source_id} {'enabled' if enabled else 'disabled'}"})
        return api_err(f"Source '{source_id}' not found", 404)
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/news/sources/<source_id>", methods=["DELETE"])
@admin_required
def api_news_source_delete(source_id):
    try:
        ok = news.delete_source(source_id)
        if ok:
            cache.clear("national_news")
            return api_ok({"message": f"Feed '{source_id}' deleted"})
        return api_err(f"Feed '{source_id}' not found", 404)
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/news/sources/test", methods=["POST"])
def api_news_test():
    try:
        payload = request.get_json(force=True) or {}
        url = payload.get("url","").strip()
        if not url: return api_err("url required", 400)
        return api_ok(news.test_feed_url(url))
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/news/trending")
def api_news_trending():
    try:
        articles = news.fetch_national_news(ttl=15)
        return api_ok(news.extract_trending(articles, top_n=20))
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/news/health")
def api_news_health():
    return api_ok(news.get_feed_health())


# ── States ────────────────────────────────────────────────────────
@app.route("/api/states")
def api_states():
    try:
        region = request.args.get("region","").strip().lower()
        if region and region not in states.get_regions():
            return api_err("Unknown region", 400)
        data = states.get_states_by_region(region) if region else states.get_all_states()
        return api_ok(data)
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/state/<state_id>")
def api_state(state_id):
    try:
        sid = state_id.strip().lower()
        if not _valid_state(sid): return api_err("Unknown state", 400)
        return api_ok({"state": states.get_state(sid),
                       "news":  news.get_top_headlines(n=5)})
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/states/meta")
def api_states_meta():
    return api_ok(states.get_meta())

@app.route("/api/reload-states", methods=["POST"])
@admin_required
def api_reload_states():
    try:
        states.reload()
        return api_ok({"message": "States reloaded"})
    except Exception as e:
        return api_err(str(e), 500)


# ── Scheduler ─────────────────────────────────────────────────────
@app.route("/api/scheduler/status")
def api_scheduler_status():
    return api_ok(scheduler.get_status())

@app.route("/api/scheduler/run/<job_id>", methods=["POST"])
@admin_required
def api_scheduler_run(job_id):
    try:
        JOB_MAP = {"markets":scheduler._job_markets,"news":scheduler._job_news,
                   "currency":scheduler._job_currency}
        if job_id not in JOB_MAP: return api_err(f"Unknown job: {job_id}", 400)
        import threading
        threading.Thread(target=JOB_MAP[job_id], daemon=True).start()
        return api_ok({"message": f"Job '{job_id}' triggered"})
    except Exception as e:
        return api_err(str(e), 500)


# ── Settings / Cache ──────────────────────────────────────────────
@app.route("/api/settings", methods=["GET","POST"])
@admin_required
def api_settings():
    try:
        if request.method == "GET":
            conf = dict(cfg.load_config())
            conf.pop("admin_password_hash", None)
            return api_ok(conf)
        updates = request.get_json(force=True) or {}
        updates.pop("admin_password_hash", None)
        if "port" in updates:
            p = int(updates["port"])
            if not (1024 <= p <= 65535): return api_err("Port must be 1024-65535", 400)
        saved = cfg.save_config(updates)
        saved.pop("admin_password_hash", None)
        cache.clear()
        return api_ok(saved)
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/cache/clear", methods=["POST"])
@admin_required
def api_cache_clear():
    try:
        cache.clear()
        return api_ok({"message": "Cache cleared."})
    except Exception as e:
        return api_err(str(e), 500)

@app.route("/api/cache/stats")
def api_cache_stats():
    return api_ok(cache.stats())


# ── Error handlers ────────────────────────────────────────────────
@app.errorhandler(404)
def err_404(e): return jsonify({"status":"error","message":"Not found"}), 404
@app.errorhandler(500)
def err_500(e): return jsonify({"status":"error","message":"Server error"}), 500


# ── Startup ───────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("=" * 56)
    logger.info("  DRISHTI v5 — News-First India Platform")
    logger.info("  Markets + Currency (live) + 103 RSS feeds")
    logger.info("=" * 56)
    conf = cfg.load_config()
    port = int(conf.get("port", 5050))
    scheduler.start(
        markets_interval  = int(conf.get("markets_refresh_minutes", 5)),
        news_interval     = int(conf.get("news_refresh_minutes", 15)),
        currency_interval = 5,
    )
    logger.info(f"  http://127.0.0.1:{port}")
    print(f"\n  DRISHTI v5  ->  http://127.0.0.1:{port}\n  Ctrl+C to stop\n")
    try:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    finally:
        scheduler.stop()
