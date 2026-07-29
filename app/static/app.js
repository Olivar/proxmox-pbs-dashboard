"use strict";

const $ = (id) => document.getElementById(id);
const csrf = document.body.dataset.csrf;
const refreshSeconds = Number(document.body.dataset.refreshSeconds || 60);
const state = {payload: null, query: "", status: "all", pve: "all", tab: "monitoring", noteGuest: null, powerGuest: null, powerAction: null};
const elements = {search: $("search"), status: $("filter-state"), pve: $("filter-pve"), clear: $("clear-filters"), refresh: $("refresh"), logout: $("logout"), theme: $("theme-select"), lastUpdate: $("last-update"), sourceStatus: $("source-status"), vmTable: $("vm-table"), backupTable: $("backup-table"), vmCount: $("vm-count"), error: $("error"), metricTotal: $("metric-total"), metricRunning: $("metric-running"), metricStopped: $("metric-stopped"), toast: $("toast"), noteDialog: $("note-dialog"), noteForm: $("note-form"), noteTitle: $("note-title"), noteText: $("note-text"), noteDelete: $("note-delete"), powerDialog: $("power-dialog"), powerForm: $("power-form"), powerTitle: $("power-title"), powerDescription: $("power-description")};
const escapeHtml = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const formatDate = (v) => { if (!v) return "—"; const d = new Date(v); return Number.isNaN(d.getTime()) ? "—" : new Intl.DateTimeFormat("pt-BR", {dateStyle: "short", timeStyle: "short"}).format(d); };
const showToast = (text) => { elements.toast.textContent = text; elements.toast.hidden = false; clearTimeout(showToast.timer); showToast.timer = setTimeout(() => elements.toast.hidden = true, 2600); };
const api = async (url, options = {}) => { const headers = {...(options.headers || {}), Accept: "application/json"}; if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrf; const response = await fetch(url, {...options, headers, cache: "no-store"}); if (response.status === 401) { location.replace("/login"); throw new Error("Sessão expirada"); } const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`); return payload; };

const applyTheme = (theme) => { document.documentElement.dataset.theme = theme; elements.theme.value = theme; localStorage.setItem("ppd-theme", theme); };
applyTheme(localStorage.getItem("ppd-theme") || document.body.dataset.defaultTheme || "system");
elements.theme.addEventListener("change", (e) => applyTheme(e.target.value));

const filtered = () => {
  if (!state.payload) return [];
  const q = state.query.trim().toLocaleLowerCase("pt-BR");
  return state.payload.vms.filter((g) => (!q || [g.vmid, g.name, g.ip, g.pve_name, g.note].some((x) => String(x ?? "").toLocaleLowerCase("pt-BR").includes(q))) && (state.status === "all" || g.state === state.status) && (state.pve === "all" || g.pve_id === state.pve));
};
const statusBadge = (g) => `<span class="status status-${escapeHtml(g.state)}"><i></i>${escapeHtml(g.state_display)}</span>`;
const pveLink = (g) => `<a href="${escapeHtml(g.pve_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(g.pve_name)}</a>`;
const usage = (g) => `CPU: ${g.cpu_percent}% / RAM: ${g.ram_percent}%`;
const actionButtons = (g) => g.state === "stopped"
  ? `<button class="row-icon play" data-power="start" data-pve="${escapeHtml(g.pve_id)}" data-vmid="${g.vmid}" title="Iniciar" aria-label="Iniciar">▶</button>`
  : `<button class="row-icon stop" data-power="shutdown" data-pve="${escapeHtml(g.pve_id)}" data-vmid="${g.vmid}" title="Desligar" aria-label="Desligar">■</button><button class="row-icon restart" data-power="reboot" data-pve="${escapeHtml(g.pve_id)}" data-vmid="${g.vmid}" title="Reiniciar" aria-label="Reiniciar">↻</button>`;
const noteButton = (g) => `<button class="row-icon note ${g.note ? "has-note" : ""}" data-note="1" data-pve="${escapeHtml(g.pve_id)}" data-vmid="${g.vmid}" title="${escapeHtml(g.note || "Adicionar nota")}" aria-label="Nota">✎</button>`;

function renderPveOptions() {
  const entries = [...new Map((state.payload?.vms || []).map((g) => [g.pve_id, g.pve_name])).entries()].sort((a,b) => a[1].localeCompare(b[1], "pt-BR"));
  elements.pve.innerHTML = `<option value="all">Todos os PVE</option>${entries.map(([id,name]) => `<option value="${escapeHtml(id)}">${escapeHtml(name)}</option>`).join("")}`;
  elements.pve.value = entries.some(([id]) => id === state.pve) ? state.pve : "all";
}
function render() {
  if (!state.payload) return;
  const guests = filtered(); const all = state.payload.vms;
  elements.metricTotal.textContent = all.length; elements.metricRunning.textContent = all.filter((g) => g.state === "running").length; elements.metricStopped.textContent = all.filter((g) => g.state === "stopped").length; elements.vmCount.textContent = `${guests.length} exibidos`;
  elements.vmTable.innerHTML = guests.length ? guests.map((g) => `<tr><td data-label="Status">${statusBadge(g)}</td><td data-label="ID" class="mono">${g.vmid}</td><td data-label="Nome"><strong>${escapeHtml(g.name)}</strong></td><td data-label="Ações"><div class="row-actions">${actionButtons(g)}</div></td><td data-label="IP">${g.ip ? `<button class="ip-link" data-ip="${escapeHtml(g.ip)}">${escapeHtml(g.ip)}</button>` : "—"}</td><td data-label="Uso" class="usage">${usage(g)}</td><td data-label="Uptime">${escapeHtml(g.uptime_display)}</td><td data-label="PVE">${pveLink(g)}</td><td data-label="Notas">${noteButton(g)}</td></tr>`).join("") : `<tr><td colspan="9" class="empty">Nenhum item encontrado.</td></tr>`;
  elements.backupTable.innerHTML = guests.length ? guests.map((g) => `<tr><td>${escapeHtml(g.backup.status)}</td><td class="mono">${g.vmid}</td><td><strong>${escapeHtml(g.name)}</strong></td><td>${formatDate(g.backup.last_backup)}</td><td>${escapeHtml(g.backup.datastore || "—")}</td><td>${pveLink(g)}</td></tr>`).join("") : `<tr><td colspan="6" class="empty">Nenhum item encontrado.</td></tr>`;
  elements.lastUpdate.textContent = `${state.payload.stale ? "Dados em cache" : "Atualizado"}: ${formatDate(state.payload.updated_at)}`;
  elements.sourceStatus.innerHTML = [...state.payload.pve.map((s) => `<span class="source ${s.ok ? "ok" : "error"}">${escapeHtml(s.source_name || "PVE")}</span>`), `<span class="source ${state.payload.pbs.ok ? "ok" : "error"}">PBS</span>`].join("");
}
async function load(force = false) { elements.refresh.disabled = true; elements.error.hidden = true; try { state.payload = await api(force ? "/api/refresh" : "/api/dashboard", {method: force ? "POST" : "GET"}); renderPveOptions(); render(); } catch (error) { elements.error.textContent = error.message; elements.error.hidden = false; } finally { elements.refresh.disabled = false; } }

function findGuest(pve, vmid) { return state.payload?.vms.find((g) => g.pve_id === pve && g.vmid === Number(vmid)); }
function openPower(g, action) { state.powerGuest = g; state.powerAction = action; const labels = {start: "Iniciar", shutdown: "Desligar", reboot: "Reiniciar"}; elements.powerTitle.textContent = labels[action]; elements.powerDescription.textContent = `${labels[action]} ${g.kind_display} ${g.vmid} — ${g.name}?`; elements.powerForm.reset(); elements.powerDialog.showModal(); }
function openNote(g) { state.noteGuest = g; elements.noteTitle.textContent = `${g.vmid} — ${g.name}`; elements.noteText.value = g.note || ""; elements.noteDelete.hidden = !g.note; elements.noteDialog.showModal(); }

document.addEventListener("click", async (event) => {
  const power = event.target.closest("[data-power]"); if (power) openPower(findGuest(power.dataset.pve, power.dataset.vmid), power.dataset.power);
  const note = event.target.closest("[data-note]"); if (note) openNote(findGuest(note.dataset.pve, note.dataset.vmid));
  const ip = event.target.closest("[data-ip]"); if (ip) { await navigator.clipboard.writeText(ip.dataset.ip); showToast("IP copiado"); }
  const closer = event.target.closest("[data-close-dialog]"); if (closer) $(closer.dataset.closeDialog).close();
});

elements.powerForm.addEventListener("submit", async (event) => { event.preventDefault(); const g = state.powerGuest; const body = {username: $("power-user").value, realm: $("power-realm").value, password: $("power-password").value, otp: $("power-otp").value || null}; try { await api(`/api/guests/${encodeURIComponent(g.pve_id)}/${encodeURIComponent(g.node)}/${g.kind}/${g.vmid}/${state.powerAction}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)}); elements.powerDialog.close(); showToast("Operação enviada"); await load(true); } catch (error) { showToast(error.message); } finally { $("power-password").value = ""; $("power-otp").value = ""; } });
elements.noteForm.addEventListener("submit", async (event) => { event.preventDefault(); const g = state.noteGuest; try { const result = await api(`/api/notes/${encodeURIComponent(g.pve_id)}/${g.vmid}`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({note: elements.noteText.value})}); g.note = result.note; elements.noteDialog.close(); render(); showToast("Nota salva"); } catch (error) { showToast(error.message); } });
elements.noteDelete.addEventListener("click", async () => { elements.noteText.value = ""; elements.noteForm.requestSubmit(); });

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => { document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === button)); state.tab = button.dataset.tab; $("monitoring-panel").classList.toggle("active", state.tab === "monitoring"); $("backups-panel").classList.toggle("active", state.tab === "backups"); }));
elements.search.addEventListener("input", (e) => { state.query = e.target.value; render(); }); elements.status.addEventListener("change", (e) => { state.status = e.target.value; render(); }); elements.pve.addEventListener("change", (e) => { state.pve = e.target.value; render(); }); elements.clear.addEventListener("click", () => { state.query = ""; state.status = state.pve = "all"; elements.search.value = ""; elements.status.value = elements.pve.value = "all"; render(); }); elements.refresh.addEventListener("click", () => load(true)); elements.logout.addEventListener("click", async () => { await api("/api/logout", {method: "POST"}); location.replace("/login"); });
if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
load(); setInterval(() => load(), Math.max(15, refreshSeconds) * 1000);
