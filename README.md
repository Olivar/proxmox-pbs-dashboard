# Proxmox PBS Dashboard

Dashboard web read-only para visualizar máquinas virtuais do Proxmox VE e o último backup disponível no Proxmox Backup Server.

## Escopo

### Máquinas virtuais

- Nome
- VMID
- IP
- Uptime
- Estado: ligado ou desligado
- Nó PVE

### Backups PBS

- Nome da VM
- VMID
- Último backup
- Status: sucesso, falhou, executando, sem backup ou desconhecido
- Datastore

A interface não possui autenticação. Restrinja o acesso por firewall, VLAN ou VPN.

## Requisitos

- Ubuntu 22.04, 24.04 ou superior
- Python 3.11+
- Acesso HTTPS do container ao PVE e PBS
- QEMU Guest Agent instalado nas VMs para descoberta automática do IP
- Token PVE read-only
- Token PBS read-only

## Instalação nativa no Ubuntu

Clone o repositório no container Ubuntu e execute:

```bash
cd proxmox-pbs-dashboard
sudo bash scripts/install.sh
sudo nano /etc/proxmox-pbs-dashboard/dashboard.env
sudo systemctl restart proxmox-pbs-dashboard
sudo systemctl status proxmox-pbs-dashboard
```

Acesse:

```text
http://IP-DO-CONTAINER:8080
```

## Configuração

Arquivo principal:

```text
/etc/proxmox-pbs-dashboard/dashboard.env
```

Variáveis essenciais:

```env
PVE_URL=https://pve01:8006
PVE_TOKEN_ID=dashboard@pve!readonly
PVE_TOKEN_SECRET=TOKEN
PVE_VERIFY_TLS=false

PBS_URL=https://pbs01:8007
PBS_TOKEN_ID=dashboard@pbs!readonly
PBS_TOKEN_SECRET=TOKEN
PBS_DATASTORES=backup-prod,backup-secundario
PBS_VERIFY_TLS=false
```

Use `PVE_VERIFY_TLS=true` e `PBS_VERIFY_TLS=true` quando os certificados forem confiáveis para o Ubuntu.

## Permissões PVE

Crie um usuário/token com a role `PVEAuditor` no caminho `/`. O usuário e o token precisam das ACLs quando o token usa separação de privilégios.

A aplicação consulta:

- `/api2/json/cluster/resources?type=vm`
- `/api2/json/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces`

## Permissões PBS

Conceda ao usuário e ao token:

- `DatastoreAudit` em `/datastore/{datastore}`
- `Audit` em `/` para consultar tarefas

A aplicação consulta:

- `/api2/json/admin/datastore/{datastore}/snapshots`
- `/api2/json/nodes/{node}/tasks`

Se o token não puder listar tarefas, os snapshots continuam sendo exibidos como sucesso, mas falhas de tentativas posteriores podem não ser detectadas.

## Resolução do IP

Ordem:

1. QEMU Guest Agent
2. Override estático
3. Último IP obtido e salvo em cache
4. `Não disponível`

Overrides:

```bash
sudo nano /etc/proxmox-pbs-dashboard/ip-overrides.json
```

```json
{
  "100": "192.168.10.20",
  "101": "192.168.10.21"
}
```

## Status do backup

- Snapshot mais recente localizado no PBS: `Sucesso`
- Tarefa PBS mais recente, posterior ao snapshot e com erro: `Falhou`
- Tarefa ainda sem conclusão: `Executando`
- Sem snapshot: `Sem backup`
- Tarefa concluída sem resultado reconhecido: `Desconhecido`

O campo “Último backup” representa o último snapshot válido. Portanto, uma tentativa mais recente pode aparecer como falha enquanto a data continua mostrando o último backup bem-sucedido.

## Operação

```bash
sudo systemctl restart proxmox-pbs-dashboard
sudo journalctl -u proxmox-pbs-dashboard -f
curl http://127.0.0.1:8080/health
```

Atualização do código após `git pull`:

```bash
sudo bash /opt/proxmox-pbs-dashboard/scripts/update.sh
```

## Nginx opcional

Para publicar na porta 80:

```bash
sudo apt install nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/proxmox-pbs-dashboard
sudo ln -s /etc/nginx/sites-available/proxmox-pbs-dashboard /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Nesse cenário, altere `LISTEN_HOST=127.0.0.1` no arquivo de ambiente.

## Desenvolvimento

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
pytest
uvicorn app.main:app --reload
```
