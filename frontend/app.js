const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("msg-input");
const goalsEl = document.getElementById("goals-list");
const wearableEl = document.getElementById("wearable-data");

let ws;

function addBubble(text, role) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/chat`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "message") addBubble(msg.text, "coach");
    if (msg.type === "goal_saved") loadGoals();
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}

function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || ws.readyState !== WebSocket.OPEN) return;
  addBubble(text, "user");
  ws.send(JSON.stringify({ text }));
  inputEl.value = "";
}

function loadGoals() {
  fetch("/api/goals")
    .then((r) => r.json())
    .then((goals) => {
      goalsEl.innerHTML = "";
      goals.forEach((g) => {
        const li = document.createElement("li");
        const textNode = document.createTextNode(g.text);
        const meta = document.createElement("div");
        meta.className = "goal-meta";
        meta.textContent = `id: ${g.id.slice(0, 8)}… · ${g.created_at.slice(0, 10)}`;
        li.appendChild(textNode);
        li.appendChild(meta);
        goalsEl.appendChild(li);
      });
    });
}

function ring(pct, value) {
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
      <div class="ring-title">Weekly MVPA</div>
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


function dayDots(records, getValue, maxVal) {
  const wrap = document.createElement("div");
  wrap.className = "day-dots";
  records.forEach((rec) => {
    const val = getValue(rec);
    const pct = maxVal ? Math.min(val / maxVal, 1) : 0;
    const date = (rec.from || rec.date || rec.timestamp || "").slice(5, 10);
    const col = document.createElement("div");
    col.className = "day-col";
    col.innerHTML = `
      <div class="day-bar-wrap"><div class="day-bar" style="height:${Math.max(Math.round(pct * 100), 4)}%"></div></div>
      <div class="day-mins">${val > 0 ? val : "–"}</div>
      <div class="day-label">${date}</div>`;
    wrap.appendChild(col);
  });
  return wrap;
}

function renderWearable(d) {
  const data = d.data || {};
  wearableEl.innerHTML = "";

  const mvpa = data.mvpa || [];

  const totalMvpa = mvpa.reduce((s, r) => s + (r.minutes || 0), 0);

  // MVPA ring
  const ringSection = document.createElement("div");
  ringSection.className = "ring-section";
  ringSection.innerHTML = ring(totalMvpa / 150, totalMvpa);
  wearableEl.appendChild(ringSection);

  // Daily MVPA bars
  if (mvpa.length) {
    const actSection = document.createElement("div");
    actSection.className = "w-section";
    const actLabel = document.createElement("div");
    actLabel.className = "w-section-label";
    actLabel.textContent = "Daily MVPA Activity Minutes";
    actSection.appendChild(actLabel);
    const maxMins = Math.max(...mvpa.map(r => r.minutes || 0), 1);
    actSection.appendChild(dayDots(mvpa, r => r.minutes || 0, maxMins));
    wearableEl.appendChild(actSection);
  }
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

connectWS();
loadGoals();
