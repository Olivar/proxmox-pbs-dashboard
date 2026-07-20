#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/install.sh" >&2
  exit 1
fi

SOURCE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
APP_DIR=/opt/proxmox-pbs-dashboard
CONFIG_DIR=/etc/proxmox-pbs-dashboard
STATE_DIR=/var/lib/proxmox-pbs-dashboard
SERVICE_USER=proxmox-dashboard

apt-get update
apt-get install -y python3 python3-venv python3-pip ca-certificates git rsync

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

install -d -o root -g root -m 0755 "$APP_DIR" "$CONFIG_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$STATE_DIR"

if [[ "$SOURCE_DIR" != "$APP_DIR" ]]; then
  rsync -a --delete \
    --exclude '.venv/' \
    --exclude '.env' \
    "$SOURCE_DIR/" "$APP_DIR/"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f "$CONFIG_DIR/dashboard.env" ]]; then
  install -m 0600 "$APP_DIR/.env.example" "$CONFIG_DIR/dashboard.env"
  echo "Criado $CONFIG_DIR/dashboard.env. Configure os tokens antes de iniciar o serviço."
fi

if [[ ! -f "$CONFIG_DIR/ip-overrides.json" ]]; then
  printf '{}\n' > "$CONFIG_DIR/ip-overrides.json"
fi
chown root:"$SERVICE_USER" "$CONFIG_DIR/ip-overrides.json"
chmod 0640 "$CONFIG_DIR/ip-overrides.json"

install -m 0644 "$APP_DIR/deploy/proxmox-pbs-dashboard.service" /etc/systemd/system/proxmox-pbs-dashboard.service
systemctl daemon-reload
systemctl enable proxmox-pbs-dashboard.service

echo
printf 'Próximos passos:\n'
printf '1. Edite %s/dashboard.env\n' "$CONFIG_DIR"
printf '2. Execute: systemctl restart proxmox-pbs-dashboard\n'
printf '3. Consulte: systemctl status proxmox-pbs-dashboard\n'
printf '4. Acesse: http://IP-DO-CONTAINER:8080\n'
