"""
DRISHTI — Background Scheduler v5
Jobs: markets, news, currency. (Economy job removed — no more hardcoded
or fake-live economic data; only genuinely live market/currency data
and RSS news are kept.)
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

logger    = logging.getLogger("drishti")
_scheduler = None
_job_status: dict = {}


def _job_markets():
    try:
        from modules import markets, cache
        cache.clear("indices")
        cache.clear("top_stocks")
        markets.fetch_all_indices(ttl=0)
        markets.fetch_top_stocks(ttl=0)
        logger.info("[scheduler] Markets refreshed")
    except Exception as e:
        logger.error(f"[scheduler] Markets error: {e}")


def _job_news():
    try:
        from modules import news, cache
        cache.clear("national_news")
        news.fetch_national_news(ttl=0)
        logger.info("[scheduler] News refreshed")
    except Exception as e:
        logger.error(f"[scheduler] News error: {e}")


def _job_currency():
    try:
        from modules import markets, cache
        cache.clear("currency_rates")
        markets.fetch_currency_rates(ttl=0)
        logger.info("[scheduler] Currency rates refreshed")
    except Exception as e:
        logger.error(f"[scheduler] Currency error: {e}")


def _on_event(event):
    from datetime import datetime
    import pytz
    ts = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %Y %I:%M %p IST")
    if event.exception:
        _job_status[event.job_id] = {"last_run": ts, "status": "error",
                                     "error": str(event.exception)[:120]}
    else:
        _job_status[event.job_id] = {"last_run": ts, "status": "ok"}


def start(markets_interval: int = 5,
          news_interval: int   = 15,
          currency_interval: int = 5):
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(
        timezone="Asia/Kolkata",
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
    )
    _scheduler.add_listener(_on_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    _scheduler.add_job(_job_markets,  "interval", minutes=markets_interval,  id="markets",  name="Market indices & stocks")
    _scheduler.add_job(_job_news,     "interval", minutes=news_interval,     id="news",     name="News aggregation")
    _scheduler.add_job(_job_currency, "interval", minutes=currency_interval, id="currency", name="INR currency crosses")
    _scheduler.start()

    logger.info(f"[scheduler] Started — markets:{markets_interval}m news:{news_interval}m currency:{currency_interval}m")

    # Fast synchronous warm-up — all jobs are quick (no economy/IMF blocking calls anymore)
    logger.info("[scheduler] Warm-up: markets, news, currency...")
    _job_markets()
    _job_news()
    _job_currency()
    logger.info("[scheduler] Warm-up complete — app ready")


def stop():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] Stopped")


def get_status() -> dict:
    if not _scheduler:
        return {"running": False, "jobs": {}}
    jobs = {}
    for job in _scheduler.get_jobs():
        st      = _job_status.get(job.id, {"last_run": "Not yet run", "status": "pending"})
        next_rt = str(job.next_run_time)[:19] if job.next_run_time else "N/A"
        jobs[job.id] = {"name": job.name, "next_run": next_rt, **st}
    return {"running": _scheduler.running, "jobs": jobs}
