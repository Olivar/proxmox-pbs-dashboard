# Proxmox PBS Dashboard

Dashboard web read-only para visualizar máquinas virtuais de uma ou mais instâncias independentes do Proxmox VE e correlacionar o último backup disponível no Proxmox Backup Server.

## Escopo

### Máquinas virtuais

- Origem PVE
- Nome
- VMID
- IP
- Uptime
- Estado: ligado ou desligado
- Nó PVE

### Backups PBS

- Origem PVE
- Nome da VM
- VMID
- Último backup
- Status: sucesso, falhou, executando, sem backup ou desconhecido
- Datastore

A interface não possui autenticação. Restrinja o acesso por firewall, VLAN ou VPN.

## Requisitos

- Ubuntu 22.04, 24.04 ou superior
- Python 3.11+
- Acesso HTTPS do container aos PVE e ao PBS
- QEMU Guest Agent instalado nas VMs para descoberta automática do IP
- Um token read-only em cada PVE
- Token PBS read-only
- VMIDs únicos entre os PVE configurados

## Instalação nativa no Ubuntu

```bash
cd proxmox-pbs-dashboard
sudo bash scripts/install.sh
sudo nano /etc/proxmox-pbs-dashboard/dashboard.env
sudo nano /etc/proxmox-pbs-dashboard/pve-instances.json
sudo systemctl restart proxmox-pbs-dashboard
sudo systemctl status proxmox-pbs-dashboard
```

Acesse:

```text
http://IP-DO-CONTAINER:8080
```

## Configuração dos PVE

Arquivo:

```text
/etc/proxmox-pbs-dashboard/pve-instances.json
```

Exemplo para três PVE independentes:

```json
[
  {
    "id": "pve01",
    "name": "PVE Principal",
    "url": "https://10.0.0.11:8006",
    "token_id": "dashboard@pve!readonly",
    "token_secret": "TOKEN_1",
    "verify_tls": false
  },
  {
    "id": "pve02",
    "name": "PVE Secundário",
    "url": "https://10.0.0.12:8006",
    "token_id": "dashboard@pve!readonly",
    "token_secret": "TOKEN_2",
    "verify_tls": false
  },
  {
    "id": "pve03",
    "name": "PVE Terceiro",
    "url": "https://10.0.0.13:8006",
    "token_id": "dashboard@pve!readonly",
    "token_secret": "TOKEN_3",
    "verify_tls": false
  }
]
```

O campo `id` deve ser único. O campo `name` é exibido na interface. Como a correlação com o PBS é feita pelo VMID, os VMIDs devem permanecer únicos entre as instâncias.

A aplicação consulta todos os PVE em paralelo. Se uma instância estiver indisponível, as demais continuam sendo atualizadas e os últimos dados da instância com falha são mantidos em cache, quando disponíveis.

### Compatibilidade com uma única instância

A configuração antiga continua aceita quando `pve-instances.json` não existe:

```env
PVE_URL=https://pve01:8006
PVE_TOKEN_ID=dashboard@pve!readonly
PVE_TOKEN_SECRET=TOKEN
PVE_VERIFY_TLS=false
```

## Configuração do PBS

Arquivo:

```text
/etc/proxmox-pbs-dashboard/dashboard.env
```

Variáveis essenciais:

```env
PVE_INSTANCES_FILE=/etc/proxmox-pbs-dashboard/pve-instances.json

PBS_URL=https://pbs01:8007
PBS_TOKEN_ID=dashboard@pbs!readonly
PBS_TOKEN_SECRET=TOKEN
PBS_DATASTORES=backup-prod,backup-secundario
PBS_VERIFY_TLS=false
```

Use `verify_tls: true` nos PVE e `PBS_VERIFY_TLS=true` quando os certificados forem confiáveis para o Ubuntu.

## Permissões PVE

Em cada PVE, crie um usuário/token com a role `PVEAuditor` no caminho `/`. O usuário e o token precisam das ACLs quando o token usa separação de privilégios.

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
  "201": "192.168.20.21"
}
```

## Status do backup

- Snapshot mais recente localizado no PBS: `Sucesso`
- Tarefa PBS mais recente, posterior ao snapshot e com erro: `Falhou`
- Tarefa ainda sem conclusão: `Executando`
- Sem snapshot: `Sem backup`
- Tarefa concluída sem resultado reconhecido: `Desconhecido`

O campo “Último backup” representa o último snapshot válido. Uma tentativa mais recente pode aparecer como falha enquanto a data continua mostrando o último backup bem-sucedido.

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

## Registro de mudanças

As funcionalidades e decisões implementadas devem ser registradas em [`docs/CHANGELOG.md`](docs/CHANGELOG.md), junto com a versão correspondente.

## Múltiplos PBS

A tela **Configurações** permite adicionar e remover instâncias PBS. Todas são gravadas no campo `PBS_INSTANCES_JSON` do `dashboard.env`:

```json
[
  {
    "id": "pbs01",
    "name": "PBS Principal",
    "url": "https://pbs01:8007",
    "token_id": "dashboard@pbs!readonly",
    "token_secret": "TOKEN_1",
    "datastores": "backup-prod,backup-secundario",
    "node": "localhost",
    "verify_tls": false
  }
]
```

O formato antigo com `PBS_URL`, `PBS_TOKEN_ID`, `PBS_TOKEN_SECRET` e `PBS_DATASTORES` continua aceito quando `PBS_INSTANCES_JSON` não existir.
