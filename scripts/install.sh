#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo ./scripts/install.sh" >&2
  exit 1
fi

SOURCE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
APP_DIR=/opt/proxmox-pbs-dashboard
CONFIG_DIR=/etc/proxmox-pbs-dashboard
STATE_DIR=/var/lib/proxmox-pbs-dashboard
SERVICE_USER=proxmox-dashboard

apt-get update
apt-get install -y python3 python3-venv python3-pip ca-certificates git rsync openssl

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
  install -m 0660 "$APP_DIR/.env.example" "$CONFIG_DIR/dashboard.env"
  DASH_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
  SESSION_SECRET=$(openssl rand -hex 32)
  sed -i "0,/^DASHBOARD_PASSWORD=SUBSTITUA$/s//DASHBOARD_PASSWORD=${DASH_PASSWORD}/" "$CONFIG_DIR/dashboard.env"
  sed -i "0,/^DASHBOARD_SESSION_SECRET=SUBSTITUA$/s//DASHBOARD_SESSION_SECRET=${SESSION_SECRET}/" "$CONFIG_DIR/dashboard.env"
  echo "Criado $CONFIG_DIR/dashboard.env"
  echo "Usuário inicial: admin"
  echo "Senha inicial: $DASH_PASSWORD"
  echo "Guarde esta senha. Ela não será exibida novamente."
fi
chown root:"$SERVICE_USER" "$CONFIG_DIR/dashboard.env"
chmod 0660 "$CONFIG_DIR/dashboard.env"

if [[ ! -f "$CONFIG_DIR/pve-instances.json" && -f "$APP_DIR/config/pve-instances.example.json" ]]; then
  install -m 0640 "$APP_DIR/config/pve-instances.example.json" "$CONFIG_DIR/pve-instances.json"
fi
if [[ -f "$CONFIG_DIR/pve-instances.json" ]]; then
  chown root:"$SERVICE_USER" "$CONFIG_DIR/pve-instances.json"
  chmod 0640 "$CONFIG_DIR/pve-instances.json"
fi

if [[ ! -f "$CONFIG_DIR/ip-overrides.json" ]]; then
  printf '{}\n' > "$CONFIG_DIR/ip-overrides.json"
fi
chown root:"$SERVICE_USER" "$CONFIG_DIR/ip-overrides.json"
chmod 0640 "$CONFIG_DIR/ip-overrides.json"

if [[ ! -f "$STATE_DIR/notes.json" ]]; then
  printf '{}\n' > "$STATE_DIR/notes.json"
fi
chown "$SERVICE_USER":"$SERVICE_USER" "$STATE_DIR/notes.json"
chmod 0640 "$STATE_DIR/notes.json"

install -m 0644 "$APP_DIR/deploy/proxmox-pbs-dashboard.service" /etc/systemd/system/proxmox-pbs-dashboard.service
systemctl daemon-reload
systemctl enable proxmox-pbs-dashboard.service

printf '\nPróximos passos:\n'
printf '1. Revise %s/dashboard.env\n' "$CONFIG_DIR"
printf '2. Edite %s/pve-instances.json\n' "$CONFIG_DIR"
printf '3. Execute: systemctl restart proxmox-pbs-dashboard\n'
printf '4. Acesse: http://IP-DO-CONTAINER:8080\n'
