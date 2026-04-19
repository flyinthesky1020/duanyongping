/* ── Stocks Tab ── */

let currentMarketFilter = "ALL";
let currentSearchQuery = "";

function renderStocksList(stocks) {
  const listEl = document.getElementById("stocks-list");

  const filtered = filterStocks(stocks);
  if (filtered.length === 0) {
    listEl.innerHTML = '<div class="empty-state"><div class="icon">📊</div>没有找到匹配的股票</div>';
    return;
  }

  listEl.innerHTML = filtered.map(stock => {
    const marketBadgeHtml = marketBadge(stock.market);
    return `
      <div class="stock-item" data-ticker="${escapeHtml(stock.ticker)}" data-market="${escapeHtml(stock.market)}">
        <div class="stock-item-header" onclick="toggleStockItem(this.parentElement, '${escapeHtml(stock.ticker)}', '${escapeHtml(stock.market)}')">
          <div class="si-info">
            <span class="si-name">${escapeHtml(stock.name)}</span>
            <span class="si-ticker">${escapeHtml(stock.ticker)}</span>
            ${marketBadgeHtml}
          </div>
          <div class="si-sentiment">
            ${stock.bullish_count > 0 ? `<span class="si-bull">▲ ${stock.bullish_count}</span>` : ""}
            ${stock.bearish_count > 0 ? `<span class="si-bear">▼ ${stock.bearish_count}</span>` : ""}
            <span style="color:var(--text-muted);font-size:11px">${stock.opinion_count}条</span>
          </div>
          <span class="si-expand">▾</span>
        </div>
        <div class="stock-item-body">
          <!-- Filled dynamically when expanded -->
          <div class="stock-body-inner"></div>
        </div>
      </div>
    `;
  }).join("");
}

function filterStocks(stocks) {
  return stocks.filter(s => {
    const matchesMarket = currentMarketFilter === "ALL" || s.market === currentMarketFilter;
    const q = currentSearchQuery.toLowerCase();
    const matchesSearch = !q ||
      s.name.toLowerCase().includes(q) ||
      s.ticker.toLowerCase().includes(q);
    return matchesMarket && matchesSearch;
  });
}

async function toggleStockItem(itemEl, ticker, market) {
  const isExpanded = itemEl.classList.contains("expanded");
  // Collapse all others
  document.querySelectorAll(".stock-item.expanded").forEach(el => {
    if (el !== itemEl) {
      el.classList.remove("expanded");
      el.querySelector(".stock-item-body").style.display = "none";
    }
  });

  if (isExpanded) {
    itemEl.classList.remove("expanded");
    itemEl.querySelector(".stock-item-body").style.display = "none";
    return;
  }

  itemEl.classList.add("expanded");
  const bodyEl = itemEl.querySelector(".stock-item-body");
  bodyEl.style.display = "block";

  const innerEl = itemEl.querySelector(".stock-body-inner");
  innerEl.innerHTML = '<div class="empty-state" style="padding:20px">加载中<span class="loading-dots"></span></div>';

  try {
    const res = await fetch(`/api/stocks/${encodeURIComponent(ticker)}`);
    if (!res.ok) throw new Error("not found");
    const stock = await res.json();
    renderStockBody(innerEl, stock, market);
  } catch (e) {
    innerEl.innerHTML = '<div class="empty-state" style="padding:20px">加载失败</div>';
  }
}

function renderStockBody(container, stock, market) {
  const opinions = stock.opinions || [];
  const safeId = sanitizeId(stock.ticker);
  const chartId = `stock-chart-${safeId}`;
  const statsId = `stock-stats-${safeId}`;
  const opinionsId = `stock-opinions-${safeId}`;

  container.innerHTML = `
    <div class="inline-chart-wrap">
      <div id="${chartId}" class="inline-chart"></div>
      <div id="${statsId}" class="inline-chart-stats">
        <span class="stat-label loading-dots">加载行情数据</span>
      </div>
      <div id="${opinionsId}"></div>
    </div>
  `;

  const chartEl = document.getElementById(chartId);
  const statsEl = document.getElementById(statsId);
  const listDiv = document.getElementById(opinionsId);

  loadChart(stock.ticker, market, opinions, chartEl);
  loadStockStats(stock.ticker, market, statsEl);

  // Render opinion list inline
  renderOpinionList(listDiv, opinions);
}

function sanitizeId(ticker) {
  return ticker.replace(/[^a-zA-Z0-9]/g, "_");
}

/* ── Search & Filter ── */
document.getElementById("stocks-search").addEventListener("input", function() {
  currentSearchQuery = this.value.trim();
  if (App.stocks) renderStocksList(App.stocks);
});

document.querySelectorAll(".mf-btn").forEach(btn => {
  btn.addEventListener("click", function() {
    document.querySelectorAll(".mf-btn").forEach(b => b.classList.remove("active"));
    this.classList.add("active");
    currentMarketFilter = this.dataset.market;
    if (App.stocks) renderStocksList(App.stocks);
  });
});
