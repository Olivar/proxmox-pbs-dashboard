import RFB from "./novnc/core/rfb.js";

const dialog = document.getElementById("console-dialog");
const authForm = document.getElementById("console-auth-form");
const authFields = document.getElementById("console-auth-fields");
const authSubmit = document.getElementById("console-auth-submit");
const description = document.getElementById("console-description");
const status = document.getElementById("console-status");
const screen = document.getElementById("console-screen");
const closeButton = document.getElementById("console-close");
const toolbar = document.getElementById("console-toolbar");
const powerControls = document.getElementById("console-power-controls");
const metrics = document.getElementById("console-metrics");
const actionStatus = document.getElementById("console-action-status");
const ctrlAltDelButton = document.getElementById("console-ctrl-alt-del");
const focusButton = document.getElementById("console-focus");
const powerButtons = {
  reboot: document.getElementById("console-reboot"),
  shutdown: document.getElementById("console-stop"),
  start: document.getElementById("console-start"),
};
const metricNodes = {
  cpu: {percent: document.getElementById("console-cpu-percent"), detail: document.getElementById("console-cpu-detail")},
  ram: {percent: document.getElementById("console-ram-percent"), detail: document.getElementById("console-ram-detail")},
  disk: {percent: document.getElementById("console-disk-percent"), detail: document.getElementById("console-disk-detail")},
  network: {percent: document.getElementById("console-network-percent"), detail: document.getElementById("console-network-detail")},
};
const csrf = document.body.dataset.csrf;
const METRICS_INTERVAL_MS = 5000;
let currentGuest = null;
let currentSessionId = null;
let rfb = null;
let metricsTimer = null;
let metricsPrevious = null;

function setStatus(message, error = false) {
  status.textContent = message;
  status.className = error ? "error-banner" : "muted";
  status.hidden = !message;
}

function setActionStatus(message, error = false) {
  actionStatus.textContent = message;
  actionStatus.className = `console-action-status${error ? " error" : ""}`;
}

function releaseConsoleSession() {
  const sessionId = currentSessionId;
  currentSessionId = null;
  if (!sessionId) return;
  fetch(`/api/console/${encodeURIComponent(sessionId)}/close`, {
    method: "POST",
    headers: {"X-CSRF-Token": csrf, Accept: "application/json"},
    keepalive: true,
  }).catch(() => {});
}

function resetMetricValues() {
  Object.values(metricNodes).forEach((node) => {
    node.percent.textContent = "—";
    node.detail.textContent = "online";
  });
  metricsPrevious = null;
}

function stopLiveMetrics() {
  if (metricsTimer) {
    clearInterval(metricsTimer);
    metricsTimer = null;
  }
  metricsPrevious = null;
}

function resetConsole() {
  stopLiveMetrics();
  releaseConsoleSession();
  if (rfb) {
    rfb.disconnect();
    rfb = null;
  }
  dialog.classList.remove("console-connected");
  screen.replaceChildren();
  authForm.hidden = false;
  authFields.hidden = false;
  authSubmit.disabled = false;
  description.hidden = false;
  toolbar.hidden = true;
  powerControls.hidden = true;
  metrics.hidden = true;
  Object.values(powerButtons).forEach((button) => { button.disabled = false; });
  setActionStatus("");
  resetMetricValues();
  setStatus("");
}

function openConsole(guest) {
  currentGuest = guest;
  resetConsole();
  description.textContent = `Console da VM ${guest.vmid} — ${guest.name}`;
  dialog.showModal();
  document.getElementById("console-user").focus();
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  return `${new Intl.NumberFormat("pt-BR", {maximumFractionDigits: index < 2 ? 0 : 1}).format(value / (1024 ** index))} ${units[index]}`;
}

function formatRate(bytesPerSecond) {
  const mbps = Number(bytesPerSecond || 0) * 8 / 1_000_000;
  if (mbps < 1) return `${new Intl.NumberFormat("pt-BR", {maximumFractionDigits: 0}).format(mbps * 1000)} Kbps`;
  return `${new Intl.NumberFormat("pt-BR", {maximumFractionDigits: 1}).format(mbps)} Mbps`;
}

function setMetric(name, percent, detail) {
  const node = metricNodes[name];
  const value = percent == null || Number.isNaN(Number(percent)) ? null : Math.max(0, Math.min(100, Math.round(Number(percent))));
  node.percent.textContent = value == null ? "—" : `${value}%`;
  node.percent.dataset.level = value == null ? "" : value >= 80 ? "high" : value >= 60 ? "medium" : "low";
  node.detail.textContent = detail;
}

function renderLiveMetrics(payload) {
  const now = performance.now();
  const previous = metricsPrevious;
  const elapsed = previous ? (now - previous.time) / 1000 : 0;
  let inRate = null;
  let outRate = null;
  if (previous && elapsed > 0) {
    inRate = Math.max(0, (Number(payload.network_in_bytes || 0) - previous.inBytes) / elapsed);
    outRate = Math.max(0, (Number(payload.network_out_bytes || 0) - previous.outBytes) / elapsed);
  }
  const totalRate = inRate == null || outRate == null ? null : inRate + outRate;
  const networkPercent = payload.network_percent ?? (totalRate != null && payload.network_limit_bps ? totalRate * 100 / payload.network_limit_bps : null);
  setMetric("cpu", payload.cpu_percent, "uso atual");
  setMetric("ram", payload.ram_percent, `${formatBytes(payload.ram_used_bytes)} de ${formatBytes(payload.ram_total_bytes)}`);
  const diskDetail = payload.disk_percent == null
    ? "sem dados do QEMU Agent"
    : `${formatBytes(payload.disk_used_bytes)} de ${formatBytes(payload.disk_total_bytes)}`;
  setMetric("disk", payload.disk_percent, diskDetail);
  const networkDetail = totalRate == null
    ? "calculando taxa..."
    : `↓ ${formatRate(inRate)} · ↑ ${formatRate(outRate)}`;
  setMetric("network", networkPercent, networkDetail);
  metricsPrevious = {time: now, inBytes: Number(payload.network_in_bytes || 0), outBytes: Number(payload.network_out_bytes || 0)};
}

async function loadLiveMetrics() {
  if (!currentSessionId) return;
  try {
    const response = await fetch(`/api/console/${encodeURIComponent(currentSessionId)}/metrics`, {headers: {Accept: "application/json"}, cache: "no-store"});
    const payload = await response.json();
    if (response.status === 401) { location.replace("/login"); return; }
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    renderLiveMetrics(payload);
  } catch (error) {
    // Falhas transitórias não devem alterar o cabeçalho nem redimensionar o noVNC.
    // Os últimos valores válidos permanecem visíveis até a próxima leitura.
  }
}

function startLiveMetrics() {
  stopLiveMetrics();
  resetMetricValues();
  loadLiveMetrics();
  metricsTimer = setInterval(loadLiveMetrics, METRICS_INTERVAL_MS);
}

function updatePowerButtons() {
  const running = currentGuest?.state === "running";
  const stopped = currentGuest?.state === "stopped";
  powerButtons.start.disabled = running;
  powerButtons.shutdown.disabled = stopped;
  powerButtons.reboot.disabled = stopped;
}

async function runPowerAction(action) {
  if (!currentSessionId || !currentGuest) return;
  const labels = {start: "Start", shutdown: "Stop", reboot: "Reboot"};
  const label = labels[action];
  if (!window.confirm(`${label} VM ${currentGuest.vmid} — ${currentGuest.name}?`)) return;
  Object.values(powerButtons).forEach((button) => { button.disabled = true; });
  setActionStatus(`${label} em execução...`);
  try {
    const response = await fetch(`/api/console/${encodeURIComponent(currentSessionId)}/action`, {
      method: "POST",
      headers: {"Content-Type": "application/json", Accept: "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify({action}),
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    setActionStatus(`${label} enviado ao Proxmox`);
    setTimeout(loadLiveMetrics, 1200);
  } catch (error) {
    setActionStatus(error.message, true);
  } finally {
    updatePowerButtons();
  }
}

async function connectConsole(event) {
  event.preventDefault();
  if (!currentGuest) return;
  authSubmit.disabled = true;
  setStatus("Autenticando no PVE e preparando o console...");
  try {
    const response = await fetch("/api/console", {
      method: "POST",
      headers: {"Content-Type": "application/json", Accept: "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify({
        pve_id: currentGuest.pve,
        node: currentGuest.node,
        kind: "qemu",
        vmid: Number(currentGuest.vmid),
        username: document.getElementById("console-user").value,
        realm: document.getElementById("console-realm").value,
        password: document.getElementById("console-password").value,
        otp: document.getElementById("console-otp").value || null,
      }),
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Não foi possível abrir o console");

    currentSessionId = payload.session_id;
    document.getElementById("console-password").value = "";
    document.getElementById("console-otp").value = "";
    authForm.hidden = true;
    description.hidden = true;
    toolbar.hidden = false;
    powerControls.hidden = false;
    metrics.hidden = false;
    updatePowerButtons();
    startLiveMetrics();
    setStatus("Conectando ao console...");
    const websocketUrl = new URL(payload.websocket_path, window.location.href);
    websocketUrl.protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const vncPassword = payload.vnc_password;
    rfb = new RFB(screen, websocketUrl.toString(), {credentials: {password: vncPassword}});
    rfb.scaleViewport = true;
    // Mantém a resolução da VM estável; o viewport continua sendo escalado pelo navegador.
    rfb.resizeSession = false;
    rfb.clipViewport = false;
    rfb.addEventListener("connect", () => {
      dialog.classList.add("console-connected");
      setStatus("");
    });
    rfb.addEventListener("disconnect", (event) => {
      if (dialog.open) setStatus(event.detail?.clean ? "Console desconectado" : "Console desconectado inesperadamente", !event.detail?.clean);
    });
    rfb.addEventListener("credentialsrequired", () => {
      rfb.sendCredentials({password: vncPassword});
      setStatus("Autenticando o console...");
    });
  } catch (error) {
    authSubmit.disabled = false;
    setStatus(error.message, true);
  }
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-console]");
  if (button) openConsole({pve: button.dataset.pve, node: button.dataset.node, vmid: button.dataset.vmid, name: button.dataset.name, state: button.dataset.state});
});
authForm.addEventListener("submit", connectConsole);
closeButton.addEventListener("click", () => dialog.close());
Object.entries(powerButtons).forEach(([action, button]) => button.addEventListener("click", () => runPowerAction(action)));
ctrlAltDelButton.addEventListener("click", () => {
  if (!rfb) return;
  rfb.sendCtrlAltDel();
  setActionStatus("Ctrl + Alt + Del enviado ao console");
});
focusButton.addEventListener("click", () => {
  if (!rfb) return;
  rfb.focus();
  setActionStatus("Teclado direcionado para o console");
});
dialog.addEventListener("close", () => { currentGuest = null; resetConsole(); });
