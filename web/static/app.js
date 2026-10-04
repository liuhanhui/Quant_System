const els = {
  strategy: document.getElementById("strategy"),
  strategyDesc: document.getElementById("strategyDesc"),
  paramFields: document.getElementById("paramFields"),
  source: document.getElementById("source"),
  sourceHint: document.getElementById("sourceHint"),
  symbol: document.getElementById("symbol"),
  cash: document.getElementById("cash"),
  days: document.getElementById("days"),
  start: document.getElementById("start"),
  end: document.getElementById("end"),
  freq: document.getElementById("freq"),
  token: document.getElementById("token"),
  syntheticFields: document.getElementById("syntheticFields"),
  tushareFields: document.getElementById("tushareFields"),
  slippage: document.getElementById("slippage"),
  file: document.getElementById("file"),
  runBtn: document.getElementById("runBtn"),
  runStatus: document.getElementById("runStatus"),
  kpis: document.getElementById("kpis"),
  fillsBody: document.getElementById("fillsBody"),
  fillCount: document.getElementById("fillCount"),
  quoteStatus: document.getElementById("quoteStatus"),
  quoteQuery: document.getElementById("quoteQuery"),
  searchBtn: document.getElementById("searchBtn"),
  stockHits: document.getElementById("stockHits"),
  quotePicked: document.getElementById("quotePicked"),
  quoteStart: document.getElementById("quoteStart"),
  quoteEnd: document.getElementById("quoteEnd"),
  quoteBtn: document.getElementById("quoteBtn"),
  quoteKpis: document.getElementById("quoteKpis"),
  klineTitle: document.getElementById("klineTitle"),
  klineNote: document.getElementById("klineNote"),
  klineCanvas: document.getElementById("klineCanvas"),
  barsBody: document.getElementById("barsBody"),
  barCount: document.getElementById("barCount"),
  usStatus: document.getElementById("usStatus"),
  usQuery: document.getElementById("usQuery"),
  usSearchBtn: document.getElementById("usSearchBtn"),
  usHits: document.getElementById("usHits"),
  usPicked: document.getElementById("usPicked"),
  usStart: document.getElementById("usStart"),
  usEnd: document.getElementById("usEnd"),
  usBtn: document.getElementById("usBtn"),
  usKpis: document.getElementById("usKpis"),
  usKlineTitle: document.getElementById("usKlineTitle"),
  usKlineNote: document.getElementById("usKlineNote"),
  usKlineCanvas: document.getElementById("usKlineCanvas"),
  usBarsBody: document.getElementById("usBarsBody"),
  usBarCount: document.getElementById("usBarCount"),
  hkStatus: document.getElementById("hkStatus"),
  hkQuery: document.getElementById("hkQuery"),
  hkSearchBtn: document.getElementById("hkSearchBtn"),
  hkHits: document.getElementById("hkHits"),
  hkPicked: document.getElementById("hkPicked"),
  hkStart: document.getElementById("hkStart"),
  hkEnd: document.getElementById("hkEnd"),
  hkBtn: document.getElementById("hkBtn"),
  hkKpis: document.getElementById("hkKpis"),
  hkKlineTitle: document.getElementById("hkKlineTitle"),
  hkKlineNote: document.getElementById("hkKlineNote"),
  hkKlineCanvas: document.getElementById("hkKlineCanvas"),
  hkBarsBody: document.getElementById("hkBarsBody"),
  hkBarCount: document.getElementById("hkBarCount"),
};

let strategies = [];
let equityChart;
let ddChart;

function setStatus(kind, text) {
  els.runStatus.className = `status ${kind}`;
  els.runStatus.textContent = text;
}

function currentMeta() {
  return strategies.find((s) => s.key === els.strategy.value);
}

function renderParams() {
  const meta = currentMeta();
  els.strategyDesc.textContent = meta ? meta.desc : "";
  els.paramFields.innerHTML = "";
  (meta?.params || []).forEach((p) => {
    const label = document.createElement("label");
    label.textContent = p.label;
    const input = document.createElement("input");
    input.id = `param_${p.name}`;
    input.type = "number";
    input.value = p.default;
    input.min = p.min;
    input.max = p.max;
    input.step = p.step;
    label.appendChild(input);
    els.paramFields.appendChild(label);
  });
}

function kpiClass(key, metrics) {
  if (key === "总收益率" || key === "年化收益率" || key === "夏普比率") {
    return metrics.total_return >= 0 ? "up" : "down";
  }
  if (key === "最大回撤") return "down";
  return "";
}

function renderKpis(data) {
  const order = ["总收益率", "年化收益率", "夏普比率", "最大回撤", "胜率", "交易次数(完整)", "期末净值"];
  els.kpis.innerHTML = order.map((key) => {
    const cls = kpiClass(key, data.metrics);
    return `<article class="kpi ${cls}"><div class="lab">${key}</div><div class="val">${data.report[key] ?? "—"}</div></article>`;
  }).join("");
}

function chartOptions(yTitle, isPercent) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { maxTicksLimit: 6, color: "#8b9aab" }, grid: { color: "#22303d" } },
      y: {
        title: { display: true, text: yTitle, color: "#8b9aab" },
        ticks: {
          color: "#8b9aab",
          callback: (v) => isPercent ? `${(v * 100).toFixed(2)}%` : v.toLocaleString(),
        },
        grid: { color: "#22303d" },
      },
    },
  };
}

function renderCharts(data) {
  const labels = data.equity.map((p) => p.t.replace("T", " ").slice(0, 16));
  const equity = data.equity.map((p) => p.equity);
  const dd = data.equity.map((p) => p.drawdown);
  if (equityChart) equityChart.destroy();
  if (ddChart) ddChart.destroy();
  equityChart = new Chart(document.getElementById("equityChart"), {
    type: "line",
    data: { labels, datasets: [{ data: equity, borderColor: "#d4a017", backgroundColor: "rgba(212,160,23,0.12)", fill: true, pointRadius: 0, borderWidth: 1.6, tension: 0.15 }] },
    options: chartOptions("净值", false),
  });
  ddChart = new Chart(document.getElementById("ddChart"), {
    type: "line",
    data: { labels, datasets: [{ data: dd, borderColor: "#e15b5b", backgroundColor: "rgba(225,91,91,0.18)", fill: true, pointRadius: 0, borderWidth: 1.4, tension: 0.15 }] },
    options: chartOptions("回撤", true),
  });
}

function renderFills(fills) {
  els.fillCount.textContent = `${fills.length} 笔`;
  if (!fills.length) {
    els.fillsBody.innerHTML = `<tr><td colspan="5" class="empty">本次没有成交</td></tr>`;
    return;
  }
  els.fillsBody.innerHTML = fills.map((f) => {
    const dir = f.direction === "BUY" ? "买入" : "卖出";
    const cls = f.direction === "BUY" ? "buy" : "sell";
    return `<tr>
      <td>${f.timestamp.replace("T", " ").slice(0, 19)}</td>
      <td class="${cls}">${dir}</td>
      <td>${f.volume}</td>
      <td>${Number(f.price).toFixed(2)}</td>
      <td>${Number(f.commission).toFixed(2)}</td>
    </tr>`;
  }).join("");
}

async function loadStrategies() {
  const rv = await fetch("/api/strategies");
  const body = await rv.json();
  strategies = body.strategies || [];
  els.strategy.innerHTML = strategies.map((s) => `<option value="${s.key}">${s.name}</option>`).join("");
  renderParams();
}

function ymd(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function defaultRange() {
  const end = new Date();
  end.setDate(end.getDate() - 1);
  const start = new Date(end);
  start.setDate(start.getDate() - (els.freq.value === "D" ? 400 : 6));
  return { start: ymd(start), end: ymd(end) };
}

function syncSourceFields() {
  const tushare = els.source.value === "tushare";
  els.syntheticFields.hidden = tushare;
  els.tushareFields.hidden = !tushare;
  if (tushare) {
    if (!els.start.value) {
      const range = defaultRange();
      els.start.value = range.start;
      els.end.value = range.end;
    }
    if (els.symbol.value === "SIM000001") els.symbol.value = "600519";
    els.sourceHint.textContent = "你这套账号目前能拉分钟线。默认 1 分钟收盘价；若日线没权限会自动改用分钟。";
  } else {
    if (els.symbol.value === "600519") els.symbol.value = "SIM000001";
    els.sourceHint.textContent = "本机几何布朗运动合成 tick，仅用于把管线跑通。";
  }
}

function collectForm() {
  const fd = new FormData();
  fd.set("strategy", els.strategy.value);
  fd.set("source", els.source.value);
  fd.set("symbol", els.symbol.value.trim() || (els.source.value === "tushare" ? "600519" : "SIM000001"));
  fd.set("cash", els.cash.value);
  fd.set("days", els.days.value);
  fd.set("start", els.start.value);
  fd.set("end", els.end.value);
  fd.set("freq", els.freq.value);
  fd.set("slippage", els.slippage.value);
  if (els.token.value.trim()) fd.set("token", els.token.value.trim());
  (currentMeta()?.params || []).forEach((p) => {
    const input = document.getElementById(`param_${p.name}`);
    if (input) fd.set(p.name, input.value);
  });
  if (els.file.files[0]) fd.set("file", els.file.files[0]);
  return fd;
}

async function runBacktest() {
  els.runBtn.disabled = true;
  setStatus("busy", "回测中…");
  try {
    const rv = await fetch("/api/run", { method: "POST", body: collectForm() });
    const body = await rv.json();
    if (!rv.ok) throw new Error(body.error || "回测失败");
    renderKpis(body);
    renderCharts(body);
    renderFills(body.fills || []);
    const note = body.data_note ? ` · ${body.data_note}` : "";
    setStatus("ok", `${body.tick_count.toLocaleString()} 根${note}`);
  } catch (err) {
    setStatus("err", err.message);
  } finally {
    els.runBtn.disabled = false;
  }
}

els.strategy.addEventListener("change", renderParams);
els.source.addEventListener("change", syncSourceFields);
els.runBtn.addEventListener("click", runBacktest);

syncSourceFields();
loadStrategies().then(() => {
  if (els.source && els.source.value === "synthetic") runBacktest();
});

let pickedStock = null;
let lastQuote = null;
let pickedUs = null;
let lastUsQuote = null;
let pickedHk = null;
let lastHkQuote = null;

function setQuoteStatus(kind, text) {
  if (!els.quoteStatus) return;
  els.quoteStatus.className = `status ${kind}`;
  els.quoteStatus.textContent = text;
}

function setUsStatus(kind, text) {
  if (!els.usStatus) return;
  els.usStatus.hidden = false;
  els.usStatus.className = `status ${kind}`;
  els.usStatus.textContent = text;
}

function setHkStatus(kind, text) {
  if (!els.hkStatus) return;
  els.hkStatus.className = `status ${kind}`;
  els.hkStatus.textContent = text;
}

function fillYearRange(startEl, endEl) {
  if (startEl.value) return;
  const end = new Date();
  end.setDate(end.getDate() - 1);
  const start = new Date(end);
  start.setFullYear(start.getFullYear() - 1);
  endEl.value = ymd(end);
  startEl.value = ymd(start);
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === name);
  });
  [
    ["view-backtest", "backtest"],
    ["view-quotes", "quotes"],
    ["view-us", "us"],
    ["view-hk", "hk"],
  ].forEach(([id, key]) => {
    const node = document.getElementById(id);
    if (node) node.hidden = name !== key;
  });
  if (els.runStatus) els.runStatus.hidden = name !== "backtest";
  if (els.quoteStatus) els.quoteStatus.hidden = name !== "quotes";
  if (els.usStatus) els.usStatus.hidden = name !== "us";
  if (els.hkStatus) els.hkStatus.hidden = name !== "hk";
  if (name === "quotes") {
    if (els.quoteStart) fillYearRange(els.quoteStart, els.quoteEnd);
    if (lastQuote) drawKline(els.klineCanvas, lastQuote.bars);
  }
  if (name === "us") {
    if (els.usStart) fillYearRange(els.usStart, els.usEnd);
    if (els.usQuery && !els.usQuery.value) els.usQuery.value = "AAPL";
    pickedUs = pickedUs || { ts_code: "AAPL", name: "Apple" };
    if (lastUsQuote) {
      requestAnimationFrame(() => drawKline(els.usKlineCanvas, lastUsQuote.bars, { up: "#3dbe7a", down: "#e15b5b" }));
    } else {
      loadUsQuotes();
    }
  }
  if (name === "hk") {
    if (els.hkStart) fillYearRange(els.hkStart, els.hkEnd);
    if (lastHkQuote) drawKline(els.hkKlineCanvas, lastHkQuote.bars);
  }
}

function fmtNum(v, digits = 2) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function pctText(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${(Number(v) * 100).toFixed(2)}%`;
}

function renderHits(stocks) {
  if (!stocks.length) {
    els.stockHits.innerHTML = `<li class="empty-hit">没有匹配，试试 6 位代码</li>`;
    return;
  }
  els.stockHits.innerHTML = stocks.map((s, i) => `
    <li data-i="${i}">
      <span class="code">${s.ts_code}</span>${s.name}
      <div class="meta">${s.industry || ""} ${s.market || ""}</div>
    </li>
  `).join("");
  els.stockHits.querySelectorAll("li[data-i]").forEach((li) => {
    li.addEventListener("click", () => pickStock(stocks[Number(li.dataset.i)]));
  });
}

function pickStock(stock) {
  pickedStock = stock;
  els.quoteQuery.value = stock.name && stock.name !== stock.symbol ? stock.name : stock.ts_code;
  els.quotePicked.textContent = `当前：${stock.name} ${stock.ts_code}`;
  els.stockHits.querySelectorAll("li").forEach((li) => {
    li.classList.toggle("active", li.textContent.includes(stock.ts_code));
  });
  loadQuotes();
}

async function searchStocks() {
  const q = els.quoteQuery.value.trim();
  if (!q) {
    els.stockHits.innerHTML = `<li class="empty-hit">输入名称或 6 位代码，点搜索</li>`;
    return;
  }
  setQuoteStatus("busy", "搜索中…");
  try {
    const rv = await fetch(`/api/stocks?q=${encodeURIComponent(q)}`);
    const body = await rv.json();
    if (!rv.ok) throw new Error(body.error || "搜索失败");
    renderHits(body.stocks || []);
    setQuoteStatus("ok", `${(body.stocks || []).length} 只匹配`);
    if ((body.stocks || []).length === 1) pickStock(body.stocks[0]);
  } catch (err) {
    setQuoteStatus("err", err.message);
  }
}

function renderQuoteKpis(data) {
  const s = data.stats || {};
  const chg = Number(s.change_pct);
  const tone = chg >= 0 ? "cn-up" : "cn-down";
  const sign = chg >= 0 ? "+" : "";
  els.quoteKpis.innerHTML = [
    { lab: "公司", val: data.name, cls: "" },
    { lab: "代码", val: data.ts_code, cls: "" },
    { lab: "区间末收", val: fmtNum(s.last_close), cls: tone },
    { lab: "区间涨跌", val: sign + pctText(chg), cls: tone },
    { lab: "最高 / 最低", val: `${fmtNum(s.high)} / ${fmtNum(s.low)}`, cls: "" },
    { lab: "K 线根数", val: String(s.bars ?? 0), cls: "" },
  ].map((x) => `<article class="kpi ${x.cls}"><div class="lab">${x.lab}</div><div class="val">${x.val}</div></article>`).join("");
}

function renderBars(bars) {
  els.barCount.textContent = `${bars.length} 根`;
  if (!bars.length) {
    els.barsBody.innerHTML = `<tr><td colspan="8" class="empty">没有日线</td></tr>`;
    return;
  }
  const rows = [...bars].reverse();
  els.barsBody.innerHTML = rows.map((b) => {
    const pct = b.pct_chg == null ? "—" : `${Number(b.pct_chg).toFixed(2)}%`;
    const cls = Number(b.pct_chg) > 0 ? "chg-up" : Number(b.pct_chg) < 0 ? "chg-down" : "";
    return `<tr>
      <td>${b.date}</td>
      <td>${fmtNum(b.open)}</td>
      <td>${fmtNum(b.high)}</td>
      <td>${fmtNum(b.low)}</td>
      <td class="${cls}">${fmtNum(b.close)}</td>
      <td class="${cls}">${pct}</td>
      <td>${Math.round(b.vol).toLocaleString("zh-CN")}</td>
      <td>${fmtNum(b.amount, 0)}</td>
    </tr>`;
  }).join("");
}

function drawKline(canvas, bars, colors) {
  if (!canvas || !bars || !bars.length) return;
  const upColor = colors?.up || "#e15b5b";
  const downColor = colors?.down || "#3dbe7a";
  bars = bars
    .filter((b) => [b.open, b.high, b.low, b.close].every((x) => Number.isFinite(Number(x))))
    .slice()
    .sort((a, b) => String(a.date).localeCompare(String(b.date)));
  if (!bars.length) return;
  const wrap = canvas.parentElement;
  const cssW = wrap.clientWidth || 800;
  const cssH = wrap.clientHeight || 420;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  canvas.style.width = `${cssW}px`;
  canvas.style.height = `${cssH}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  const pad = { l: 58, r: 16, t: 12, b: 22 };
  const gap = 10;
  const volH = Math.floor((cssH - pad.t - pad.b - gap) * 0.22);
  const priceH = cssH - pad.t - pad.b - gap - volH;
  const plotW = cssW - pad.l - pad.r;
  const highs = bars.map((b) => b.high);
  const lows = bars.map((b) => b.low);
  const vols = bars.map((b) => b.vol);
  let pMin = Math.min(...lows);
  let pMax = Math.max(...highs);
  const pPad = (pMax - pMin) * 0.06 || 1;
  pMin -= pPad;
  pMax += pPad;
  const vMax = Math.max(...vols, 1);
  const n = bars.length;
  const slot = plotW / n;
  const bodyW = Math.max(1, Math.min(8, slot * 0.7));

  const yPrice = (v) => pad.t + (pMax - v) / (pMax - pMin) * priceH;
  const yVol = (v) => pad.t + priceH + gap + volH - (v / vMax) * volH;
  const xAt = (i) => pad.l + (i + 0.5) * slot;

  ctx.strokeStyle = "#22303d";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, pad.t + priceH);
  ctx.lineTo(cssW - pad.r, pad.t + priceH);
  ctx.moveTo(pad.l, pad.t + priceH + gap);
  ctx.lineTo(pad.l, pad.t + priceH + gap + volH);
  ctx.lineTo(cssW - pad.r, pad.t + priceH + gap + volH);
  ctx.stroke();

  ctx.fillStyle = "#8b9aab";
  ctx.font = "11px Segoe UI, Microsoft YaHei, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let i = 0; i < 5; i += 1) {
    const v = pMin + (pMax - pMin) * (1 - i / 4);
    const y = yPrice(v);
    ctx.fillText(v.toFixed(pMax >= 50 ? 0 : 2), pad.l - 6, y);
    ctx.strokeStyle = "#1a2430";
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(cssW - pad.r, y);
    ctx.stroke();
  }

  bars.forEach((b, i) => {
    const up = b.close >= b.open;
    const color = up ? upColor : downColor;
    const x = xAt(i);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, yPrice(b.high));
    ctx.lineTo(x, yPrice(b.low));
    ctx.stroke();
    const top = yPrice(Math.max(b.open, b.close));
    const bot = yPrice(Math.min(b.open, b.close));
    const h = Math.max(bot - top, 1);
    ctx.fillRect(x - bodyW / 2, top, bodyW, h);
    const vh = Math.max(yVol(0) - yVol(b.vol), 1);
    ctx.globalAlpha = 0.85;
    ctx.fillRect(x - bodyW / 2, yVol(b.vol), bodyW, vh);
    ctx.globalAlpha = 1;
  });

  ctx.fillStyle = "#8b9aab";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const step = Math.max(1, Math.ceil(n / 6));
  for (let i = 0; i < n; i += step) {
    ctx.fillText(bars[i].date.slice(0, 7), xAt(i), cssH - pad.b + 4);
  }
}

async function loadQuotes() {
  const symbol = (pickedStock && pickedStock.ts_code) || els.quoteQuery.value.trim();
  if (!symbol) {
    setQuoteStatus("err", "请先搜索并选择公司");
    return;
  }
  els.quoteBtn.disabled = true;
  setQuoteStatus("busy", "拉取日 K…");
  try {
    const params = new URLSearchParams({
      symbol,
      start: els.quoteStart.value,
      end: els.quoteEnd.value,
    });
    const rv = await fetch(`/api/quotes?${params}`);
    const body = await rv.json();
    if (!rv.ok) throw new Error(body.error || "拉取失败");
    lastQuote = body;
    els.klineTitle.textContent = `${body.name} ${body.ts_code} 日K`;
    els.klineNote.textContent = body.note || "";
    renderQuoteKpis(body);
    renderBars(body.bars || []);
    drawKline(els.klineCanvas, body.bars || []);
    setQuoteStatus("ok", `${(body.bars || []).length} 根 · ${body.note || ""}`);
  } catch (err) {
    setQuoteStatus("err", err.message);
  } finally {
    els.quoteBtn.disabled = false;
  }
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});
els.searchBtn && els.searchBtn.addEventListener("click", searchStocks);
els.quoteQuery && els.quoteQuery.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") searchStocks();
});
els.quoteBtn && els.quoteBtn.addEventListener("click", loadQuotes);
document.querySelectorAll("#quoteChips .chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    els.quoteQuery.value = btn.dataset.q;
    searchStocks();
  });
});

function renderUsHits(stocks) {
  if (!stocks.length) {
    els.usHits.innerHTML = `<li class="empty-hit">没有匹配，试试 AAPL / TSLA</li>`;
    return;
  }
  els.usHits.innerHTML = stocks.map((s, i) => `
    <li data-i="${i}">
      <span class="code">${s.ts_code}</span>${s.name}
      <div class="meta">${s.enname || ""} ${s.classify || ""}</div>
    </li>
  `).join("");
  els.usHits.querySelectorAll("li[data-i]").forEach((li) => {
    li.addEventListener("click", () => pickUs(stocks[Number(li.dataset.i)]));
  });
}

function pickUs(stock) {
  pickedUs = stock;
  els.usQuery.value = stock.ts_code;
  els.usPicked.textContent = `当前：${stock.name} ${stock.ts_code}`;
  els.usHits.querySelectorAll("li").forEach((li) => {
    li.classList.toggle("active", li.textContent.includes(stock.ts_code));
  });
  loadUsQuotes();
}

async function searchUs() {
  const q = els.usQuery.value.trim();
  if (!q) {
    els.usHits.innerHTML = `<li class="empty-hit">输入英文名或代码，点搜索</li>`;
    return;
  }
  setUsStatus("busy", "搜索中…");
  try {
    const rv = await fetch(`/api/us/stocks?q=${encodeURIComponent(q)}`);
    const body = await rv.json();
    if (!rv.ok) throw new Error(body.error || "搜索失败");
    renderUsHits(body.stocks || []);
    setUsStatus("ok", `${(body.stocks || []).length} 只匹配`);
    if ((body.stocks || []).length === 1) pickUs(body.stocks[0]);
  } catch (err) {
    setUsStatus("err", err.message);
  }
}

function renderUsKpis(data) {
  const s = data.stats || {};
  const chg = Number(s.change_pct);
  const tone = chg >= 0 ? "us-up" : "us-down";
  const sign = chg >= 0 ? "+" : "";
  els.usKpis.innerHTML = [
    { lab: "公司", val: data.name, cls: "" },
    { lab: "代码", val: data.ts_code, cls: "" },
    { lab: "区间末收", val: fmtNum(s.last_close), cls: tone },
    { lab: "区间涨跌", val: sign + pctText(chg), cls: tone },
    { lab: "最高 / 最低", val: `${fmtNum(s.high)} / ${fmtNum(s.low)}`, cls: "" },
    { lab: "K 线根数", val: String(s.bars ?? 0), cls: "" },
  ].map((x) => `<article class="kpi ${x.cls}"><div class="lab">${x.lab}</div><div class="val">${x.val}</div></article>`).join("");
}

function renderUsBars(bars) {
  els.usBarCount.textContent = `${bars.length} 根`;
  if (!bars.length) {
    els.usBarsBody.innerHTML = `<tr><td colspan="8" class="empty">没有日线</td></tr>`;
    return;
  }
  const rows = [...bars].reverse();
  els.usBarsBody.innerHTML = rows.map((b) => {
    const pct = b.pct_chg == null ? "—" : `${Number(b.pct_chg).toFixed(2)}%`;
    const cls = Number(b.pct_chg) > 0 ? "chg-us-up" : Number(b.pct_chg) < 0 ? "chg-us-down" : "";
    return `<tr>
      <td>${b.date}</td>
      <td>${fmtNum(b.open)}</td>
      <td>${fmtNum(b.high)}</td>
      <td>${fmtNum(b.low)}</td>
      <td class="${cls}">${fmtNum(b.close)}</td>
      <td class="${cls}">${pct}</td>
      <td>${Math.round(b.vol).toLocaleString("en-US")}</td>
      <td>${b.amount ? fmtNum(b.amount, 0) : "—"}</td>
    </tr>`;
  }).join("");
}

async function loadUsQuotes() {
  const symbol = (pickedUs && pickedUs.ts_code) || (els.usQuery && els.usQuery.value.trim());
  if (!symbol) {
    if (els.usStatus) setUsStatus("err", "请先搜索并选择公司");
    return;
  }
  if (els.usBtn) els.usBtn.disabled = true;
  if (els.usStatus) setUsStatus("busy", "拉取日 K…");
  try {
    if (els.usStart && els.usEnd) fillYearRange(els.usStart, els.usEnd);
    const params = new URLSearchParams({
      symbol,
      start: (els.usStart && els.usStart.value) || "",
      end: (els.usEnd && els.usEnd.value) || "",
    });
    const rv = await fetch(`/api/us/quotes?${params}`);
    const body = await rv.json();
    if (!rv.ok) throw new Error(body.error || "拉取失败");
    lastUsQuote = body;
    if (els.usKlineTitle) els.usKlineTitle.textContent = `${body.name} ${body.ts_code} 日K`;
    if (els.usKlineNote) els.usKlineNote.textContent = body.note || "";
    renderUsKpis(body);
    renderUsBars(body.bars || []);
    requestAnimationFrame(() => {
      drawKline(els.usKlineCanvas, body.bars || [], { up: "#3dbe7a", down: "#e15b5b" });
    });
    if (els.usStatus) setUsStatus("ok", `${(body.bars || []).length} 根 · ${body.note || ""}`);
  } catch (err) {
    if (els.usStatus) setUsStatus("err", err.message);
    if (els.usKpis) {
      els.usKpis.innerHTML = `<article class="kpi down"><div class="lab">美股加载失败</div><div class="val">${err.message}</div></article>`;
    }
  } finally {
    if (els.usBtn) els.usBtn.disabled = false;
  }
}

pickedUs = { ts_code: "AAPL", name: "Apple" };
if (els.usQuery) els.usQuery.value = "AAPL";
if (els.usStart && els.usEnd) fillYearRange(els.usStart, els.usEnd);
loadUsQuotes();

els.usSearchBtn && els.usSearchBtn.addEventListener("click", searchUs);
els.usQuery && els.usQuery.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") searchUs();
});
els.usBtn && els.usBtn.addEventListener("click", loadUsQuotes);
document.querySelectorAll("#usChips .chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    els.usQuery.value = btn.dataset.q;
    searchUs();
  });
});

function renderHkHits(stocks) {
  if (!stocks.length) {
    els.hkHits.innerHTML = `<li class="empty-hit">没有匹配，试试 00700 / 腾讯</li>`;
    return;
  }
  els.hkHits.innerHTML = stocks.map((s, i) => `
    <li data-i="${i}">
      <span class="code">${s.ts_code}</span>${s.name}
      <div class="meta">${s.enname || ""} ${s.market || "HK"}</div>
    </li>
  `).join("");
  els.hkHits.querySelectorAll("li[data-i]").forEach((li) => {
    li.addEventListener("click", () => pickHk(stocks[Number(li.dataset.i)]));
  });
}

function pickHk(stock) {
  pickedHk = stock;
  els.hkQuery.value = stock.ts_code;
  els.hkPicked.textContent = `当前：${stock.name} ${stock.ts_code}`;
  els.hkHits.querySelectorAll("li").forEach((li) => {
    li.classList.toggle("active", li.textContent.includes(stock.ts_code));
  });
  loadHkQuotes();
}

async function searchHk() {
  const q = els.hkQuery.value.trim();
  if (!q) {
    els.hkHits.innerHTML = `<li class="empty-hit">输入名称或 4/5 位代码，点搜索</li>`;
    return;
  }
  setHkStatus("busy", "搜索中…");
  try {
    const rv = await fetch(`/api/hk/stocks?q=${encodeURIComponent(q)}`);
    const body = await rv.json();
    if (!rv.ok) throw new Error(body.error || "搜索失败");
    renderHkHits(body.stocks || []);
    setHkStatus("ok", `${(body.stocks || []).length} 只匹配`);
    if ((body.stocks || []).length === 1) pickHk(body.stocks[0]);
  } catch (err) {
    setHkStatus("err", err.message);
  }
}

function renderHkKpis(data) {
  const s = data.stats || {};
  const chg = Number(s.change_pct);
  const tone = chg >= 0 ? "cn-up" : "cn-down";
  const sign = chg >= 0 ? "+" : "";
  els.hkKpis.innerHTML = [
    { lab: "公司", val: data.name, cls: "" },
    { lab: "代码", val: data.ts_code, cls: "" },
    { lab: "区间末收", val: fmtNum(s.last_close), cls: tone },
    { lab: "区间涨跌", val: sign + pctText(chg), cls: tone },
    { lab: "最高 / 最低", val: `${fmtNum(s.high)} / ${fmtNum(s.low)}`, cls: "" },
    { lab: "K 线根数", val: String(s.bars ?? 0), cls: "" },
  ].map((x) => `<article class="kpi ${x.cls}"><div class="lab">${x.lab}</div><div class="val">${x.val}</div></article>`).join("");
}

function renderHkBars(bars) {
  els.hkBarCount.textContent = `${bars.length} 根`;
  if (!bars.length) {
    els.hkBarsBody.innerHTML = `<tr><td colspan="8" class="empty">没有日线</td></tr>`;
    return;
  }
  const rows = [...bars].reverse();
  els.hkBarsBody.innerHTML = rows.map((b) => {
    const pct = b.pct_chg == null ? "—" : `${Number(b.pct_chg).toFixed(2)}%`;
    const cls = Number(b.pct_chg) > 0 ? "chg-up" : Number(b.pct_chg) < 0 ? "chg-down" : "";
    return `<tr>
      <td>${b.date}</td>
      <td>${fmtNum(b.open)}</td>
      <td>${fmtNum(b.high)}</td>
      <td>${fmtNum(b.low)}</td>
      <td class="${cls}">${fmtNum(b.close)}</td>
      <td class="${cls}">${pct}</td>
      <td>${Math.round(b.vol).toLocaleString("zh-CN")}</td>
      <td>${b.amount ? fmtNum(b.amount, 0) : "—"}</td>
    </tr>`;
  }).join("");
}

async function loadHkQuotes() {
  const symbol = (pickedHk && pickedHk.ts_code) || els.hkQuery.value.trim();
  if (!symbol) {
    setHkStatus("err", "请先搜索并选择公司");
    return;
  }
  els.hkBtn.disabled = true;
  setHkStatus("busy", "拉取日 K…");
  try {
    const params = new URLSearchParams({
      symbol,
      start: els.hkStart.value,
      end: els.hkEnd.value,
    });
    const rv = await fetch(`/api/hk/quotes?${params}`);
    const body = await rv.json();
    if (!rv.ok) throw new Error(body.error || "拉取失败");
    lastHkQuote = body;
    els.hkKlineTitle.textContent = `${body.name} ${body.ts_code} 日K`;
    els.hkKlineNote.textContent = body.note || "";
    renderHkKpis(body);
    renderHkBars(body.bars || []);
    drawKline(els.hkKlineCanvas, body.bars || []);
    setHkStatus("ok", `${(body.bars || []).length} 根 · ${body.note || ""}`);
  } catch (err) {
    setHkStatus("err", err.message);
  } finally {
    els.hkBtn.disabled = false;
  }
}

els.hkSearchBtn && els.hkSearchBtn.addEventListener("click", searchHk);
els.hkQuery && els.hkQuery.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") searchHk();
});
els.hkBtn && els.hkBtn.addEventListener("click", loadHkQuotes);
document.querySelectorAll("#hkChips .chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    els.hkQuery.value = btn.dataset.q;
    searchHk();
  });
});
window.addEventListener("resize", () => {
  if (lastQuote) drawKline(els.klineCanvas, lastQuote.bars);
  if (lastUsQuote) drawKline(els.usKlineCanvas, lastUsQuote.bars, { up: "#3dbe7a", down: "#e15b5b" });
  if (lastHkQuote) drawKline(els.hkKlineCanvas, lastHkQuote.bars);
});

