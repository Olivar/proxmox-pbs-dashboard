# Registro de mudanças

Este arquivo registra as funcionalidades, correções e decisões relevantes do dashboard. Toda implementação nova deve incluir uma entrada aqui, com a versão, data e uma descrição objetiva do que mudou.

## [0.2.5] — 2026-08-05

### Console noVNC

- Ajustada a área do console para ocupar apenas o espaço disponível da janela e evitar a barra de rolagem lateral/vertical após a conexão.

## [0.2.4] — 2026-08-05

### Console noVNC

- Mantido o formulário inicial de autenticação e ocultado automaticamente após a conexão do console, deixando a tela noVNC e os atalhos em destaque.

## [0.2.3] — 2026-08-05

### Console noVNC

- Após a autenticação, o formulário grande é ocultado e os atalhos ficam disponíveis no cabeçalho do modal.

### Atualização automática

- Adicionado um timer systemd que consulta `origin/main` a cada 5 minutos.
- O servidor executa `scripts/update.sh` somente quando existe um commit novo em avanço direto.
- A atualização automática é ignorada quando o repositório está fora da branch `main`, contém alterações locais ou divergiu do remoto.
- Removido o workflow de deploy por SSH e sua necessidade de secrets, chave SSH e porta pública.
- Os scripts de instalação e atualização passam a instalar e ativar o timer automaticamente.

## [0.2.2] — 2026-08-05

### Console noVNC

- Adicionada uma barra de atalhos com **Ctrl + Alt + Del**, necessário para desbloquear a tela de login do Windows.
- Adicionado o botão **Focar teclado** para direcionar a digitação para a tela da VM.
- Os atalhos são enviados pelo noVNC ao console remoto.

## [0.2.1] — 2026-08-05

### Correção do console

- O ticket VNC temporário retornado pelo `vncproxy` agora é fornecido ao noVNC como credencial do protocolo, corrigindo a solicitação adicional de senha após a autenticação no PVE.

## [0.2.0] — 2026-08-05

### Interface

- Adicionado ícone de tela na coluna **Ações** para abrir o console noVNC por meio do dashboard, com autenticação temporária no PVE e proxy WebSocket pelo servidor público.
- Incluído o cliente noVNC localmente, sem dependência de acesso externo do navegador ao PVE.

## [0.1.0] — 2026-08-04

### Interface

- Exibição da versão `0.1.0` no canto superior esquerdo do dashboard.
- Escala visual de uso de CPU e RAM em três faixas: verde até 59%, amarelo de 60% a 79% e vermelho a partir de 80%, com barras de progresso.
- Indicadores PVE na seção “Fontes” tornados clicáveis.
- Inclusão de mini dashboard por PVE com CPU, memória, disco, nós online, uptime, carga e status individual dos nós.

### Backend

- Nova coleta das métricas dos nós pelo endpoint `/api2/json/nodes` do Proxmox VE.
- Novo endpoint autenticado `GET /api/pve/{pve_id}/summary` para o resumo de recursos.
- Agregação de CPU, memória e disco para instalações PVE com mais de um nó.

### Operação e validação

- A aplicação de desenvolvimento passou a ser executada em `0.0.0.0:8080` para acesso pela rede local.
- Adicionado teste automatizado para a coleta do resumo dos nós PVE.
- Código publicado na instalação Linux existente, com serviço `proxmox-pbs-dashboard.service` reiniciado e validado em produção.
- Configuração local sincronizada para `/etc/proxmox-pbs-dashboard/dashboard.env`, com backup da configuração anterior e preservação das permissões do serviço.
- Arquivos estáticos do dashboard passaram a usar versionamento e cache do service worker renovado para evitar diferenças entre ambientes após deploy.

## Correção adicional — 2026-08-04

- Operações de ligar, desligar e reiniciar agora respondem imediatamente após o Proxmox aceitar a ação, evitando que o modal fique preso aguardando a atualização completa do dashboard.
- Versão e status de cache do cabeçalho agora são exibidos na mesma linha, com separador visual.

## Correção de layout — 2026-08-04

- Dashboard principal passou a ocupar toda a largura disponível, removendo as margens laterais causadas pelo limite de 1680px.
- Configurações agora permitem múltiplas instâncias PBS, com cards equivalentes aos PVEs, persistência em `PBS_INSTANCES_JSON`, fallback para o PBS único legado e agregação dos backups entre os PBS configurados.
- Serviço systemd passou a permitir escrita controlada em `/etc/proxmox-pbs-dashboard`, necessária para salvar configurações e criar backups pelo menu Configurações.

### Correção de diagnóstico PBS

- Quando a consulta ao PBS falha, os itens passam a ser marcados como “Desconhecido” em vez de “Sem backup”, evitando confundir indisponibilidade de rede com ausência de snapshots.
- Erros de validação do cadastro de PVE/PBS agora exibem os campos rejeitados no formulário de configurações.
- O botão de salvar configurações agora reinicia automaticamente o serviço após gravar o `dashboard.env`.

## Como registrar próximas mudanças

1. Atualize `APP_VERSION` em `app/version.py` e a versão correspondente em `pyproject.toml` quando houver uma nova versão.
2. Adicione uma seção neste arquivo com a data da alteração.
3. Registre as mudanças separadas por interface, backend, configuração, testes e operação quando aplicável.
4. Atualize também o README quando a mudança alterar instalação, configuração ou uso da aplicação.
