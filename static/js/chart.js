/* K-line chart — adapted from check_finance/static/js/chart.js */
let chartInstance = null;

async function loadChart(ticker, market, opinions, container = document.getElementById("chart-container"), options = {}) {
  if (!container) return;

  if (!opinions || opinions.length === 0) {
    container.innerHTML =
      '<div style="color:#666;padding:40px;text-align:center">没有该股票的观点数据</div>';
    return;
  }

  const opDates = opinions.map(o => o.date).sort();
  const earliest = opDates[0];
  const start = options.start || addDays(earliest, -10);
  const end = options.end || new Date().toISOString().split("T")[0];

  let bars = [];
  try {
    const res = await fetch(
      `/api/stock/${encodeURIComponent(ticker)}?market=${encodeURIComponent(market)}&start=${start}&end=${end}&force=0`
    );
    const data = await res.json();
    bars = data.bars || [];
    if (bars.length === 0) {
      container.innerHTML =
        `<div style="color:#666;padding:40px;text-align:center;line-height:1.7">
          暂无行情数据 (${escapeHtml(ticker)})<br>
          <span style="font-size:12px;color:#888">${escapeHtml(data.error || "")}</span>
        </div>`;
      return;
    }
  } catch (e) {
    container.innerHTML =
      '<div style="color:#666;padding:40px;text-align:center">行情数据加载失败</div>';
    return;
  }

  renderChart(ticker, bars, opinions, container);
}

function addDays(dateStr, days) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return d.toISOString().split("T")[0];
}

function renderChart(ticker, bars, opinions, container) {
  disposeChart();
  chartInstance = echarts.init(container, "dark");
  const isMobile = isMobileViewport();

  const dates = bars.map(b => b.date);
  const ohlcData = bars.map(b => [b.open, b.close, b.low, b.high]);

  const allHighs = bars.map(b => b.high);
  const allLows = bars.map(b => b.low);
  const priceRange = (Math.max(...allHighs) - Math.min(...allLows)) || 1;
  const offset = priceRange * 0.025;

  const barMap = {};
  bars.forEach(b => { barMap[b.date] = b; });

  const scatterData = opinions.map(op => {
    const tradeDate = findNearestTradingDate(dates, op.date);
    const bar = tradeDate ? barMap[tradeDate] : null;
    if (!bar) return null;
    const y = op.sentiment === "bullish" ? bar.high + offset : bar.low - offset;
    return {
      value: [tradeDate, y],
      sentiment: op.sentiment,
      summary: op.summary,
      url: op.url,
      date: op.date,
    };
  }).filter(Boolean);

  const initialZoom = computeInitialZoomWindow(dates, opinions);
  const labelInterval = isMobile ? Math.max(0, Math.ceil(dates.length / 4) - 1) : "auto";

  const option = {
    backgroundColor: "#111118",
    animation: false,
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "cross" },
      formatter: params => {
        const candle = params.find(p => p.seriesType === "candlestick");
        if (!candle) return "";
        const bar = barMap[candle.axisValue];
        if (!bar) return candle.axisValue || "";
        return `${candle.axisValue}<br>开: ${bar.open}<br>收: ${bar.close}<br>低: ${bar.low}<br>高: ${bar.high}`;
      }
    },
    legend: isMobile ? undefined : { data: [ticker], top: 4, textStyle: { color: "#ccc" } },
    grid: {
      left: isMobile ? "10%" : "7%",
      right: isMobile ? "4%" : "3%",
      top: isMobile ? 24 : 40,
      bottom: isMobile ? 58 : 72,
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: {
        color: "#888",
        fontSize: isMobile ? 9 : 10,
        rotate: isMobile ? 0 : 30,
        interval: labelInterval,
        hideOverlap: true,
      },
      axisLine: { lineStyle: { color: "#333" } }
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: "#888", fontSize: isMobile ? 9 : 10 },
      splitLine: { lineStyle: { color: "#222" } }
    },
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: 0,
        startValue: initialZoom.startValue,
        endValue: initialZoom.endValue,
        minValueSpan: initialZoom.minValueSpan,
      },
      {
        type: "slider",
        xAxisIndex: 0,
        startValue: initialZoom.startValue,
        endValue: initialZoom.endValue,
        minValueSpan: initialZoom.minValueSpan,
        height: isMobile ? 14 : 20,
        bottom: isMobile ? 4 : 6,
        fillerColor: "rgba(201,168,76,0.2)", borderColor: "#333", handleStyle: { color: "#555" } }
    ],
    series: [
      {
        name: ticker,
        type: "candlestick",
        data: ohlcData,
        itemStyle: {
          color: "#ef5350",
          color0: "#26a69a",
          borderColor: "#ef5350",
          borderColor0: "#26a69a"
        }
      },
      {
        name: "opinions",
        type: "scatter",
        data: scatterData,
        symbolSize: isMobile ? 7 : 10,
        itemStyle: {
          color: params => params.data.sentiment === "bullish" ? "#00e676" : "#ff1744",
          borderColor: "#fff",
          borderWidth: isMobile ? 0.8 : 1,
          opacity: 0.9
        },
        tooltip: {
          trigger: "item",
          confine: true,
          formatter: params => {
            const d = params.data;
            const dir = d.sentiment === "bullish" ? "▲ 看多" : "▼ 看空";
            return `${d.date}<br>${dir}: ${escapeHtml(d.summary)}`;
          }
        },
        z: 10
      }
    ]
  };

  chartInstance.setOption(option);

  window.addEventListener("resize", () => {
    if (chartInstance) chartInstance.resize();
  });

  // Click on scatter dot → open original Xueqiu URL
  chartInstance.on("click", { seriesName: "opinions" }, params => {
    if (params.data && params.data.url) {
      window.open(params.data.url, "_blank", "noopener");
    }
  });
}

function isMobileViewport() {
  return window.matchMedia("(max-width: 768px)").matches;
}

function findNearestTradingDate(dates, targetDate) {
  for (const date of dates) {
    if (date >= targetDate) return date;
  }
  return null;
}

function computeInitialZoomWindow(dates, opinions) {
  if (!dates.length) {
    return { startValue: undefined, endValue: undefined, minValueSpan: 20 };
  }

  const opinionDates = opinions
    .map(op => findNearestTradingDate(dates, op.date))
    .filter(Boolean)
    .sort();

  if (!opinionDates.length) {
    return {
      startValue: dates[Math.max(0, dates.length - 120)],
      endValue: dates[dates.length - 1],
      minValueSpan: Math.min(dates.length, 20),
    };
  }

  const firstIdx = dates.indexOf(opinionDates[0]);
  const lastIdx = dates.indexOf(opinionDates[opinionDates.length - 1]);
  const leadingPadding = 30;
  const trailingPadding = 45;
  const minSpan = 90;

  let startIdx = Math.max(0, firstIdx - leadingPadding);
  let endIdx = Math.min(dates.length - 1, lastIdx + trailingPadding);

  if (endIdx - startIdx + 1 < minSpan) {
    const deficit = minSpan - (endIdx - startIdx + 1);
    startIdx = Math.max(0, startIdx - Math.ceil(deficit / 2));
    endIdx = Math.min(dates.length - 1, endIdx + Math.floor(deficit / 2));
  }

  return {
    startValue: dates[startIdx],
    endValue: dates[endIdx],
    minValueSpan: Math.min(dates.length, 20),
  };
}

function disposeChart() {
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
}
