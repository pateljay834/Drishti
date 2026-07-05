"""
DRISHTI — States module
Loads all 36 state/UT records from static/data/states_data.json.
To update leadership or figures: edit that JSON file, restart DRISHTI.
"""

import os
import json
import logging

logger = logging.getLogger("drishti")

_DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static", "data", "states_data.json"
)

# In-process cache so the file is only read once per run
_STATES: dict = {}
_META: dict = {}


def _load() -> None:
    global _STATES, _META
    if _STATES:
        return  # already loaded

    if not os.path.exists(_DATA_FILE):
        logger.error(f"states_data.json not found at: {_DATA_FILE}")
        _STATES = {}
        return

    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _STATES = raw.get("states", {})
        _META   = raw.get("_meta", {})
        logger.info(f"Loaded {len(_STATES)} states/UTs from states_data.json")
    except json.JSONDecodeError as e:
        logger.error(f"states_data.json parse error: {e}")
        _STATES = {}
    except Exception as e:
        logger.error(f"states_data.json load error: {e}")
        _STATES = {}


def reload() -> None:
    """Force re-read of JSON file (e.g. after manual edits)."""
    global _STATES, _META
    _STATES = {}
    _META   = {}
    _load()
    logger.info("States data reloaded from disk")


# ── Public API ────────────────────────────────────────────────────

def get_all_states() -> list:
    _load()
    return list(_STATES.values())


def get_state(state_id: str) -> dict:
    _load()
    return _STATES.get(state_id, {})


def get_states_by_region(region: str) -> list:
    _load()
    return [s for s in _STATES.values() if s.get("region") == region]


def get_regions() -> list:
    _load()
    return list({s["region"] for s in _STATES.values()})


def get_state_summary() -> list:
    """
    Lightweight list for map markers and state selector cards.
    Deliberately excludes GDP/growth/per-capita figures — those are static
    estimates bundled in states_data.json for reference on the state detail
    page only, and are not presented as live indicators anywhere in the UI.
    """
    _load()
    return [
        {
            "id":       s["id"],
            "name":     s["name"],
            "code":     s["code"],
            "type":     s["type"],
            "capital":  s["capital"],
            "region":   s["region"],
            "color":    s.get("color", "#FF6B35"),
            "population": s.get("population"),
        }
        for s in _STATES.values()
    ]


def get_meta() -> dict:
    """Return data-source metadata (for Settings / About page)."""
    _load()
    return _META


# Expose raw dict for validation in app.py
STATES = property(lambda self: (_load(), _STATES)[1])  # lazy alias


# Allow `state_id in states.STATES` pattern used in app.py
class _StatesProxy:
    def __contains__(self, key):
        _load()
        return key in _STATES

    def get(self, key, default=None):
        _load()
        return _STATES.get(key, default)

    def keys(self):
        _load()
        return _STATES.keys()


STATES = _StatesProxy()
