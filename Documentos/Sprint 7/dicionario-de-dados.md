# Dicionário de dados

Descrição de todas as tabelas e colunas do banco do ArtConnect (PostgreSQL), incluindo as tabelas criadas na Sprint 7. Os tipos e chaves foram tirados direto do banco (`information_schema`), para o documento não ficar diferente do que está rodando.

**Legenda:** PK = chave primária · FK = chave estrangeira (aponta para outra tabela) · Obrig. = não aceita vazio.

## Resumo das tabelas

| Tabela | Para que serve | Colunas |
|---|---|---|
| `profiles` | Contas de usuário: clientes, artistas e administradores. | 9 |
| `categorias` | Tipos de serviço oferecidos (DJs, Cantores, Chefs...). | 4 |
| `artistas` | Perfil público de quem presta o serviço. | 11 |
| `eventos` | Evento que o cliente está organizando. | 8 |
| `pedidos_orcamento` | Pedido de orçamento enviado aos artistas de uma categoria. | 11 |
| `propostas` | Resposta de um artista a um pedido (proposta, contraproposta ou recusa). | 9 |
| `contratos` | Contratação fechada quando o cliente aceita uma proposta. | 11 |
| `pagamentos` | Movimentação do valor de um contrato (retido, liberado ou reembolsado). | 8 |
| `avaliacoes` | Nota e comentário do cliente depois do evento concluído. | 8 |
| `mensagens` | Mensagens trocadas entre cliente e artista. | 7 |
| `chamados_suporte` | Pedidos de ajuda dos usuários à equipe. | 6 |
| `disponibilidade` | Agenda do artista: dias ocupados ou disponíveis. | 6 |
| `tokens_senha` | Tokens de recuperação de senha (só o hash fica salvo). | 6 |
| `favoritos` | Artistas salvos pelo cliente. | 3 |
| `notificacoes` | Avisos que aparecem no sino do topo da página. | 7 |
| `cancelamentos` | Registro de cada cancelamento e do cálculo do reembolso. | 9 |
| `denuncias` | Denúncias de perfis e avaliações para a moderação. | 10 |
| `portfolio` | Links de fotos, vídeos e áudios do artista. | 6 |

## profiles

Contas de usuário: clientes, artistas e administradores.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| username | texto |  | sim | Nome de login (único, minúsculo) |
| senha_hash | texto |  | sim | Senha criptografada (scrypt), nunca a senha em si |
| nome | texto |  | sim | Nome completo |
| email | texto |  | sim | E-mail (único), usado na recuperação de senha |
| telefone | texto |  | não | Telefone de contato |
| cidade | texto |  | não | Cidade do usuário |
| papel | papel_usuario |  | sim | cliente, artista ou admin |
| criado_em | data e hora |  | sim | Data e hora de criação |

## categorias

Tipos de serviço oferecidos (DJs, Cantores, Chefs...).

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | inteiro | PK | sim | Identificador único gerado automaticamente |
| nome | texto |  | sim | Nome exibido |
| slug | texto |  | sim | Nome sem acento usado em links |
| descricao | texto |  | não | Frase curta exibida no card da categoria |

## artistas

Perfil público de quem presta o serviço.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| user_id | UUID | FK → profiles | não | Conta de login do artista (vazio se cadastrado pela equipe) |
| nome_artistico | texto |  | sim | Nome exibido no perfil |
| categoria_id | inteiro | FK → categorias | sim | Categoria do serviço |
| estilo | texto |  | não | Estilo (ex.: Jazz & MPB) |
| cidade | texto |  | sim | Cidade de atuação |
| preco_minimo | numeric(10,2) |  | sim | Cachê inicial em reais |
| descricao | texto |  | não | Texto de apresentação |
| foto_url | texto |  | não | Foto própria (se vazio, usa a foto da categoria) |
| ativo | sim/não |  | sim | FALSE quando o perfil é excluído ou suspenso pela moderação |
| criado_em | data e hora |  | sim | Data e hora de criação |

## eventos

Evento que o cliente está organizando.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| cliente_id | UUID | FK → profiles | sim | Dono do evento |
| tipo | tipo_evento |  | sim | casamento, corporativo, aniversário, formatura ou outro |
| categoria_id | inteiro | FK → categorias | sim | Serviço buscado |
| data_evento | data |  | não | Data do evento |
| localizacao | texto |  | não | Local |
| orcamento | numeric(10,2) |  | não | Orçamento previsto |
| criado_em | data e hora |  | sim | Data e hora de criação |

## pedidos_orcamento

Pedido de orçamento enviado aos artistas de uma categoria.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| evento_id | UUID | FK → eventos | sim | Evento do pedido |
| categoria_id | inteiro | FK → categorias | sim | Categoria que recebe o pedido |
| data_evento | data |  | sim | Data pedida |
| horario_inicio | hora |  | sim | Horário de início |
| duracao_horas | numeric(4,1) |  | sim | Duração em horas |
| estimativa_convidados | inteiro |  | sim | Número de convidados |
| local | texto |  | sim | Endereço do evento |
| observacoes | texto |  | não | Até 600 caracteres |
| status | status_orcamento |  | sim | aberto, com_propostas, fechado ou cancelado |
| criado_em | data e hora |  | sim | Data e hora de criação |

## propostas

Resposta de um artista a um pedido (proposta, contraproposta ou recusa).

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| pedido_id | UUID | FK → pedidos_orcamento | sim | Pedido respondido |
| artista_id | UUID | FK → artistas | sim | Artista que respondeu |
| valor | numeric(10,2) |  | não | Valor proposto (vazio quando o artista recusou) |
| mensagem | texto |  | não | O que está incluso |
| data_sugerida | data |  | não | Nova data, quando é contraproposta |
| horario_sugerido | hora |  | não | Novo horário, quando é contraproposta |
| status | status_proposta |  | sim | enviada, aceita, recusada (pelo cliente) ou declinada (pelo artista) |
| criado_em | data e hora |  | sim | Data e hora de criação |

## contratos

Contratação fechada quando o cliente aceita uma proposta.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| evento_id | UUID | FK → eventos | sim | Evento contratado |
| proposta_id | UUID | FK → propostas | não | Proposta aceita que gerou o contrato |
| cliente_id | UUID | FK → profiles | sim | Quem contratou |
| artista_id | UUID | FK → artistas | sim | Quem foi contratado |
| descricao | texto |  | não | Resumo do serviço |
| data_evento | data |  | sim | Data final (pode ser a da contraproposta) |
| local | texto |  | sim | Local do evento |
| valor_total | numeric(10,2) |  | sim | Valor do contrato |
| status | status_contrato |  | sim | aguardando_pagamento, valor_retido, concluido ou cancelado |
| criado_em | data e hora |  | sim | Data e hora de criação |

## pagamentos

Movimentação do valor de um contrato (retido, liberado ou reembolsado).

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| contrato_id | UUID | FK → contratos | sim | Contrato pago |
| valor | numeric(10,2) |  | sim | Valor da movimentação |
| metodo | texto |  | não | pix ou boleto (simulados) |
| status | status_pagamento |  | sim | pendente, retido, liberado ou reembolsado |
| pago_em | data e hora |  | não | Quando o cliente pagou |
| liberado_em | data e hora |  | não | Quando o valor foi para o artista |
| criado_em | data e hora |  | sim | Data e hora de criação |

## avaliacoes

Nota e comentário do cliente depois do evento concluído.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| contrato_id | UUID | FK → contratos | sim | Contrato avaliado (uma avaliação por contrato) |
| artista_id | UUID | FK → artistas | sim | Artista avaliado |
| cliente_id | UUID | FK → profiles | sim | Quem avaliou |
| nota | inteiro |  | sim | De 1 a 5 |
| comentario | texto |  | não | Até 500 caracteres |
| criado_em | data e hora |  | sim | Data e hora de criação |
| oculta | sim/não |  | sim | TRUE quando a moderação escondeu a avaliação |

## mensagens

Mensagens trocadas entre cliente e artista.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| contrato_id | UUID | FK → contratos | não | Contrato da conversa |
| remetente_id | UUID | FK → profiles | sim | Quem enviou |
| destinatario_id | UUID | FK → profiles | sim | Quem recebe |
| conteudo | texto |  | sim | Texto (até 1000 caracteres pela tela) |
| lida | sim/não |  | sim | TRUE quando o destinatário abriu a conversa |
| enviada_em | data e hora |  | sim | Data e hora do envio |

## chamados_suporte

Pedidos de ajuda dos usuários à equipe.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| user_id | UUID | FK → profiles | sim | Quem abriu o chamado |
| assunto | texto |  | sim | Assunto |
| descricao | texto |  | sim | Descrição do problema |
| status | status_suporte |  | sim | aberto, em_andamento ou resolvido |
| criado_em | data e hora |  | sim | Data e hora de criação |

## disponibilidade

Agenda do artista: dias ocupados ou disponíveis.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| artista_id | UUID | FK → artistas | sim | Dono da agenda |
| data | data |  | sim | Dia marcado |
| status | status_agenda |  | sim | ocupado ou disponivel |
| observacao | texto |  | não | Até 120 caracteres |
| criado_em | data e hora |  | sim | Data e hora de criação |

## tokens_senha

Tokens de recuperação de senha (só o hash fica salvo).

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| user_id | UUID | FK → profiles | sim | Conta que pediu a recuperação |
| token_hash | texto |  | sim | SHA-256 do token enviado por e-mail |
| expira_em | data e hora |  | sim | Validade (30 minutos) |
| usado | sim/não |  | sim | TRUE depois de usado ou de um pedido novo |
| criado_em | data e hora |  | sim | Data e hora de criação |

## favoritos

Artistas salvos pelo cliente.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| cliente_id | UUID | PK · FK → profiles | sim | Cliente que salvou |
| artista_id | UUID | PK · FK → artistas | sim | Artista salvo |
| criado_em | data e hora |  | sim | Data e hora de criação |

## notificacoes

Avisos que aparecem no sino do topo da página.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| user_id | UUID | FK → profiles | sim | Quem recebe o aviso |
| tipo | texto |  | sim | proposta, contrato, pagamento, cancelamento, mensagem, avaliacao ou moderacao |
| texto | texto |  | sim | Frase do aviso (até 200 caracteres) |
| link | texto |  | não | Página interna aberta no clique |
| lida | sim/não |  | sim | TRUE depois de aberta |
| criada_em | data e hora |  | sim | Data e hora de criação |

## cancelamentos

Registro de cada cancelamento e do cálculo do reembolso.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| contrato_id | UUID | FK → contratos | sim | Contrato cancelado (um registro por contrato) |
| cancelado_por | texto |  | sim | cliente ou artista |
| motivo | texto |  | sim | De 5 a 300 caracteres |
| dias_antecedencia | inteiro |  | sim | Dias entre o cancelamento e o evento |
| percentual_reembolso | inteiro |  | sim | 0, 50, 70 ou 100, pela política |
| valor_reembolso | numeric(10,2) |  | sim | Valor devolvido ao cliente |
| valor_artista | numeric(10,2) |  | sim | Valor que ficou com o artista |
| criado_em | data e hora |  | sim | Data e hora de criação |

## denuncias

Denúncias de perfis e avaliações para a moderação.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| denunciante_id | UUID | FK → profiles | sim | Quem denunciou |
| artista_id | UUID | FK → artistas | não | Perfil denunciado (ou vazio) |
| avaliacao_id | UUID | FK → avaliacoes | não | Avaliação denunciada (ou vazio) |
| motivo | texto |  | sim | ofensivo, falso, spam, golpe ou outro |
| detalhes | texto |  | não | Até 500 caracteres |
| status | texto |  | sim | aberta, procedente ou improcedente |
| decisao | texto |  | não | Justificativa do administrador |
| criada_em | data e hora |  | sim | Data e hora de criação |
| resolvida_em | data e hora |  | não | Quando foi decidida |

## portfolio

Links de fotos, vídeos e áudios do artista.

| Coluna | Tipo | Chave | Obrig. | Descrição |
|---|---|---|---|---|
| id | UUID | PK | sim | Identificador único gerado automaticamente |
| artista_id | UUID | FK → artistas | sim | Dono do portfólio |
| tipo | texto |  | sim | foto, video ou audio |
| titulo | texto |  | sim | De 3 a 80 caracteres |
| url | texto |  | sim | Link https:// (ou imagem da própria plataforma) |
| criado_em | data e hora |  | sim | Data e hora de criação |

## Views

| View | O que calcula |
|---|---|
| `vw_artistas` | Artista + nome da categoria + nota média e total de avaliações (sem contar as ocultas pela moderação) |
| `vw_painel_cliente` | Indicadores do painel do cliente: próximos eventos, valor retido, total contratado e mensagens novas |
