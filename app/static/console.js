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
const ctrlAltDelButton = document.getElementById("console-ctrl-alt-del");
const focusButton = document.getElementById("console-focus");
const csrf = document.body.dataset.csrf;
let currentGuest = null;
let rfb = null;

function setStatus(message, error = false) {
  status.textContent = message;
  status.className = error ? "error-banner" : "muted";
  status.hidden = !message;
}

function resetConsole() {
  if (rfb) {
    rfb.disconnect();
    rfb = null;
  }
  screen.replaceChildren();
  authForm.hidden = false;
  authFields.hidden = false;
  authSubmit.disabled = false;
  toolbar.hidden = true;
  setStatus("");
}

function openConsole(guest) {
  currentGuest = guest;
  resetConsole();
  description.textContent = `Console da VM ${guest.vmid} — ${guest.name}`;
  dialog.showModal();
  document.getElementById("console-user").focus();
}

async function connectConsole(event) {
  event.preventDefault();
  if (!currentGuest) return;
  authSubmit.disabled = true;
  setStatus("Autenticando no PVE e preparando o console…");
  try {
    const response = await fetch("/api/console", {
      method: "POST",
      headers: {"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": csrf},
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

    document.getElementById("console-password").value = "";
    document.getElementById("console-otp").value = "";
    authForm.hidden = true;
    toolbar.hidden = false;
    setStatus("Conectando ao console…");
    const websocketUrl = new URL(payload.websocket_path, window.location.href);
    websocketUrl.protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const vncPassword = payload.vnc_password;
    rfb = new RFB(screen, websocketUrl.toString(), {credentials: {password: vncPassword}});
    rfb.scaleViewport = true;
    rfb.resizeSession = true;
    rfb.clipViewport = false;
    rfb.addEventListener("connect", () => setStatus("Console conectado"));
    rfb.addEventListener("disconnect", (event) => {
      if (dialog.open) setStatus(event.detail?.clean ? "Console desconectado" : "Console desconectado inesperadamente", !event.detail?.clean);
    });
    rfb.addEventListener("credentialsrequired", () => {
      rfb.sendCredentials({password: vncPassword});
      setStatus("Autenticando o console…");
    });
  } catch (error) {
    authSubmit.disabled = false;
    setStatus(error.message, true);
  }
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-console]");
  if (button) openConsole({pve: button.dataset.pve, node: button.dataset.node, vmid: button.dataset.vmid, name: button.dataset.name});
});
authForm.addEventListener("submit", connectConsole);
closeButton.addEventListener("click", () => dialog.close());
ctrlAltDelButton.addEventListener("click", () => {
  if (!rfb) return;
  rfb.sendCtrlAltDel();
  setStatus("Ctrl + Alt + Del enviado ao console");
});
focusButton.addEventListener("click", () => {
  if (!rfb) return;
  rfb.focus();
  setStatus("Teclado direcionado para o console");
});
dialog.addEventListener("close", resetConsole);
