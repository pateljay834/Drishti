/* DRISHTI v5 — app.js  (global: ticker, clock, theme, search) */

// ── IST Clock ─────────────────────────────────────────────────────
function updateClock() {
  const ist = new Intl.DateTimeFormat("en-IN", {
    timeZone:"Asia/Kolkata",
    hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:true
  }).format(new Date());
  const el = document.getElementById("istClock");
  if (el) el.textContent = "IST " + ist;
}
setInterval(updateClock, 1000);
updateClock();


// ── Dark / Light Theme ────────────────────────────────────────────
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const icon = document.getElementById("themeIcon");
  if (icon) icon.textContent = theme === "dark" ? "\u263D" : "\u2600";
  localStorage.setItem("drishti_theme", theme);
}
function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  applyTheme(current === "dark" ? "light" : "dark");
}
(function() {
  const saved = localStorage.getItem("drishti_theme") || "dark";
  applyTheme(saved);
})();


// ── Global Search ─────────────────────────────────────────────────
let _allStates = [], _searchTimer = null;

async function _loadStatesForSearch() {
  if (_allStates.length) return;
  try {
    const r = await fetch("/api/states");
    const j = await r.json();
    if (j.status === "ok") _allStates = j.data;
  } catch (e) { /* non-fatal */ }
}
_loadStatesForSearch();

function globalSearchRun(q) {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(() => _doSearch(q.trim().toLowerCase()), 200);
}

function _doSearch(q) {
  const panel = document.getElementById("searchResults");
  if (!panel) return;
  if (!q || q.length < 2) { panel.style.display = "none"; return; }

  const results = [];

  _allStates.filter(s =>
    s.name.toLowerCase().includes(q) ||
    s.code.toLowerCase().includes(q) ||
    (s.capital || "").toLowerCase().includes(q)
  ).slice(0, 4).forEach(s => results.push({
    type: "state", icon: "\uD83D\uDDFA", label: s.name,
    sub: (s.capital || "") + " \u00B7 " + s.type,
    href: `/state/${s.id}`
  }));

  const PAGES = [
    {k:"markets",  icon:"\uD83D\uDCC8", label:"Markets",     sub:"NSE/BSE indices and stocks", href:"/markets"},
    {k:"currency", icon:"\uD83D\uDCB1", label:"Currency",    sub:"INR vs major pairs",          href:"/currency"},
    {k:"news",     icon:"\uD83D\uDCF0", label:"News",        sub:"National and state news",     href:"/news"},
    {k:"states",   icon:"\uD83D\uDDFE", label:"All States",  sub:"28 States + 8 UTs",           href:"/states"},
    {k:"settings", icon:"\u2699",       label:"Settings",    sub:"Configure DRISHTI",           href:"/settings"},
    {k:"feeds",    icon:"\uD83D\uDCE1", label:"Feed Manager",sub:"Manage RSS feeds",            href:"/news/feeds"},
  ];
  PAGES.filter(p => p.k.includes(q) || p.label.toLowerCase().includes(q) || p.sub.toLowerCase().includes(q))
    .slice(0, 3).forEach(p => results.push({...p, type:"page"}));

  if (!results.length) {
    panel.innerHTML = `<div class="sr-item sr-empty">No results for "${q}"</div>`;
    panel.style.display = "block";
    return;
  }

  panel.innerHTML = results.map(r => `
    <a href="${r.href}" class="sr-item">
      <span class="sr-icon">${r.icon}</span>
      <div class="sr-body">
        <div class="sr-label">${r.label}</div>
        <div class="sr-sub">${r.sub}</div>
      </div>
      <span class="sr-type">${r.type}</span>
    </a>`).join("");
  panel.style.display = "block";
}

function showSearchPanel() {
  const q = document.getElementById("globalSearch")?.value?.trim();
  if (q && q.length >= 2) document.getElementById("searchResults").style.display = "block";
}
function hideSearchPanel() {
  setTimeout(() => {
    const el = document.getElementById("searchResults");
    if (el) el.style.display = "none";
  }, 200);
}


// ── Live Market Ticker (top bar) ──────────────────────────────────
const TICKER_SYMBOLS = ["^BSESN","^NSEI","^NSEBANK","^CNXIT","USDINR=X","GC=F","CL=F","^INDIAVIX"];
const TICKER_NAMES   = {
  "^BSESN":"Sensex","^NSEI":"Nifty","^NSEBANK":"Bank Nifty",
  "^CNXIT":"IT","USDINR=X":"USD/INR","GC=F":"Gold","CL=F":"Crude","^INDIAVIX":"VIX"
};

function fmtTickerPrice(val, sym) {
  if (val == null) return "\u2013";
  if (sym === "USDINR=X") return "\u20B9" + val.toFixed(2);
  if (sym === "GC=F" || sym === "CL=F") return "$" + val.toFixed(2);
  if (val >= 10000) return val.toLocaleString("en-IN", {maximumFractionDigits:0});
  return val.toFixed(2);
}

let _tickerPos = 0, _tickerRAF = null;

async function loadTicker() {
  try {
    const res  = await fetch("/api/markets");
    const json = await res.json();
    if (json.status !== "ok") return;
    const indices = json.data.indices || [];
    const track   = document.getElementById("tickerTrack");
    if (!track) return;

    const items = TICKER_SYMBOLS.map(sym => {
      const idx = indices.find(i => i.symbol === sym);
      if (!idx || idx.price == null) return null;
      const up    = (idx.change_pct || 0) >= 0;
      const arrow = up ? "\u25B2" : "\u25BC";
      const chg   = Math.abs(idx.change_pct || 0).toFixed(2) + "%";
      const cls   = up ? "up" : "dn";
      return `<span class="ticker-item ${cls}">` +
             `<span class="t-name">${TICKER_NAMES[sym] || sym}</span> ` +
             `<span class="t-price">${fmtTickerPrice(idx.price, sym)}</span> ` +
             `<span class="t-chg">${arrow} ${chg}</span>` +
             `</span><span class="ticker-sep"> \u00B7 </span>`;
    }).filter(Boolean).join("");

    if (!items) {
      track.innerHTML = `<span class="ticker-label">LIVE</span><span class="ticker-item">Market data unavailable \u2014 check connection</span>`;
      return;
    }
    track.innerHTML = `<span class="ticker-label">LIVE</span>` + items + items;
    _startTickerAnim();
  } catch (e) {
    console.warn("Ticker error:", e);
  }
}

function _startTickerAnim() {
  if (_tickerRAF) cancelAnimationFrame(_tickerRAF);
  const track = document.getElementById("tickerTrack");
  if (!track) return;
  const half = track.scrollWidth / 2;
  function step() {
    _tickerPos += 0.5;
    if (_tickerPos >= half) _tickerPos = 0;
    track.style.transform = `translateX(-${_tickerPos}px)`;
    _tickerRAF = requestAnimationFrame(step);
  }
  _tickerRAF = requestAnimationFrame(step);
}

loadTicker();
setInterval(loadTicker, 5 * 60 * 1000);
