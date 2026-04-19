/* ── Global State ── */
const App = {
  currentTab: "home",
  timeline: null,
  philosophies: null,
  stocks: null,
  wordcloudData: null,
};

/* ── Utilities ── */
function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatPercent(val) {
  if (val == null) return "—";
  return (val * 100).toFixed(1) + "%";
}

function sentimentBadge(sentiment) {
  if (sentiment === "bullish") return '<span class="badge badge-bull">▲ 看多</span>';
  if (sentiment === "bearish") return '<span class="badge badge-bear">▼ 看空</span>';
  return "";
}

function marketBadge(market) {
  return `<span class="badge badge-market">${escapeHtml(market)}</span>`;
}

/* ── Tab Routing ── */
function switchTab(tabId) {
  document.querySelectorAll(".tab-panel").forEach(el => {
    el.hidden = true;
    el.classList.remove("active");
  });
  document.querySelectorAll(".nav-btn").forEach(el => el.classList.remove("active"));
  const panel = document.getElementById(`tab-${tabId}`);
  if (panel) {
    panel.hidden = false;
    panel.classList.add("active");
  }
  const btn = document.querySelector(`[data-tab="${tabId}"]`);
  if (btn) btn.classList.add("active");
  App.currentTab = tabId;

  if (tabId === "home" && App.wordcloudData) {
    // Re-trigger resize for Three.js
    window.dispatchEvent(new Event("resize"));
  }
  if (tabId === "philosophy" && !App.philosophies) {
    loadPhilosophies();
  }
  if (tabId === "timeline" && !App.timeline) {
    loadTimeline();
  }
  if (tabId === "stocks" && !App.stocks) {
    loadStocks();
  }
}

document.querySelectorAll(".nav-btn").forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

/* ── Chart Modal ── */
function openChartModal(stockName, ticker, market, opinions, filterPhilosophy, options = {}) {
  const modal = document.getElementById("chart-modal");
  const title = document.getElementById("chart-modal-title");
  modal.hidden = false;
  title.textContent = `${escapeHtml(stockName)}  ${escapeHtml(ticker)}`;

  // Render opinions list
  const listEl = document.getElementById("chart-opinions-list");
  const opsToShow = filterPhilosophy
    ? opinions  // already filtered upstream
    : opinions;
  renderOpinionList(listEl, opsToShow);

  // Clear stats while loading
  const statsEl = document.getElementById("chart-stats");
  const chartEl = document.getElementById("chart-container");
  statsEl.innerHTML =
    '<span class="stat-label loading-dots">加载行情数据</span>';
  chartEl.innerHTML = "";

  // Load chart
  loadChart(ticker, market, opinions, chartEl, options);

  // Load stats
  loadStockStats(ticker, market, statsEl, options);
}

function closeChartModal() {
  document.getElementById("chart-modal").hidden = true;
  disposeChart();
}

document.getElementById("chart-modal-close").addEventListener("click", closeChartModal);
document.getElementById("chart-modal-overlay").addEventListener("click", closeChartModal);

/* ── Render Opinion List ── */
function renderOpinionList(container, opinions) {
  if (!opinions || opinions.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="icon">💬</div>暂无观点记录</div>';
    return;
  }
  const sorted = [...opinions].sort((a, b) => a.date > b.date ? 1 : -1);
  container.innerHTML = `
    <div class="section-title" style="margin-top:16px">全部观点 · ${sorted.length}条</div>
    <div class="opinion-timeline">
      ${sorted.map(op => {
        const icon = op.sentiment === "bullish" ? '<span class="opinion-sentiment-icon" style="color:var(--green)">▲</span>'
          : '<span class="opinion-sentiment-icon" style="color:var(--red)">▼</span>';
        const dateEl = op.url
          ? `<a class="opinion-date-link" href="${escapeHtml(op.url)}" target="_blank" rel="noopener">${escapeHtml(op.date)}</a>`
          : `<span class="opinion-date-link">${escapeHtml(op.date)}</span>`;
        return `<div class="opinion-item">
          ${icon}
          <div class="opinion-body">
            <div class="opinion-meta">
              ${dateEl}
              <span class="opinion-summary">${escapeHtml(op.summary)}</span>
            </div>
            <div class="opinion-quote">${escapeHtml(op.quote)}</div>
          </div>
        </div>`;
      }).join("")}
    </div>
  `;
}

/* ── Load Stock Stats ── */
async function loadStockStats(ticker, market, statsEl = document.getElementById("chart-stats"), options = {}) {
  try {
    const res = await fetch(`/api/stats/stock/${encodeURIComponent(ticker)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        market,
        opinions: options.opinions || undefined,
        start: options.start || undefined,
        end: options.end || undefined,
      }),
    });
    if (!res.ok) {
      statsEl.innerHTML = '<span class="stat-label" style="color:var(--text-muted)">暂无统计数据</span>';
      return;
    }
    const data = await res.json();
    const stats = data.stats;
    if (!stats) {
      statsEl.innerHTML = '<span class="stat-label" style="color:var(--text-muted)">暂无统计数据</span>';
      return;
    }
    const wr = stats.win_rate;
    const ret = stats.returns;
    const winRateVal = wr.win_rate != null ? parseFloat((wr.win_rate * 100).toFixed(1)) : null;
    const returnRateVal = ret.return_rate != null ? parseFloat((ret.return_rate * 100).toFixed(1)) : null;
    const pendingCount = wr.pending || 0;

    statsEl.innerHTML = `
      <div class="stat-item">
        <div class="stat-label">观点数</div>
        <div class="stat-value gold">${stats.opinion_count}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">胜率</div>
        <div class="stat-value ${winRateVal != null ? (winRateVal >= 50 ? 'green' : 'red') : ''}">
          ${winRateVal != null ? winRateVal + "%" : "—"}
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-label">正确/错误/待验证</div>
        <div class="stat-value">${wr.correct}/${wr.wrong}/${pendingCount}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">模拟收益率</div>
        <div class="stat-value ${returnRateVal != null ? (returnRateVal >= 0 ? 'green' : 'red') : ''}">
          ${returnRateVal != null ? (returnRateVal >= 0 ? "+" : "") + returnRateVal + "%" : "—"}
        </div>
      </div>
    `;
  } catch (e) {
    statsEl.innerHTML = '<span class="stat-label" style="color:var(--text-muted)">统计加载失败</span>';
  }
}

/* ── Data Loaders ── */
async function loadPhilosophies() {
  try {
    const res = await fetch("/api/philosophies");
    const data = await res.json();
    App.philosophies = [...(data.philosophies || [])].sort((a, b) => (b.quote_count || 0) - (a.quote_count || 0));
    renderPhilosophyNav();
    if (App.philosophies.length > 0) {
      selectPhilosophy(App.philosophies[0].key);
    }
  } catch (e) {
    console.error("Failed to load philosophies", e);
  }
}

async function loadStocks() {
  const listEl = document.getElementById("stocks-list");
  listEl.innerHTML = '<div class="empty-state"><div class="icon loading-dots">加载中</div></div>';
  try {
    const res = await fetch("/api/stocks");
    if (!res.ok) {
      throw new Error(`stocks request failed: ${res.status}`);
    }
    const data = await res.json();
    App.stocks = data.stocks || [];
    renderStocksList(App.stocks);
  } catch (e) {
    listEl.innerHTML = '<div class="empty-state">加载失败，请确认数据管道已运行</div>';
  }
}

async function loadWordcloud() {
  try {
    const res = await fetch("/api/wordcloud");
    const data = await res.json();
    App.wordcloudData = data.words || [];
    initWordCloud(App.wordcloudData);
  } catch (e) {
    console.error("Failed to load wordcloud data", e);
    // Init with fallback data
    initWordCloud(getFallbackWords());
  }
}

function getFallbackWords() {
  return [
    {text:"长期主义",weight:95,type:"concept",target:"philosophy:long_termism"},
    {text:"本分",weight:88,type:"concept",target:"philosophy:integrity"},
    {text:"商业模式",weight:85,type:"concept",target:"philosophy:business_model"},
    {text:"企业文化",weight:80,type:"concept",target:"philosophy:corporate_culture"},
    {text:"不懂不投",weight:78,type:"concept",target:"philosophy:circle_of_competence"},
    {text:"现金流",weight:75,type:"concept",target:"philosophy:cash_flow"},
    {text:"等待",weight:72,type:"concept",target:"philosophy:patience"},
    {text:"护城河",weight:70,type:"concept",target:"philosophy:business_model"},
    {text:"Apple",weight:85,type:"stock",target:"stock:AAPL"},
    {text:"茅台",weight:78,type:"stock",target:"stock:600519.SH"},
    {text:"腾讯",weight:72,type:"stock",target:"stock:0700.HK"},
    {text:"Stop Doing",weight:68,type:"concept",target:"philosophy:stop_doing"},
    {text:"定价权",weight:65,type:"concept",target:"philosophy:business_model"},
    {text:"安全边际",weight:62,type:"concept",target:"philosophy:patience"},
    {text:"ROE",weight:60,type:"concept",target:"philosophy:business_model"},
  ];
}

/* ── Navigate from wordcloud click ── */
window.navigateFromWordcloud = function(target) {
  if (!target) return;
  if (target.startsWith("philosophy:")) {
    const key = target.replace("philosophy:", "");
    switchTab("philosophy");
    // Wait for philosophies to load
    const trySelect = () => {
      if (App.philosophies) {
        selectPhilosophy(key);
      } else {
        setTimeout(trySelect, 200);
      }
    };
    trySelect();
  } else if (target.startsWith("stock:")) {
    const ticker = target.replace("stock:", "");
    switchTab("stocks");
    const tryExpand = () => {
      if (App.stocks) {
        const el = document.querySelector(`[data-ticker="${CSS.escape(ticker)}"]`);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          if (!el.classList.contains("expanded")) el.querySelector(".stock-item-header").click();
        }
      } else {
        setTimeout(tryExpand, 300);
      }
    };
    tryExpand();
  }
};

/* ── Init ── */
window.addEventListener("DOMContentLoaded", () => {
  switchTab(App.currentTab);
  void loadWordcloud();
  void loadStocks();
});
