# DRISHTI v5 — India News & Markets Platform
## दृष्टि — भारत सूचना मंच

> **Free. Open Source. Honest about what's live and what isn't.**

An India-focused news and markets dashboard. v5 is a deliberate pivot:
we removed everything that looked live but wasn't, and doubled down on
what genuinely is — real-time markets and a comprehensive news engine.

---

## Why v5 looks different from earlier versions

Earlier versions had an Economy page (IMF/World Bank data, often blocked
or stale) and a Mutual Funds page (AMFI AUM figures that are only
published monthly and were hardcoded). Both **looked** live but weren't,
which is worse than not having them. v5 removes both entirely.

State pages no longer show GDP, growth-rate, or per-capita-income figures
— those were static estimates dressed up next to a live ticker, which is
misleading. State pages now lead with **live local news** instead.

What's left is honest:
- **Markets** — yfinance, genuinely live, ~15min exchange delay
- **Currency** — yfinance, genuinely live, INR vs 7 pairs
- **News** — 103 RSS feeds, fetched on a real schedule, genuinely live

---

## News App — the core of v5

- **13 categories**: National, Business, Markets, Politics, Technology,
  Sports, Health, Science, Defence, Environment, Entertainment, International, Policy
- **36 state-specific dashboards** — every state page leads with its own
  local news tab, combining dedicated regional RSS feeds with nationally-tagged articles
- **12 languages** — Hindi, Marathi, Tamil, Malayalam, Kannada, Telugu,
  Gujarati, Bengali, Odia, Assamese, Punjabi, English — local-language
  feeds alongside English wherever both exist for a state's press
- **Continuous scrolling news ticker** — a genuine CSS marquee (not a
  static row) on both the Dashboard and News page, always populated with
  the latest headlines, speed auto-scales to content, pauses on hover
- **Feed Manager** (`/news/feeds`) — add, test, enable/disable, delete
  any RSS feed. Test button validates a URL live before you save it.
- **Trending topics**, **feed health tracking**, **deduplication**,
  **breaking news detection**

---

## Quick Start

**Windows:** Double-click `run.bat`
**Mac/Linux:** `pip install -r requirements.txt && python app.py`

Open `http://127.0.0.1:5050`

---

## Architecture

```
drishti/
├── app.py                    Flask routes — markets, currency, news, states
├── config.py                 Settings (in-process cached)
├── requirements.txt
├── run.bat
├── modules/
│   ├── markets.py            yfinance — indices, stocks, currency (all live)
│   ├── news.py                RSS engine — JSON-driven, CRUD, health tracking
│   ├── states.py              Loads static/data/states_data.json (reference only)
│   ├── scheduler.py           APScheduler — markets/news/currency refresh
│   └── cache.py               Atomic file cache, cross-platform
├── templates/
│   ├── base.html              Nav, theme toggle, global search
│   ├── dashboard.html         Continuous ticker, map, live indices, headlines
│   ├── markets.html  currency.html
│   ├── states.html            All 36 states/UTs grid
│   ├── state_detail.html      State News tab (default) + Overview (reference facts)
│   ├── news.html               Full news dashboard — categories, marquee, trending
│   ├── feed_manager.html      Add/edit/test/delete RSS feeds
│   └── settings.html
└── static/
    ├── css/style.css
    ├── js/app.js               Ticker, clock, theme, global search
    ├── js/charts.js
    └── data/
        ├── states_data.json    36 states/UTs — reference facts only
        └── news_sources.json   103 RSS feeds — edit to customise
```

---

## Customising News Feeds

**In-app:** `/news/feeds` → paste a URL → click Test → see article count
and sample headline → Add.

**Direct JSON edit:** `static/data/news_sources.json`. Many regional-language
feed URLs marked `"enabled": false` are unverified from the build
environment (which has no internet access) — test them via the Feed
Manager before enabling. That's the whole point of the Test button: this
registry is meant to be self-healing without needing a code update.

---

## What Was Removed and Why

| Removed | Reason |
|---|---|
| Economy page (IMF/World Bank) | IMF API frequently blocked; embedded fallback numbers looked live but were static — misleading |
| Mutual Funds page (AMFI) | AUM figures only published monthly, had to be hardcoded — same problem |
| State GDP / growth % / per-capita income | Static estimates shown next to a live UI implied freshness they didn't have |
| Economic Calendar | Hardcoded dates went stale within weeks |

---

## License

MIT — free forever, modify and share without restriction.
