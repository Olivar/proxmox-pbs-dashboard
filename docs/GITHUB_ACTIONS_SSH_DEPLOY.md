# Deploy automático com GitHub Actions e SSH

O workflow `.github/workflows/deploy-main.yml` conecta ao servidor após cada `push` na branch `main` e executa:

```bash
sudo -n /opt/proxmox-pbs-dashboard/scripts/update.sh
```

O deploy permanece desativado até a variável de repositório `ENABLE_SSH_DEPLOY` receber o valor `true`.

## 1. Criar usuário de deploy no servidor

```bash
sudo useradd --create-home --shell /bin/bash github-deploy
sudo install -d -m 0700 -o github-deploy -g github-deploy /home/github-deploy/.ssh
```

## 2. Criar chave SSH dedicada

Em uma máquina administrativa:

```bash
ssh-keygen \
  -t ed25519 \
  -f ./proxmox-dashboard-deploy \
  -C github-actions-proxmox-dashboard \
  -N ''
```

Isso cria:

- `proxmox-dashboard-deploy`: chave privada para o secret do GitHub;
- `proxmox-dashboard-deploy.pub`: chave pública para o servidor.

## 3. Autorizar a chave no servidor

Copie o conteúdo da chave pública e grave no servidor. A opção `restrict` bloqueia encaminhamento de portas, agente, X11 e terminal. O comando forçado limita a chave ao atualizador do dashboard.

```bash
PUBLIC_KEY=$(cat proxmox-dashboard-deploy.pub)

printf 'restrict,command="sudo -n /opt/proxmox-pbs-dashboard/scripts/update.sh" %s\n' "$PUBLIC_KEY" \
  | sudo tee /home/github-deploy/.ssh/authorized_keys >/dev/null

sudo chown github-deploy:github-deploy /home/github-deploy/.ssh/authorized_keys
sudo chmod 0600 /home/github-deploy/.ssh/authorized_keys
```

## 4. Liberar somente o atualizador no sudo

```bash
sudo tee /etc/sudoers.d/proxmox-pbs-dashboard-deploy >/dev/null <<'EOF'
github-deploy ALL=(root) NOPASSWD: /opt/proxmox-pbs-dashboard/scripts/update.sh
EOF

sudo chmod 0440 /etc/sudoers.d/proxmox-pbs-dashboard-deploy
sudo visudo -cf /etc/sudoers.d/proxmox-pbs-dashboard-deploy
```

Teste:

```bash
sudo -u github-deploy sudo -n /opt/proxmox-pbs-dashboard/scripts/update.sh
```

## 5. Obter a chave pública do servidor SSH

Execute de uma rede confiável. Substitua host e porta:

```bash
ssh-keyscan -H -p 22 IP_OU_DNS_DO_SERVIDOR
```

Guarde a linha completa retornada. Ela será usada no secret `DEPLOY_KNOWN_HOSTS`.

## 6. Cadastrar secrets no GitHub

No repositório, abra:

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

Crie:

| Secret | Conteúdo |
|---|---|
| `DEPLOY_HOST` | IP ou DNS acessível pelo GitHub Actions |
| `DEPLOY_PORT` | Porta SSH, normalmente `22` |
| `DEPLOY_USER` | `github-deploy` |
| `DEPLOY_SSH_PRIVATE_KEY` | Conteúdo completo de `proxmox-dashboard-deploy` |
| `DEPLOY_KNOWN_HOSTS` | Saída completa do `ssh-keyscan` |

A chave privada deve começar com:

```text
-----BEGIN OPENSSH PRIVATE KEY-----
```

## 7. Ativar o deploy

Em:

`Settings` → `Secrets and variables` → `Actions` → `Variables`

Crie a variável:

```text
ENABLE_SSH_DEPLOY=true
```

A partir desse momento, cada atualização da `main` executará o deploy.

## 8. Testar sem novo commit

Abra:

`Actions` → `Deploy main via SSH` → `Run workflow`

## Diagnóstico

No GitHub, veja o log do workflow em `Actions`.

No servidor:

```bash
sudo journalctl -u proxmox-pbs-dashboard -n 100 --no-pager -l
sudo systemctl status proxmox-pbs-dashboard --no-pager -l
cd /opt/proxmox-pbs-dashboard && git log -1 --oneline
```

## Requisitos de rede

O runner do GitHub precisa alcançar a porta SSH do servidor. Se o servidor estiver apenas em uma rede privada, use uma VPN acessível pelo runner, um túnel controlado ou um runner autohospedado. Não exponha SSH à internet sem firewall, autenticação por chave e restrições adequadas.
