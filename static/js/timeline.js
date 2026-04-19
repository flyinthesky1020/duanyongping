/* ── Timeline Tab ── */

let currentTimelineYear = null;

async function loadTimeline() {
  const navEl = document.getElementById("timeline-nav-list");
  const detailEl = document.getElementById("timeline-detail");
  if (!navEl || !detailEl) return;

  navEl.innerHTML = '<div class="empty-state" style="padding:24px 16px">加载中</div>';
  detailEl.innerHTML = '<div class="empty-state"><div class="icon loading-dots">加载中</div></div>';

  try {
    const res = await fetch("/api/timeline");
    if (!res.ok) throw new Error(`timeline request failed: ${res.status}`);
    const data = await res.json();
    App.timeline = data.timeline || [];
    renderTimelineNav(App.timeline);
    if (App.timeline.length > 0) {
      const ordered = [...App.timeline].sort((a, b) => Number(b.year) - Number(a.year));
      selectTimelineYear(ordered[0].year);
    } else {
      detailEl.innerHTML = '<div class="empty-state">暂无年度数据</div>';
    }
  } catch (e) {
    console.error("Failed to load timeline", e);
    navEl.innerHTML = "";
    detailEl.innerHTML = '<div class="empty-state">年度脉络加载失败</div>';
  }
}

function renderTimelineNav(items) {
  const listEl = document.getElementById("timeline-nav-list");
  if (!listEl) return;

  if (!items || items.length === 0) {
    listEl.innerHTML = '<div class="empty-state">暂无年度数据</div>';
    return;
  }

  const ordered = [...items].sort((a, b) => Number(b.year) - Number(a.year));
  listEl.innerHTML = ordered.map(item => `
    <button class="phi-nav-item timeline-nav-item" data-year="${escapeHtml(item.year)}" onclick="selectTimelineYear('${escapeHtml(item.year)}')">
      ${escapeHtml(item.year)}
      <span style="font-size:10px;color:var(--text-muted);margin-left:4px">(${(item.philosophy_quote_count || 0) + (item.stock_opinion_count || 0)})</span>
    </button>
  `).join("");
}

function selectTimelineYear(year) {
  if (currentTimelineYear === year) return;
  currentTimelineYear = year;

  document.querySelectorAll(".timeline-nav-item").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.year === year);
  });

  const item = (App.timeline || []).find(entry => entry.year === year);
  if (!item) return;
  renderTimelineDetail(item);
}

function renderTimelineDetail(item) {
  const detailEl = document.getElementById("timeline-detail");
  if (!detailEl) return;

  detailEl.innerHTML = `
    <div class="phi-header-card timeline-detail-header">
      <div class="phi-title">年度脉络 · ${escapeHtml(item.year)}</div>
      <div class="phi-tagline">按时间回看这一年里段永平关注的核心理念、代表性股票与关键表达。</div>
      <div class="phi-description">${buildYearLead(item)}</div>
      <div class="timeline-stat-row">
        <div class="timeline-stat-chip">原始发言 ${item.post_count || 0} 条</div>
        <div class="timeline-stat-chip">理念语录 ${item.philosophy_quote_count || 0} 条</div>
        <div class="timeline-stat-chip">股票观点 ${item.stock_opinion_count || 0} 条</div>
      </div>
    </div>

    <div class="quotes-section">
      <div class="section-title">年度高频理念</div>
      <div class="timeline-pill-row">
        ${(item.top_philosophies || []).map(phi => `
          <div class="timeline-pill">
            <div class="timeline-pill-title">${escapeHtml(phi.title)}</div>
            <div class="timeline-pill-meta">${phi.count} 条相关表达${phi.tagline ? ` · ${escapeHtml(phi.tagline)}` : ""}</div>
          </div>
        `).join("") || '<div class="empty-state" style="padding:24px 0">这一年没有归纳到明显的高频理念。</div>'}
      </div>
    </div>

    <div class="quotes-section">
      <div class="section-title">年度重点股票</div>
      <div id="timeline-stocks-grid" class="timeline-stocks-grid">
        ${(item.top_stocks || []).map(stock => `
          <div class="phi-stock-card" onclick="openStockFromTimeline('${escapeHtml(stock.ticker)}', '${escapeHtml(item.year)}')">
            <div class="psc-ticker">${escapeHtml(stock.ticker)} · ${escapeHtml(stock.market || "?")}</div>
            <div class="psc-name">${escapeHtml(stock.name)}</div>
            <div class="psc-badges">
              ${stock.bullish_count > 0 ? `<span class="badge badge-bull">▲ 看多 ${stock.bullish_count}</span>` : ""}
              ${stock.bearish_count > 0 ? `<span class="badge badge-bear">▼ 看空 ${stock.bearish_count}</span>` : ""}
              ${stock.count > 0 ? `<span class="badge badge-market">${stock.count}条观点</span>` : ""}
            </div>
          </div>
        `).join("") || '<div class="empty-state" style="padding:24px 0">这一年没有明显集中的个股讨论。</div>'}
      </div>
    </div>

    <div class="quotes-section">
      <div class="section-title">年度关键切片</div>
      <div class="timeline-moments">
        ${(item.moments || []).map(moment => `
          <div class="timeline-moment">
            <div class="timeline-moment-head">
              <span class="timeline-moment-type">${escapeHtml(moment.type === "stock" ? "Stock" : "Philosophy")}</span>
              <span class="timeline-moment-title">${escapeHtml(moment.title)}</span>
              <span class="timeline-moment-meta">${escapeHtml(moment.meta || "")}${moment.date ? ` · ${escapeHtml(moment.date)}` : ""}</span>
            </div>
            <div class="timeline-moment-text">
              ${moment.url ? `<a class="timeline-moment-link" href="${escapeHtml(moment.url)}" target="_blank" rel="noopener">${escapeHtml(moment.text || "查看原文")}</a>` : escapeHtml(moment.text || "")}
            </div>
          </div>
        `).join("") || '<div class="empty-state" style="padding:24px 0">这一年还没有抽出代表性的片段。</div>'}
      </div>
    </div>

    <div class="quotes-section">
      <div class="section-title">分月观点</div>
      ${renderTimelineMonthlyPosts(item.monthly_posts || [])}
    </div>
  `;
}

function buildYearLead(item) {
  const topPhi = item.top_philosophies && item.top_philosophies[0];
  const topStock = item.top_stocks && item.top_stocks[0];
  if (topPhi && topStock) {
    return `${escapeHtml(item.year)} 年里，${escapeHtml(topPhi.title)} 是最突出的理念主题，同时对 ${escapeHtml(topStock.name)} 的讨论也最集中。`;
  }
  if (topPhi) {
    return `${escapeHtml(item.year)} 年里，${escapeHtml(topPhi.title)} 是最突出的理念主题。`;
  }
  if (topStock) {
    return `${escapeHtml(item.year)} 年里，对 ${escapeHtml(topStock.name)} 的讨论最集中。`;
  }
  return `${escapeHtml(item.year)} 年的可归类内容相对较少。`;
}

function renderTimelineMonthlyPosts(monthlyPosts) {
  if (!monthlyPosts.length) {
    return '<div class="empty-state" style="padding:24px 0">这一年还没有可展示的分月观点。</div>';
  }

  return `
    <div class="timeline-month-stream">
      ${monthlyPosts.map(item => `
        <section class="timeline-month-block">
          <div class="timeline-month-head">
            <div class="timeline-month-title">${escapeHtml(item.month)}月</div>
            <div class="timeline-month-count">${item.count} 条观点</div>
          </div>
          ${(item.posts || []).map(post => `
            <article class="timeline-post-card">
              <div class="timeline-post-meta">
                <span class="timeline-post-kicker">MONTHLY</span>
                <span class="timeline-post-date">${escapeHtml(post.datetime || post.date || "")}</span>
                ${post.url ? `<a class="quote-link" href="${escapeHtml(post.url)}" target="_blank" rel="noopener">[原文 ↗]</a>` : ""}
              </div>
              <div class="timeline-post-text">${escapeHtml(truncateText(post.text || "", 220))}</div>
            </article>
          `).join("") || `
            <div class="timeline-post-card">
              <div class="timeline-post-text">这个月还没有可展示的代表性观点。</div>
            </div>
          `}
        </section>
      `).join("")}
    </div>
  `;
}

function truncateText(text, maxLength) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) return normalized;
  return normalized.slice(0, Math.max(0, maxLength - 1)).trimEnd() + "…";
}

async function openStockFromTimeline(ticker, year) {
  try {
    const res = await fetch(`/api/stocks/${encodeURIComponent(ticker)}`);
    if (!res.ok) return;
    const stock = await res.json();
    const yearOpinions = (stock.opinions || []).filter(op => String(op.date || "").startsWith(`${year}-`));
    if (yearOpinions.length === 0) return;
    openChartModal(
      stock.name,
      stock.ticker,
      stock.market,
      yearOpinions,
      null,
      {
        opinions: yearOpinions,
        start: `${year}-01-01`,
        end: `${year}-12-31`,
      },
    );
  } catch (e) {
    console.error("Failed to load timeline stock detail", e);
  }
}
