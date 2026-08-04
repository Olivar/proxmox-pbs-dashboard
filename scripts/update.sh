#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/update.sh" >&2
  exit 1
fi

APP_DIR=/opt/proxmox-pbs-dashboard
CONFIG_DIR=/etc/proxmox-pbs-dashboard
ENV_FILE="$CONFIG_DIR/dashboard.env"
LEGACY_PVE_FILE="$CONFIG_DIR/pve-instances.json"
SERVICE_FILE=/etc/systemd/system/proxmox-pbs-dashboard.service
SERVICE_USER=proxmox-dashboard

cd "$APP_DIR"
git pull --ff-only
.venv/bin/pip install -r requirements.txt

if [[ -f "$ENV_FILE" ]]; then
  if ! grep -q '^DASHBOARD_USERNAME=' "$ENV_FILE"; then printf '\nDASHBOARD_USERNAME=admin\n' >> "$ENV_FILE"; fi
  if ! grep -q '^DASHBOARD_PASSWORD=' "$ENV_FILE"; then
    DASH_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
    printf 'DASHBOARD_PASSWORD=%s\n' "$DASH_PASSWORD" >> "$ENV_FILE"
    echo "Senha inicial do dashboard: $DASH_PASSWORD"
    echo "Guarde esta senha. Ela não será exibida novamente."
  fi
  if ! grep -q '^DASHBOARD_SESSION_SECRET=' "$ENV_FILE"; then printf 'DASHBOARD_SESSION_SECRET=%s\n' "$(openssl rand -hex 32)" >> "$ENV_FILE"; fi
  if ! grep -q '^DASHBOARD_DEFAULT_THEME=' "$ENV_FILE"; then printf 'DASHBOARD_DEFAULT_THEME=system\n' >> "$ENV_FILE"; fi
  if ! grep -q '^DASHBOARD_ENV_FILE=' "$ENV_FILE"; then printf 'DASHBOARD_ENV_FILE=%s\n' "$ENV_FILE" >> "$ENV_FILE"; fi

  if ! grep -q '^PVE_INSTANCES_JSON=' "$ENV_FILE" && [[ -f "$LEGACY_PVE_FILE" ]]; then
    PVE_ENV_LINE=$(.venv/bin/python - "$LEGACY_PVE_FILE" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
print("PVE_INSTANCES_JSON=" + json.dumps(compact, ensure_ascii=False))
PY
)
    printf '\n%s\n' "$PVE_ENV_LINE" >> "$ENV_FILE"
    echo "PVEs migrados de pve-instances.json para dashboard.env."
  fi

  chown root:"$SERVICE_USER" "$ENV_FILE"
  chmod 0660 "$ENV_FILE"
fi

install -m 0644 "$APP_DIR/deploy/proxmox-pbs-dashboard.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl restart proxmox-pbs-dashboard
sleep 2
systemctl --no-pager --full status proxmox-pbs-dashboard
