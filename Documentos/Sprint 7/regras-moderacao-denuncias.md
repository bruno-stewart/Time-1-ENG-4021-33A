# Regras de moderação e denúncia de conteúdos

## Por que estas regras existem

O ArtConnect depende de confiança: o cliente contrata alguém que nunca viu, com base no perfil e nas avaliações. Nas entrevistas, a falta de confiança e de avaliações reais foi o principal motivo para as pessoas não contratarem artistas pela internet. Por isso, perfis falsos, avaliações inventadas e pedidos de pagamento "por fora" precisam ser removidos rápido. Estas regras dizem **o que pode ser denunciado, quem decide e o que acontece depois**.

## O que pode ser denunciado

| Conteúdo | Quem pode denunciar | Onde fica o botão |
|---|---|---|
| Perfil de artista | Qualquer usuário logado (cliente ou artista) | Topo da página do artista, "Denunciar perfil" |
| Avaliação | Qualquer usuário logado | Embaixo de cada avaliação, "Denunciar avaliação" |

Visitantes sem login não denunciam. Isso evita denúncias em massa feitas por robôs e permite avisar o denunciante sobre a decisão.

## Motivos aceitos

| Código | Motivo | Exemplos |
|---|---|---|
| ofensivo | Conteúdo ofensivo ou discriminatório | Xingamento, preconceito, ataque pessoal a quem avaliou |
| falso | Informação falsa ou avaliação de quem não contratou | Foto de outra pessoa no portfólio, nota de quem nunca fez evento |
| spam | Propaganda ou spam | Link de outro site, divulgação de outro serviço |
| golpe | Tentativa de golpe ou pagamento por fora | Pedido de Pix direto para o artista, fora da plataforma |
| outro | Outro motivo | Qualquer caso que não se encaixe acima, com detalhes obrigatórios na prática |

O campo de detalhes é opcional e aceita até 500 caracteres.

## Regras para evitar abuso

- **Uma denúncia aberta por pessoa e por conteúdo.** A mesma pessoa não consegue denunciar duas vezes a mesma avaliação enquanto a primeira estiver em análise.
- **A denúncia não esconde nada sozinha.** Nada sai do ar antes da decisão de um administrador, para que um concorrente não consiga derrubar um artista só denunciando.
- **O denunciado não vê quem denunciou.** Só o administrador vê o nome do denunciante.

## Quem decide e em quanto tempo

- Só o **administrador** decide, na tela "Denúncias" (fila de moderação).
- Prazo de análise: **48 horas**, o mesmo da contestação na política de cancelamento.
- Toda decisão exige uma **justificativa** de 5 a 300 caracteres, que fica registrada.

## O que acontece em cada decisão

| Decisão | Se for avaliação | Se for perfil |
|---|---|---|
| Procedente | A avaliação fica oculta: some do perfil, da home e deixa de contar na nota média | O artista é suspenso: some da busca e a página dele deixa de abrir |
| Improcedente | Nada muda | Nada muda |

Em qualquer caso:

- o denunciante recebe uma notificação com o resultado;
- se o perfil for suspenso, o artista também recebe uma notificação com a justificativa;
- quando uma denúncia é procedente, as outras denúncias abertas sobre o mesmo conteúdo são fechadas juntas.

## Reativação

Um perfil suspenso pode ser **reativado pelo administrador** na aba "Procedentes", por exemplo depois que o artista corrige as fotos ou comprova a identidade. O artista recebe uma notificação avisando que voltou para a busca.

## Gravidade e reincidência

| Situação | Ação recomendada |
|---|---|
| Primeira avaliação ofensiva de um cliente | Ocultar a avaliação |
| Perfil com foto ou portfólio de outra pessoa | Suspender até o artista corrigir |
| Pedido de pagamento por fora (golpe) | Suspender o perfil na hora |
| Artista suspenso duas vezes em 12 meses | Não reativar sem análise da equipe |

## Como isso aparece no sistema

| Regra | Onde está |
|---|---|
| Tabela de denúncias, motivos e status | `artconnect/schema_sprint7.sql`, tabela `denuncias` |
| Uma denúncia aberta por pessoa e conteúdo | Índices únicos `idx_denuncias_unica_artista` e `idx_denuncias_unica_avaliacao` |
| Avaliação oculta não conta na nota | Coluna `avaliacoes.oculta` e view `vw_artistas` |
| Fila de moderação e decisão | `artconnect/app.py`, rotas `admin_denuncias` e `decidir_denuncia` |
