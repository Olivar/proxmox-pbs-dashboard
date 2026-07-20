"use strict";

const state = { payload: null, query: "" };
const refreshSeconds = Number(document.body.dataset.refreshSeconds || 60);

const elements = {
  search: document.getElementById("search"),
  refresh: document.getElementById("refresh"),
  lastUpdate: document.getElementById("last-update"),
  sourceStatus: document.getElementById("source-status"),
  vmTable: document.getElementById("vm-table"),
  backupTable: document.getElementById("backup-table"),
  vmCount: document.getElementById("vm-count"),
  backupCount: document.getElementById("backup-count"),
  error: document.getElementById("error"),
  metricTotal: document.getElementById("metric-total"),
  metricRunning: document.getElementById("metric-running"),
  metricStopped: document.getElementById("metric-stopped"),
  metricBackupFailed: document.getElementById("metric-backup-failed"),
};

const htmlEscape = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const stateBadge = (vm) => `<span class="badge badge-${htmlEscape(vm.state)}">${htmlEscape(vm.state_display)}</span>`;

const backupLabels = {
  success: "Sucesso",
  failed: "Falhou",
  running: "Executando",
  missing: "Sem backup",
  unknown: "Desconhecido",
};

const backupBadge = (backup) => {
  const css = backup.status === "running" ? "backup-running" : backup.status;
  const label = backupLabels[backup.status] || "Desconhecido";
  const title = backup.detail ? ` title="${htmlEscape(backup.detail)}"` : "";
  return `<span class="badge badge-${css}"${title}>${label}</span>`;
};

const formatDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(date);
};

const filteredVms = () => {
  if (!state.payload) return [];
  const query = state.query.trim().toLocaleLowerCase("pt-BR");
  if (!query) return state.payload.vms;
  return state.payload.vms.filter((vm) => [vm.pve_name, vm.pve_id, vm.name, vm.vmid, vm.ip, vm.node]
    .some((value) => String(value ?? "").toLocaleLowerCase("pt-BR").includes(query)));
};

const sourceChip = (label, source) => {
  const status = source.ok ? "ok" : "error";
  const text = source.ok ? "online" : "erro";
  const title = source.error ? ` title="${htmlEscape(source.error)}"` : "";
  return `<span class="status-chip ${status}"${title}>${htmlEscape(label)}: ${text}</span>`;
};

const render = () => {
  if (!state.payload) return;
  const vms = filteredVms();
  const allVms = state.payload.vms;

  elements.metricTotal.textContent = allVms.length;
  elements.metricRunning.textContent = allVms.filter((vm) => vm.state === "running").length;
  elements.metricStopped.textContent = allVms.filter((vm) => vm.state === "stopped").length;
  elements.metricBackupFailed.textContent = allVms.filter((vm) => vm.backup.status === "failed").length;

  elements.vmCount.textContent = `${vms.length} de ${allVms.length}`;
  elements.backupCount.textContent = `${vms.length} VMs`;

  elements.vmTable.innerHTML = vms.length ? vms.map((vm) => `
    <tr>
      <td>${stateBadge(vm)}</td>
      <td>${htmlEscape(vm.pve_name)}</td>
      <td><strong>${htmlEscape(vm.name)}</strong></td>
      <td>${htmlEscape(vm.vmid)}</td>
      <td>${htmlEscape(vm.ip || "Não disponível")}</td>
      <td>${htmlEscape(vm.uptime_display)}</td>
      <td>${htmlEscape(vm.node)}</td>
    </tr>`).join("") : `<tr><td class="empty" colspan="7">Nenhuma VM encontrada.</td></tr>`;

  elements.backupTable.innerHTML = vms.length ? vms.map((vm) => `
    <tr>
      <td>${backupBadge(vm.backup)}</td>
      <td>${htmlEscape(vm.pve_name)}</td>
      <td><strong>${htmlEscape(vm.name)}</strong></td>
      <td>${htmlEscape(vm.vmid)}</td>
      <td>${formatDate(vm.backup.last_backup)}</td>
      <td>${htmlEscape(vm.backup.datastore || "—")}</td>
    </tr>`).join("") : `<tr><td class="empty" colspan="6">Nenhuma VM encontrada.</td></tr>`;

  const updatedAt = formatDate(state.payload.updated_at);
  elements.lastUpdate.textContent = `${state.payload.stale ? "Dados parcialmente em cache" : "Atualizado"}: ${updatedAt}`;
  elements.sourceStatus.innerHTML = [
    ...state.payload.pve.map((source) => sourceChip(source.source_name || source.source_id || "PVE", source)),
    sourceChip("PBS", state.payload.pbs),
  ].join("");
};

const loadDashboard = async (force = false) => {
  elements.refresh.disabled = true;
  elements.error.hidden = true;
  try {
    const response = await fetch(force ? "/api/refresh" : "/api/dashboard", {
      method: force ? "POST" : "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    state.payload = payload;
    render();
  } catch (error) {
    elements.error.textContent = `Falha ao carregar dashboard: ${error.message}`;
    elements.error.hidden = false;
  } finally {
    elements.refresh.disabled = false;
  }
};

elements.search.addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});
elements.refresh.addEventListener("click", () => loadDashboard(true));

loadDashboard(false);
window.setInterval(() => loadDashboard(false), Math.max(15, refreshSeconds) * 1000);
