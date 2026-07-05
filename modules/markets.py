import yfinance as yf
from modules import cache
from datetime import datetime
import pytz
import logging
import time

logger = logging.getLogger("drishti")
IST = pytz.timezone("Asia/Kolkata")

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5
REQUEST_TIMEOUT = 10

INDICES = {
    "^BSESN":    {"name": "Sensex",     "exchange": "BSE", "category": "index"},
    "^NSEI":     {"name": "Nifty 50",   "exchange": "NSE", "category": "index"},
    "^NSEBANK":  {"name": "Nifty Bank", "exchange": "NSE", "category": "index"},
    "^CNXIT":    {"name": "Nifty IT",   "exchange": "NSE", "category": "index"},
    "^CNXAUTO":  {"name": "Nifty Auto", "exchange": "NSE", "category": "index"},
    "^CNXPHARMA":{"name": "Nifty Pharma","exchange": "NSE","category": "index"},
    "^CNXMETAL": {"name": "Nifty Metal","exchange": "NSE", "category": "index"},
    "^CNXFMCG":  {"name": "Nifty FMCG","exchange": "NSE", "category": "index"},
    "^INDIAVIX": {"name": "India VIX",  "exchange": "NSE", "category": "volatility"},
    "USDINR=X":  {"name": "USD/INR",    "exchange": "FX",  "category": "currency"},
    "GC=F":      {"name": "Gold",       "exchange": "COMEX","category": "commodity"},
    "CL=F":      {"name": "Crude Oil",  "exchange": "NYMEX","category": "commodity"},
    "SI=F":      {"name": "Silver",     "exchange": "COMEX","category": "commodity"},
}

TOP_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "BAJFINANCE.NS", "KOTAKBANK.NS", "LT.NS",
    "SBIN.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "WIPRO.NS",
    "HCLTECH.NS", "TITAN.NS", "NESTLEIND.NS", "ULTRACEMCO.NS", "TECHM.NS"
]

STOCK_NAMES = {
    "RELIANCE.NS": "Reliance Industries", "TCS.NS": "Tata Consultancy Services",
    "HDFCBANK.NS": "HDFC Bank", "INFY.NS": "Infosys", "ICICIBANK.NS": "ICICI Bank",
    "HINDUNILVR.NS": "Hindustan Unilever", "ITC.NS": "ITC Limited",
    "BAJFINANCE.NS": "Bajaj Finance", "KOTAKBANK.NS": "Kotak Mahindra Bank",
    "LT.NS": "Larsen & Toubro", "SBIN.NS": "State Bank of India",
    "AXISBANK.NS": "Axis Bank", "ASIANPAINT.NS": "Asian Paints",
    "MARUTI.NS": "Maruti Suzuki", "WIPRO.NS": "Wipro",
    "HCLTECH.NS": "HCL Technologies", "TITAN.NS": "Titan Company",
    "NESTLEIND.NS": "Nestle India", "ULTRACEMCO.NS": "UltraTech Cement",
    "TECHM.NS": "Tech Mahindra"
}


def _safe_float(val, decimals=2):
    """Safely convert to float, handling NaN/Inf."""
    try:
        if val is None or str(val) in ["nan", "inf", "-inf"]:
            return None
        num = float(val)
        if num != num or num == float('inf') or num == float('-inf'):  # NaN or Inf
            return None
        return round(num, decimals)
    except (ValueError, TypeError):
        return None


def _pct_change(current, prev):
    """Calculate percentage change safely."""
    if current is None or prev is None or prev == 0:
        return None
    try:
        result = ((current - prev) / abs(prev)) * 100
        return _safe_float(result, 2)
    except:
        return None


def _retry_with_backoff(func, max_retries=MAX_RETRIES, initial_delay=RETRY_BACKOFF):
    """Retry function with exponential backoff."""
    delay = initial_delay
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"Attempt {attempt} failed: {str(e)[:50]}. Retrying in {delay}s...")
                time.sleep(delay)
                delay *= RETRY_BACKOFF
            else:
                logger.error(f"All {max_retries} attempts failed for {func.__name__}")
    
    return None, str(last_error) if last_error else "Unknown error"


def fetch_quote(symbol: str) -> dict:
    """Fetch single quote with timeout and retry logic."""
    def _fetch():
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        hist = ticker.history(period="2d", interval="1d")
        
        price = _safe_float(getattr(info, "last_price", None))
        prev_close = _safe_float(getattr(info, "previous_close", None))
        
        if hist is not None and len(hist) >= 2:
            prev_close = _safe_float(hist["Close"].iloc[-2])
            price = _safe_float(hist["Close"].iloc[-1]) if price is None else price
        
        change = _safe_float((price or 0) - (prev_close or 0))
        change_pct = _pct_change(price, prev_close)
        
        return {
            "symbol": symbol,
            "name": INDICES.get(symbol, {}).get("name", STOCK_NAMES.get(symbol, symbol)),
            "price": price,
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "exchange": INDICES.get(symbol, {}).get("exchange", "NSE"),
            "category": INDICES.get(symbol, {}).get("category", "stock"),
            "data_age": "live",
        }
    
    try:
        result = _retry_with_backoff(_fetch)
        if isinstance(result, tuple):
            return {
                "symbol": symbol,
                "name": INDICES.get(symbol, {}).get("name", symbol),
                "price": None, "prev_close": None,
                "change": None, "change_pct": None,
                "error": str(result[1])[:100]
            }
        return result
    except Exception as e:
        logger.error(f"Quote fetch error for {symbol}: {e}")
        return {
            "symbol": symbol,
            "name": INDICES.get(symbol, {}).get("name", symbol),
            "price": None, "prev_close": None,
            "change": None, "change_pct": None,
            "error": str(e)[:100]
        }


def fetch_all_indices(ttl=5):
    """Fetch all indices with timeout and caching."""
    cached = cache.get("indices", ttl_minutes=ttl)
    if cached:
        logger.debug("Indices from cache")
        return cached
    
    logger.info("Fetching all indices...")
    results = []
    symbols = list(INDICES.keys())
    
    def _download():
        return yf.download(
            symbols, period="2d", interval="1d",
            group_by="ticker", auto_adjust=True, progress=False,
            timeout=REQUEST_TIMEOUT
        )
    
    try:
        tickers = _retry_with_backoff(_download)
        if isinstance(tickers, tuple):  # Error occurred
            logger.error(f"Download failed: {tickers[1]}")
            # Return empty results instead of crashing
            return []
        
        for sym in symbols:
            try:
                if len(symbols) == 1:
                    closes = tickers["Close"]
                else:
                    closes = tickers[sym]["Close"]
                closes = closes.dropna()
                
                if len(closes) >= 2:
                    price = _safe_float(closes.iloc[-1])
                    prev = _safe_float(closes.iloc[-2])
                elif len(closes) == 1:
                    price = _safe_float(closes.iloc[-1])
                    prev = None
                else:
                    price = prev = None
                
                results.append({
                    "symbol": sym,
                    "name": INDICES[sym]["name"],
                    "price": price,
                    "prev_close": prev,
                    "change": _safe_float((price or 0) - (prev or 0)),
                    "change_pct": _pct_change(price, prev),
                    "exchange": INDICES[sym]["exchange"],
                    "category": INDICES[sym]["category"],
                    "data_age": "~15min delayed",
                })
            except Exception as e:
                logger.warning(f"Error processing {sym}: {e}")
                results.append(fetch_quote(sym))
    except Exception as e:
        logger.error(f"Indices fetch error: {e}")
        # Fallback to individual quotes
        for sym in symbols:
            results.append(fetch_quote(sym))
    
    cache.set("indices", results)
    return results


def fetch_top_stocks(ttl=10):
    """Fetch top stocks with error handling."""
    cached = cache.get("top_stocks", ttl_minutes=ttl)
    if cached:
        logger.debug("Top stocks from cache")
        return cached
    
    logger.info("Fetching top stocks...")
    results = []
    
    def _download():
        return yf.download(
            TOP_STOCKS, period="2d", interval="1d",
            group_by="ticker", auto_adjust=True, progress=False,
            timeout=REQUEST_TIMEOUT
        )
    
    try:
        tickers = _retry_with_backoff(_download)
        if isinstance(tickers, tuple):
            logger.error(f"Download failed: {tickers[1]}")
            return []
        
        for sym in TOP_STOCKS:
            try:
                closes = tickers[sym]["Close"].dropna()
                price = _safe_float(closes.iloc[-1]) if len(closes) >= 1 else None
                prev = _safe_float(closes.iloc[-2]) if len(closes) >= 2 else None
                results.append({
                    "symbol": sym,
                    "name": STOCK_NAMES.get(sym, sym),
                    "price": price,
                    "prev_close": prev,
                    "change": _safe_float((price or 0) - (prev or 0)),
                    "change_pct": _pct_change(price, prev),
                    "exchange": "NSE",
                    "category": "stock",
                    "data_age": "~15min delayed",
                })
            except Exception as e:
                logger.warning(f"Error processing {sym}: {e}")
                results.append(fetch_quote(sym))
    except Exception as e:
        logger.error(f"Top stocks fetch error: {e}")
        for sym in TOP_STOCKS:
            results.append(fetch_quote(sym))
    
    cache.set("top_stocks", results)
    return results


def fetch_history(symbol: str, period: str = "1mo", interval: str = "1d") -> dict:
    """Fetch historical data with validation and error handling."""
    cache_key = f"history_{symbol}_{period}_{interval}"
    cached = cache.get(cache_key, ttl_minutes=30)
    if cached:
        logger.debug(f"History from cache: {symbol}")
        return cached
    
    try:
        logger.info(f"Fetching history: {symbol} {period}")
        def _fetch():
            ticker = yf.Ticker(symbol)
            return ticker.history(period=period, interval=interval)
        
        hist = _retry_with_backoff(_fetch)
        if isinstance(hist, tuple):
            return {"symbol": symbol, "labels": [], "closes": [], 
                   "volumes": [], "error": hist[1][:100]}
        
        labels = [str(d.date()) for d in hist.index]
        closes = [_safe_float(v) for v in hist["Close"].tolist()]
        volumes = [int(v) if v == v and v < 1e15 else 0 for v in hist["Volume"].tolist()]
        
        result = {
            "symbol": symbol,
            "name": INDICES.get(symbol, {}).get("name", STOCK_NAMES.get(symbol, symbol)),
            "labels": labels,
            "closes": closes,
            "volumes": volumes,
            "period": period,
            "interval": interval,
            "data_age": "~15min delayed",
        }
        cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"History fetch error for {symbol}: {e}")
        return {"symbol": symbol, "labels": [], "closes": [], 
               "volumes": [], "error": str(e)[:100]}


def get_market_summary():
    """Compact summary for dashboard ticker."""
    indices = fetch_all_indices(ttl=5)
    summary = {}
    for item in indices:
        summary[item["symbol"]] = item
    return summary


# ── Extended market data (52W H/L, breadth, P/E) ─────────────────
def fetch_extended_data(ttl: int = 10) -> dict:
    """52-week high/low, P/E, and multi-currency INR rates."""
    cached = cache.get("extended_data", ttl_minutes=ttl)
    if cached:
        return cached
    result = {"52w": {}, "pe": {}, "breadth": {}}
    try:
        symbols = ["^BSESN", "^NSEI", "^NSEBANK", "^CNXIT"]
        tickers = yf.download(symbols, period="1y", interval="1d",
                              group_by="ticker", auto_adjust=True,
                              progress=False, timeout=REQUEST_TIMEOUT)
        for sym in symbols:
            try:
                data  = tickers[sym] if len(symbols) > 1 else tickers
                high  = _safe_float(data["High"].max())
                low   = _safe_float(data["Low"].min())
                close = _safe_float(data["Close"].iloc[-1])
                from_high = _safe_float(((close - high) / high) * 100, 1) if high and close else None
                result["52w"][sym] = {
                    "name":      INDICES.get(sym, {}).get("name", sym),
                    "high52":    high,
                    "low52":     low,
                    "current":   close,
                    "pct_from_high": from_high,
                }
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Extended data error: {e}")
    cache.set("extended_data", result)
    return result


# ── INR Currency Crosses (moved from economy.py — genuinely live via yfinance) ──
CURRENCY_PAIRS = {
    "USDINR=X": {"name": "USD / INR", "flag": "\U0001F1FA\U0001F1F8", "base": "USD"},
    "EURINR=X": {"name": "EUR / INR", "flag": "\U0001F1EA\U0001F1FA", "base": "EUR"},
    "GBPINR=X": {"name": "GBP / INR", "flag": "\U0001F1EC\U0001F1E7", "base": "GBP"},
    "JPYINR=X": {"name": "JPY / INR", "flag": "\U0001F1EF\U0001F1F5", "base": "JPY"},
    "AEDINR=X": {"name": "AED / INR", "flag": "\U0001F1E6\U0001F1EA", "base": "AED"},
    "SGDINR=X": {"name": "SGD / INR", "flag": "\U0001F1F8\U0001F1EC", "base": "SGD"},
    "CNHINR=X": {"name": "CNH / INR", "flag": "\U0001F1E8\U0001F1F3", "base": "CNH"},
}
# Note: SARINR=X intentionally excluded — delisted on Yahoo Finance.

def fetch_currency_rates(ttl: int = 5) -> list:
    """Fetch INR vs major currencies. Genuinely live — no static fallback."""
    cached = cache.get("currency_rates", ttl_minutes=ttl)
    if cached:
        return cached
    try:
        symbols = list(CURRENCY_PAIRS.keys())
        tickers = yf.download(symbols, period="5d", interval="1d",
                               group_by="ticker", auto_adjust=True,
                               progress=False, timeout=REQUEST_TIMEOUT)

        results = []
        for sym in symbols:
            try:
                closes = (tickers[sym]["Close"] if len(symbols) > 1
                          else tickers["Close"]).dropna()
                price = _safe_float(closes.iloc[-1]) if len(closes) >= 1 else None
                prev  = _safe_float(closes.iloc[-2]) if len(closes) >= 2 else None
                chg   = _safe_float((price or 0) - (prev or 0)) if price and prev else None
                chg_p = _pct_change(price, prev)
                results.append({
                    "symbol": sym, **CURRENCY_PAIRS[sym],
                    "price": price, "prev_close": prev,
                    "change": chg, "change_pct": chg_p,
                })
            except Exception as ex:
                logger.debug(f"Currency {sym}: {ex}")
                results.append({"symbol": sym, **CURRENCY_PAIRS[sym], "price": None})

        cache.set("currency_rates", results)
        return results
    except Exception as e:
        logger.error(f"Currency rates error: {e}")
        return [{"symbol": s, **v, "price": None} for s, v in CURRENCY_PAIRS.items()]
