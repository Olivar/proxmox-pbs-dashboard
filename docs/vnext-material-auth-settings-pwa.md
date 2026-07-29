# Próxima versão — Material UI, autenticação, configurações e PWA

Branch: `agent/material-auth-settings-pwa`

## Tabela de monitoramento

Ordem final das colunas:

1. Status
2. ID
3. Nome
4. Ações
5. IP
6. Uso
7. Uptime
8. PVE

Alterações:

- remover coluna `Nó`;
- remover coluna `Tipo`;
- renomear `Estado` para `Status`;
- manter `Uso` no formato `CPU: 30% / RAM: 12%`;
- usar somente ícones na coluna `Ações`:
  - Play: iniciar;
  - Stop: desligamento convencional;
  - Restart: reiniciar;
- cada botão deve ter `title`, `aria-label` e estado desabilitado adequado;
- nenhuma ação de parada forçada.

## Tema

Modos disponíveis:

- Claro;
- Escuro;
- Sistema.

Requisitos:

- preferência salva no navegador;
- modo Sistema acompanha `prefers-color-scheme`;
- alteração imediata, sem recarregar a página;
- opção também disponível na página de configurações.

## Autenticação do dashboard

- todas as páginas e APIs administrativas exigem login;
- `/health`, arquivos estáticos, manifesto e página de login podem permanecer públicos;
- sessão por cookie `HttpOnly`, `SameSite=Strict` e `Secure` quando HTTPS;
- proteção contra CSRF nas operações de escrita;
- senha armazenada somente como hash forte;
- nenhuma senha, ticket ou token em logs;
- logout invalida a sessão;
- limite de tentativas e atraso progressivo contra força bruta;
- configuração inicial do administrador via ambiente ou comando de bootstrap.

## Página de configurações

Permitir alterar:

### Aplicação

- título do dashboard;
- intervalo de atualização;
- tema padrão;
- densidade da interface;
- nome curto do WebApp;

### Conectividade

- configurações não secretas do PBS;
- arquivo/lista das instâncias PVE;
- verificação TLS;
- datastores;

### Segurança

- usuário administrador do dashboard;
- alteração da senha do dashboard;
- duração da sessão.

Regras:

- segredos existentes nunca retornam completos ao navegador;
- campo vazio mantém o segredo atual;
- gravação atômica do arquivo ENV;
- validação antes de salvar;
- backup do ENV antes da alteração;
- informar quando reinício do serviço é necessário;
- não permitir edição arbitrária de caminhos ou variáveis desconhecidas.

## Redesign

Direção visual:

- Material Design;
- interface data-dense;
- barra superior compacta;
- navegação clara entre Monitoramento, Backups e Configurações;
- tabelas compactas com cabeçalho fixo;
- ícones consistentes;
- dialogs e formulários acessíveis;
- contraste AA;
- foco de teclado visível;
- suporte completo a mouse, teclado e toque.

## Responsividade

Desktop:

- tabela completa;
- filtros em linha;
- alta densidade.

Tablet:

- tabela com rolagem horizontal controlada;
- ações sempre acessíveis.

Celular:

- tabela transformada em cartões densos ou linhas responsivas;
- ações com área de toque mínima adequada;
- navegação inferior ou menu compacto;
- dialogs adaptados à tela inteira.

## Progressive Web App

- `manifest.webmanifest`;
- nome, nome curto, cor de tema e cor de fundo;
- ícones 192×192 e 512×512;
- ícone maskable;
- service worker;
- cache apenas do shell estático;
- dados de monitoramento sempre `network-first` ou `no-store`;
- credenciais e respostas administrativas nunca armazenadas em cache;
- modo standalone;
- botão ou orientação de instalação quando suportado;
- atualização segura do service worker.

## Critérios de aceite

- usuário não autenticado é redirecionado para login;
- usuário autenticado acessa Monitoramento, Backups e Configurações;
- tema Claro, Escuro e Sistema funciona e persiste;
- tabela possui exatamente as oito colunas definidas;
- ações usam somente ícones e mantêm confirmação;
- configurações podem ser validadas e salvas sem expor segredos;
- aplicação funciona em desktop, tablet e celular;
- WebApp pode ser instalado em navegadores compatíveis;
- service worker não guarda APIs, senhas, tickets ou tokens;
- testes cobrem autenticação, autorização, CSRF, configuração, tema e rotas administrativas.
