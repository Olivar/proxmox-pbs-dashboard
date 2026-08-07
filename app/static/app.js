"use strict";

const $ = (id) => document.getElementById(id);
const csrf = document.body.dataset.csrf;
const refreshSeconds = Number(document.body.dataset.refreshSeconds || 60);
const state = {payload: null, query: "", status: "all", pve: "all", tab: "monitoring", noteGuest: null, powerGuest: null, powerAction: null, pveSummaries: {}, pbsSummaries: {}, openSummary: null};
const elements = {
  search: $("search"), status: $("filter-state"), pve: $("filter-pve"), clear: $("clear-filters"), refresh: $("refresh"), logout: $("logout"), theme: $("theme-select"),
  lastUpdate: $("last-update"), sourceStatus: $("source-status"), vmTable: $("vm-table"), backupTable: $("backup-table"), vmCount: $("vm-count"), error: $("error"),
  metricTotal: $("metric-total"), metricRunning: $("metric-running"), metricStopped: $("metric-stopped"), toast: $("toast"), noteDialog: $("note-dialog"), noteForm: $("note-form"), noteTitle: $("note-title"), noteText: $("note-text"), noteDelete: $("note-delete"), noteCounter: $("note-counter"),
  powerDialog: $("power-dialog"), powerForm: $("power-form"), powerTitle: $("power-title"), powerDescription: $("power-description"), resourceDialog: $("resource-dialog"), resourceKicker: $("resource-kicker"), resourceTitle: $("resource-title"), resourceBody: $("resource-body")
};

const ICONS = {
  play: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7Z"/></svg>',
  stop: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>',
  restart: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.34 5.66M20 5v6h-6"/></svg>',
  console: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="1"/><path d="M8 20h8M12 16v4"/></svg>',
  note: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16v13H8l-4 3Z"/><path d="M8 8h8M8 12h6"/></svg>'
};

const escapeHtml = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const formatDate = (value) => { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat("pt-BR", {dateStyle: "short", timeStyle: "short"}).format(date); };
const formatBytes = (bytes) => { const total = Number(bytes || 0); if (!total) return "—"; const gib = total / 1073741824; return `${new Intl.NumberFormat("pt-BR", {maximumFractionDigits: gib < 10 ? 1 : 0}).format(gib)} GB`; };
const formatCores = (cores) => { const total = Number(cores || 0); if (!total) return "—"; return `${new Intl.NumberFormat("pt-BR", {maximumFractionDigits: 1}).format(total)} ${total === 1 ? "core" : "cores"}`; };
const showToast = (text) => { elements.toast.textContent = text; elements.toast.hidden = false; clearTimeout(showToast.timer); showToast.timer = setTimeout(() => { elements.toast.hidden = true; }, 3000); };
const api = async (url, options = {}) => { const headers = {...(options.headers || {}), Accept: "application/json"}; if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrf; const response = await fetch(url, {...options, headers, cache: "no-store"}); if (response.status === 401) { location.replace("/login"); throw new Error("Sessão expirada"); } const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`); return payload; };
const TASK_READ_STORAGE = "ppd-task-errors-read";
const readTaskErrors = () => { try { const value = JSON.parse(localStorage.getItem(TASK_READ_STORAGE) || "{}"); return value && typeof value === "object" ? value : {}; } catch { return {}; } };
const writeTaskErrors = (value) => { try { localStorage.setItem(TASK_READ_STORAGE, JSON.stringify(value)); } catch {} };
const taskIsError = (task) => /error|fail|abort/i.test(String(task?.status || ""));
const taskKey = (pveId, task) => `${pveId}|${task.upid || `${task.node || ""}|${task.task_type || ""}|${task.task_id || ""}|${task.start_at || ""}`}`;
const unreadTaskErrors = (pveId, summary) => { const read = readTaskErrors(); return (summary?.tasks || []).filter((task) => taskIsError(task) && !read[taskKey(pveId, task)]); };

const applyTheme = (theme) => { document.documentElement.dataset.theme = theme; elements.theme.value = theme; localStorage.setItem("ppd-theme", theme); };
applyTheme(localStorage.getItem("ppd-theme") || document.body.dataset.defaultTheme || "system");
elements.theme.addEventListener("change", (event) => applyTheme(event.target.value));

const filtered = () => {
  if (!state.payload) return [];
  const query = state.query.trim().toLocaleLowerCase("pt-BR");
  return state.payload.vms.filter((guest) => (!query || [guest.vmid, guest.name, guest.ip, guest.pve_name, guest.note].some((item) => String(item ?? "").toLocaleLowerCase("pt-BR").includes(query))) && (state.status === "all" || guest.state === state.status) && (state.pve === "all" || guest.pve_id === state.pve));
};

const statusBadge = (guest) => `<span class="status status-${escapeHtml(guest.state)}"><i></i>${escapeHtml(guest.state_display)}</span>`;
const pveLink = (guest) => `<a href="${escapeHtml(guest.pve_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(guest.pve_name)}</a>`;
const normalizeUsage = (value) => Math.min(100, Math.max(0, Number(value) || 0));
const usageLevel = (value) => { const percent = normalizeUsage(value); return percent >= 80 ? "high" : percent >= 60 ? "medium" : "low"; };
const usageLine = (label, value, total) => {
  const percent = value == null ? null : normalizeUsage(value);
  const level = percent == null ? "unavailable" : usageLevel(percent);
  return `<span class="usage-line usage-${level}"><b>${label}</b><span class="usage-indicator" aria-hidden="true"><i style="width:${percent ?? 0}%"></i></span><strong>${percent == null ? "—" : `${percent}%`}</strong><small>de ${escapeHtml(total)}</small></span>`;
};
const usage = (guest) => `<div class="usage-stack">${usageLine("CPU", guest.cpu_percent, formatCores(guest.cpu_total_cores))}${usageLine("RAM", guest.ram_percent, formatBytes(guest.ram_total_bytes))}${usageLine("Disco", guest.disk_percent, formatBytes(guest.disk_total_bytes))}</div>`;
const consoleButton = (guest) => guest.kind === "qemu"
  ? `<button class="row-icon console" data-console="1" data-pve="${escapeHtml(guest.pve_id)}" data-node="${escapeHtml(guest.node)}" data-vmid="${guest.vmid}" data-name="${escapeHtml(guest.name)}" data-state="${escapeHtml(guest.state)}" title="Abrir console noVNC" aria-label="Abrir console noVNC">${ICONS.console}</button>`
  : "";
const formatResourceBytes = (bytes) => { const total = Number(bytes || 0); if (!total) return "0 B"; const gib = total / 1073741824; return `${new Intl.NumberFormat("pt-BR", {maximumFractionDigits: gib < 10 ? 1 : 0}).format(gib)} GB`; };
const formatLoad = (value) => value == null ? "—" : new Intl.NumberFormat("pt-BR", {minimumFractionDigits: 2, maximumFractionDigits: 2}).format(Number(value));
const resourceMetric = (label, percent, detail) => { const normalized = normalizeUsage(percent); return `<article class="resource-metric"><header><strong>${label}</strong><b class="usage-${usageLevel(normalized)}">${normalized}%</b></header><div class="resource-bar"><i class="usage-${usageLevel(normalized)}" style="width:${normalized}%"></i></div><small>${detail}</small></article>`; };
const renderLegacyResourceSummary = (summary) => {
  const nodeLabel = `${summary.online_node_count} de ${summary.node_count} nós online`;
  const nodes = (summary.nodes || []).map((node) => `<article class="resource-node"><header><strong>${escapeHtml(node.node)}</strong><span class="node-state node-${escapeHtml(node.status)}">${escapeHtml(node.status)}</span></header><div class="resource-node-grid"><span>CPU <b class="usage-${usageLevel(node.cpu_percent)}">${node.cpu_percent}%</b></span><span>RAM <b class="usage-${usageLevel(node.ram_percent)}">${node.ram_percent}%</b></span><span>Disco <b class="usage-${usageLevel(node.disk_percent)}">${node.disk_percent}%</b></span><span>Load <b>${formatLoad(node.load_average)}</b></span><span>Uptime <b>${escapeHtml(node.uptime_display)}</b></span></div></article>`).join("");
  elements.resourceTitle.textContent = summary.pve_name;
  elements.resourceBody.innerHTML = `<div class="resource-overview"><span class="muted">${escapeHtml(nodeLabel)}</span><span class="muted">Atualizado: ${formatDate(summary.updated_at)}</span></div><div class="resource-metrics">${resourceMetric("CPU", summary.cpu_percent, `${summary.cpu_total_cores} cores disponíveis`)}${resourceMetric("RAM", summary.ram_percent, `${formatResourceBytes(summary.ram_used_bytes)} de ${formatResourceBytes(summary.ram_total_bytes)}`)}${resourceMetric("Disco", summary.disk_percent, `${formatResourceBytes(summary.disk_used_bytes)} de ${formatResourceBytes(summary.disk_total_bytes)}`)}</div><section class="resource-nodes"><h3>Nós</h3>${nodes || '<p class="muted">Nenhum nó retornado.</p>'}</section>`;
};
const taskStatus = (value) => {
  const raw = String(value ?? "unknown");
  const lower = raw.toLocaleLowerCase("pt-BR");
  const level = /error|fail|abort/.test(lower) ? "failed" : /running|started|queued/.test(lower) ? "running" : "success";
  const labels = {stopped: "Conclu\u00edda", ok: "Conclu\u00edda", success: "Conclu\u00edda", running: "Executando", queued: "Na fila", unknown: "Desconhecido"};
  return `<span class="task-status task-${level}">${escapeHtml(labels[lower] || raw)}</span>`;
};
const renderResourceSummary = (summary) => {
  state.openSummary = summary;
  state.pveSummaries[summary.pve_id] = summary;
  elements.resourceKicker.textContent = "Resumo do PVE";
  renderSourceStatus();
  const nodeLabel = `${summary.online_node_count} de ${summary.node_count} n\u00f3s online`;
  const nodes = (summary.nodes || []).map((node) => `<article class="resource-node"><header><strong>${escapeHtml(node.node)}</strong><span class="node-state node-${escapeHtml(node.status)}">${escapeHtml(node.status)}</span></header><div class="resource-node-grid"><span>CPU <b class="usage-${usageLevel(node.cpu_percent)}">${node.cpu_percent}%</b></span><span>RAM <b class="usage-${usageLevel(node.ram_percent)}">${node.ram_percent}%</b></span><span>Disco <b class="usage-${usageLevel(node.disk_percent)}">${node.disk_percent}%</b></span><span>Load <b>${formatLoad(node.load_average)}</b></span><span>Uptime <b>${escapeHtml(node.uptime_display)}</b></span></div></article>`).join("");
  const tasks = (summary.tasks || []).map((task) => `<article class="resource-task"><time>${formatDate(task.start_at)}</time><span class="resource-task-node">${escapeHtml(task.node)}</span><span class="resource-task-name"><strong>${escapeHtml(task.description || task.task_type)}</strong></span>${taskStatus(task.status)}</article>`).join("");
  const errorTasks = (summary.tasks || []).filter(taskIsError);
  const unreadErrors = unreadTaskErrors(`pve:${summary.pve_id}`, summary);
  const taskReadControl = errorTasks.length ? `<label class="task-read-control ${unreadErrors.length ? "" : "task-read-complete"}"><input type="checkbox" data-mark-task-errors data-source-id="${escapeHtml(summary.pve_id)}" data-source-kind="pve" ${unreadErrors.length ? "" : "checked disabled"}><span>${unreadErrors.length ? `Marcar ${unreadErrors.length} erro${unreadErrors.length === 1 ? "" : "s"} como lido${unreadErrors.length === 1 ? "" : "s"}` : "Erros marcados como lidos"}</span></label>` : "";
  elements.resourceTitle.textContent = summary.pve_name;
  const taskCount = summary.tasks?.length || 0;
  elements.resourceBody.innerHTML = `<div class="resource-overview"><span class="muted">${escapeHtml(nodeLabel)}</span><span class="muted">Atualizado: ${formatDate(summary.updated_at)}</span></div><div class="resource-metrics">${resourceMetric("CPU", summary.cpu_percent, `${summary.cpu_total_cores} cores dispon\u00edveis`)}${resourceMetric("RAM", summary.ram_percent, `${formatResourceBytes(summary.ram_used_bytes)} de ${formatResourceBytes(summary.ram_total_bytes)}`)}${resourceMetric("Disco", summary.disk_percent, `${formatResourceBytes(summary.disk_used_bytes)} de ${formatResourceBytes(summary.disk_total_bytes)}`)}</div><section class="resource-nodes"><h3>N\u00f3s</h3>${nodes || '<p class="muted">Nenhum n\u00f3 retornado.</p>'}</section><details class="resource-tasks"><summary><span>Hist\u00f3rico de tarefas${unreadErrors.length ? `<b class="task-unread-count">${unreadErrors.length}</b>` : ""}</span><small>${taskCount} ${taskCount === 1 ? "tarefa" : "tarefas"}</small></summary>${taskReadControl ? `<div class="task-log-controls">${taskReadControl}</div>` : ""}<div class="resource-task-list">${tasks || '<p class="muted">Nenhuma tarefa encontrada ou sem permiss\u00e3o para consultar o hist\u00f3rico.</p>'}</div></details>`;
};
const renderPbsSummary = (summary) => {
  state.openSummary = summary;
  state.pbsSummaries[summary.pbs_id] = summary;
  elements.resourceKicker.textContent = "Resumo do PBS";
  renderSourceStatus();
  const datastores = (summary.datastores || []).map((store) => `<article class="resource-node"><header><strong>${escapeHtml(store.name)}</strong><span class="node-state node-${escapeHtml(store.status)}">${escapeHtml(store.status)}</span></header><div class="resource-node-grid"><span>Uso <b class="usage-${usageLevel(store.percent)}">${store.percent}%</b></span><span>Usado <b>${formatResourceBytes(store.used_bytes)}</b></span><span>Total <b>${formatResourceBytes(store.total_bytes)}</b></span><span>Livre <b>${formatResourceBytes(store.avail_bytes)}</b></span></div></article>`).join("");
  const tasks = (summary.tasks || []).map((task) => `<article class="resource-task"><time>${formatDate(task.start_at)}</time><span class="resource-task-node">PBS</span><span class="resource-task-name"><strong>${escapeHtml(task.description || task.task_type)}</strong></span>${taskStatus(task.status)}</article>`).join("");
  const errorTasks = (summary.tasks || []).filter(taskIsError);
  const unreadErrors = unreadTaskErrors(`pbs:${summary.pbs_id}`, summary);
  const taskReadControl = errorTasks.length ? `<label class="task-read-control ${unreadErrors.length ? "" : "task-read-complete"}"><input type="checkbox" data-mark-task-errors data-source-id="${escapeHtml(summary.pbs_id)}" data-source-kind="pbs" ${unreadErrors.length ? "" : "checked disabled"}><span>${unreadErrors.length ? `Marcar ${unreadErrors.length} erro${unreadErrors.length === 1 ? "" : "s"} como lido${unreadErrors.length === 1 ? "" : "s"}` : "Erros marcados como lidos"}</span></label>` : "";
  const taskCount = summary.tasks?.length || 0;
  elements.resourceTitle.textContent = summary.pbs_name;
  elements.resourceBody.innerHTML = `<div class="resource-overview"><span class="muted">${escapeHtml(summary.status)} · Nó ${escapeHtml(summary.node)}</span><span class="muted">Atualizado: ${formatDate(summary.updated_at)}</span></div><div class="resource-metrics">${resourceMetric("CPU", summary.cpu_percent, `${summary.cpu_total_cores || "—"} cores disponíveis`)}${resourceMetric("RAM", summary.ram_percent, `${formatResourceBytes(summary.ram_used_bytes)} de ${formatResourceBytes(summary.ram_total_bytes)}`)}${resourceMetric("Disco", summary.disk_percent, `${formatResourceBytes(summary.disk_used_bytes)} de ${formatResourceBytes(summary.disk_total_bytes)}`)}</div><section class="resource-nodes"><h3>Datastores</h3>${datastores || '<p class="muted">Nenhum datastore retornado ou sem permissão.</p>'}</section><details class="resource-tasks"><summary><span>Histórico de jobs${unreadErrors.length ? `<b class="task-unread-count">${unreadErrors.length}</b>` : ""}</span><small>${taskCount} ${taskCount === 1 ? "job" : "jobs"}</small></summary>${taskReadControl ? `<div class="task-log-controls">${taskReadControl}</div>` : ""}<div class="resource-task-list">${tasks || '<p class="muted">Nenhum job encontrado ou sem permissão para consultar o histórico.</p>'}</div></details>`;
};
const actionButtons = (guest) => guest.state === "stopped"
  ? `<button class="row-icon play" data-power="start" data-pve="${escapeHtml(guest.pve_id)}" data-vmid="${guest.vmid}" title="Iniciar" aria-label="Iniciar">${ICONS.play}</button>${consoleButton(guest)}`
  : `<button class="row-icon stop" data-power="shutdown" data-pve="${escapeHtml(guest.pve_id)}" data-vmid="${guest.vmid}" title="Desligar" aria-label="Desligar">${ICONS.stop}</button><button class="row-icon restart" data-power="reboot" data-pve="${escapeHtml(guest.pve_id)}" data-vmid="${guest.vmid}" title="Reiniciar" aria-label="Reiniciar">${ICONS.restart}</button>${consoleButton(guest)}`;
const noteButton = (guest) => `<button class="row-icon note ${guest.note ? "has-note" : ""}" data-note="1" data-pve="${escapeHtml(guest.pve_id)}" data-vmid="${guest.vmid}" title="${escapeHtml(guest.note || "Adicionar nota")}" aria-label="${guest.note ? "Editar nota" : "Adicionar nota"}">${ICONS.note}</button>`;
const backupStatus = (status) => { const labels = {success: "Sucesso", failed: "Erro", running: "Executando", missing: "Sem backup", unknown: "Desconhecido"}; return `<span class="backup-status backup-${escapeHtml(status)}">${escapeHtml(labels[status] || labels.unknown)}</span>`; };

function renderSourceStatus() {
  if (!state.payload) return;
  const pveSummaries = state.pveSummaries || {};
  const pbsSummaries = state.pbsSummaries || {};
  const pveSources = state.payload.pve.map((source) => {
    const unread = unreadTaskErrors(`pve:${source.source_id}`, pveSummaries[source.source_id]);
    const alert = unread.length ? `<span class="source-alert" aria-label="${unread.length} erro${unread.length === 1 ? "" : "s"} não lido${unread.length === 1 ? "" : "s"}" title="${unread.length} erro${unread.length === 1 ? "" : "s"} não lido${unread.length === 1 ? "" : "s"}">!</span>` : "";
    return `<button type="button" class="source source-button ${source.ok ? "ok" : "error"}" data-pve-summary="${escapeHtml(source.source_id || "")}" title="${escapeHtml(source.error || "Ver resumo de recursos")}"><i></i>${escapeHtml(source.source_name || "PVE")}${alert}</button>`;
  });
  const pbsSources = Array.isArray(state.payload.pbs) ? state.payload.pbs : [state.payload.pbs].filter(Boolean);
  const pbsMarkup = pbsSources.map((source) => {
    const unread = unreadTaskErrors(`pbs:${source.source_id}`, pbsSummaries[source.source_id]);
    const alert = unread.length ? `<span class="source-alert" aria-label="${unread.length} erro${unread.length === 1 ? "" : "s"} não lido${unread.length === 1 ? "" : "s"}" title="${unread.length} erro${unread.length === 1 ? "" : "s"} não lido${unread.length === 1 ? "" : "s"}">!</span>` : "";
    return `<button type="button" class="source source-button ${source.ok ? "ok" : "error"}" data-pbs-summary="${escapeHtml(source.source_id || "")}" title="${escapeHtml(source.error || "Ver resumo do PBS")}"><i></i>${escapeHtml(source.source_name || "PBS")}${alert}</button>`;
  });
  elements.sourceStatus.innerHTML = [...pveSources, ...pbsMarkup].join("");
}

async function refreshTaskAlerts() {
  const pveSources = state.payload?.pve || [];
  const pbsSources = Array.isArray(state.payload?.pbs) ? state.payload.pbs : [state.payload?.pbs].filter(Boolean);
  const pveResults = Promise.allSettled(pveSources.map(async (source) => [source.source_id, await api(`/api/pve/${encodeURIComponent(source.source_id)}/summary`)]));
  const pbsResults = Promise.allSettled(pbsSources.map(async (source) => [source.source_id, await api(`/api/pbs/${encodeURIComponent(source.source_id)}/summary`)]));
  const [pveSettled, pbsSettled] = await Promise.all([pveResults, pbsResults]);
  if (!state.payload) return;
  state.pveSummaries = Object.fromEntries(pveSettled.filter((result) => result.status === "fulfilled").map((result) => result.value));
  state.pbsSummaries = Object.fromEntries(pbsSettled.filter((result) => result.status === "fulfilled").map((result) => result.value));
  renderSourceStatus();
}

function renderPveOptions() {
  const entries = [...new Map((state.payload?.vms || []).map((guest) => [guest.pve_id, guest.pve_name])).entries()].sort((a, b) => a[1].localeCompare(b[1], "pt-BR"));
  elements.pve.innerHTML = `<option value="all">Todos os PVEs</option>${entries.map(([id, name]) => `<option value="${escapeHtml(id)}">${escapeHtml(name)}</option>`).join("")}`;
  elements.pve.value = entries.some(([id]) => id === state.pve) ? state.pve : "all";
}

function render() {
  if (!state.payload) return;
  const guests = filtered();
  const all = state.payload.vms;
  elements.metricTotal.textContent = all.length;
  elements.metricRunning.textContent = all.filter((guest) => guest.state === "running").length;
  elements.metricStopped.textContent = all.filter((guest) => guest.state === "stopped").length;
  elements.vmCount.textContent = `${guests.length} de ${all.length}`;
  elements.vmTable.innerHTML = guests.length ? guests.map((guest) => `<tr><td data-label="Status">${statusBadge(guest)}</td><td data-label="ID" class="mono">${guest.vmid}</td><td data-label="Nome"><div class="guest-name"><strong>${escapeHtml(guest.name)}</strong><small>${escapeHtml(guest.kind_display)}</small></div></td><td data-label="Ações"><div class="row-actions">${actionButtons(guest)}</div></td><td data-label="IP">${guest.ip ? `<button class="ip-link" data-ip="${escapeHtml(guest.ip)}">${escapeHtml(guest.ip)}</button>` : "—"}</td><td data-label="Uso">${usage(guest)}</td><td data-label="Uptime" class="mono">${escapeHtml(guest.uptime_display)}</td><td data-label="PVE">${pveLink(guest)}</td><td data-label="Notas">${noteButton(guest)}</td></tr>`).join("") : `<tr><td colspan="9" class="empty">Nenhum item encontrado.</td></tr>`;
  elements.backupTable.innerHTML = guests.length ? guests.map((guest) => `<tr><td data-label="Status">${backupStatus(guest.backup.status)}</td><td data-label="ID" class="mono">${guest.vmid}</td><td data-label="Nome"><strong>${escapeHtml(guest.name)}</strong></td><td data-label="Último backup">${formatDate(guest.backup.last_backup)}</td><td data-label="Datastore">${escapeHtml(guest.backup.datastore || "—")}</td><td data-label="PVE">${pveLink(guest)}</td></tr>`).join("") : `<tr><td colspan="6" class="empty">Nenhum item encontrado.</td></tr>`;
  elements.lastUpdate.textContent = `${state.payload.stale ? "Dados em cache" : "Atualizado"}: ${formatDate(state.payload.updated_at)}`;
  renderSourceStatus();
}

async function load(force = false) {
  elements.refresh.disabled = true;
  elements.error.hidden = true;
  try {
    state.payload = await api(force ? "/api/refresh" : "/api/dashboard", {method: force ? "POST" : "GET"});
    state.pveSummaries = {};
    state.pbsSummaries = {};
    renderPveOptions();
    render();
    void refreshTaskAlerts();
  } catch (error) {
    elements.error.textContent = error.message;
    elements.error.hidden = false;
  } finally {
    elements.refresh.disabled = false;
  }
}

function findGuest(pve, vmid) { return state.payload?.vms.find((guest) => guest.pve_id === pve && guest.vmid === Number(vmid)); }
function openPower(guest, action) { if (!guest) return; state.powerGuest = guest; state.powerAction = action; const labels = {start: "Iniciar", shutdown: "Desligar", reboot: "Reiniciar"}; elements.powerTitle.textContent = labels[action]; elements.powerDescription.textContent = `${labels[action]} ${guest.kind_display} ${guest.vmid} — ${guest.name}?`; elements.powerForm.reset(); elements.powerDialog.showModal(); }
function updateNoteCounter() { elements.noteCounter.textContent = String(elements.noteText.value.length); }
function openNote(guest) { if (!guest) return; state.noteGuest = guest; elements.noteTitle.textContent = `${guest.vmid} — ${guest.name}`; elements.noteText.value = guest.note || ""; elements.noteDelete.hidden = !guest.note; updateNoteCounter(); elements.noteDialog.showModal(); elements.noteText.focus(); }
async function openPveSummary(pveId) {
  if (!pveId) return;
  const source = state.payload?.pve.find((item) => item.source_id === pveId);
  elements.resourceKicker.textContent = "Resumo do PVE";
  elements.resourceTitle.textContent = source?.source_name || "Recursos do PVE";
  elements.resourceBody.innerHTML = '<p class="muted">Carregando recursos do servidor…</p>';
  elements.resourceDialog.showModal();
  try { renderResourceSummary(await api(`/api/pve/${encodeURIComponent(pveId)}/summary`)); }
  catch (error) { elements.resourceBody.innerHTML = `<p class="error-banner">${escapeHtml(error.message)}</p>`; }
}

async function openPbsSummary(pbsId) {
  if (!pbsId) return;
  const source = (Array.isArray(state.payload?.pbs) ? state.payload.pbs : [state.payload?.pbs]).find((item) => item?.source_id === pbsId);
  elements.resourceKicker.textContent = "Resumo do PBS";
  elements.resourceTitle.textContent = source?.source_name || "Recursos do PBS";
  elements.resourceBody.innerHTML = '<p class="muted">Carregando recursos do servidor…</p>';
  elements.resourceDialog.showModal();
  try { renderPbsSummary(await api(`/api/pbs/${encodeURIComponent(pbsId)}/summary`)); }
  catch (error) { elements.resourceBody.innerHTML = `<p class="error-banner">${escapeHtml(error.message)}</p>`; }
}

function markTaskErrorsRead(sourceId, sourceKind) {
  const summaries = sourceKind === "pbs" ? state.pbsSummaries : state.pveSummaries;
  const summary = summaries[sourceId] || state.openSummary;
  if (!summary) return;
  const read = readTaskErrors();
  (summary.tasks || []).filter(taskIsError).forEach((task) => { read[taskKey(`${sourceKind}:${sourceId}`, task)] = true; });
  writeTaskErrors(read);
  const checkbox = elements.resourceBody.querySelector("[data-mark-task-errors]");
  if (checkbox) { checkbox.checked = true; checkbox.disabled = true; }
  const controlText = elements.resourceBody.querySelector(".task-read-control span");
  if (controlText) controlText.textContent = "Erros marcados como lidos";
  elements.resourceBody.querySelector(".task-read-control")?.classList.add("task-read-complete");
  elements.resourceBody.querySelector(".task-unread-count")?.remove();
  renderSourceStatus();
  showToast("Erros marcados como lidos");
}

async function copyIp(value) {
  try { await navigator.clipboard.writeText(value); }
  catch { const area = document.createElement("textarea"); area.value = value; document.body.append(area); area.select(); document.execCommand("copy"); area.remove(); }
  showToast("IP copiado");
}

document.addEventListener("click", async (event) => {
  const pveSummary = event.target.closest("[data-pve-summary]"); if (pveSummary) { await openPveSummary(pveSummary.dataset.pveSummary); return; }
  const pbsSummary = event.target.closest("[data-pbs-summary]"); if (pbsSummary) { await openPbsSummary(pbsSummary.dataset.pbsSummary); return; }
  const power = event.target.closest("[data-power]"); if (power) openPower(findGuest(power.dataset.pve, power.dataset.vmid), power.dataset.power);
  const note = event.target.closest("[data-note]"); if (note) openNote(findGuest(note.dataset.pve, note.dataset.vmid));
  const ip = event.target.closest("[data-ip]"); if (ip) await copyIp(ip.dataset.ip);
  const closer = event.target.closest("[data-close-dialog]"); if (closer) $(closer.dataset.closeDialog).close();
});
document.addEventListener("change", (event) => { const checkbox = event.target.closest("[data-mark-task-errors]"); if (checkbox?.checked) markTaskErrorsRead(checkbox.dataset.sourceId, checkbox.dataset.sourceKind); });

elements.powerForm.addEventListener("submit", async (event) => { event.preventDefault(); const guest = state.powerGuest; const body = {username: $("power-user").value, realm: $("power-realm").value, password: $("power-password").value, otp: $("power-otp").value || null}; try { await api(`/api/guests/${encodeURIComponent(guest.pve_id)}/${encodeURIComponent(guest.node)}/${guest.kind}/${guest.vmid}/${state.powerAction}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)}); elements.powerDialog.close(); showToast("Operação enviada"); await load(true); } catch (error) { showToast(error.message); } finally { $("power-password").value = ""; $("power-otp").value = ""; } });
elements.noteForm.addEventListener("submit", async (event) => { event.preventDefault(); const guest = state.noteGuest; try { const result = await api(`/api/notes/${encodeURIComponent(guest.pve_id)}/${guest.vmid}`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({note: elements.noteText.value.trim()})}); guest.note = result.note; elements.noteDialog.close(); render(); showToast(result.note ? "Nota salva" : "Nota excluída"); } catch (error) { showToast(error.message); } });
elements.noteDelete.addEventListener("click", () => { elements.noteText.value = ""; elements.noteForm.requestSubmit(); });
elements.noteText.addEventListener("input", updateNoteCounter);

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => { document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === button)); state.tab = button.dataset.tab; $("monitoring-panel").classList.toggle("active", state.tab === "monitoring"); $("backups-panel").classList.toggle("active", state.tab === "backups"); }));
elements.search.addEventListener("input", (event) => { state.query = event.target.value; render(); });
elements.status.addEventListener("change", (event) => { state.status = event.target.value; render(); });
elements.pve.addEventListener("change", (event) => { state.pve = event.target.value; render(); });
elements.clear.addEventListener("click", () => { state.query = ""; state.status = state.pve = "all"; elements.search.value = ""; elements.status.value = elements.pve.value = "all"; render(); });
elements.refresh.addEventListener("click", () => load(true));
elements.logout.addEventListener("click", async () => { await api("/api/logout", {method: "POST"}); location.replace("/login"); });
if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
load();
setInterval(() => load(), Math.max(15, refreshSeconds) * 1000);
