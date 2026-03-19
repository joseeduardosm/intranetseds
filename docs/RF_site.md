# Especificação de Requisitos Funcionais (RF) - Intranet

## 1. Objetivo
Este documento consolida os requisitos funcionais (RFs) identificados no sistema Intranet a partir do código-fonte atual.

## 2. Escopo
Abrange os módulos:
- Autenticação e Segurança
- Perfis, Permissões e Usuários
- Notícias
- Ramais e Organograma
- Contratos
- Empresas e Prepostos
- Diário de Bordo
- Reserva de Salas
- Administração e RH
- Folha de Ponto
- Auditoria

## 3. Convenções
- ID: `RF-<MÓDULO><NÚMERO>`
- Prioridade: Alta / Média / Baixa
- Critério de aceite: comportamento verificável
- Rastreabilidade: URL/tela principal

## 4. Requisitos Funcionais

## 4.1 Autenticação e Segurança

| ID | Requisito | Prioridade | Critério de Aceite | Rastreabilidade |
|---|---|---|---|---|
| RF-AUTH01 | O sistema deve permitir login de usuário. | Alta | Dado usuário válido, ao autenticar, o sistema inicia sessão e redireciona para home. | `/login/` |
| RF-AUTH02 | O sistema deve permitir logout de usuário. | Alta | Ao acionar logout, a sessão é encerrada e usuário retorna à home. | `/logout/` |
| RF-AUTH03 | O sistema deve autenticar via AD/LDAP quando configurado. | Alta | Com credenciais válidas no AD, o usuário autentica com sucesso. | backend LDAP |
| RF-AUTH04 | O sistema deve manter fallback para autenticação local Django. | Alta | Se LDAP não autenticar e usuário local existir, autenticação local pode ocorrer. | backend Django |
| RF-AUTH05 | O sistema deve validar CSRF em formulários POST. | Alta | POST sem token válido deve retornar 403 CSRF. | middleware CSRF |
| RF-AUTH06 | O sistema deve restringir hosts permitidos por `ALLOWED_HOSTS`. | Alta | Requisição com host não permitido deve ser rejeitada. | `settings.py` |

## 4.2 Perfis, Permissões e Usuários

| ID | Requisito | Prioridade | Critério de Aceite | Rastreabilidade |
|---|---|---|---|---|
| RF-USR01 | O sistema deve listar usuários para perfil staff. | Alta | Usuário staff acessa listagem; não-staff recebe bloqueio de acesso. | `/usuarios/` |
| RF-USR02 | O sistema deve permitir busca de usuários por login, nome, e-mail e grupo. | Média | Informando termo de busca, a lista deve retornar apenas correspondências. | `/usuarios/?q=` |
| RF-USR03 | O sistema deve permitir criar usuário com senha. | Alta | Ao cadastrar usuário válido, registro é criado e senha definida. | `/usuarios/novo/` |
| RF-USR04 | O sistema deve permitir editar usuário e opcionalmente alterar senha. | Alta | Edição salva dados e, se senha preenchida, atualiza credencial. | `/usuarios/<id>/editar/` |
| RF-USR05 | O sistema deve permitir excluir usuário para perfil staff. | Alta | Ao confirmar exclusão, usuário é removido. | `/usuarios/<id>/excluir/` |
| RF-USR06 | O sistema deve permitir atribuir perfis/grupos por módulo e nível. | Alta | Seleção de perfis resulta em associação correta de grupos. | tela de usuário |
| RF-USR07 | O sistema deve criar/atualizar grupos padrão de perfis após migração. | Média | Após `migrate`, grupos definidos em matriz de perfis existem no banco. | `usuarios.apps` |

## 4.3 Notícias

| ID | Requisito | Prioridade | Critério de Aceite | Rastreabilidade |
|---|---|---|---|---|
| RF-NOT01 | O sistema deve listar notícias na página inicial. | Alta | Home exibe notícias ordenadas por data de publicação mais recente. | `/` |
| RF-NOT02 | O sistema deve exibir detalhes de notícia. | Alta | Ao acessar notícia, título/texto/imagem são exibidos. | `/noticias/<id>/` |
| RF-NOT03 | O sistema deve permitir criação de notícia com permissão adequada. | Alta | Usuário com `add_noticia` cria notícia com sucesso. | `/noticias/nova/` |
| RF-NOT04 | O sistema deve permitir edição de notícia com permissão adequada. | Alta | Usuário com `change_noticia` edita notícia com sucesso. | `/noticias/<id>/editar/` |
| RF-NOT05 | O sistema deve permitir exclusão de notícia com permissão adequada. | Alta | Usuário com `delete_noticia` remove notícia. | `/noticias/<id>/excluir/` |
| RF-NOT06 | O sistema deve exibir atalhos de serviços ativos na home. | Média | Apenas atalhos ativos aparecem na home. | home |

## 4.4 Ramais e Organograma

| ID | Requisito | Prioridade | Critério de Aceite | Rastreabilidade |
|---|---|---|---|---|
| RF-RAM01 | O sistema deve listar ramais com paginação. | Alta | Lista apresenta até 12 registros por página. | `/ramais/` |
| RF-RAM02 | O sistema deve permitir busca textual de ramais. | Alta | Busca filtra por nome, usuário, e-mail, cargo, setor e ramal. | `/ramais/?q=` |
| RF-RAM03 | O sistema deve exibir detalhe do ramal. | Alta | Tela mostra dados completos do perfil. | `/ramais/<id>/` |
| RF-RAM04 | O sistema deve permitir criar ramal com permissão `add_pessoaramal`. | Alta | Usuário autorizado cria novo registro de ramal. | `/ramais/novo/` |
| RF-RAM05 | O sistema deve permitir edição de ramal por staff/permissão ou próprio titular. | Alta | Usuário comum só edita seu próprio perfil; staff/permissão edita qualquer um. | `/ramais/<id>/editar/` |
| RF-RAM06 | O sistema deve permitir excluir ramal com permissão `delete_pessoaramal`. | Alta | Exclusão confirmada remove registro. | `/ramais/<id>/excluir/` |
| RF-RAM07 | O sistema deve exibir organograma hierárquico. | Média | Organograma mostra árvore superior-subordinados. | `/ramais/organograma/` |
| RF-RAM08 | O sistema deve sincronizar e-mail entre usuário e perfil de ramal. | Média | Alteração de e-mail no perfil reflete no usuário associado. | model `PessoaRamal` |

## 4.5 Contratos

| ID | Requisito | Prioridade | Critério de Aceite | Rastreabilidade |
|---|---|---|---|---|
| RF-CON01 | O sistema deve listar contratos para usuários com permissão de visualização. | Alta | Lista exibe contratos quando usuário possui `view_contrato`. | `/contratos/` |
| RF-CON02 | O sistema deve calcular prazo restante de contrato. | Alta | Lista mostra meses/dias para fim quando data de término existe. | listagem de contratos |
| RF-CON03 | O sistema deve classificar visualmente contratos por criticidade de prazo. | Média | Contratos recebem classe de alerta conforme proximidade do vencimento. | listagem de contratos |
| RF-CON04 | O sistema deve somar o valor total de contratos na listagem. | Média | Total agregado é exibido na tela. | listagem de contratos |
| RF-CON05 | O sistema deve permitir CRUD de contratos conforme permissões. | Alta | Operações respeitam `view/add/change/delete`. | `/contratos/*` |
| RF-CON06 | O sistema deve calcular `data_fim` automaticamente quando possível. | Média | Com `data_inicial + vigencia`, data final é preenchida automaticamente. | form/model contrato |
| RF-CON07 | O sistema deve criar bloco no Diário de Bordo ao entrar em “Em Contratação”. | Alta | Ao salvar contrato nesse status, bloco é criado se não existir. | model `Contrato.save()` |
| RF-CON08 | O sistema deve registrar incremento automático no bloco criado por contrato. | Média | Incremento inicial é adicionado ao bloco automático. | model `Contrato.save()` |

## 4.6 Empresas e Prepostos

| ID | Requisito | Prioridade | Critério de Aceite | Rastreabilidade |
|---|---|---|---|---|
| RF-EMP01 | O sistema deve permitir CRUD de empresas para usuário autenticado. | Alta | Usuário logado acessa e executa operações em empresas. | `/empresas/*` |
| RF-EMP02 | O sistema deve exibir prepostos e contratos no detalhe da empresa. | Média | Tela de detalhe mostra relacionamentos da empresa. | `/empresas/<id>/` |
| RF-PRE01 | O sistema deve permitir CRUD de prepostos para usuário autenticado. | Alta | Usuário logado acessa e executa operações em prepostos. | `/prepostos/*` |
| RF-PRE02 | O sistema deve vincular preposto a uma empresa. | Alta | Cadastro/edição exige seleção de empresa válida. | form preposto |

## 4.7 Diário de Bordo

| ID | Requisito | Prioridade | Critério de Aceite | Rastreabilidade |
|---|---|---|---|---|
| RF-DB01 | O sistema deve listar blocos com controle por participante (exceto superuser). | Alta | Usuário comum visualiza apenas blocos em que participa. | `/diario-de-bordo/` |
| RF-DB02 | O sistema deve filtrar blocos por status. | Alta | Filtros retornam blocos conforme status selecionado. | `/diario-de-bordo/?status=` |
| RF-DB03 | O sistema deve permitir busca textual em blocos. | Alta | Busca por nome, descrição e status deve funcionar. | `/diario-de-bordo/?q=` |
| RF-DB04 | O sistema deve exibir alerta visual por dias sem atualização. | Média | Blocos recebem classe de alerta conforme regra de dias. | lista/relatórios |
| RF-DB05 | O sistema deve alternar visualização card/tabela da listagem. | Baixa | Toggle muda modo de exibição preservando filtros. | listagem de blocos |
| RF-DB06 | O sistema deve exibir feed das últimas atualizações de incrementos. | Média | Feed mostra até 5 atualizações mais recentes. | listagem de blocos |
| RF-DB07 | O sistema deve gerar relatório de blocos (completo, executivo e diário). | Alta | Relatórios respondem ao tipo selecionado e filtros correntes. | `/diario-de-bordo/relatorio/` |
| RF-DB08 | O sistema deve permitir filtrar relatório por legenda de alerta. | Média | Relatório apresenta apenas blocos da legenda escolhida. | relatório |
| RF-DB09 | O sistema deve exibir detalhe do bloco com paginação de incrementos. | Alta | Detalhe mostra incrementos paginados (6 por página). | `/diario-de-bordo/<id>/` |
| RF-DB10 | O sistema deve ordenar incrementos por data asc/desc no detalhe. | Média | Troca de ordem reflete na lista de incrementos. | detalhe do bloco |
| RF-DB11 | O sistema deve registrar leitura de bloco ao abrir detalhe/relatório detalhe. | Média | Campo de leitura do usuário é atualizado para último incremento. | detalhe/relatório detalhe |
| RF-DB12 | O sistema deve permitir navegação para bloco anterior/próximo no contexto filtrado. | Baixa | Botões navegam respeitando filtro ativo. | detalhe do bloco |
| RF-DB13 | O sistema deve permitir criar bloco com permissão `add_blocotrabalho`. | Alta | Usuário autorizado cria bloco com sucesso. | `/diario-de-bordo/novo/` |
| RF-DB14 | O sistema deve incluir criador como participante automático do bloco. | Alta | Após criação, usuário criador consta na lista de participantes. | create bloco |
| RF-DB15 | O sistema deve registrar incremento de criação de bloco automaticamente. | Média | Ao criar bloco, incremento inicial é persistido. | create bloco |
| RF-DB16 | O sistema deve registrar incremento quando participantes forem adicionados. | Média | Participante novo gera incremento automático no histórico. | update bloco |
| RF-DB17 | O sistema deve permitir editar/excluir bloco conforme permissões e escopo. | Alta | Operações bloqueadas para não participantes não superuser. | `/diario-de-bordo/<id>/editar|excluir/` |
| RF-DB18 | O sistema deve permitir criar incremento com permissão `add_incremento`. | Alta | Usuário autorizado adiciona incremento com texto/arquivo/imagem. | `/diario-de-bordo/<id>/incrementos/novo/` |
| RF-DB19 | O sistema deve alterar status de bloco `NOVO` para `EM_ANDAMENTO` no primeiro incremento. | Alta | Ao incluir incremento em bloco novo, status muda automaticamente. | create incremento |
| RF-DB20 | O sistema deve permitir editar/excluir incremento conforme permissões e escopo. | Alta | Não participante não superuser não pode alterar incremento do bloco. | `/diario-de-bordo/incrementos/<id>/*` |

## 4.8 Reserva de Salas

| ID | Requisito | Prioridade | Critério de Aceite | Rastreabilidade |
|---|---|---|---|---|
| RF-SAL01 | O sistema deve listar salas disponíveis. | Alta | Lista retorna todas as salas cadastradas. | `/reserva-salas/` |
| RF-SAL02 | O sistema deve disponibilizar dados de reservas para visualização em calendário/timeline. | Média | Tela de salas contém payload com início/fim/sala/evento/solicitante. | lista de salas |
| RF-SAL03 | O sistema deve exibir detalhe da sala com reservas futuras paginadas. | Média | Detalhe exibe apenas reservas com fim >= agora, 6 por página. | `/reserva-salas/<id>/` |
| RF-SAL04 | O sistema deve permitir CRUD de salas com permissões específicas. | Alta | Operações respeitam `add/change/delete_sala`. | `/reserva-salas/nova|<id>/editar|excluir/` |
| RF-RES01 | O sistema deve listar reservas. | Alta | Lista exibe registros de reservas. | `/reserva-salas/reservas/` |
| RF-RES02 | O sistema deve exibir detalhe de reserva. | Alta | Detalhe mostra dados da reserva e do responsável pelo registro. | `/reserva-salas/reservas/<id>/` |
| RF-RES03 | O sistema deve permitir criação de reserva para usuário autenticado. | Alta | Usuário logado cria reserva válida. | `/reserva-salas/reservas/nova/` |
| RF-RES04 | O sistema deve permitir reservas recorrentes (diária, semanal, quinzenal, mensal). | Média | Ao informar recorrência + data fim, sistema cria múltiplas ocorrências. | form de reserva |
| RF-RES05 | O sistema deve criar série de reservas com identificador único (`serie_id`). | Média | Reservas recorrentes ficam vinculadas por mesmo `serie_id`. | create reserva |
| RF-RES06 | O sistema deve permitir edição por dono, staff ou permissão de alteração. | Alta | Usuário sem autorização não edita reserva de terceiros. | update reserva |
| RF-RES07 | O sistema deve permitir aplicar edição em uma ocorrência ou série inteira. | Média | Seleção de escopo altera apenas item atual ou todos da série. | update reserva |
| RF-RES08 | O sistema deve permitir exclusão por dono, staff ou permissão de exclusão. | Alta | Usuário sem autorização não exclui reserva de terceiros. | delete reserva |
| RF-RES09 | O sistema deve permitir excluir uma ocorrência ou série inteira. | Média | Seleção de escopo remove item atual ou todas ocorrências da série. | delete reserva |
| RF-RES10 | O sistema deve validar conflitos de horário para mesma sala/data. | Alta | Em conflito, formulário deve bloquear salvamento com erro. | `ReservaForm.clean()` |
| RF-RES11 | O sistema deve validar capacidade da sala contra quantidade de pessoas. | Alta | Se exceder capacidade, formulário deve apresentar erro. | `ReservaForm.clean()` |
| RF-RES12 | O sistema deve validar disponibilidade de recursos solicitados na sala. | Alta | Recurso não existente deve gerar erro de validação. | `ReservaForm.clean()` |
| RF-RES13 | O sistema deve validar intervalo de horário (fim > início). | Alta | Horário inválido deve gerar erro no formulário. | `ReservaForm.clean()` |

## 4.9 Administração e RH

| ID | Requisito | Prioridade | Critério de Aceite | Rastreabilidade |
|---|---|---|---|---|
| RF-ADM01 | O sistema deve exibir painel de configurações com cartões por permissão. | Média | Cards exibidos devem refletir permissões do usuário logado. | `/administracao/configuracoes/` |
| RF-ADM02 | O sistema deve restringir configuração AD para superuser. | Alta | Não-superuser não acessa tela de configuração AD. | `/administracao/configuracoes/ad/` |
| RF-ADM03 | O sistema deve permitir salvar configuração AD. | Alta | Formulário válido persiste parâmetros de conexão AD. | config AD |
| RF-ADM04 | O sistema deve permitir testar conexão com AD. | Alta | Ação de teste retorna feedback de sucesso/erro. | config AD |
| RF-ADM05 | O sistema deve permitir sincronizar usuários do AD com base local. | Alta | Ação de sincronização informa totais criados/atualizados/ignorados. | config AD |
| RF-ADM06 | O sistema deve permitir CRUD de atalhos de serviço para perfis autorizados. | Média | Usuário autorizado lista/cria/edita/exclui atalhos. | `/administracao/atalhos/*` |
| RF-ADM07 | O sistema deve validar URL de atalho com esquema HTTP/HTTPS. | Alta | URL inválida deve bloquear salvamento do atalho. | model `AtalhoServico` |
| RF-ADM08 | O sistema deve validar extensão de imagem do atalho (png/jpg/jpeg). | Média | Arquivo com extensão não permitida deve ser rejeitado. | model `AtalhoServico` |
| RF-RH01 | O sistema deve restringir funcionalidades RH a perfis autorizados. | Alta | Usuário sem permissão RH não acessa telas de RH. | `/administracao/rh/` e `/folha-ponto/*` |
| RF-RH02 | O sistema deve permitir upload/atualização do brasão institucional. | Média | Upload válido atualiza brasão exibido na folha de ponto. | `/folha-ponto/brasao/` |

## 4.10 Folha de Ponto

| ID | Requisito | Prioridade | Critério de Aceite | Rastreabilidade |
|---|---|---|---|---|
| RF-FOL01 | O sistema deve exibir home de Folha de Ponto para usuário autenticado. | Alta | Usuário logado acessa tela com opções de mês. | `/folha-ponto/` |
| RF-FOL02 | O sistema deve oferecer seleção de mês (anterior, atual, próximo). | Média | Home apresenta exatamente três opções de referência mensal. | home folha ponto |
| RF-FOL03 | O sistema deve gerar folha imprimível por mês/ano do usuário logado. | Alta | Tela de impressão monta folha conforme mês/ano informados. | `/folha-ponto/imprimir/` |
| RF-FOL04 | O sistema deve marcar automaticamente sábados, domingos, feriados e férias. | Alta | Linhas do mês devem refletir corretamente cada tipo de dia. | impressão folha |
| RF-FOL05 | O sistema deve consolidar eventos de feriados/férias em quadro auxiliar. | Média | Quadro de consolidação lista eventos do mês em ordem cronológica. | impressão folha |
| RF-FOL06 | O sistema deve exibir dados funcionais do servidor na folha. | Média | Jornada, horário, intervalo e regimes aparecem na impressão. | impressão folha |
| RF-FOL07 | O sistema deve permitir CRUD de feriados para perfis RH com permissão específica. | Alta | Operações de feriado respeitam `add/change/delete_feriado`. | `/folha-ponto/feriados/*` |
| RF-FOL08 | O sistema deve permitir CRUD de férias de servidor para perfis RH com permissão específica. | Alta | Operações de férias respeitam `add/change/delete_feriasservidor`. | `/folha-ponto/ferias/*` |
| RF-FOL09 | O sistema deve validar intervalo de férias (`data_fim >= data_inicio`). | Alta | Registro inválido deve ser rejeitado com mensagem de erro. | model `FeriasServidor.clean()` |

## 4.11 Auditoria

| ID | Requisito | Prioridade | Critério de Aceite | Rastreabilidade |
|---|---|---|---|---|
| RF-AUD01 | O sistema deve permitir consulta de auditoria apenas para superuser. | Alta | Usuário não-superuser não acessa tela de auditoria. | `/auditoria/` |
| RF-AUD02 | O sistema deve exigir execução explícita da consulta (`auditar=1`). | Média | Sem parâmetro de execução, lista de logs deve vir vazia. | `/auditoria/` |
| RF-AUD03 | O sistema deve filtrar logs por período parametrizável (valor + unidade). | Alta | Consulta retorna apenas eventos dentro do período informado. | auditoria |
| RF-AUD04 | O sistema deve permitir busca textual nos logs. | Média | Busca filtra por data, usuário, ação, objeto e changes. | auditoria |
| RF-AUD05 | O sistema deve ordenar logs por data, usuário ou ação (asc/desc). | Média | Ordenação escolhida deve refletir no resultado da lista. | auditoria |

## 5. Observações de Qualidade e Governança
- Alguns módulos usam controle por permissão granular e outros apenas por autenticação (`LoginRequiredMixin`).
- Há dependência de configuração de AD para autenticação corporativa.
- Auditoria é transversal e depende da disponibilidade da tabela de logs.
- Requisitos não-funcionais (desempenho, disponibilidade, LGPD, backup, observabilidade) não estão formalizados neste documento.

## 6. Rastreabilidade Técnica (artefatos base)
- Rotas: `intranet/urls.py` e `<app>/urls.py`
- Regras de negócio: `<app>/views.py`, `<app>/models.py`, `<app>/forms.py`
- Permissões/perfis: `usuarios/permissions.py`
- AD/LDAP: `administracao/ldap_backend.py`, `administracao/views.py`
- Auditoria: `auditoria/signals.py`, `auditoria/views.py`, `auditoria/middleware.py`
- Alertas de contexto: `intranet/context_processors.py`

---
Documento gerado a partir do estado atual do código da aplicação.
