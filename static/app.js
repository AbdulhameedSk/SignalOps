// app.js — the dashboard's brain. Vanilla JS, no build step:
//   fetch() for REST, EventSource for the SSE live feed.
let currentIncident = null;
let eventSource = null;

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...opts,
  });
  return r.json();
}

// ---------- incident list ----------
async function loadIncidents() {
  const list = await api("/api/incidents");
  const ul = document.getElementById("incident-list");
  ul.innerHTML = "";
  for (const inc of list) {
    const li = document.createElement("li");
    if (currentIncident === inc.id) li.className = "active";
    li.innerHTML =
      `<div class="inc-title">#${inc.id} ${inc.title}</div>
       <div class="inc-meta">
         <span class="sev ${inc.severity}">${inc.severity}</span>
         ${inc.service}
         <span class="status ${inc.status}">${inc.status}</span>
       </div>`;
    li.onclick = () => selectIncident(inc.id);
    ul.appendChild(li);
  }
}

// ---------- live feed ----------
function renderEvent(ev) {
  const div = document.createElement("div");
  div.className = `ev ${ev.kind}`;
  div.innerHTML = `<span class="kind">${ev.kind}</span>${escapeHtml(ev.content)}`;
  const feed = document.getElementById("feed");
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

async function selectIncident(id) {
  currentIncident = id;
  document.getElementById("empty").classList.add("hidden");
  document.getElementById("incident-view").classList.remove("hidden");
  document.getElementById("feed").innerHTML = "";
  loadIncidents();
  loadIncidentHead(id);
  loadActions(id);

  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/incidents/${id}/stream`);
  eventSource.onmessage = (e) => renderEvent(JSON.parse(e.data));
}

async function loadIncidentHead(id) {
  const list = await api("/api/incidents");
  const inc = list.find((i) => i.id === id);
  document.getElementById("incident-head").innerHTML = inc
    ? `<h2>#${inc.id} ${escapeHtml(inc.title)}</h2>
       <div class="summary">${escapeHtml(inc.summary || "")}</div>`
    : "";
}

async function loadActions(id) {
  const actions = await api(`/api/incidents/${id}/actions`);
  const box = document.getElementById("actions");
  box.innerHTML = actions.length
    ? ""
    : '<div style="color:#8b949e;font-size:13px">None proposed yet.</div>';
  for (const a of actions) {
    const card = document.createElement("div");
    card.className = "action-card";
    card.innerHTML =
      `<div class="a-title">${escapeHtml(a.title)}</div>
       <div class="a-desc">${escapeHtml(a.description)}</div>
       <div class="a-evidence">${escapeHtml(a.evidence || "")}</div>`;
    if (a.status === "pending") {
      const approve = document.createElement("button");
      approve.textContent = "Approve & execute";
      approve.onclick = () => decide(a.id, "approved");
      const reject = document.createElement("button");
      reject.textContent = "Reject";
      reject.className = "reject";
      reject.style.marginLeft = "8px";
      reject.onclick = () => decide(a.id, "rejected");
      card.appendChild(approve);
      card.appendChild(reject);
    } else {
      card.innerHTML += `<div class="a-status">status: ${a.status}</div>`;
    }
    box.appendChild(card);
  }
}

async function decide(actionId, decision) {
  await api(`/api/actions/${actionId}/decide`, {
    method: "POST", body: JSON.stringify({ decision }),
  });
  loadActions(currentIncident);
  loadIncidents();
  loadIncidentHead(currentIncident);
}

// ---------- demo + stats ----------
document.getElementById("demo-btn").onclick = async () => {
  const info = await api("/api/demo", { method: "POST" });
  await loadIncidents();
  selectIncident(info.id);
};

async function loadStats() {
  const s = await api("/api/stats");
  const q = s.queue || {};
  document.getElementById("stats").textContent =
    `queue — queued:${q.queued || 0} claimed:${q.claimed || 0} ` +
    `done:${q.done || 0} dead:${q.dead || 0} · incidents:${s.incidents}`;
}

loadIncidents();
loadStats();
setInterval(() => { loadStats(); if (!currentIncident) loadIncidents(); }, 3000);
