#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/update.sh" >&2
  exit 1
fi

APP_DIR=/opt/proxmox-pbs-dashboard
ENV_FILE=/etc/proxmox-pbs-dashboard/dashboard.env
SERVICE_USER=proxmox-dashboard

cd "$APP_DIR"
git pull --ff-only
.venv/bin/pip install -r requirements.txt

if [[ -f "$ENV_FILE" ]]; then
  if ! grep -q '^DASHBOARD_USERNAME=' "$ENV_FILE"; then
    printf '\nDASHBOARD_USERNAME=admin\n' >> "$ENV_FILE"
  fi
  if ! grep -q '^DASHBOARD_PASSWORD=' "$ENV_FILE"; then
    DASH_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
    printf 'DASHBOARD_PASSWORD=%s\n' "$DASH_PASSWORD" >> "$ENV_FILE"
    echo "Senha inicial do dashboard: $DASH_PASSWORD"
    echo "Guarde esta senha. Ela não será exibida novamente."
  fi
  if ! grep -q '^DASHBOARD_SESSION_SECRET=' "$ENV_FILE"; then
    printf 'DASHBOARD_SESSION_SECRET=%s\n' "$(openssl rand -hex 32)" >> "$ENV_FILE"
  fi
  if ! grep -q '^DASHBOARD_DEFAULT_THEME=' "$ENV_FILE"; then
    printf 'DASHBOARD_DEFAULT_THEME=system\n' >> "$ENV_FILE"
  fi
  if ! grep -q '^DASHBOARD_ENV_FILE=' "$ENV_FILE"; then
    printf 'DASHBOARD_ENV_FILE=%s\n' "$ENV_FILE" >> "$ENV_FILE"
  fi
  chown root:"$SERVICE_USER" "$ENV_FILE"
  chmod 0660 "$ENV_FILE"
fi

systemctl restart proxmox-pbs-dashboard
systemctl --no-pager --full status proxmox-pbs-dashboard
