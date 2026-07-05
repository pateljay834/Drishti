"""
DRISHTI — Configuration
Loads settings from config.json; falls back to DEFAULTS.
In-process cache avoids re-reading the file on every request.
"""

import os
import json
import logging

logger = logging.getLogger("drishti")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULTS: dict = {
    "app_name":                  "DRISHTI",
    "tagline":                   "India Intelligence Platform",
    "version":                   "2.0",
    "port":                      5050,
    "debug":                     False,
    "cache_ttl_minutes":         10,
    "news_refresh_minutes":      15,
    "markets_refresh_minutes":   5,
    "theme":                     "dark",
    "admin_password_hash":       None,
    "news_sources_enabled": {
        "economic_times":    True,
        "hindu":             True,
        "ndtv":              True,
        "mint":              True,
        "business_standard": True,
        "pib":               True,
        "moneycontrol":      True,
    },
    "market_watchlist": [
        "^BSESN", "^NSEI", "^NSEBANK", "^CNXIT", "USDINR=X", "GC=F", "CL=F"
    ],
    "top_stocks_watchlist": [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
        "HINDUNILVR.NS", "ITC.NS", "BAJFINANCE.NS", "KOTAKBANK.NS", "LT.NS",
        "SBIN.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "WIPRO.NS",
    ],
}

# ── In-process cache ──────────────────────────────────────────────
_cached_config: dict | None = None


def _read_file() -> dict:
    """Read config.json, merge with DEFAULTS, return result."""
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        return {**DEFAULTS, **saved}
    except json.JSONDecodeError as e:
        logger.error(f"config.json JSON error: {e} — using defaults")
        return dict(DEFAULTS)
    except Exception as e:
        logger.error(f"config.json read error: {e} — using defaults")
        return dict(DEFAULTS)


def load_config(force: bool = False) -> dict:
    """Return config, reading from disk only on first call (or when forced)."""
    global _cached_config
    if _cached_config is None or force:
        _cached_config = _read_file()
        if not os.path.exists(CONFIG_FILE):
            logger.info("No config.json found — using defaults (will be created on first Save)")
        else:
            logger.debug("Config loaded from config.json")
    return _cached_config


def save_config(updates: dict) -> dict:
    """Merge updates into config, write to disk, refresh in-process cache."""
    global _cached_config

    # Validate key ranges
    if "port" in updates:
        p = int(updates["port"])
        if not (1024 <= p <= 65535):
            raise ValueError(f"Port must be 1024–65535, got {p}")
    for ttl_key in ("cache_ttl_minutes", "news_refresh_minutes", "markets_refresh_minutes"):
        if ttl_key in updates:
            t = int(updates[ttl_key])
            if not (1 <= t <= 240):
                raise ValueError(f"{ttl_key} must be 1–240, got {t}")

    current = load_config()
    current.update(updates)

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except Exception:
            pass  # Windows may not support chmod; non-fatal
        _cached_config = current
        logger.info(f"Config saved: {list(updates.keys())}")
    except Exception as e:
        logger.error(f"Config save error: {e}")
        raise

    return current


def get(key: str, default=None):
    return load_config().get(key, default)
