"use strict";
const form = document.getElementById("settings-form");
const message = document.getElementById("settings-message");
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  message.hidden = true;
  const values = Object.fromEntries(new FormData(form).entries());
  try {
    const response = await fetch("/api/settings", {
      method: "PUT",
      headers: {"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": document.body.dataset.csrf},
      body: JSON.stringify({values}),
      cache: "no-store"
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Falha ao salvar");
    message.textContent = "Salvo. Reinicie o serviço para aplicar.";
    message.className = "message success-message";
  } catch (error) {
    message.textContent = error.message;
    message.className = "message error";
  } finally {
    message.hidden = false;
    button.disabled = false;
  }
});
