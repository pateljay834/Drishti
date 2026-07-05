import os
import json
import time
import logging

logger = logging.getLogger("drishti")

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(key: str) -> str:
    """Generate safe, Windows-compatible cache file path."""
    safe_key = (
        key.replace("/", "_")
           .replace("\\", "_")
           .replace(":", "_")
           .replace(" ", "_")
           .replace("^", "_")
           .replace("=", "_")
    )
    return os.path.join(CACHE_DIR, f"{safe_key[:100]}.json")


def get(key: str, ttl_minutes: int = 10):
    """Return cached value if still fresh, else None."""
    if not key:
        return None
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            entry = json.load(f)
        age_minutes = (time.time() - entry.get("timestamp", 0)) / 60
        if age_minutes < ttl_minutes:
            logger.debug(f"Cache hit: {key} ({age_minutes:.1f}min old)")
            return entry.get("data")
        logger.debug(f"Cache expired: {key} ({age_minutes:.1f}min > {ttl_minutes}min TTL)")
        return None
    except json.JSONDecodeError:
        logger.warning(f"Cache file corrupt for '{key}', removing")
        try:
            os.remove(path)
        except Exception:
            pass
        return None
    except Exception as e:
        logger.error(f"Cache read error for '{key}': {e}")
        return None


def set(key: str, data) -> bool:
    """Store data in cache using an atomic write (temp file + rename).
    Works on Windows and Unix without any platform-specific locking."""
    if not key:
        return False
    path = _cache_path(key)
    temp_path = path + ".tmp"
    entry = {"timestamp": time.time(), "data": data}
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False)
        # Atomic swap — on Windows we must remove the target first
        if os.path.exists(path):
            os.remove(path)
        os.rename(temp_path, path)
        logger.debug(f"Cache stored: {key}")
        return True
    except Exception as e:
        logger.error(f"Cache write error for '{key}': {e}")
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        return False


def clear(key: str = None):
    """Clear a single cache key or the entire cache directory."""
    try:
        if key:
            path = _cache_path(key)
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"Cache cleared: {key}")
        else:
            count = 0
            for fname in os.listdir(CACHE_DIR):
                if fname.endswith(".json") or fname.endswith(".tmp"):
                    try:
                        os.remove(os.path.join(CACHE_DIR, fname))
                        count += 1
                    except Exception as e:
                        logger.warning(f"Could not remove {fname}: {e}")
            logger.info(f"Full cache cleared: {count} files removed")
    except Exception as e:
        logger.error(f"Cache clear error: {e}")


def stats() -> dict:
    """Return basic cache statistics."""
    try:
        files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".json")]
        size_bytes = sum(
            os.path.getsize(os.path.join(CACHE_DIR, f)) for f in files
        )
        return {
            "files": len(files),
            "size_kb": round(size_bytes / 1024, 1),
            "path": CACHE_DIR,
        }
    except Exception as e:
        logger.error(f"Cache stats error: {e}")
        return {"error": str(e)}
