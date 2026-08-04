"use strict";

const form = document.getElementById("settings-form");
const message = document.getElementById("settings-message");
const lists = {
  pve: {list: document.getElementById("pve-list"), template: document.getElementById("pve-template"), add: document.getElementById("add-pve"), label: "PVE"},
  pbs: {list: document.getElementById("pbs-list"), template: document.getElementById("pbs-template"), add: document.getElementById("add-pbs"), label: "PBS"}
};

function refreshCardTitle(card, type) {
  const name = card.querySelector(`[data-${type}="name"]`)?.value.trim();
  const id = card.querySelector(`[data-${type}="id"]`)?.value.trim();
  card.querySelector(`.${type}-card-title`).textContent = name || id || `Novo ${type.toUpperCase()}`;
}

function bindCard(card, type) {
  const config = lists[type];
  card.querySelectorAll(`[data-${type}]`).forEach((field) => field.addEventListener("input", () => refreshCardTitle(card, type)));
  card.querySelector(`.remove-${type}`).addEventListener("click", () => {
    if (config.list.querySelectorAll(`.${type}-card`).length <= 1) {
      showMessage(`É necessário manter pelo menos um ${config.label}.`, true);
      return;
    }
    card.remove();
  });
  refreshCardTitle(card, type);
}

function showMessage(text, error = false) {
  message.textContent = text;
  message.className = error ? "message error-banner" : "message success-message";
  message.hidden = false;
}

function collectItems(type) {
  return [...lists[type].list.querySelectorAll(`.${type}-card`)].map((card) => {
    const value = (name) => card.querySelector(`[data-${type}="${name}"]`).value;
    return {
      id: value("id"), name: value("name"), url: value("url"), token_id: value("token_id"), token_secret: value("token_secret"), verify_tls: value("verify_tls") === "true",
      ...(type === "pbs" ? {datastores: value("datastores"), node: value("node")} : {})
    };
  });
}

for (const [type, config] of Object.entries(lists)) {
  config.list.querySelectorAll(`.${type}-card`).forEach((card) => bindCard(card, type));
  config.add.addEventListener("click", () => {
    const card = config.template.content.firstElementChild.cloneNode(true);
    config.list.append(card);
    bindCard(card, type);
    card.querySelector(`[data-${type}="id"]`).focus();
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  message.hidden = true;
  const values = Object.fromEntries(new FormData(form).entries());
  try {
    const response = await fetch("/api/settings", {
      method: "PUT",
      headers: {"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": document.body.dataset.csrf},
      body: JSON.stringify({values, pves: collectItems("pve"), pbses: collectItems("pbs")}),
      cache: "no-store"
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(payload.detail)
        ? payload.detail.map((item) => `${Array.isArray(item.loc) ? item.loc.join(".") : "campo"}: ${item.msg || "valor inválido"}`).join("; ")
        : payload.detail;
      throw new Error(detail || "Falha ao salvar");
    }
    showMessage("Configurações salvas. O serviço está reiniciando para aplicar as alterações.");
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    button.disabled = false;
  }
});
