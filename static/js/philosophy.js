/* ── Philosophy Tab ── */

let currentPhiKey = null;

function renderPhilosophyNav() {
  const list = document.getElementById("phi-nav-list");
  list.innerHTML = App.philosophies.map(p => `
    <button class="phi-nav-item" data-key="${escapeHtml(p.key)}" onclick="selectPhilosophy('${escapeHtml(p.key)}')">
      ${escapeHtml(p.title)}
      ${p.quote_count > 0 ? `<span style="font-size:10px;color:var(--text-muted);margin-left:4px">(${p.quote_count})</span>` : ""}
    </button>
  `).join("");
}

function selectPhilosophy(key) {
  if (currentPhiKey === key) return;
  currentPhiKey = key;

  // Update nav active state
  document.querySelectorAll(".phi-nav-item").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.key === key);
  });

  const phi = App.philosophies.find(p => p.key === key);
  if (!phi) return;

  renderPhilosophyDetail(phi);
  renderPhilosophyStocks(phi);
}

function starsHtml(score) {
  const filled = Math.round(score || 3);
  return "★".repeat(filled) + "☆".repeat(5 - filled);
}

function shuffleArray(items) {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function diversifyQuotesByYear(quotes) {
  if (!quotes || quotes.length <= 1) return quotes || [];

  const buckets = new Map();
  quotes.forEach(quote => {
    const year = String(quote.date || "").slice(0, 4) || "unknown";
    if (!buckets.has(year)) buckets.set(year, []);
    buckets.get(year).push(quote);
  });

  const shuffledYears = shuffleArray([...buckets.keys()]);
  shuffledYears.forEach(year => {
    buckets.set(year, shuffleArray(buckets.get(year) || []));
  });

  const diversified = [];
  let hasRemaining = true;

  while (hasRemaining) {
    hasRemaining = false;
    shuffledYears.forEach(year => {
      const yearQuotes = buckets.get(year) || [];
      if (yearQuotes.length > 0) {
        diversified.push(yearQuotes.shift());
        hasRemaining = true;
      }
    });
  }

  return diversified.slice(0, quotes.length);
}

function renderPhilosophyDetail(phi) {
  const el = document.getElementById("phi-detail");
  const displayQuotes = diversifyQuotesByYear(phi.top_quotes || []);
  el.innerHTML = `
    <div class="phi-header-card">
      <div class="phi-title">${escapeHtml(phi.title)}</div>
      <div class="phi-tagline">${escapeHtml(phi.tagline)}</div>
      <div class="phi-description">${escapeHtml(phi.description)}</div>
    </div>

    <div class="quotes-section">
      <div class="section-title">代表性语录</div>
      ${displayQuotes && displayQuotes.length > 0
        ? displayQuotes.map((q, i) => `
          <div class="quote-card">
            <div class="quote-text">${escapeHtml(q.text)}</div>
            <div class="quote-cite">
              <span class="quote-stars">${starsHtml(q.quality_score)}</span>
              <span class="quote-date">段永平, ${escapeHtml(q.date || "")}</span>
              ${q.url ? `<a class="quote-link" href="${escapeHtml(q.url)}" target="_blank" rel="noopener">[原文 ↗]</a>` : ""}
            </div>
          </div>
        `).join("")
        : `<div class="empty-state" style="padding:24px 0">
            <div class="icon">💬</div>
            暂无代表性语录（请先运行数据管道）
           </div>`
      }
    </div>
  `;
}

function renderPhilosophyStocks(phi) {
  const section = document.getElementById("phi-stocks-section");
  const grid = document.getElementById("phi-stocks-grid");

  const tickers = phi.stocks || [];
  if (tickers.length === 0) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  // Look up stock details from App.stocks (if loaded)
  const stockMap = {};
  if (App.stocks) {
    App.stocks.forEach(s => { stockMap[s.ticker] = s; });
  }

  const cards = tickers.map(ticker => {
    const stock = stockMap[ticker] || { name: ticker, ticker, market: "US", bullish_count: 0, bearish_count: 0, opinions: [] };
    return stock;
  });

  // If stocks not loaded yet, fetch summary
  const renderCards = (stocks) => {
    grid.innerHTML = stocks.map(stock => `
      <div class="phi-stock-card" onclick="openStockFromPhilosophy('${escapeHtml(stock.ticker)}', '${escapeHtml(phi.key)}')">
        <div class="psc-ticker">${escapeHtml(stock.ticker)} · ${escapeHtml(stock.market)}</div>
        <div class="psc-name">${escapeHtml(stock.name)}</div>
        <div class="psc-badges">
          ${stock.bullish_count > 0 ? `<span class="badge badge-bull">▲ 看多 ${stock.bullish_count}</span>` : ""}
          ${stock.bearish_count > 0 ? `<span class="badge badge-bear">▼ 看空 ${stock.bearish_count}</span>` : ""}
          ${stock.opinion_count > 0 ? `<span class="badge badge-market">${stock.opinion_count}条观点</span>` : ""}
        </div>
      </div>
    `).join("");
  };

  if (App.stocks) {
    renderCards(cards);
  } else {
    // Load stocks then render
    fetch("/api/stocks").then(r => r.json()).then(data => {
      App.stocks = data.stocks || [];
      const stockMap2 = {};
      App.stocks.forEach(s => { stockMap2[s.ticker] = s; });
      renderCards(tickers.map(t => stockMap2[t] || { name: t, ticker: t, market: "?", bullish_count: 0, bearish_count: 0, opinion_count: 0, opinions: [] }));
    });
  }
}

async function openStockFromPhilosophy(ticker, philosophyKey) {
  // Fetch full stock data
  try {
    const res = await fetch(`/api/stocks/${encodeURIComponent(ticker)}`);
    if (!res.ok) return;
    const stock = await res.json();
    openChartModal(stock.name, stock.ticker, stock.market, stock.opinions || [], philosophyKey);
  } catch (e) {
    console.error("Failed to load stock detail", e);
  }
}
