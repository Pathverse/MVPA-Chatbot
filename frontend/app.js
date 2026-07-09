const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("msg-input");
const goalsEl = document.getElementById("goals-list");
const wearableEl = document.getElementById("wearable-data");

function addBubble(text, role) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderGoals(goals) {
  goalsEl.innerHTML = "";
  const list = goals || [];
  for (let i = 0; i < 3; i++) {
    const text = list[i];
    const li = document.createElement("li");
    const num = document.createElement("div");
    num.className = "goal-number";
    num.textContent = `Goal ${i + 1}`;
    li.appendChild(num);
    const body = document.createElement("div");
    if (text) {
      body.className = "goal-text";
      body.textContent = text;
    } else {
      li.classList.add("goal-empty");
      body.className = "goal-placeholder";
      body.textContent = "Empty — not set yet";
    }
    li.appendChild(body);
    goalsEl.appendChild(li);
  }
}

async function startSession() {
  const r = await fetch("/session/start", { method: "POST" });
  const d = await r.json();
  if (d.onboarding_complete) {
    addBubble(d.name ? `Welcome back, ${d.name}.` : "Welcome back.", "coach");
    renderGoals(d.smart_goals);
  } else if (d.question) {
    addBubble(d.question, "coach");
  }
}

async function sendToCoach(text) {
  addBubble(text, "user");

  const r = await fetch("/session/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text }),
  });
  const d = await r.json();

  addBubble(d.response, "coach");

  if (d.field_updated) renderGoals(d.smart_goals);
}

function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = "";
  sendToCoach(text);
}

function ring(pct, value, title) {
  const r = 46, circ = 2 * Math.PI * r;
  const achieved = pct >= 1;
  // Overshoot slightly so the tip overlaps the start (Apple style)
  const fill = achieved ? circ * 1.015 : Math.min(pct, 1) * circ;
  const trackStroke = achieved ? 'rgba(0,166,153,0.22)' : 'var(--border)';
  // Cap dot sits at the 12-o'clock position in SVG space (before CSS -90deg rotation)
  // which is the rightmost point: (cx+r, cy)
  const capDot = achieved
    ? `<circle cx="${54 + r}" cy="54" r="5.5" fill="#00a699" class="ring-cap"/>`
    : '';
  return `
    <div class="ring-meta">
      <div class="ring-title">${title}</div>
    </div>
    <div class="ring-wrap">
      <svg viewBox="0 0 108 108" class="ring-svg">
        <circle cx="54" cy="54" r="${r}" class="ring-track" stroke="${trackStroke}"/>
        <circle cx="54" cy="54" r="${r}" class="ring-fill ${achieved ? "ring-fill--done" : ""}"
          stroke-dasharray="${fill} ${circ}"/>
        ${capDot}
      </svg>
      <div class="ring-inner">
        <span class="ring-value">${value}</span>
        <span class="ring-unit">min</span>
      </div>
    </div>`;
}

function weekdayShort(dateStr) {
  return new Date(`${dateStr}T00:00:00`).toLocaleDateString("en-US", { weekday: "short" });
}

function dayDots(records, getValue, maxVal, getLabel) {
  const wrap = document.createElement("div");
  wrap.className = "day-dots";
  records.forEach((rec) => {
    const val = getValue(rec);
    const pct = maxVal ? Math.min(val / maxVal, 1) : 0;
    const barHeight = val > 0 ? Math.max(Math.round(pct * 100), 4) : 0;
    const col = document.createElement("div");
    col.className = "day-col";
    col.innerHTML = `
      <div class="day-bar-wrap"><div class="day-bar" style="height:${barHeight}%"></div></div>
      <div class="day-mins">${val > 0 ? val : "–"}</div>
      <div class="day-label">${getLabel(rec)}</div>`;
    wrap.appendChild(col);
  });
  return wrap;
}

function section(label) {
  const el = document.createElement("div");
  el.className = "w-section";
  const lbl = document.createElement("div");
  lbl.className = "w-section-label";
  lbl.textContent = label;
  el.appendChild(lbl);
  return el;
}

function trendChart(weeklyTotals) {
  const wrap = document.createElement("div");
  wrap.className = "trend-chart-wrap";
  if (weeklyTotals.length < 2) {
    wrap.innerHTML = '<p class="wearable-placeholder">Need at least 2 completed weeks to show a trend.</p>';
    return wrap;
  }

  const width = 300, height = 190, padX = 10, padY = 20, padLeft = 34;
  const vals = weeklyTotals.map((w) => w.total_minutes || 0);
  // Recommended MVPA range is 150-300 min/week; scale the chart to at least cover
  // it so those two reference lines are always meaningful, not the raw data's max.
  const REFERENCE_LINES = [150, 300];
  const maxVal = Math.max(...vals, ...REFERENCE_LINES, 1);
  const plotWidth = width - padLeft - padX;
  const stepX = plotWidth / (weeklyTotals.length - 1);
  const points = vals.map((v, i) => [
    padLeft + i * stepX,
    height - padY - (v / maxVal) * (height - padY * 2),
  ]);

  const gridLines = REFERENCE_LINES.map((refVal) => {
    const y = height - padY - (refVal / maxVal) * (height - padY * 2);
    return `
      <line x1="${padLeft}" y1="${y}" x2="${width - padX}" y2="${y}" class="trend-gridline"/>
      <text x="${padLeft - 6}" y="${y + 3}" class="trend-axis-label" text-anchor="end">${refVal}</text>`;
  }).join("");

  const svg = `
    <svg viewBox="0 0 ${width} ${height}" class="trend-svg" preserveAspectRatio="none">
      ${gridLines}
      <polyline points="${points.map((p) => p.join(",")).join(" ")}" class="trend-line" fill="none"/>
      ${points.map(([x, y]) => `<circle cx="${x}" cy="${y}" r="4" class="trend-dot"/>`).join("")}
    </svg>`;
  wrap.innerHTML = svg;

  const labels = document.createElement("div");
  labels.className = "trend-labels";
  labels.style.paddingLeft = `${(padLeft / width) * 100}%`;
  weeklyTotals.forEach((w) => {
    const span = document.createElement("span");
    span.textContent = w.week_start.slice(5, 10);
    labels.appendChild(span);
  });
  wrap.appendChild(labels);
  return wrap;
}

function renderTrendTab(d) {
  const weeklyTotals = d.weekly_totals || [];
  const wrap = document.createElement("div");
  wrap.className = "trend-section";

  const vals = weeklyTotals.map((w) => w.total_minutes || 0);
  const avg = vals.length ? Math.round(vals.reduce((s, v) => s + v, 0) / vals.length) : 0;
  const rangeLabel = weeklyTotals.length
    ? `${weeklyTotals[0].week_start.slice(5, 10)} – ${weeklyTotals[weeklyTotals.length - 1].week_end.slice(5, 10)}`
    : "No completed weeks yet";

  const header = document.createElement("div");
  header.className = "trend-header";
  header.innerHTML = `
    <div class="trend-avg-label">Average</div>
    <div class="trend-avg-value">${avg}<span class="trend-avg-unit"> min/wk</span></div>
    <div class="trend-range">${rangeLabel}</div>`;
  wrap.appendChild(header);

  wrap.appendChild(trendChart(weeklyTotals));

  if (vals.length >= 2) {
    const changePerWeek = Math.round((vals[vals.length - 1] - vals[0]) / (vals.length - 1));
    const sign = changePerWeek > 0 ? "+" : "";
    const pill = document.createElement("div");
    pill.className = "trend-pill";
    pill.innerHTML = `<span>Average change</span><span class="trend-pill-value">${sign}${changePerWeek} min/wk over ${weeklyTotals.length} weeks</span>`;
    wrap.appendChild(pill);
  }

  if (vals.length) {
    const weeksMeetingGuideline = vals.filter((v) => v >= 150).length;
    const guidelinePill = document.createElement("div");
    guidelinePill.className = "trend-pill";
    guidelinePill.innerHTML = `<span>Weeks meeting guideline (150+ min)</span><span class="trend-pill-value">${weeksMeetingGuideline} of ${vals.length}</span>`;
    wrap.appendChild(guidelinePill);
  }

  wearableEl.appendChild(wrap);
}

function renderRingTab({ total, daily, ringTitle, sectionLabel }) {
  const ringSection = document.createElement("div");
  ringSection.className = "ring-section";
  ringSection.innerHTML = ring(total / 150, total, ringTitle);
  wearableEl.appendChild(ringSection);

  if (daily.length) {
    const sec = section(sectionLabel);
    const maxMins = Math.max(...daily.map((r) => r.minutes || 0), 1);
    sec.appendChild(dayDots(daily, (r) => r.minutes || 0, maxMins, (r) => weekdayShort(r.date)));
    wearableEl.appendChild(sec);
  }
}

function renderRollingTab(d) {
  const daily = d.rolling_7d_daily || [];
  renderRingTab({
    total: d.rolling_7d_total || 0,
    daily,
    ringTitle: "Rolling 7-Day MVPA",
    sectionLabel: "Daily (Last 7 Days)",
  });
}

function renderWeekTab(d) {
  const currentWeek = d.current_week || [];
  const total = currentWeek.reduce((s, r) => s + (r.minutes || 0), 0);
  const sectionLabel = currentWeek.length
    ? `Mon–Sun (${currentWeek[0].date.slice(5, 10)} – ${currentWeek[currentWeek.length - 1].date.slice(5, 10)})`
    : "";
  renderRingTab({ total, daily: currentWeek, ringTitle: "This Week's MVPA", sectionLabel });
}

let lastWearableData = null;
let activeWearableTab = "trend";

function renderActiveTab() {
  wearableEl.innerHTML = "";
  if (!lastWearableData) return;
  if (activeWearableTab === "trend") renderTrendTab(lastWearableData);
  else if (activeWearableTab === "rolling") renderRollingTab(lastWearableData);
  else renderWeekTab(lastWearableData);
}

function renderWearable(d) {
  lastWearableData = d;
  renderActiveTab();
}

function loadWearable() {
  wearableEl.innerHTML = '<p class="wearable-placeholder">Loading…</p>';
  fetch("/api/wearable")
    .then((r) => r.json())
    .then(renderWearable)
    .catch((e) => { wearableEl.innerHTML = `<p class="wearable-placeholder">Error: ${e.message}</p>`; });
}

document.getElementById("send-btn").addEventListener("click", sendMessage);
inputEl.addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });
document.getElementById("refresh-btn").addEventListener("click", loadWearable);
document.querySelectorAll(".w-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".w-tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    activeWearableTab = btn.dataset.tab;
    renderActiveTab();
  });
});

renderGoals([]);
startSession();
