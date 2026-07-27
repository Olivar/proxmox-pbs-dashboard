"use strict";

const state = { payload: null, query: "", kind: "all", guestState: "all", backup: "all", pve: "all", tab: "monitoring", noteGuest: null };
const refreshSeconds = Number(document.body.dataset.refreshSeconds || 60);
const $ = (id) => document.getElementById(id);
const elements = {
  search: $("search"), kind: $("filter-kind"), guestState: $("filter-state"), backup: $("filter-backup"), pve: $("filter-pve"), clear: $("clear-filters"), refresh: $("refresh"),
  lastUpdate: $("last-update"), sourceStatus: $("source-status"), vmTable: $("vm-table"), backupTable: $("backup-table"), vmCount: $("vm-count"), backupCount: $("backup-count"), error: $("error"),
  metricTotal: $("metric-total"), metricVms: $("metric-vms"), metricCts: $("metric-cts"), metricRunning: $("metric-running"), metricStopped: $("metric-stopped"),
  metricBackupSuccess: $("metric-backup-success"), metricBackupFailed: $("metric-backup-failed"), metricBackupMissing: $("metric-backup-missing"), metricBackupRunning: $("metric-backup-running"),
  pie: $("backup-pie"), pieCenter: $("pie-center"), legend: $("backup-legend"), chartTotal: $("backup-chart-total"), noteDialog: $("note-dialog"), noteForm: $("note-form"), noteTitle: $("note-title"), noteText: $("note-text"), noteDelete: $("note-delete"), toast: $("toast")
};

const htmlEscape = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const attrEscape = (value) => htmlEscape(value);
const backupLabels = { success: "Sucesso", failed: "Erro", running: "Executando", missing: "Sem backup", unknown: "Desconhecido" };
const chartColors = { success: "#45d493", failed: "#ff746c", missing: "#c5cedb", running: "#ffd166", unknown: "#748198" };
const stateBadge = (guest) => `<span class="badge badge-${attrEscape(guest.state)}">${htmlEscape(guest.state_display)}</span>`;
const backupBadge = (backup) => `<span class="badge badge-${backup.status === "running" ? "backup-running" : attrEscape(backup.status)}"${backup.detail ? ` title="${attrEscape(backup.detail)}"` : ""}>${htmlEscape(backupLabels[backup.status] || "Desconhecido")}</span>`;
const formatDate = (value) => { if (!value) return "—"; const d = new Date(value); return Number.isNaN(d.getTime()) ? "—" : new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" }).format(d); };
const pveLink = (guest) => `<a class="table-link" href="${attrEscape(guest.pve_url)}" target="_blank" rel="noopener noreferrer">${htmlEscape(guest.pve_name)}</a>`;
const nodeLink = (guest) => `<a class="table-link" href="${attrEscape(guest.pve_url)}/#v1:0:=node/${encodeURIComponent(guest.node)}" target="_blank" rel="noopener noreferrer">${htmlEscape(guest.node)}</a>`;
const ipButton = (guest) => guest.ip ? `<button class="copy-ip" type="button" data-copy-ip="${attrEscape(guest.ip)}" title="Copiar IP">${htmlEscape(guest.ip)}</button>` : `<button class="copy-ip unavailable" type="button" disabled>Indisponível</button>`;
const noteButton = (guest) => `<button class="note-button ${guest.note ? "has-note" : ""}" type="button" data-note-pve="${attrEscape(guest.pve_id)}" data-note-vmid="${guest.vmid}" title="${attrEscape(guest.note || "Adicionar nota")}">${guest.note ? "Ver nota" : "Adicionar"}</button>`;

const filteredGuests = () => {
  if (!state.payload) return [];
  const query = state.query.trim().toLocaleLowerCase("pt-BR");
  return state.payload.vms.filter((guest) => {
    const matchesText = !query || [guest.name, guest.vmid, guest.ip, guest.node, guest.pve_name, guest.note, guest.kind_display].some((v) => String(v ?? "").toLocaleLowerCase("pt-BR").includes(query));
    return matchesText && (state.kind === "all" || guest.kind === state.kind) && (state.guestState === "all" || guest.state === state.guestState) && (state.backup === "all" || guest.backup.status === state.backup) && (state.pve === "all" || guest.pve_id === state.pve);
  });
};

const sourceChip = (label, source) => `<span class="status-chip ${source.ok ? "ok" : "error"}"${source.error ? ` title="${attrEscape(source.error)}"` : ""}>${htmlEscape(label)}: ${source.ok ? "online" : "erro"}</span>`;

const renderPveOptions = () => {
  const current = state.pve;
  const entries = [...new Map((state.payload?.vms || []).map((g) => [g.pve_id, g.pve_name])).entries()].sort((a, b) => a[1].localeCompare(b[1], "pt-BR"));
  elements.pve.innerHTML = `<option value="all">Todos</option>${entries.map(([id, name]) => `<option value="${attrEscape(id)}">${htmlEscape(name)}</option>`).join("")}`;
  elements.pve.value = entries.some(([id]) => id === current) ? current : "all";
};

const renderChart = (guests) => {
  const counts = { success: 0, failed: 0, missing: 0, running: 0, unknown: 0 };
  guests.forEach((g) => { counts[g.backup.status] = (counts[g.backup.status] || 0) + 1; });
  const total = guests.length;
  let cursor = 0;
  const slices = Object.entries(counts).filter(([, count]) => count > 0).map(([status, count]) => { const start = cursor; cursor += total ? (count / total) * 100 : 0; return `${chartColors[status]} ${start}% ${cursor}%`; });
  elements.pie.style.background = slices.length ? `conic-gradient(${slices.join(",")})` : "var(--neutral-bg)";
  elements.pieCenter.textContent = total;
  elements.chartTotal.textContent = `${total} guests`;
  elements.legend.innerHTML = Object.entries(counts).filter(([status]) => status !== "unknown" || counts.unknown).map(([status, count]) => `<div class="legend-item"><span class="legend-dot" style="background:${chartColors[status]}"></span><span>${htmlEscape(backupLabels[status])}</span><strong>${count}</strong></div>`).join("");
  elements.metricBackupSuccess.textContent = counts.success;
  elements.metricBackupFailed.textContent = counts.failed;
  elements.metricBackupMissing.textContent = counts.missing + counts.unknown;
  elements.metricBackupRunning.textContent = counts.running;
};

const render = () => {
  if (!state.payload) return;
  const guests = filteredGuests();
  const all = state.payload.vms;
  elements.metricTotal.textContent = all.length;
  elements.metricVms.textContent = all.filter((g) => g.kind === "qemu").length;
  elements.metricCts.textContent = all.filter((g) => g.kind === "lxc").length;
  elements.metricRunning.textContent = all.filter((g) => g.state === "running").length;
  elements.metricStopped.textContent = all.filter((g) => g.state === "stopped").length;
  elements.vmCount.textContent = `${guests.length} de ${all.length}`;
  elements.backupCount.textContent = `${guests.length} itens`;

  elements.vmTable.innerHTML = guests.length ? guests.map((g) => `<tr><td>${stateBadge(g)}</td><td><span class="type-badge">${htmlEscape(g.kind_display)}</span></td><td>${pveLink(g)}</td><td><strong>${htmlEscape(g.name)}</strong></td><td>${g.vmid}</td><td>${ipButton(g)}</td><td>${htmlEscape(g.uptime_display)}</td><td>${nodeLink(g)}</td><td>${noteButton(g)}</td></tr>`).join("") : `<tr><td class="empty" colspan="9">Nenhum item encontrado.</td></tr>`;
  elements.backupTable.innerHTML = guests.length ? guests.map((g) => `<tr><td>${backupBadge(g.backup)}</td><td><span class="type-badge">${htmlEscape(g.kind_display)}</span></td><td>${pveLink(g)}</td><td><strong>${htmlEscape(g.name)}</strong></td><td>${g.vmid}</td><td>${formatDate(g.backup.last_backup)}</td><td>${htmlEscape(g.backup.datastore || "—")}</td></tr>`).join("") : `<tr><td class="empty" colspan="7">Nenhum item encontrado.</td></tr>`;
  renderChart(guests);
  elements.lastUpdate.textContent = `${state.payload.stale ? "Dados parciais/em cache" : "Atualizado"}: ${formatDate(state.payload.updated_at)}`;
  elements.sourceStatus.innerHTML = [...state.payload.pve.map((source) => sourceChip(source.source_name || "PVE", source)), sourceChip("PBS", state.payload.pbs)].join("");
};

const showToast = (message) => { elements.toast.textContent = message; elements.toast.hidden = false; window.clearTimeout(showToast.timer); showToast.timer = window.setTimeout(() => { elements.toast.hidden = true; }, 2200); };
const copyIp = async (ip) => { try { await navigator.clipboard.writeText(ip); showToast(`IP ${ip} copiado`); } catch { const input = document.createElement("textarea"); input.value = ip; document.body.append(input); input.select(); document.execCommand("copy"); input.remove(); showToast(`IP ${ip} copiado`); } };

const openNote = (pveId, vmid) => {
  const guest = state.payload?.vms.find((g) => g.pve_id === pveId && g.vmid === Number(vmid));
  if (!guest) return;
  state.noteGuest = guest;
  elements.noteTitle.textContent = `${guest.kind_display} ${guest.vmid} — ${guest.name}`;
  elements.noteText.value = guest.note || "";
  elements.noteDelete.hidden = !guest.note;
  elements.noteDialog.showModal();
  elements.noteText.focus();
};

const saveNote = async (note) => {
  const guest = state.noteGuest;
  if (!guest) return;
  const response = await fetch(`/api/notes/${encodeURIComponent(guest.pve_id)}/${guest.vmid}`, { method: "PUT", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ note }) });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  guest.note = payload.note;
  elements.noteDialog.close();
  render();
  showToast(payload.note ? "Nota salva" : "Nota excluída");
};

const loadDashboard = async (force = false) => {
  elements.refresh.disabled = true; elements.error.hidden = true;
  try {
    const response = await fetch(force ? "/api/refresh" : "/api/dashboard", { method: force ? "POST" : "GET", headers: { Accept: "application/json" }, cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    state.payload = payload; renderPveOptions(); render();
  } catch (error) { elements.error.textContent = `Falha ao carregar dashboard: ${error.message}`; elements.error.hidden = false; }
  finally { elements.refresh.disabled = false; }
};

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => { state.tab = button.dataset.tab; document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === button)); $("monitoring-panel").classList.toggle("active", state.tab === "monitoring"); $("backups-panel").classList.toggle("active", state.tab === "backups"); }));
[[elements.search, "query", "input"], [elements.kind, "kind", "change"], [elements.guestState, "guestState", "change"], [elements.backup, "backup", "change"], [elements.pve, "pve", "change"]].forEach(([element, key, eventName]) => element.addEventListener(eventName, (event) => { state[key] = event.target.value; render(); }));
elements.clear.addEventListener("click", () => { state.query = ""; state.kind = state.guestState = state.backup = state.pve = "all"; elements.search.value = ""; elements.kind.value = elements.guestState.value = elements.backup.value = elements.pve.value = "all"; render(); });
elements.refresh.addEventListener("click", () => loadDashboard(true));
document.addEventListener("click", (event) => { const copy = event.target.closest("[data-copy-ip]"); if (copy) copyIp(copy.dataset.copyIp); const note = event.target.closest("[data-note-pve]"); if (note) openNote(note.dataset.notePve, note.dataset.noteVmid); });
elements.noteForm.addEventListener("submit", async (event) => { event.preventDefault(); try { await saveNote(elements.noteText.value); } catch (error) { showToast(`Erro: ${error.message}`); } });
elements.noteDelete.addEventListener("click", async () => { try { await saveNote(""); } catch (error) { showToast(`Erro: ${error.message}`); } });
$("note-close").addEventListener("click", () => elements.noteDialog.close());
$("note-cancel").addEventListener("click", () => elements.noteDialog.close());

loadDashboard(false);
window.setInterval(() => loadDashboard(false), Math.max(15, refreshSeconds) * 1000);
