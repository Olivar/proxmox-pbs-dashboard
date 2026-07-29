"use strict";

const form = document.getElementById("settings-form");
const message = document.getElementById("settings-message");
const pveList = document.getElementById("pve-list");
const template = document.getElementById("pve-template");

function refreshCardTitle(card) {
  const name = card.querySelector('[data-pve="name"]')?.value.trim();
  const id = card.querySelector('[data-pve="id"]')?.value.trim();
  card.querySelector(".pve-card-title").textContent = name || id || "Novo PVE";
}

function bindCard(card) {
  card.querySelectorAll("[data-pve]").forEach((field) => field.addEventListener("input", () => refreshCardTitle(card)));
  card.querySelector(".remove-pve").addEventListener("click", () => {
    if (pveList.querySelectorAll(".pve-card").length <= 1) {
      showMessage("É necessário manter pelo menos um PVE.", true);
      return;
    }
    card.remove();
  });
  refreshCardTitle(card);
}

function showMessage(text, error = false) {
  message.textContent = text;
  message.className = error ? "message error-banner" : "message success-message";
  message.hidden = false;
}

function collectPves() {
  return [...pveList.querySelectorAll(".pve-card")].map((card) => ({
    id: card.querySelector('[data-pve="id"]').value,
    name: card.querySelector('[data-pve="name"]').value,
    url: card.querySelector('[data-pve="url"]').value,
    token_id: card.querySelector('[data-pve="token_id"]').value,
    token_secret: card.querySelector('[data-pve="token_secret"]').value,
    verify_tls: card.querySelector('[data-pve="verify_tls"]').value === "true"
  }));
}

pveList.querySelectorAll(".pve-card").forEach(bindCard);
document.getElementById("add-pve").addEventListener("click", () => {
  const card = template.content.firstElementChild.cloneNode(true);
  pveList.append(card);
  bindCard(card);
  card.querySelector('[data-pve="id"]').focus();
});

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
      body: JSON.stringify({values, pves: collectPves()}),
      cache: "no-store"
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Falha ao salvar");
    showMessage("Configurações salvas. Reinicie o serviço para aplicar.");
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    button.disabled = false;
  }
});
